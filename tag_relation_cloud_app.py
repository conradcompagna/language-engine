import csv
import io
import json
import math
import os
import random
import re
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from flask import Flask, Response, abort, render_template_string


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path.home() / "Downloads"

TOP_TAGS_TSV = DOWNLOADS_DIR / "finerweb_collapsed_groups_top458_with_frequency_samples (1).tsv"
FULL_MAP_ZIP = DOWNLOADS_DIR / "final_full_tag_maps.zip"
FULL_MAP_MEMBER = "final_full_tag_maps/full_coarse_and_fine_grained_tag_map.tsv"
INVENTORY_TSV = DOWNLOADS_DIR / "finerweb_label_inventory.tsv"

CACHE_DIR = BASE_DIR / "runtime_cache"
CACHE_PATH = CACHE_DIR / "finerweb_tag_relation_cloud_graph.json"
ALGORITHM_VERSION = "similarity_only_knn_communities_v4"

WIDTH = 1560
HEIGHT = 1040

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

PALETTE = [
    "#2f80ed",
    "#d94841",
    "#2f9e44",
    "#b7791f",
    "#7c3aed",
    "#0f766e",
    "#c026d3",
    "#ea580c",
    "#2563eb",
    "#16a34a",
    "#be123c",
    "#0891b2",
    "#9333ea",
    "#ca8a04",
    "#64748b",
    "#db2777",
    "#4d7c0f",
    "#7f1d1d",
    "#0369a1",
]

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
SPLIT_RE = re.compile(r"[/,;:|(){}\[\]<>_\-]+")


def norm_label(value):
    return unicodedata.normalize("NFKC", (value or "").strip()).casefold()


def plain_label(value):
    return unicodedata.normalize("NFKC", (value or "").strip())


def ascii_fold(value):
    folded = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def stem_token(token):
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ses"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def tokenize(value):
    text = ascii_fold(norm_label(value))
    tokens = []
    for token in TOKEN_RE.findall(text):
        token = stem_token(token)
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token.isdigit() and len(token) < 3:
            continue
        tokens.append(token)
    return tokens


def components(value):
    text = ascii_fold(norm_label(value))
    parts = []
    for part in SPLIT_RE.split(text):
        part = " ".join(tokenize(part))
        if len(part) >= 2 and part not in STOPWORDS:
            parts.append(part)
    return parts


def split_sample(value):
    return [plain_label(part) for part in (value or "").split(";") if plain_label(part)]


def read_top_rows():
    if not TOP_TAGS_TSV.exists():
        raise FileNotFoundError(f"Missing top tags TSV: {TOP_TAGS_TSV}")

    rows = []
    with TOP_TAGS_TSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for rank, row in enumerate(reader, start=1):
            label = plain_label(row.get("coarse_tag"))
            if not label:
                continue
            try:
                frequency = int(row.get("frequency") or 0)
            except ValueError:
                frequency = 0
            rows.append(
                {
                    "label": label,
                    "key": norm_label(label),
                    "rank": rank,
                    "frequency": frequency,
                    "sample_10": split_sample(row.get("fine_grained_tagset_10")),
                }
            )
    return rows


def read_inventory_counts():
    counts = {}
    if not INVENTORY_TSV.exists():
        return counts
    with INVENTORY_TSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            label = plain_label(row.get("original_label"))
            if not label:
                continue
            try:
                counts[norm_label(label)] = int(row.get("count") or 0)
            except ValueError:
                counts[norm_label(label)] = 0
    return counts


def read_full_map(top_keys):
    if not FULL_MAP_ZIP.exists():
        raise FileNotFoundError(f"Missing full tag map zip: {FULL_MAP_ZIP}")

    full_tags = defaultdict(list)
    with zipfile.ZipFile(FULL_MAP_ZIP) as archive:
        with archive.open(FULL_MAP_MEMBER) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            reader = csv.DictReader(text, delimiter="\t")
            for row in reader:
                coarse = plain_label(row.get("coarse_label"))
                fine = plain_label(row.get("fine_grained_tag"))
                if not coarse or not fine:
                    continue
                key = norm_label(coarse)
                if key not in top_keys:
                    continue
                full_tags[key].append(fine)
    return full_tags


def source_stamp():
    paths = [TOP_TAGS_TSV, FULL_MAP_ZIP, INVENTORY_TSV]
    stamp = {
        str(path): {
            "exists": path.exists(),
            "mtime": path.stat().st_mtime if path.exists() else None,
            "size": path.stat().st_size if path.exists() else None,
        }
        for path in paths
    }
    stamp["algorithm_version"] = ALGORITHM_VERSION
    return stamp


def cache_is_fresh(payload):
    return payload.get("source_stamp") == source_stamp()


def fine_count_for(label, inventory_counts):
    return inventory_counts.get(norm_label(label), 1) or 1


def build_profiles(nodes, inventory_counts):
    raw_vectors = []
    component_sets = []

    for node in nodes:
        vector = Counter()
        comps = Counter()

        for token in tokenize(node["label"]):
            vector[token] += 20.0
        for part in components(node["label"]):
            comps[part] += 8.0

        for sample in node["sample_10"]:
            for token in tokenize(sample):
                vector[token] += 4.0
            for part in components(sample):
                comps[part] += 2.5

        for tag in node["fine_tags"]:
            count = fine_count_for(tag, inventory_counts)
            weight = 1.0 + math.log1p(count)
            for token in tokenize(tag):
                vector[token] += weight
            for part in components(tag):
                comps[part] += math.sqrt(weight)

        raw_vectors.append(vector)
        component_sets.append(comps)

    df = Counter()
    for vector in raw_vectors:
        for token in vector:
            df[token] += 1

    n_nodes = len(raw_vectors)
    vectors = []
    norms = []
    for vector in raw_vectors:
        weighted = {}
        for token, value in vector.items():
            idf = math.log(1.0 + n_nodes / (1.0 + df[token]))
            weighted[token] = (1.0 + math.log1p(value)) * idf
        norm = math.sqrt(sum(value * value for value in weighted.values())) or 1.0
        vectors.append(weighted)
        norms.append(norm)

    return vectors, norms, raw_vectors, component_sets


