from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "statistical_ner_taxonomy_louvain"

CANDIDATES_OUT = OUT_DIR / "candidate_partitions.tsv"
SUMMARY_OUT = OUT_DIR / "recommended_taxonomy_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "recommended_taxonomy_tag_map.tsv"
ASSIGNMENT_OUT = OUT_DIR / "all_vectorized_tag_assignments.tsv"
REPORT_OUT = OUT_DIR / "recommended_taxonomy_report.md"

DISCOVERY_MIN_COUNT = 100
RANDOM_SEED = 13
K_VALUES = [10, 15, 25, 40]
MIN_SIM_VALUES = [0.55, 0.60, 0.65, 0.70, 0.75]
RESOLUTION_VALUES = [0.55, 0.70, 0.85, 1.00, 1.20, 1.45, 1.75, 2.10]
MIN_ASSIGNMENT_FLOOR = 0.45
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
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
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "tag",
    "tags",
    "type",
    "types",
    "category",
    "categories",
    "entity",
    "entities",
    "item",
    "items",
    "reference",
    "references",
    "general",
    "other",
    "misc",
}


def token_words(label: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(label.lower().replace("_", " ")) if token not in STOPWORDS and len(token) > 1]


def matrix(rows: list[dict[str, object]]) -> np.ndarray:
    return np.stack([row["vector"] for row in rows]).astype(np.float32)


def build_mutual_knn_graph(sims: np.ndarray, k: int, min_sim: float) -> nx.Graph:
    n = sims.shape[0]
    top_sets: list[set[int]] = []
    for idx in range(n):
        row = sims[idx].copy()
        row[idx] = -np.inf
        limit = min(k, n - 1)
        top = np.argpartition(-row, kth=limit - 1)[:limit]
        top_sets.append({int(pos) for pos in top if row[int(pos)] >= min_sim})

    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    for left in range(n):
        for right in top_sets[left]:
            if left < right and left in top_sets[right]:
                graph.add_edge(left, right, weight=float(sims[left, right]))
    return graph


def communities_for_graph(graph: nx.Graph, resolution: float) -> list[list[int]]:
    communities = nx.algorithms.community.louvain_communities(
        graph,
        weight="weight",
        resolution=resolution,
        seed=RANDOM_SEED,
    )
    return [sorted(int(idx) for idx in community) for community in communities]


