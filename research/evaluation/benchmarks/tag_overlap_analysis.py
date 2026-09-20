import csv
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize
from sklearn.decomposition import TruncatedSVD


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = Path.home() / "Downloads"
TOP_TAGS_TSV = DOWNLOADS_DIR / "finerweb_collapsed_groups_top458_with_frequency_samples (1).tsv"
FULL_MAP_ZIP = DOWNLOADS_DIR / "final_full_tag_maps.zip"
FULL_MAP_MEMBER = "final_full_tag_maps/full_coarse_and_fine_grained_tag_map.tsv"
INVENTORY_TSV = DOWNLOADS_DIR / "finerweb_label_inventory.tsv"
OUT_DIR = BASE_DIR / "runtime_cache" / "tag_overlap_analysis"

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
SPLIT_RE = re.compile(r"[/,;:|(){}\[\]<>_\-]+")
STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
    "is", "of", "on", "or", "the", "to", "with",
    "type", "kind", "category", "name", "term", "label", "entity",
    "misc", "other", "general", "specific", "related",
}


def plain(value):
    return unicodedata.normalize("NFKC", (value or "").strip())


def norm(value):
    return plain(value).casefold()


def ascii_fold(value):
    folded = unicodedata.normalize("NFKD", norm(value))
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def stem(token):
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("ses"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def tokens(value):
    out = []
    for token in TOKEN_RE.findall(ascii_fold(value)):
        token = stem(token)
        if len(token) < 2 or token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        out.append(token)
    return out


def phrases(value):
    parts = []
    for part in SPLIT_RE.split(ascii_fold(value)):
        phrase = " ".join(tokens(part))
        if phrase and phrase not in STOPWORDS:
            parts.append(phrase)
    return parts


def split_sample(value):
    return [plain(part) for part in (value or "").split(";") if plain(part)]


def read_top_rows():
    rows = []
    with TOP_TAGS_TSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for rank, row in enumerate(csv.DictReader(handle, delimiter="\t"), start=1):
            label = plain(row.get("coarse_tag"))
            if not label:
                continue
            rows.append(
                {
                    "rank": rank,
                    "label": label,
                    "key": norm(label),
                    "frequency": int(row.get("frequency") or 0),
                    "sample_10": split_sample(row.get("fine_grained_tagset_10")),
                }
            )
    return rows


def read_inventory_counts():
    counts = defaultdict(lambda: 1)
    with INVENTORY_TSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            label = plain(row.get("original_label"))
            if label:
                counts[norm(label)] = max(1, int(row.get("count") or 1))
    return counts


def read_full_map(top_keys):
    full = defaultdict(list)
    with zipfile.ZipFile(FULL_MAP_ZIP) as archive:
        with archive.open(FULL_MAP_MEMBER) as raw:
            text = raw.read().decode("utf-8-sig").splitlines()
    for row in csv.DictReader(text, delimiter="\t"):
        coarse = plain(row.get("coarse_label"))
        fine = plain(row.get("fine_grained_tag"))
        if coarse and fine and norm(coarse) in top_keys:
            full[norm(coarse)].append(fine)
    return full


def make_nodes():
    rows = read_top_rows()
    inventory = read_inventory_counts()
    full = read_full_map({row["key"] for row in rows})
    nodes = []
    for row in rows:
        seen = set()
        fine_tags = []
        for tag in full.get(row["key"], row["sample_10"]):
            key = norm(tag)
            if key in seen:
                continue
            seen.add(key)
            fine_tags.append(tag)
        fine_tags.sort(key=lambda tag: (-inventory[norm(tag)], norm(tag)))
        nodes.append({**row, "fine_tags": fine_tags})
    return nodes, inventory


def weighted_doc(node, inventory, mode):
    bag = []

    def add_label(label, times):
        toks = tokens(label)
        phrs = phrases(label)
        for _ in range(times):
            bag.extend(toks)
            bag.extend("ph_" + phrase.replace(" ", "_") for phrase in phrs)

    if mode == "coarse_heavy":
        add_label(node["label"], 18)
    else:
        add_label(node["label"], 10)

    for sample in node["sample_10"]:
        add_label(sample, 5)

    for idx, tag in enumerate(node["fine_tags"]):
        count = inventory[norm(tag)]
        weight = 1 + min(8, int(math.log1p(count)))
        if idx < 80:
            weight += 2
        if mode == "child_focused":
            parts = phrases(tag)
            if parts:
                add_label(parts[-1], max(1, weight + 1))
            if len(parts) > 1:
                add_label(parts[0], 1)
        elif mode == "balanced":
            add_label(tag, weight)
            parts = phrases(tag)
            if parts:
                add_label(parts[-1], max(1, weight // 2))
        else:
            add_label(tag, weight)

    return " ".join(bag)


def keep_top_features(matrix, top_k):
    matrix = matrix.tolil()
    for row_idx in range(matrix.shape[0]):
        row = np.asarray(matrix.getrow(row_idx).toarray()).ravel()
        nonzero = row.nonzero()[0]
        if len(nonzero) <= top_k:
            continue
        keep = set(nonzero[row[nonzero].argsort()[::-1][:top_k]])
        for col_idx in nonzero:
            if col_idx not in keep:
                matrix[row_idx, col_idx] = 0
    return normalize(matrix.tocsr())


def build_sparse_profile_similarity(nodes, inventory):
    docs = [weighted_doc(node, inventory, "child_focused") for node in nodes]
    vectorizer = TfidfVectorizer(
        min_df=2,
        max_df=0.30,
        sublinear_tf=True,
        ngram_range=(1, 3),
        norm="l2",
    )
    full_x = vectorizer.fit_transform(docs)
    sparse_x = keep_top_features(full_x, top_k=180)
    sim = cosine_similarity(sparse_x)
    np.fill_diagonal(sim, 1.0)
    return sim, sparse_x, vectorizer


def one_level_louvain(adjacency, resolution=0.6):
    n_nodes = len(adjacency)
    communities = list(range(n_nodes))
    degrees = [sum(edges.values()) for edges in adjacency]
    totals = degrees[:]
    total_weight = sum(degrees) / 2.0
    if total_weight <= 0:
        return communities

    order = list(range(n_nodes))
    rng = np.random.default_rng(919)
    for _ in range(50):
        rng.shuffle(order)
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

    remap = {}
    compact = []
    for comm in communities:
        if comm not in remap:
            remap[comm] = len(remap)
        compact.append(remap[comm])
    return np.array(compact, dtype=int)


def build_knn_adjacency(sim, k=12, floor=0.03):
    n_nodes = sim.shape[0]
    adjacency = [defaultdict(float) for _ in range(n_nodes)]
    for source in range(n_nodes):
        neighbors = np.argsort(sim[source])[::-1]
        added = 0
        for target in neighbors:
            if source == target:
                continue
            score = float(sim[source, target])
            if score < floor:
                break
            weight = score * score
            adjacency[source][target] = max(adjacency[source][target], weight)
            adjacency[target][source] = max(adjacency[target][source], weight)
            added += 1
            if added >= k:
                break
    return [dict(row) for row in adjacency]


def final_cluster_labels(nodes, inventory):
    sim, x, vectorizer = build_sparse_profile_similarity(nodes, inventory)
    adjacency = build_knn_adjacency(sim, k=12, floor=0.03)
    labels = one_level_louvain(adjacency, resolution=0.6)
    return labels, sim, x, vectorizer, adjacency


def component_sets(nodes, inventory):
    rows = []
    for node in nodes:
        weights = Counter()
        for phrase in phrases(node["label"]):
            weights[phrase] += 16
        for sample in node["sample_10"]:
            for phrase in phrases(sample):
                weights[phrase] += 5
        for tag in node["fine_tags"]:
            count = inventory[norm(tag)]
            weight = 1 + math.log1p(count)
            parts = phrases(tag)
            for phrase in parts:
                weights[phrase] += weight
            if parts:
                weights[parts[-1]] += weight
        rows.append(weights)
    return rows


def weighted_jaccard(left, right):
    if len(left) > len(right):
        left, right = right, left
    num = 0.0
    for key, value in left.items():
        if key in right:
            num += min(value, right[key])
    den = sum(left.values()) + sum(right.values()) - num
    return num / den if den else 0.0


def build_similarity(nodes, inventory, mode):
    docs = [weighted_doc(node, inventory, mode) for node in nodes]
    word_vectorizer = TfidfVectorizer(
        min_df=2,
        max_df=0.38,
        sublinear_tf=True,
        ngram_range=(1, 3),
        norm="l2",
    )
    word_x = word_vectorizer.fit_transform(docs)
    word_sim = cosine_similarity(word_x)

    char_vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        min_df=2,
        max_df=0.32,
        ngram_range=(4, 6),
        sublinear_tf=True,
        norm="l2",
    )
    char_x = char_vectorizer.fit_transform([" ".join(tokens(node["label"])) for node in nodes])
    char_sim = cosine_similarity(char_x)

    svd_dims = min(64, word_x.shape[1] - 1)
    if svd_dims >= 8:
        svd = TruncatedSVD(n_components=svd_dims, random_state=17)
        latent_x = normalize(svd.fit_transform(word_x))
        latent_sim = latent_x @ latent_x.T
    else:
        latent_sim = word_sim

    comps = component_sets(nodes, inventory)
    comp_sim = np.zeros_like(word_sim)
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            score = weighted_jaccard(comps[i], comps[j])
            comp_sim[i, j] = score
            comp_sim[j, i] = score

    sim = 0.62 * word_sim + 0.18 * latent_sim + 0.12 * comp_sim + 0.08 * char_sim
    np.fill_diagonal(sim, 1.0)
    sim = np.clip(sim, 0, 1)
    return sim, word_x, word_vectorizer, docs


def cluster_similarity(sim, n_clusters):
    distance = 1.0 - sim
    np.fill_diagonal(distance, 0.0)
    condensed = squareform(distance, checks=False)
    tree = linkage(condensed, method="average")
    labels = fcluster(tree, t=n_clusters, criterion="maxclust") - 1
    return labels


def cluster_terms(node_ids, word_x, vectorizer):
    if not node_ids:
        return []
    arr = np.asarray(word_x[node_ids].mean(axis=0)).ravel()
    names = vectorizer.get_feature_names_out()
    top = arr.argsort()[::-1]
    chosen = []
    for idx in top:
        term = names[idx]
        if arr[idx] <= 0:
            break
        if term.startswith("ph_"):
            term = term[3:].replace("_", " ")
        if any(term == other or term in other or other in term for other in chosen):
            continue
        chosen.append(term)
        if len(chosen) == 5:
            break
    return chosen


def evaluate(nodes, sim, labels, word_x, vectorizer):
    clusters = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[int(label)].append(idx)

    distance = 1.0 - sim
    np.fill_diagonal(distance, 0.0)
    sil = silhouette_score(distance, labels, metric="precomputed")

    sizes = [len(ids) for ids in clusters.values()]
    intra_scores = []
    nearest_external = []
    for ids in clusters.values():
        if len(ids) > 1:
            vals = [sim[i, j] for pos, i in enumerate(ids) for j in ids[pos + 1:]]
            intra_scores.append(float(np.mean(vals)))
        outside = [idx for idx in range(len(nodes)) if idx not in ids]
        if outside:
            ext = max(float(np.mean([sim[i, j] for i in ids])) for j in outside)
            nearest_external.append(ext)

    size_penalty = sum(1 for size in sizes if size < 3) / len(sizes)
    huge_penalty = max(sizes) / len(nodes)
    score = (
        sil
        + 0.65 * float(np.mean(intra_scores))
        - 0.45 * float(np.mean(nearest_external))
        - 0.55 * size_penalty
        - 0.25 * huge_penalty
    )

    summaries = []
    for label, ids in clusters.items():
        ordered = sorted(ids, key=lambda idx: nodes[idx]["rank"])
        summaries.append(
            {
                "cluster": int(label),
                "size": len(ids),
                "frequency": sum(nodes[idx]["frequency"] for idx in ids),
                "terms": cluster_terms(ids, word_x, vectorizer),
                "top_tags": [nodes[idx]["label"] for idx in ordered[:12]],
            }
        )
    summaries.sort(key=lambda row: (-row["frequency"], row["size"]))
    return {
        "score": score,
        "silhouette": sil,
        "mean_intra": float(np.mean(intra_scores)),
        "mean_external": float(np.mean(nearest_external)),
        "size_penalty": size_penalty,
        "huge_penalty": huge_penalty,
        "sizes": sorted(sizes, reverse=True),
        "summaries": summaries,
    }


def evaluate_graph_clusters(nodes, sim, labels, adjacency, word_x, vectorizer):
    clusters = defaultdict(list)
    for idx, label in enumerate(labels):
        clusters[int(label)].append(idx)

    intra = []
    nearest_external = []
    top_neighbor_retention = []
    cut_weight = 0.0
    total_weight = 0.0

    for source, edges in enumerate(adjacency):
        source_cluster = int(labels[source])
        ranked = sorted(edges.items(), key=lambda item: item[1], reverse=True)[:10]
        if ranked:
            top_neighbor_retention.append(
                sum(1 for target, _ in ranked if int(labels[target]) == source_cluster) / len(ranked)
            )
        for target, weight in edges.items():
            if target <= source:
                continue
            total_weight += weight
            if int(labels[target]) != source_cluster:
                cut_weight += weight

    for ids in clusters.values():
        if len(ids) > 1:
            vals = [sim[i, j] for pos, i in enumerate(ids) for j in ids[pos + 1:]]
            intra.append(float(np.mean(vals)))
        outside = [idx for idx in range(len(nodes)) if idx not in ids]
        if outside:
            nearest_external.append(max(float(np.mean([sim[i, j] for i in ids])) for j in outside))

    summaries = []
    for cluster, ids in clusters.items():
        ordered = sorted(ids, key=lambda idx: nodes[idx]["rank"])
        summaries.append(
            {
                "cluster": int(cluster),
                "size": len(ids),
                "frequency": sum(nodes[idx]["frequency"] for idx in ids),
                "terms": cluster_terms(ids, word_x, vectorizer),
                "top_tags": [nodes[idx]["label"] for idx in ordered[:15]],
                "all_tags": [nodes[idx]["label"] for idx in ordered],
            }
        )
    summaries.sort(key=lambda row: (-row["frequency"], row["size"]))

    return {
        "clusters": len(clusters),
        "sizes": sorted((len(ids) for ids in clusters.values()), reverse=True),
        "mean_intra_similarity": float(np.mean(intra)),
        "mean_nearest_external_similarity": float(np.mean(nearest_external)),
        "mean_top10_neighbor_retention": float(np.mean(top_neighbor_retention)),
        "graph_cut_weight_ratio": float(cut_weight / total_weight) if total_weight else 0.0,
        "summaries": summaries,
    }


def write_outputs(nodes, best):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = best["labels"]
    summaries = best["evaluation"]["summaries"]
    summary_by_cluster = {row["cluster"]: row for row in summaries}
    ordered_clusters = {row["cluster"]: idx + 1 for idx, row in enumerate(summaries)}

    with (OUT_DIR / "best_clusters.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["derived_region", "coarse_tag", "rank", "frequency", "region_terms"])
        for idx, node in enumerate(nodes):
            old_cluster = int(labels[idx])
            region = f"R{ordered_clusters[old_cluster]:02d}"
            writer.writerow(
                [
                    region,
                    node["label"],
                    node["rank"],
                    node["frequency"],
                    "; ".join(summary_by_cluster[old_cluster]["terms"]),
                ]
            )

    with (OUT_DIR / "best_cluster_summary.md").open("w", encoding="utf-8") as handle:
        ev = best["evaluation"]
        handle.write("# Derived NER-Style Regions\n\n")
        handle.write(f"- Similarity mode: `{best['mode']}`\n")
        handle.write(f"- Cluster count: {best['n_clusters']}\n")
        handle.write(f"- Composite score: {ev['score']:.4f}\n")
        handle.write(f"- Silhouette: {ev['silhouette']:.4f}\n")
        handle.write(f"- Mean intra-cluster similarity: {ev['mean_intra']:.4f}\n")
        handle.write(f"- Mean nearest-external similarity: {ev['mean_external']:.4f}\n\n")
        for out_idx, row in enumerate(summaries, start=1):
            handle.write(f"## R{out_idx:02d}: {' / '.join(row['terms'])}\n\n")
            handle.write(f"- Tags: {row['size']}\n")
            handle.write(f"- Total frequency: {row['frequency']}\n")
            handle.write(f"- Top coarse tags: {', '.join(row['top_tags'])}\n\n")

    machine = {
        "mode": best["mode"],
        "n_clusters": best["n_clusters"],
        "evaluation": {k: v for k, v in best["evaluation"].items() if k != "summaries"},
        "summaries": summaries,
    }
    (OUT_DIR / "best_cluster_summary.json").write_text(
        json.dumps(machine, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def node_confidence(nodes, labels, sim, ordered_clusters):
    clusters = defaultdict(list)
    for idx, cluster in enumerate(labels):
        clusters[int(cluster)].append(idx)

    rows = []
    for idx, node in enumerate(nodes):
        cluster = int(labels[idx])
        own_ids = [other for other in clusters[cluster] if other != idx]
        own_similarity = float(np.mean([sim[idx, other] for other in own_ids])) if own_ids else 1.0

        best_external_cluster = None
        best_external_similarity = -1.0
        for other_cluster, ids in clusters.items():
            if other_cluster == cluster:
                continue
            value = float(np.mean([sim[idx, other] for other in ids]))
            if value > best_external_similarity:
                best_external_similarity = value
                best_external_cluster = other_cluster

        rows.append(
            {
                "node": idx,
                "coarse_tag": node["label"],
                "cluster": cluster,
                "region": f"R{ordered_clusters[cluster]:02d}",
                "own_similarity": own_similarity,
                "nearest_external_region": f"R{ordered_clusters[best_external_cluster]:02d}"
                if best_external_cluster is not None
                else "",
                "nearest_external_similarity": best_external_similarity,
                "margin": own_similarity - best_external_similarity,
            }
        )
    return rows


def write_final_outputs(nodes, labels, sim, metrics):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ordered_clusters = {row["cluster"]: idx + 1 for idx, row in enumerate(metrics["summaries"])}
    summary_by_cluster = {row["cluster"]: row for row in metrics["summaries"]}
    confidence_rows = node_confidence(nodes, labels, sim, ordered_clusters)
    confidence_by_node = {row["node"]: row for row in confidence_rows}

    with (OUT_DIR / "final_statistical_regions.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            [
                "region",
                "coarse_tag",
                "rank",
                "frequency",
                "region_terms",
                "own_similarity",
                "nearest_external_region",
                "nearest_external_similarity",
                "margin",
            ]
        )
        for idx, node in enumerate(nodes):
            cluster = int(labels[idx])
            confidence = confidence_by_node[idx]
            writer.writerow(
                [
                    f"R{ordered_clusters[cluster]:02d}",
                    node["label"],
                    node["rank"],
                    node["frequency"],
                    "; ".join(summary_by_cluster[cluster]["terms"]),
                    f"{confidence['own_similarity']:.6f}",
                    confidence["nearest_external_region"],
                    f"{confidence['nearest_external_similarity']:.6f}",
                    f"{confidence['margin']:.6f}",
                ]
            )

    with (OUT_DIR / "final_statistical_region_confidence.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "region",
                "coarse_tag",
                "own_similarity",
                "nearest_external_region",
                "nearest_external_similarity",
                "margin",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for row in sorted(confidence_rows, key=lambda item: item["margin"]):
            writer.writerow(
                {
                    "region": row["region"],
                    "coarse_tag": row["coarse_tag"],
                    "own_similarity": f"{row['own_similarity']:.6f}",
                    "nearest_external_region": row["nearest_external_region"],
                    "nearest_external_similarity": f"{row['nearest_external_similarity']:.6f}",
                    "margin": f"{row['margin']:.6f}",
                }
            )

    with (OUT_DIR / "final_statistical_regions.md").open("w", encoding="utf-8") as handle:
        handle.write("# Final Statistical Tag Regions\n\n")
        handle.write("This run uses no precomputed region labels, no tag-specific exceptions, and no manually defined synonym maps.\n\n")
        handle.write("## Algorithm\n\n")
        handle.write("1. Build one weighted profile document per coarse tag from its label, sample fine tags, and complete fine-tag list.\n")
        handle.write("2. Weight the final component of slash/path-like fine tags more than parent components.\n")
        handle.write("3. Vectorize profiles with word 1-3 gram TF-IDF using corpus IDF.\n")
        handle.write("4. Keep only the top 180 TF-IDF features per coarse tag to suppress generic hub vocabulary.\n")
        handle.write("5. Compute cosine similarity over the sparse discriminative profile vectors.\n")
        handle.write("6. Build a 12-nearest-neighbor similarity graph with minimum edge similarity 0.03.\n")
        handle.write("7. Weight graph edges by similarity squared.\n")
        handle.write("8. Run Louvain-style community detection with resolution 0.6.\n\n")
        handle.write("## Metrics\n\n")
        handle.write(f"- Coarse tags: {len(nodes)}\n")
        handle.write(f"- Regions: {metrics['clusters']}\n")
        handle.write(f"- Largest region size: {metrics['sizes'][0]}\n")
        handle.write(f"- Mean intra-region similarity: {metrics['mean_intra_similarity']:.4f}\n")
        handle.write(f"- Mean nearest-external similarity: {metrics['mean_nearest_external_similarity']:.4f}\n")
        handle.write(f"- Mean top-10 neighbor retention: {metrics['mean_top10_neighbor_retention']:.4f}\n")
        handle.write(f"- Graph cut weight ratio: {metrics['graph_cut_weight_ratio']:.4f}\n\n")
        handle.write("## Lowest-Margin Tags\n\n")
        handle.write("These are statistical boundary cases, not manually reassigned exceptions.\n\n")
        for row in sorted(confidence_rows, key=lambda item: item["margin"])[:25]:
            handle.write(
                f"- {row['coarse_tag']}: {row['region']} vs {row['nearest_external_region']}, "
                f"margin {row['margin']:.4f}\n"
            )
        handle.write("\n")

        for out_idx, row in enumerate(metrics["summaries"], start=1):
            handle.write(f"## R{out_idx:02d}: {' / '.join(row['terms'])}\n\n")
            handle.write(f"- Tags: {row['size']}\n")
            handle.write(f"- Total frequency: {row['frequency']}\n")
            handle.write(f"- Top tags: {', '.join(row['top_tags'])}\n")
            handle.write(f"- All tags: {', '.join(row['all_tags'])}\n\n")

    (OUT_DIR / "final_statistical_regions.json").write_text(
        json.dumps(
            {
                "algorithm": {
                    "profile": "child-focused weighted fine-tag TF-IDF",
                    "top_features_per_tag": 180,
                    "similarity": "cosine over sparse discriminative TF-IDF profiles",
                    "graph": "12-nearest-neighbor, floor=0.03, edge_weight=similarity^2",
                    "clustering": "one-level Louvain-style modularity optimization, resolution=0.6",
                },
                "metrics": {key: value for key, value in metrics.items() if key != "summaries"},
                "lowest_margin_tags": sorted(confidence_rows, key=lambda item: item["margin"])[:50],
                "summaries": metrics["summaries"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    nodes, inventory = make_nodes()
    labels, sim, x, vectorizer, adjacency = final_cluster_labels(nodes, inventory)
    final_metrics = evaluate_graph_clusters(nodes, sim, labels, adjacency, x, vectorizer)
    write_final_outputs(nodes, labels, sim, final_metrics)

    print("Final statistical method")
    print(
        f"regions={final_metrics['clusters']}\t"
        f"largest={final_metrics['sizes'][0]}\t"
        f"intra={final_metrics['mean_intra_similarity']:.4f}\t"
        f"external={final_metrics['mean_nearest_external_similarity']:.4f}\t"
        f"top10_retention={final_metrics['mean_top10_neighbor_retention']:.4f}\t"
        f"cut={final_metrics['graph_cut_weight_ratio']:.4f}"
    )
    for idx, row in enumerate(final_metrics["summaries"][:40], start=1):
        print(f"R{idx:02d}\t{row['size']}\t{' / '.join(row['terms'][:4])}\t{', '.join(row['top_tags'][:10])}")
    print(f"\nWrote {OUT_DIR / 'final_statistical_regions.md'}")
    print(f"Wrote {OUT_DIR / 'final_statistical_regions.tsv'}")

    print("\nBaseline fixed-k candidates")
    candidates = []
    for mode in ("balanced", "child_focused", "coarse_heavy"):
        sim, word_x, vectorizer, _ = build_similarity(nodes, inventory, mode)
        for n_clusters in range(14, 33):
            labels = cluster_similarity(sim, n_clusters)
            ev = evaluate(nodes, sim, labels, word_x, vectorizer)
            candidates.append(
                {
                    "mode": mode,
                    "n_clusters": n_clusters,
                    "labels": labels,
                    "similarity": sim,
                    "word_x": word_x,
                    "vectorizer": vectorizer,
                    "evaluation": ev,
                }
            )

    candidates.sort(key=lambda row: row["evaluation"]["score"], reverse=True)
    best = candidates[0]
    write_outputs(nodes, best)

    print("Top candidates")
    for row in candidates[:12]:
        ev = row["evaluation"]
        print(
            f"{row['mode']}\tk={row['n_clusters']}\tscore={ev['score']:.4f}\t"
            f"sil={ev['silhouette']:.4f}\tintra={ev['mean_intra']:.4f}\t"
            f"external={ev['mean_external']:.4f}\tsizes={ev['sizes'][:8]}"
        )
    print()
    print(f"Best: {best['mode']} k={best['n_clusters']}")
    for idx, row in enumerate(best["evaluation"]["summaries"][:30], start=1):
        print(f"R{idx:02d}\t{row['size']}\t{' / '.join(row['terms'])}\t{', '.join(row['top_tags'][:8])}")
    print(f"\nWrote {OUT_DIR / 'best_cluster_summary.md'}")
    print(f"Wrote {OUT_DIR / 'best_clusters.tsv'}")


if __name__ == "__main__":
    main()