def cosine_similarity(left, right, left_norm, right_norm):
    if len(left) > len(right):
        left, right = right, left
    score = 0.0
    for key, left_value in left.items():
        right_value = right.get(key)
        if right_value:
            score += left_value * right_value
    return score / (left_norm * right_norm)


def weighted_jaccard(left, right):
    if len(left) > len(right):
        left, right = right, left
    numerator = 0.0
    for key, value in left.items():
        if key in right:
            numerator += min(value, right[key])
    denominator = sum(left.values()) + sum(right.values()) - numerator
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def label_inclusion_score(a_label, b_label, a_components, b_components):
    a = norm_label(a_label)
    b = norm_label(b_label)
    score = 0.0
    if a and b:
        if a in b_components or b in a_components:
            score += 0.08
        if a in b or b in a:
            score += 0.04
    return score


def shared_terms(raw_a, raw_b, comps_a, comps_b):
    token_scores = []
    for key in set(raw_a).intersection(raw_b):
        if key.startswith("#"):
            continue
        token_scores.append((min(raw_a[key], raw_b[key]), key))
    token_scores.sort(reverse=True)

    component_scores = []
    for key in set(comps_a).intersection(comps_b):
        component_scores.append((min(comps_a[key], comps_b[key]), key))
    component_scores.sort(reverse=True)

    return {
        "terms": [key for _, key in token_scores[:8]],
        "components": [key for _, key in component_scores[:6]],
    }


def build_links(nodes, vectors, norms, raw_vectors, component_sets):
    pair_scores = []
    per_node = defaultdict(list)

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            token_score = cosine_similarity(vectors[i], vectors[j], norms[i], norms[j])
            component_score = weighted_jaccard(component_sets[i], component_sets[j])
            inclusion = label_inclusion_score(
                nodes[i]["label"],
                nodes[j]["label"],
                component_sets[i],
                component_sets[j],
            )
            score = (0.76 * token_score) + (0.24 * component_score) + inclusion
            score = max(0.0, min(1.0, score))
            if score <= 0:
                continue
            pair_scores.append((score, i, j))
            per_node[i].append((score, j))
            per_node[j].append((score, i))

    selected = {}
    for i, values in per_node.items():
        values.sort(reverse=True)
        for score, j in values[:10]:
            if score < 0.055:
                continue
            key = (min(i, j), max(i, j))
            selected[key] = max(selected.get(key, 0.0), score)

    pair_scores.sort(reverse=True)
    for score, i, j in pair_scores[:650]:
        if score < 0.075:
            break
        selected[(i, j)] = max(selected.get((i, j), 0.0), score)

    links = []
    for (i, j), score in selected.items():
        shared = shared_terms(raw_vectors[i], raw_vectors[j], component_sets[i], component_sets[j])
        links.append(
            {
                "source": i,
                "target": j,
                "score": round(score, 4),
                "shared_terms": shared["terms"],
                "shared_components": shared["components"],
            }
        )

    links.sort(key=lambda item: item["score"], reverse=True)

    top_neighbors = defaultdict(list)
    for score, i, j in pair_scores:
        if len(top_neighbors[i]) < 30:
            top_neighbors[i].append({"id": j, "score": round(score, 4)})
        if len(top_neighbors[j]) < 30:
            top_neighbors[j].append({"id": i, "score": round(score, 4)})
        if len(top_neighbors) == len(nodes) and all(len(top_neighbors[idx]) >= 30 for idx in range(len(nodes))):
            break

    return links, top_neighbors, pair_scores


def build_region_adjacency(pair_scores, n_nodes):
    ranked = defaultdict(list)
    for score, i, j in pair_scores:
        ranked[i].append((score, j))
        ranked[j].append((score, i))

    selected = {}
    for i, values in ranked.items():
        values.sort(reverse=True)
        for score, j in values[:10]:
            if score < 0.10:
                continue
            key = (min(i, j), max(i, j))
            selected[key] = max(selected.get(key, 0.0), score)

    adjacency = [defaultdict(float) for _ in range(n_nodes)]
    for (i, j), score in selected.items():
        weight = score * score
        adjacency[i][j] += weight
        adjacency[j][i] += weight
    return [dict(row) for row in adjacency]


def one_level_louvain(adjacency, resolution=1.16):
    n_nodes = len(adjacency)
    communities = list(range(n_nodes))
    degrees = [sum(edges.values()) for edges in adjacency]
    totals = degrees[:]
    total_weight = sum(degrees) / 2.0
    if total_weight <= 0:
        return communities

    order = list(range(n_nodes))
    rnd = random.Random(9371)

    for pass_num in range(40):
        rnd.shuffle(order)
        moved = False
        for node in order:
            degree = degrees[node]
            if degree <= 0:
                continue

            old_comm = communities[node]
            neighbor_weights = defaultdict(float)
            for neighbor, weight in adjacency[node].items():
                neighbor_weights[communities[neighbor]] += weight

            totals[old_comm] -= degree
            best_comm = old_comm
            best_gain = 0.0
            for comm, weight_in_comm in neighbor_weights.items():
                gain = weight_in_comm - resolution * degree * totals[comm] / (2.0 * total_weight)
                if gain > best_gain + 1e-12:
                    best_gain = gain
                    best_comm = comm

            totals[best_comm] += degree
            if best_comm != old_comm:
                communities[node] = best_comm
                moved = True

        if not moved:
            break

    return compact_partition(communities)


def compact_partition(partition):
    remap = {}
    compact = []
    for comm in partition:
        if comm not in remap:
            remap[comm] = len(remap)
        compact.append(remap[comm])
    return compact