def centroid(indices: list[int], x: np.ndarray) -> np.ndarray:
    vec = x[indices].mean(axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def partition_metrics(
    communities: list[list[int]],
    rows: list[dict[str, object]],
    x: np.ndarray,
    total_count: int,
    graph: nx.Graph,
) -> dict[str, object]:
    centers = np.stack([centroid(group, x) for group in communities]).astype(np.float32)
    assignment = np.empty(len(rows), dtype=np.int32)
    for cluster_id, group in enumerate(communities):
        for idx in group:
            assignment[idx] = cluster_id

    own_sims = np.sum(x * centers[assignment], axis=1)
    center_sims = x @ centers.T
    center_sims[np.arange(len(rows)), assignment] = -np.inf
    nearest_other = np.max(center_sims, axis=1)
    margins = own_sims - nearest_other
    weights = np.array([float(row["count"]) for row in rows], dtype=np.float64)

    counts = []
    tag_counts = []
    singleton_count = 0
    for group in communities:
        count = sum(int(rows[idx]["count"]) for idx in group)
        counts.append(count)
        tag_counts.append(len(group))
        if len(group) == 1:
            singleton_count += 1

    largest_count = max(counts)
    non_singleton_mentions = sum(count for count, tag_count in zip(counts, tag_counts) if tag_count > 1)
    modularity = nx.algorithms.community.modularity(
        graph,
        [set(group) for group in communities],
        weight="weight",
    )
    weighted_coherence = float(np.average(own_sims, weights=weights))
    weighted_margin = float(np.average(margins, weights=weights))
    p10_margin = float(np.percentile(margins, 10))
    cluster_count = len(communities)
    largest_pct = largest_count / total_count * 100.0
    non_singleton_pct = non_singleton_mentions / total_count * 100.0

    blob_penalty = max(0.0, largest_pct - 24.0) / 24.0
    singleton_penalty = singleton_count / max(1, cluster_count)
    count_penalty = abs(cluster_count - 32) / 32.0
    score = (
        modularity
        + 0.80 * weighted_margin
        + 0.25 * weighted_coherence
        + 0.004 * non_singleton_pct
        - 0.50 * blob_penalty
        - 0.20 * singleton_penalty
        - 0.08 * count_penalty
    )

    return {
        "cluster_count": cluster_count,
        "singleton_clusters": singleton_count,
        "largest_pct": largest_pct,
        "non_singleton_pct": non_singleton_pct,
        "weighted_coherence": weighted_coherence,
        "weighted_margin": weighted_margin,
        "p10_margin": p10_margin,
        "modularity": modularity,
        "score": score,
    }


def choose_partition(
    rows: list[dict[str, object]],
    x: np.ndarray,
    total_count: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    sims = x @ x.T
    candidates: list[dict[str, object]] = []
    best: dict[str, object] | None = None

    for k in K_VALUES:
        for min_sim in MIN_SIM_VALUES:
            graph = build_mutual_knn_graph(sims, k, min_sim)
            edge_count = graph.number_of_edges()
            if edge_count == 0:
                continue
            for resolution in RESOLUTION_VALUES:
                communities = communities_for_graph(graph, resolution)
                metrics = partition_metrics(communities, rows, x, total_count, graph)
                candidate = {
                    "k": k,
                    "min_sim": min_sim,
                    "resolution": resolution,
                    "edge_count": edge_count,
                    "communities": communities,
                    **metrics,
                }
                candidates.append(candidate)
                if best is None or float(candidate["score"]) > float(best["score"]):
                    best = candidate

    if best is None:
        raise RuntimeError("No candidate partitions were produced.")
    return best, candidates


def ranked_clusters(
    communities: list[list[int]],
    rows: list[dict[str, object]],
    x: np.ndarray,
) -> list[dict[str, object]]:
    clusters = []
    for raw_id, group in enumerate(communities):
        count = sum(int(rows[idx]["count"]) for idx in group)
        center = centroid(group, x)
        anchor_idx = max(group, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
        weights = np.array([float(rows[idx]["count"]) for idx in group], dtype=np.float64)
        sims = np.array([float(np.dot(rows[idx]["vector"], center)) for idx in group], dtype=np.float64)
        weighted_coherence = float(np.average(sims, weights=weights)) if weights.sum() else float(np.mean(sims))
        unweighted_coherence = float(np.mean(sims)) if len(sims) else 1.0
        threshold = max(MIN_ASSIGNMENT_FLOOR, float(np.percentile(sims, 5)) if len(sims) > 1 else 0.80)

        word_counts = Counter()
        for idx in group:
            for token in token_words(str(rows[idx]["coarse_tag"])):
                word_counts[token] += max(1, int(rows[idx]["count"]))

        clusters.append(
            {
                "raw_id": raw_id,
                "members": group,
                "count": count,
                "center": center,
                "anchor": str(rows[anchor_idx]["coarse_tag"]),
                "weighted_coherence": weighted_coherence,
                "unweighted_coherence": unweighted_coherence,
                "assignment_threshold": threshold,
                "top_words": [word for word, _count in word_counts.most_common(8)],
            }
        )

    clusters.sort(key=lambda cluster: (-int(cluster["count"]), str(cluster["anchor"])))
    for rank, cluster in enumerate(clusters, start=1):
        cluster["rank"] = rank
        words = cluster["top_words"][:4]
        label_hint = "_".join(words) if words else re.sub(r"\W+", "_", str(cluster["anchor"]).lower()).strip("_")
        cluster["stat_label"] = f"C{rank:02d}_{label_hint or 'cluster'}"
    return clusters


def assign_all_rows(
    all_rows: list[dict[str, object]],
    clusters: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    centers = np.stack([cluster["center"] for cluster in clusters]).astype(np.float32)
    assignments = []
    assigned_count = 0
    low_sim_count = 0
    assigned_mentions = 0
    low_sim_mentions = 0

    for row in all_rows:
        vector = row["vector"].astype(np.float32)
        sims = centers @ vector
        best_pos = int(np.argmax(sims))
        cluster = clusters[best_pos]
        similarity = float(sims[best_pos])
        threshold = float(cluster["assignment_threshold"])
        status = "assigned" if similarity >= threshold else "low_similarity"
        if status == "assigned":
            assigned_count += 1
            assigned_mentions += int(row["count"])
        else:
            low_sim_count += 1
            low_sim_mentions += int(row["count"])
        assignments.append(
            {
                "coarse_tag": row["coarse_tag"],
                "count": int(row["count"]),
                "pct_total": float(row["percent"]),
                "status": status,
                "cluster_rank": cluster["rank"],
                "stat_label": cluster["stat_label"],
                "anchor": cluster["anchor"],
                "similarity_pct": similarity * 100.0,
                "cluster_threshold_pct": threshold * 100.0,
            }
        )

    return assignments, {
        "assigned_count": assigned_count,
        "low_sim_count": low_sim_count,
        "assigned_mentions": assigned_mentions,
        "low_sim_mentions": low_sim_mentions,
    }


def write_outputs(
    all_rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    discovery_rows: list[dict[str, object]],
    total_count: int,
    best: dict[str, object],
    candidates: list[dict[str, object]],
    clusters: list[dict[str, object]],
    assignments: list[dict[str, object]],
    assignment_stats: dict[str, object],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with CANDIDATES_OUT.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "k",
            "min_sim",
            "resolution",
            "edge_count",
            "cluster_count",
            "singleton_clusters",
            "largest_pct",
            "non_singleton_pct",
            "weighted_coherence",
            "weighted_margin",
            "p10_margin",
            "modularity",
            "score",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for candidate in sorted(candidates, key=lambda item: -float(item["score"])):
            writer.writerow(
                {
                    key: f"{candidate[key]:.6f}" if isinstance(candidate[key], float) else candidate[key]
                    for key in fieldnames
                }
            )

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "stat_label",
                "anchor_tag",
                "member_count_discovery",
                "mention_count_discovery",
                "pct_total_discovery_mentions",
                "weighted_coherence_pct",
                "unweighted_coherence_pct",
                "assignment_threshold_pct",
                "top_words",
                "top_discovery_tags",
            ]
        )
        for cluster in clusters:
            top_members = sorted(
                cluster["members"],
                key=lambda idx: (-int(discovery_rows[idx]["count"]), str(discovery_rows[idx]["coarse_tag"])),
            )[:30]
            writer.writerow(
                [
                    cluster["rank"],
                    cluster["stat_label"],
                    cluster["anchor"],
                    len(cluster["members"]),
                    cluster["count"],
                    f"{int(cluster['count']) / total_count * 100.0:.6f}",
                    f"{float(cluster['weighted_coherence']) * 100.0:.2f}",
                    f"{float(cluster['unweighted_coherence']) * 100.0:.2f}",
                    f"{float(cluster['assignment_threshold']) * 100.0:.2f}",
                    ", ".join(cluster["top_words"]),
                    "; ".join(f"{discovery_rows[idx]['coarse_tag']} ({discovery_rows[idx]['count']})" for idx in top_members),
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "count",
                "pct_total",
                "discovery_or_assigned",
                "status",
                "cluster_rank",
                "stat_label",
                "anchor_tag",
                "similarity_pct",
                "cluster_threshold_pct",
            ]
        )
        discovery_tags = {str(row["coarse_tag"]) for row in discovery_rows}
        for row in sorted(assignments, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['pct_total']:.6f}",
                    "discovery" if row["coarse_tag"] in discovery_tags else "assigned",
                    row["status"],
                    row["cluster_rank"],
                    row["stat_label"],
                    row["anchor"],
                    f"{row['similarity_pct']:.2f}",
                    f"{row['cluster_threshold_pct']:.2f}",
                ]
            )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    "unvectorized",
                    "no_vector",
                    "",
                    "NO_VECTOR",
                    "NO_VECTOR",
                    "",
                    "",
                ]
            )

    with ASSIGNMENT_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "coarse_tag",
                "count",
                "pct_total",
                "status",
                "cluster_rank",
                "stat_label",
                "anchor",
                "similarity_pct",
                "cluster_threshold_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in sorted(assignments, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            writer.writerow(
                {
                    **row,
                    "pct_total": f"{row['pct_total']:.6f}",
                    "similarity_pct": f"{row['similarity_pct']:.2f}",
                    "cluster_threshold_pct": f"{row['cluster_threshold_pct']:.2f}",
                }
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Statistical NER Taxonomy, Louvain Mutual-KNN\n\n")
        handle.write(
            "This taxonomy is generated without hand-seeded category labels and without per-tag exceptions. "
            "Discovery uses tags with count >= 100 as the statistically stable label set. "
            "A mutual-k-nearest-neighbor cosine graph is built over tag vectors, Louvain community detection is swept "
            "over graph and resolution parameters, and the recommended partition is selected by a fixed objective: "
            "high modularity, high own-community margin, high coherence, high non-singleton coverage, and penalties for giant blobs, "
            "singletons, and excessive distance from an NER-usable cluster count.\n\n"
        )
        handle.write("## Selected Partition\n\n")
        handle.write(f"- Discovery tags: {len(discovery_rows)}\n")
        handle.write(f"- Full vectorized tags: {len(all_rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Selected k: {best['k']}\n")
        handle.write(f"- Selected minimum edge similarity: {float(best['min_sim']) * 100.0:.2f}%\n")
        handle.write(f"- Selected Louvain resolution: {float(best['resolution']):.2f}\n")
        handle.write(f"- Discovery communities: {best['cluster_count']}\n")
        handle.write(f"- Largest discovery community: {float(best['largest_pct']):.4f}% of all mentions\n")
        handle.write(f"- Weighted discovery coherence: {float(best['weighted_coherence']) * 100.0:.2f}%\n")
        handle.write(f"- Weighted discovery margin: {float(best['weighted_margin']) * 100.0:.2f}%\n")
        handle.write(f"- Assigned vectorized tags: {assignment_stats['assigned_count']} ({int(assignment_stats['assigned_mentions']) / total_count * 100.0:.4f}% mentions)\n")
        handle.write(f"- Low-sim vectorized tags: {assignment_stats['low_sim_count']} ({int(assignment_stats['low_sim_mentions']) / total_count * 100.0:.4f}% mentions)\n\n")

        handle.write("## Communities\n\n")
        for cluster in clusters:
            handle.write(f"### {cluster['rank']}. {cluster['stat_label']}\n\n")
            handle.write(f"Anchor tag: `{cluster['anchor']}`\n\n")
            handle.write(
                f"Discovery coverage: {int(cluster['count']) / total_count * 100.0:.4f}% of all mentions; "
                f"{cluster['count']} mentions; {len(cluster['members'])} discovery tags\n\n"
            )
            handle.write(
                f"Weighted coherence: {float(cluster['weighted_coherence']) * 100.0:.2f}%; "
                f"assignment threshold: {float(cluster['assignment_threshold']) * 100.0:.2f}%\n\n"
            )
            if cluster["top_words"]:
                handle.write("Top words: " + ", ".join(f"`{word}`" for word in cluster["top_words"]) + "\n\n")
            top_members = sorted(
                cluster["members"],
                key=lambda idx: (-int(discovery_rows[idx]["count"]), str(discovery_rows[idx]["coarse_tag"])),
            )[:20]
            for idx in top_members:
                handle.write(f"- `{discovery_rows[idx]['coarse_tag']}` ({discovery_rows[idx]['count']})\n")
            handle.write("\n")