def aggregate_graph(adjacency, partition):
    n_comms = max(partition) + 1 if partition else 0
    aggregated = [defaultdict(float) for _ in range(n_comms)]
    for source, edges in enumerate(adjacency):
        source_comm = partition[source]
        for target, weight in edges.items():
            target_comm = partition[target]
            if source_comm == target_comm:
                continue
            aggregated[source_comm][target_comm] += weight
    return [dict(row) for row in aggregated]


def louvain_partition(adjacency):
    current_adj = adjacency
    members = [{idx} for idx in range(len(adjacency))]

    for _ in range(8):
        partition = one_level_louvain(current_adj)
        n_comms = max(partition) + 1 if partition else 0
        if n_comms == len(current_adj):
            break

        new_members = [set() for _ in range(n_comms)]
        for node, comm in enumerate(partition):
            new_members[comm].update(members[node])

        current_adj = aggregate_graph(current_adj, partition)
        members = new_members
        if len(members) <= 1:
            break

    final = [0] * len(adjacency)
    for comm, originals in enumerate(members):
        for idx in originals:
            final[idx] = comm
    return compact_partition(final)


def merge_tiny_regions(partition, adjacency, min_size=4):
    partition = compact_partition(partition)
    changed = True
    while changed:
        changed = False
        counts = Counter(partition)
        tiny = [comm for comm, count in counts.items() if count < min_size]
        if not tiny:
            break
        for comm in tiny:
            nodes = [idx for idx, value in enumerate(partition) if value == comm]
            neighbor_weights = Counter()
            for node in nodes:
                for neighbor, weight in adjacency[node].items():
                    neighbor_comm = partition[neighbor]
                    if neighbor_comm != comm:
                        neighbor_weights[neighbor_comm] += weight
            if not neighbor_weights:
                continue
            best_comm, _ = neighbor_weights.most_common(1)[0]
            for node in nodes:
                partition[node] = best_comm
            partition = compact_partition(partition)
            changed = True
            break
    return compact_partition(partition)


def choose_region_terms(node_ids, raw_vectors, component_sets, global_raw, global_components):
    component_scores = Counter()
    token_scores = Counter()

    for node_id in node_ids:
        for term, value in component_sets[node_id].items():
            component_scores[term] += value
        for term, value in raw_vectors[node_id].items():
            if term.startswith("#"):
                continue
            token_scores[term] += value

    candidates = []
    for term, value in component_scores.items():
        if len(term) < 3:
            continue
        global_value = global_components.get(term, value)
        candidates.append((value / math.sqrt(global_value), term))
    for term, value in token_scores.items():
        if len(term) < 3 or term in STOPWORDS:
            continue
        global_value = global_raw.get(term, value)
        candidates.append(((value / math.sqrt(global_value)) * 0.74, term))

    candidates.sort(reverse=True)
    chosen = []
    for _, term in candidates:
        if any(term == other or term in other or other in term for other in chosen):
            continue
        chosen.append(term)
        if len(chosen) >= 3:
            break
    return chosen or ["mixed"]


def derive_regions(nodes, pair_scores, raw_vectors, component_sets):
    adjacency = build_region_adjacency(pair_scores, len(nodes))
    partition = one_level_louvain(adjacency, resolution=1.0)

    clusters = defaultdict(list)
    for node_id, comm in enumerate(partition):
        clusters[comm].append(node_id)

    ordered_clusters = sorted(
        clusters.values(),
        key=lambda ids: (-sum(nodes[idx]["frequency"] for idx in ids), min(nodes[idx]["rank"] for idx in ids)),
    )

    global_raw = Counter()
    global_components = Counter()
    for vector in raw_vectors:
        global_raw.update(vector)
    for comps in component_sets:
        global_components.update(comps)

    region_labels = {}
    for rank, node_ids in enumerate(ordered_clusters, start=1):
        terms = choose_region_terms(node_ids, raw_vectors, component_sets, global_raw, global_components)
        label = f"R{rank:02d} " + " / ".join(terms)
        for node_id in node_ids:
            region_labels[node_id] = label

    region_names = [f"R{rank:02d} " + " / ".join(
        choose_region_terms(node_ids, raw_vectors, component_sets, global_raw, global_components)
    ) for rank, node_ids in enumerate(ordered_clusters, start=1)]
    color_by_region = {name: PALETTE[idx % len(PALETTE)] for idx, name in enumerate(region_names)}

    for node in nodes:
        region = region_labels[node["id"]]
        node["region"] = region
        node["bucket"] = region
        node["color"] = color_by_region[region]

    summaries = []
    for name in region_names:
        region_nodes = [node for node in nodes if node["region"] == name]
        summaries.append(
            {
                "name": name,
                "color": color_by_region[name],
                "count": len(region_nodes),
                "frequency": sum(node["frequency"] for node in region_nodes),
                "top_tags": [node["label"] for node in sorted(region_nodes, key=lambda item: item["rank"])[:10]],
            }
        )
    return summaries


def convex_hull(points):
    points = sorted(set((round(x, 3), round(y, 3)) for x, y in points))
    if len(points) <= 1:
        return points

    def cross(origin, left, right):
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def add_region_hulls(nodes, summaries):
    by_region = defaultdict(list)
    for node in nodes:
        by_region[node["region"]].append(node)

    for summary in summaries:
        region_nodes = by_region[summary["name"]]
        if not region_nodes:
            summary["polygon"] = []
            continue
        center_x = sum(node["x"] for node in region_nodes) / len(region_nodes)
        center_y = sum(node["y"] for node in region_nodes) / len(region_nodes)
        points = []
        for node in region_nodes:
            pad = node["radius"] + 20
            x = node["x"]
            y = node["y"]
            points.extend(
                [
                    (x - pad, y),
                    (x + pad, y),
                    (x, y - pad),
                    (x, y + pad),
                    (x - pad * 0.7, y - pad * 0.7),
                    (x + pad * 0.7, y - pad * 0.7),
                    (x - pad * 0.7, y + pad * 0.7),
                    (x + pad * 0.7, y + pad * 0.7),
                ]
            )

        hull = convex_hull(points)
        expanded = []
        for x, y in hull:
            dx = x - center_x
            dy = y - center_y
            dist = math.sqrt(dx * dx + dy * dy) or 1.0
            expanded.append([round(x + (dx / dist) * 16, 2), round(y + (dy / dist) * 16, 2)])
        summary["polygon"] = expanded


def hash_random(seed_text):
    seed = 0
    for ch in seed_text:
        seed = ((seed * 131) + ord(ch)) & 0xFFFFFFFF
    return random.Random(seed)


def compute_layout(nodes, links):
    center_x = WIDTH / 2
    center_y = HEIGHT / 2
    positions = []
    for idx, node in enumerate(nodes):
        rnd = hash_random(node["label"])
        angle = idx * 2.399963229728653 + rnd.uniform(-0.18, 0.18)
        ring = 14 * math.sqrt(idx + 1)
        positions.append(
            [
                center_x + math.cos(angle) * ring + rnd.uniform(-16, 16),
                center_y + math.sin(angle) * ring + rnd.uniform(-16, 16),
            ]
        )

    edge_list = [
        (link["source"], link["target"], link["score"])
        for link in links
        if link["score"] >= 0.115
    ]
    n_nodes = len(nodes)
    temperature = 8.5
    for step in range(460):
        disp = [[0.0, 0.0] for _ in range(n_nodes)]

        for i in range(n_nodes):
            xi, yi = positions[i]
            for j in range(i + 1, n_nodes):
                xj, yj = positions[j]
                dx = xi - xj
                dy = yi - yj
                dist2 = dx * dx + dy * dy + 0.01
                dist = math.sqrt(dist2)
                force = 8800.0 / dist2
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                disp[i][0] += fx
                disp[i][1] += fy
                disp[j][0] -= fx
                disp[j][1] -= fy

        for source, target, score in edge_list:
            sx, sy = positions[source]
            tx, ty = positions[target]
            dx = tx - sx
            dy = ty - sy
            dist = math.sqrt(dx * dx + dy * dy) + 0.01
            target_distance = 38 + (1.0 - score) * 210
            force = (dist - target_distance) * (0.01 + score * 0.07)
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            disp[source][0] += fx
            disp[source][1] += fy
            disp[target][0] -= fx
            disp[target][1] -= fy

        for idx in range(n_nodes):
            x, y = positions[idx]
            disp[idx][0] += (center_x - x) * 0.004
            disp[idx][1] += (center_y - y) * 0.004

        cooling = temperature * (1.0 - step / 460)
        for idx in range(n_nodes):
            dx, dy = disp[idx]
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                cap = min(length, max(0.35, cooling))
                positions[idx][0] += (dx / length) * cap
                positions[idx][1] += (dy / length) * cap

    min_x = min(pos[0] for pos in positions)
    max_x = max(pos[0] for pos in positions)
    min_y = min(pos[1] for pos in positions)
    max_y = max(pos[1] for pos in positions)
    pad = 64
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    scale = min((WIDTH - pad * 2) / span_x, (HEIGHT - pad * 2) / span_y)

    for idx, node in enumerate(nodes):
        x = (positions[idx][0] - min_x) * scale + pad
        y = (positions[idx][1] - min_y) * scale + pad
        node["x"] = round(x, 2)
        node["y"] = round(y, 2)


def build_graph():
    top_rows = read_top_rows()
    top_keys = {row["key"] for row in top_rows}
    inventory_counts = read_inventory_counts()
    full_tags_by_key = read_full_map(top_keys)

    nodes = []
    missing_full_map = []
    for row in top_rows:
        key = row["key"]
        fine_tags = full_tags_by_key.get(key, [])
        if not fine_tags:
            missing_full_map.append(row["label"])
            fine_tags = list(row["sample_10"])

        seen = set()
        fine_items = []
        for tag in fine_tags:
            tag_key = norm_label(tag)
            if tag_key in seen:
                continue
            seen.add(tag_key)
            fine_items.append({"tag": tag, "count": fine_count_for(tag, inventory_counts)})
        fine_items.sort(key=lambda item: (-item["count"], norm_label(item["tag"])))

        nodes.append(
            {
                "id": len(nodes),
                "label": row["label"],
                "rank": row["rank"],
                "frequency": row["frequency"],
                "sample_10": row["sample_10"],
                "bucket": "",
                "region": "",
                "fine_tags": [item["tag"] for item in fine_items],
                "fine_items": fine_items,
                "fine_count": len(fine_items),
                "color": "#64748b",
            }
        )

    max_frequency = max((node["frequency"] for node in nodes), default=1)
    for node in nodes:
        node["radius"] = round(4.5 + 18.0 * math.sqrt(node["frequency"] / max_frequency), 2)
        sample = []
        seen = set()
        for tag in node["sample_10"] + node["fine_tags"]:
            tag_key = norm_label(tag)
            if tag_key in seen:
                continue
            seen.add(tag_key)
            sample.append(tag)
            if len(sample) >= 32:
                break
        node["fine_sample"] = sample

    vectors, norms, raw_vectors, component_sets = build_profiles(nodes, inventory_counts)
    links, top_neighbors, pair_scores = build_links(nodes, vectors, norms, raw_vectors, component_sets)
    region_summaries = derive_regions(nodes, pair_scores, raw_vectors, component_sets)
    compute_layout(nodes, links)
    add_region_hulls(nodes, region_summaries)

    for idx, node in enumerate(nodes):
        node["neighbors"] = [
            {
                "id": item["id"],
                "label": nodes[item["id"]]["label"],
                "bucket": nodes[item["id"]]["bucket"],
                "score": item["score"],
            }
            for item in top_neighbors.get(idx, [])
        ]

    graph_nodes = []
    full_nodes = []
    for node in nodes:
        graph_node = {
            key: node[key]
            for key in (
                "id",
                "label",
                "rank",
                "frequency",
                "bucket",
                "region",
                "fine_count",
                "fine_sample",
                "sample_10",
                "neighbors",
                "color",
                "radius",
                "x",
                "y",
            )
        }
        graph_nodes.append(graph_node)
        full_nodes.append(
            {
                **graph_node,
                "fine_items": node["fine_items"],
            }
        )

    return {
        "source_stamp": source_stamp(),
        "sources": {
            "top_tags": str(TOP_TAGS_TSV),
            "full_map_zip": str(FULL_MAP_ZIP),
            "full_map_member": FULL_MAP_MEMBER,
            "inventory_counts": str(INVENTORY_TSV),
        },
        "stats": {
            "nodes": len(nodes),
            "links": len(links),
            "regions": len(region_summaries),
            "missing_full_map": missing_full_map,
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "width": WIDTH,
        "height": HEIGHT,
        "nodes": graph_nodes,
        "full_nodes": full_nodes,
        "links": links,
        "buckets": region_summaries,
    }


def load_graph():
    if CACHE_PATH.exists():
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if cache_is_fresh(payload):
            return payload

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_graph()
    tmp_path = CACHE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, CACHE_PATH)
    return payload