def main() -> None:
    all_rows, unvectorized, total_count = pairwise.load_intact_rows()
    discovery_rows = [row for row in all_rows if int(row["count"]) >= DISCOVERY_MIN_COUNT]
    discovery_rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    x = matrix(discovery_rows)

    best, candidates = choose_partition(discovery_rows, x, total_count)
    clusters = ranked_clusters(best["communities"], discovery_rows, x)
    assignments, assignment_stats = assign_all_rows(all_rows, clusters)
    write_outputs(
        all_rows,
        unvectorized,
        discovery_rows,
        total_count,
        best,
        candidates,
        clusters,
        assignments,
        assignment_stats,
    )

    print(f"discovery_tags={len(discovery_rows)}")
    print(f"full_vectorized_tags={len(all_rows)}")
    print(f"unvectorized_tags={len(unvectorized)}")
    print(f"selected_k={best['k']}")
    print(f"selected_min_sim={float(best['min_sim']) * 100.0:.2f}")
    print(f"selected_resolution={float(best['resolution']):.2f}")
    print(f"clusters={best['cluster_count']}")
    print(f"largest_pct={float(best['largest_pct']):.4f}")
    print(f"weighted_coherence={float(best['weighted_coherence']) * 100.0:.2f}")
    print(f"weighted_margin={float(best['weighted_margin']) * 100.0:.2f}")
    print(f"assigned_mentions_pct={int(assignment_stats['assigned_mentions']) / total_count * 100.0:.4f}")
    print(f"low_sim_mentions_pct={int(assignment_stats['low_sim_mentions']) / total_count * 100.0:.4f}")
    print(f"report={REPORT_OUT}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"candidates={CANDIDATES_OUT}")


if __name__ == "__main__":
    main()