app = Flask(__name__)


@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/api/graph")
def graph_api():
    payload = load_graph()
    compact = {
        key: payload[key]
        for key in ("sources", "stats", "width", "height", "nodes", "links", "buckets")
    }
    return Response(json.dumps(compact, ensure_ascii=False), mimetype="application/json")


@app.route("/api/node/<int:node_id>")
def node_api(node_id):
    payload = load_graph()
    nodes = payload["full_nodes"]
    if node_id < 0 or node_id >= len(nodes):
        abort(404)
    return Response(json.dumps(nodes[node_id], ensure_ascii=False), mimetype="application/json")


INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FinerWeb Tag Relation Cloud</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d8dee8;
      --soft: #edf1f6;
      --accent: #2563eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    .app {
      display: grid;
      grid-template-columns: 300px minmax(520px, 1fr) 360px;
      min-height: 100vh;
    }
    aside, main {
      min-width: 0;
    }
    .left, .right {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 18px;
      overflow: auto;
      max-height: 100vh;
    }
    .right {
      border-right: 0;
      border-left: 1px solid var(--line);
    }
    .canvas-wrap {
      position: relative;
      min-height: 100vh;
      overflow: hidden;
      background:
        linear-gradient(90deg, rgba(23, 32, 51, 0.045) 1px, transparent 1px),
        linear-gradient(180deg, rgba(23, 32, 51, 0.045) 1px, transparent 1px);
      background-size: 40px 40px;
    }
    h1 {
      font-size: 19px;
      margin: 0 0 6px;
      line-height: 1.2;
    }
    h2 {
      font-size: 13px;
      margin: 22px 0 10px;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 750;
    }
    p {
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.45;
      font-size: 13px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin: 12px 0 6px;
      font-weight: 650;
    }
    input[type="search"], select {
      width: 100%;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 8px;
      padding: 9px 10px;
      font: inherit;
      font-size: 13px;
      outline: none;
    }
    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
    }
    .row input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
    }
    .stat-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin: 16px 0;
    }
    .stat {
      border: 1px solid var(--line);
      background: #fbfcfe;
      border-radius: 8px;
      padding: 10px;
    }
    .stat strong {
      display: block;
      font-size: 18px;
    }
    .stat span {
      color: var(--muted);
      font-size: 11px;
    }
    .bucket {
      display: grid;
      grid-template-columns: 12px minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 6px 0;
      border-bottom: 1px solid #eef2f7;
      cursor: pointer;
      font-size: 12px;
    }
    .swatch {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .bucket .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bucket .count {
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    #graph {
      width: 100%;
      height: 100vh;
      display: block;
      cursor: grab;
    }
    #graph.panning { cursor: grabbing; }
    .link {
      stroke: #98a2b3;
      stroke-linecap: round;
      opacity: 0.26;
      cursor: pointer;
    }
    .hull {
      stroke-width: 1.2;
      opacity: 0.16;
      pointer-events: none;
    }
    .node circle {
      stroke: #fff;
      stroke-width: 1.8;
      cursor: pointer;
    }
    .node text {
      font-size: 11px;
      paint-order: stroke;
      stroke: rgba(255, 255, 255, 0.88);
      stroke-width: 3px;
      fill: #182033;
      pointer-events: none;
      font-weight: 650;
    }
    .node.dim, .link.dim, .hull.dim {
      opacity: 0.08;
    }
    .node.hidden, .link.hidden, .hull.hidden {
      display: none;
    }
    .node.selected circle {
      stroke: #111827;
      stroke-width: 3px;
    }
    .node.neighbor circle {
      stroke: #111827;
      stroke-width: 2.5px;
    }
    .link.hot {
      opacity: 0.85;
      stroke: #111827;
    }
    .tag-title {
      font-size: 22px;
      line-height: 1.2;
      margin: 0 0 8px;
      word-break: break-word;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--muted);
      margin: 0 6px 6px 0;
      max-width: 100%;
    }
    .list {
      display: grid;
      gap: 8px;
    }
    .neighbor {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      border: 1px solid var(--line);
      background: #fbfcfe;
      border-radius: 8px;
      padding: 8px 9px;
      cursor: pointer;
      font-size: 13px;
    }
    .neighbor span:first-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .score {
      color: var(--muted);
      font-variant-numeric: tabular-nums;
    }
    .fine-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      max-height: 280px;
      overflow: auto;
      padding-right: 4px;
    }
    .fine {
      border: 1px solid #dfe5ee;
      border-radius: 7px;
      padding: 5px 7px;
      font-size: 12px;
      background: #fff;
      color: #273449;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
    .toolbar {
      position: absolute;
      top: 14px;
      left: 14px;
      z-index: 3;
      display: flex;
      gap: 8px;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }
    .icon-button {
      width: 36px;
      height: 34px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 700;
      line-height: 1;
    }
    .edge-box {
      border: 1px solid var(--line);
      background: #fbfcfe;
      border-radius: 8px;
      padding: 10px;
      margin: 0 0 12px;
      font-size: 13px;
    }
    .muted {
      color: var(--muted);
    }
    .small {
      font-size: 12px;
    }
    @media (max-width: 1080px) {
      .app {
        grid-template-columns: 260px minmax(420px, 1fr);
      }
      .right {
        grid-column: 1 / -1;
        max-height: none;
        border-left: 0;
        border-top: 1px solid var(--line);
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="left">
      <h1>FinerWeb tag relation cloud</h1>
      <p>Positions and clusters are derived from complete fine-grained tag overlap. No source metacategory assignments are used for layout or coloring.</p>

      <div class="stat-grid">
        <div class="stat"><strong id="nodeCount">...</strong><span>coarse tags</span></div>
        <div class="stat"><strong id="linkCount">...</strong><span>statistical links</span></div>
        <div class="stat"><strong id="clusterCount">...</strong><span>clusters</span></div>
      </div>

      <label for="search">Search coarse or fine tags</label>
      <input id="search" type="search" placeholder="person, currency, disease...">

      <label for="bucketFilter">Detected cluster</label>
      <select id="bucketFilter">
        <option value="">All clusters</option>
      </select>

      <label for="minLink">Minimum displayed similarity <span id="minLinkValue">0.08</span></label>
      <input id="minLink" type="range" min="0.04" max="0.35" step="0.01" value="0.08">

      <label for="labelMode">Labels</label>
      <div class="row">
        <span class="small muted">Show all node labels</span>
        <input id="labelMode" type="checkbox">
      </div>

      <h2>Detected Clusters</h2>
      <div id="bucketList"></div>
    </aside>

    <main class="canvas-wrap">
      <div class="toolbar">
        <button id="zoomOutButton" class="icon-button" title="Zoom out">-</button>
        <button id="zoomInButton" class="icon-button" title="Zoom in">+</button>
        <button id="fitButton">Fit</button>
        <button id="clearButton">Clear</button>
      </div>
      <svg id="graph" role="img" aria-label="Relation cloud graph">
        <g id="viewport">
          <g id="hulls"></g>
          <g id="links"></g>
          <g id="nodes"></g>
        </g>
      </svg>
    </main>

    <aside class="right">
      <div id="details">
        <h2>Inspect</h2>
        <p>Select a node or link. The map is a force layout over weighted fine-tag similarity; translucent areas are communities detected from the same graph.</p>
      </div>
    </aside>
  </div>

  <script>
    const state = {
      graph: null,
      selectedNode: null,
      selectedLink: null,
      bucket: "",
      query: "",
      minLink: 0.08,
      showAllLabels: false,
      transform: { x: 0, y: 0, k: 1 }
    };

    const svg = document.getElementById("graph");
    const viewport = document.getElementById("viewport");
    const hullsLayer = document.getElementById("hulls");
    const linksLayer = document.getElementById("links");
    const nodesLayer = document.getElementById("nodes");
    const details = document.getElementById("details");

    const fmt = new Intl.NumberFormat();

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
      })[ch]);
    }

    function pct(score) {
      return `${Math.round(score * 100)}%`;
    }

    function applyTransform() {
      viewport.setAttribute("transform", `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.k})`);
    }

    function zoomBy(factor) {
      const rect = svg.getBoundingClientRect();
      const px = rect.width / 2;
      const py = rect.height / 2;
      const oldK = state.transform.k;
      const newK = Math.max(0.08, Math.min(12, oldK * factor));
      const gx = (px - state.transform.x) / oldK;
      const gy = (py - state.transform.y) / oldK;
      state.transform.x = px - gx * newK;
      state.transform.y = py - gy * newK;
      state.transform.k = newK;
      applyTransform();
    }

    function fit() {
      const graph = state.graph;
      if (!graph) return;
      const rect = svg.getBoundingClientRect();
      const minX = Math.min(...graph.nodes.map(node => node.x - node.radius));
      const maxX = Math.max(...graph.nodes.map(node => node.x + node.radius));
      const minY = Math.min(...graph.nodes.map(node => node.y - node.radius));
      const maxY = Math.max(...graph.nodes.map(node => node.y + node.radius));
      const pad = 60;
      const spanX = Math.max(1, maxX - minX + pad * 2);
      const spanY = Math.max(1, maxY - minY + pad * 2);
      const k = Math.min(rect.width / spanX, rect.height / spanY) * 0.96;
      const centerX = (minX + maxX) / 2;
      const centerY = (minY + maxY) / 2;
      state.transform = {
        k,
        x: rect.width / 2 - centerX * k,
        y: rect.height / 2 - centerY * k
      };
      applyTransform();
    }

    function nodeMatchesQuery(node) {
      if (!state.query) return true;
      const q = state.query.toLowerCase();
      if (node.label.toLowerCase().includes(q)) return true;
      return node.fine_sample.some(tag => tag.toLowerCase().includes(q));
    }

    function visibleNode(node) {
      if (state.bucket && node.bucket !== state.bucket) return false;
      return nodeMatchesQuery(node);
    }

    function visibleLink(link) {
      const source = state.graph.nodes[link.source];
      const target = state.graph.nodes[link.target];
      return link.score >= state.minLink && visibleNode(source) && visibleNode(target);
    }

    function adjacencyForSelected() {
      const ids = new Set();
      if (state.selectedNode == null) return ids;
      ids.add(state.selectedNode);
      for (const link of state.graph.links) {
        if (link.source === state.selectedNode) ids.add(link.target);
        if (link.target === state.selectedNode) ids.add(link.source);
      }
      return ids;
    }

    function renderGraph() {
      const graph = state.graph;
      const selectedAdj = adjacencyForSelected();

      for (const hullEl of hullsLayer.children) {
        const cluster = hullEl.dataset.cluster;
        const visible = !state.bucket || state.bucket === cluster;
        hullEl.classList.toggle("hidden", !visible);
        hullEl.classList.toggle("dim", state.selectedNode != null && graph.nodes[state.selectedNode].bucket !== cluster);
      }

      for (const linkEl of linksLayer.children) {
        const link = graph.links[Number(linkEl.dataset.index)];
        const visible = visibleLink(link);
        const hot = state.selectedNode != null && (link.source === state.selectedNode || link.target === state.selectedNode);
        linkEl.classList.toggle("hidden", !visible);
        linkEl.classList.toggle("hot", hot || state.selectedLink === Number(linkEl.dataset.index));
        linkEl.classList.toggle("dim", state.selectedNode != null && !hot);
      }

      for (const nodeEl of nodesLayer.children) {
        const node = graph.nodes[Number(nodeEl.dataset.id)];
        const visible = visibleNode(node);
        const selected = state.selectedNode === node.id;
        const neighbor = selectedAdj.has(node.id) && !selected;
        nodeEl.classList.toggle("hidden", !visible);
        nodeEl.classList.toggle("selected", selected);
        nodeEl.classList.toggle("neighbor", neighbor);
        nodeEl.classList.toggle("dim", state.selectedNode != null && !selected && !neighbor);
        const label = nodeEl.querySelector("text");
        const showLabel = state.showAllLabels || selected || neighbor || node.rank <= 50;
        label.style.display = showLabel ? "block" : "none";
      }
    }

    function buildGraph() {
      const graph = state.graph;

      hullsLayer.innerHTML = "";
      linksLayer.innerHTML = "";
      nodesLayer.innerHTML = "";

      graph.buckets.forEach(bucket => {
        if (!bucket.polygon || bucket.polygon.length < 3) return;
        const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        polygon.classList.add("hull");
        polygon.dataset.cluster = bucket.name;
        polygon.setAttribute("points", bucket.polygon.map(point => point.join(",")).join(" "));
        polygon.setAttribute("fill", bucket.color);
        polygon.setAttribute("stroke", bucket.color);
        hullsLayer.appendChild(polygon);
      });

      graph.links.forEach((link, index) => {
        const source = graph.nodes[link.source];
        const target = graph.nodes[link.target];
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.classList.add("link");
        line.dataset.index = index;
        line.setAttribute("x1", source.x);
        line.setAttribute("y1", source.y);
        line.setAttribute("x2", target.x);
        line.setAttribute("y2", target.y);
        line.setAttribute("stroke-width", String(0.6 + link.score * 5.0));
        line.addEventListener("click", event => {
          event.stopPropagation();
          state.selectedNode = null;
          state.selectedLink = index;
          renderEdgeDetails(link);
          renderGraph();
        });
        linksLayer.appendChild(line);
      });

      graph.nodes.forEach(node => {
        const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
        group.classList.add("node");
        group.dataset.id = node.id;
        group.setAttribute("transform", `translate(${node.x} ${node.y})`);

        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("r", node.radius);
        circle.setAttribute("fill", node.color);

        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        title.textContent = `${node.label} | ${node.bucket} | ${fmt.format(node.frequency)}`;
        circle.appendChild(title);

        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", node.radius + 4);
        text.setAttribute("y", "4");
        text.textContent = node.label;

        group.appendChild(circle);
        group.appendChild(text);
        group.addEventListener("click", event => {
          event.stopPropagation();
          selectNode(node.id);
        });
        nodesLayer.appendChild(group);
      });

      renderGraph();
      fit();
    }

    async function selectNode(id) {
      state.selectedNode = id;
      state.selectedLink = null;
      renderGraph();
      const response = await fetch(`/api/node/${id}`);
      const node = await response.json();
      renderNodeDetails(node);
    }

    function renderEdgeDetails(link) {
      const source = state.graph.nodes[link.source];
      const target = state.graph.nodes[link.target];
      const terms = [...link.shared_components, ...link.shared_terms].slice(0, 16);
      details.innerHTML = `
        <h2>Similarity Link</h2>
        <div class="edge-box">
          <div class="tag-title">${escapeHtml(source.label)} + ${escapeHtml(target.label)}</div>
          <div class="pill">Similarity ${pct(link.score)}</div>
          <div class="pill">${escapeHtml(source.bucket)}</div>
          <div class="pill">${escapeHtml(target.bucket)}</div>
        </div>
        <h2>Shared Vocabulary</h2>
        <div class="fine-list">
          ${terms.map(term => `<span class="fine">${escapeHtml(term)}</span>`).join("") || "<span class='muted'>No compact shared-term summary.</span>"}
        </div>
        <h2>Open Nodes</h2>
        <div class="list">
          <div class="neighbor" data-node="${source.id}"><span>${escapeHtml(source.label)}</span><span class="score">${fmt.format(source.frequency)}</span></div>
          <div class="neighbor" data-node="${target.id}"><span>${escapeHtml(target.label)}</span><span class="score">${fmt.format(target.frequency)}</span></div>
        </div>
      `;
      details.querySelectorAll("[data-node]").forEach(el => {
        el.addEventListener("click", () => selectNode(Number(el.dataset.node)));
      });
    }

    function renderNodeDetails(node) {
      const fineItems = node.fine_items.slice(0, 500);
      details.innerHTML = `
        <div class="tag-title">${escapeHtml(node.label)}</div>
        <div>
          <span class="pill">Rank ${node.rank}</span>
          <span class="pill">${fmt.format(node.frequency)} mentions</span>
          <span class="pill">${fmt.format(node.fine_count)} fine tags</span>
          <span class="pill">${escapeHtml(node.bucket)}</span>
        </div>

        <h2>Nearest Tags</h2>
        <div class="list">
          ${node.neighbors.slice(0, 14).map(n => `
            <div class="neighbor" data-node="${n.id}">
              <span>${escapeHtml(n.label)}</span>
              <span class="score">${pct(n.score)}</span>
            </div>
          `).join("")}
        </div>

        <h2>Fine Tags</h2>
        <p>${fineItems.length < node.fine_count ? `Showing top ${fmt.format(fineItems.length)} by label frequency.` : "Complete list for this coarse tag."}</p>
        <div class="fine-list">
          ${fineItems.map(item => `<span class="fine">${escapeHtml(item.tag)} <span class="muted">${fmt.format(item.count)}</span></span>`).join("")}
        </div>
      `;
      details.querySelectorAll("[data-node]").forEach(el => {
        el.addEventListener("click", () => selectNode(Number(el.dataset.node)));
      });
    }

    function renderBuckets() {
      const select = document.getElementById("bucketFilter");
      const bucketList = document.getElementById("bucketList");
      for (const bucket of state.graph.buckets) {
        const option = document.createElement("option");
        option.value = bucket.name;
        option.textContent = `${bucket.name} (${bucket.count})`;
        select.appendChild(option);
      }
      bucketList.innerHTML = state.graph.buckets.map(bucket => `
        <div class="bucket" data-bucket="${escapeHtml(bucket.name)}" title="${escapeHtml((bucket.top_tags || []).join(', '))}">
          <span class="swatch" style="background:${bucket.color}"></span>
          <span class="name">${escapeHtml(bucket.name)}</span>
          <span class="count">${bucket.count}</span>
        </div>
      `).join("");
      bucketList.querySelectorAll("[data-bucket]").forEach(el => {
        el.addEventListener("click", () => {
          state.bucket = el.dataset.bucket;
          select.value = state.bucket;
          renderGraph();
        });
      });
    }

    function clearSelection() {
      state.selectedNode = null;
      state.selectedLink = null;
      state.query = "";
      state.bucket = "";
      document.getElementById("search").value = "";
      document.getElementById("bucketFilter").value = "";
      details.innerHTML = `
        <h2>Inspect</h2>
        <p>Select a node or link. The map is a force layout over weighted fine-tag similarity; translucent areas are communities detected from the same graph.</p>
      `;
      renderGraph();
    }

    function wireControls() {
      document.getElementById("search").addEventListener("input", event => {
        state.query = event.target.value.trim();
        renderGraph();
      });
      document.getElementById("bucketFilter").addEventListener("change", event => {
        state.bucket = event.target.value;
        renderGraph();
      });
      document.getElementById("minLink").addEventListener("input", event => {
        state.minLink = Number(event.target.value);
        document.getElementById("minLinkValue").textContent = state.minLink.toFixed(2);
        renderGraph();
      });
      document.getElementById("labelMode").addEventListener("change", event => {
        state.showAllLabels = event.target.checked;
        renderGraph();
      });
      document.getElementById("zoomInButton").addEventListener("click", () => zoomBy(1.35));
      document.getElementById("zoomOutButton").addEventListener("click", () => zoomBy(1 / 1.35));
      document.getElementById("fitButton").addEventListener("click", fit);
      document.getElementById("clearButton").addEventListener("click", clearSelection);
    }

    function wirePanZoom() {
      let dragging = false;
      let last = null;

      svg.addEventListener("pointerdown", event => {
        if (event.target.closest(".node") || event.target.closest(".link")) return;
        dragging = true;
        last = { x: event.clientX, y: event.clientY };
        svg.classList.add("panning");
        svg.setPointerCapture(event.pointerId);
      });
      svg.addEventListener("pointermove", event => {
        if (!dragging) return;
        state.transform.x += event.clientX - last.x;
        state.transform.y += event.clientY - last.y;
        last = { x: event.clientX, y: event.clientY };
        applyTransform();
      });
      svg.addEventListener("pointerup", event => {
        dragging = false;
        svg.classList.remove("panning");
        try { svg.releasePointerCapture(event.pointerId); } catch (err) {}
      });
      svg.addEventListener("wheel", event => {
        event.preventDefault();
        const rect = svg.getBoundingClientRect();
        const px = event.clientX - rect.left;
        const py = event.clientY - rect.top;
        const oldK = state.transform.k;
        const factor = event.deltaY < 0 ? 1.12 : 0.89;
        const newK = Math.max(0.08, Math.min(12, oldK * factor));
        const gx = (px - state.transform.x) / oldK;
        const gy = (py - state.transform.y) / oldK;
        state.transform.x = px - gx * newK;
        state.transform.y = py - gy * newK;
        state.transform.k = newK;
        applyTransform();
      }, { passive: false });
      svg.addEventListener("click", event => {
        if (event.target === svg) {
          state.selectedNode = null;
          state.selectedLink = null;
          renderGraph();
        }
      });
      window.addEventListener("resize", fit);
    }

    async function init() {
      const response = await fetch("/api/graph");
      state.graph = await response.json();
      document.getElementById("nodeCount").textContent = fmt.format(state.graph.stats.nodes);
      document.getElementById("linkCount").textContent = fmt.format(state.graph.stats.links);
      document.getElementById("clusterCount").textContent = fmt.format(state.graph.stats.regions);
      renderBuckets();
      buildGraph();
      wireControls();
      wirePanZoom();
    }

    init().catch(err => {
      details.innerHTML = `<h2>Error</h2><p>${escapeHtml(err.message)}</p>`;
      console.error(err);
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5058, debug=False)
