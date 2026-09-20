from __future__ import annotations

import csv
import math
import re
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
from sklearn.neighbors import NearestNeighbors

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "statistical_ner_taxonomy_louvain_full_tagset"

CANDIDATES_OUT = OUT_DIR / "candidate_partitions.tsv"
SUMMARY_OUT = OUT_DIR / "taxonomy_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "taxonomy_tag_map.tsv"
REPORT_OUT = OUT_DIR / "taxonomy_report.md"

RANDOM_SEED = 13
K_VALUES = [10, 20, 40]
MIN_SIM_VALUES = [0.60, 0.65, 0.70, 0.75]
RESOLUTION_VALUES = [0.80, 1.00, 1.25, 1.50, 1.80, 2.20]
MAX_K = max(K_VALUES)
TARGET_COMMUNITIES = 64
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


def compute_neighbors(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    model = NearestNeighbors(n_neighbors=MAX_K + 1, metric="cosine", algorithm="brute")
    model.fit(x)
    distances, indices = model.kneighbors(x, return_distance=True)
    return indices[:, 1:].astype(np.int32), (1.0 - distances[:, 1:]).astype(np.float32)


def build_mutual_knn_graph(
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    k: int,
    min_sim: float,
) -> nx.Graph:
    n = neighbor_idx.shape[0]
    top_sets: list[set[int]] = []
    for idx in range(n):
        values = {
            int(candidate)
            for candidate, similarity in zip(neighbor_idx[idx, :k], neighbor_sim[idx, :k])
            if float(similarity) >= min_sim
        }
        top_sets.append(values)

    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    for left in range(n):
        for candidate, similarity in zip(neighbor_idx[left, :k], neighbor_sim[left, :k]):
            right = int(candidate)
            if right <= left or float(similarity) < min_sim:
                continue
            if left in top_sets[right]:
                graph.add_edge(left, right, weight=float(similarity))
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

    cluster_count = len(communities)
    largest_pct = largest_count / total_count * 100.0
    non_singleton_pct = non_singleton_mentions / total_count * 100.0
    weighted_coherence = float(np.average(own_sims, weights=weights))
    weighted_margin = float(np.average(margins, weights=weights))
    p10_margin = float(np.percentile(margins, 10))
    singleton_ratio = singleton_count / max(1, cluster_count)

    blob_penalty = max(0.0, largest_pct - 24.0) / 24.0
    count_penalty = abs(math.log(max(1, cluster_count) / TARGET_COMMUNITIES))
    score = (
        modularity
        + 0.75 * weighted_margin
        + 0.22 * weighted_coherence
        + 0.004 * non_singleton_pct
        - 0.55 * blob_penalty
        - 0.22 * singleton_ratio
        - 0.06 * count_penalty
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
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    total_count: int,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    best: dict[str, object] | None = None

    for k in K_VALUES:
        for min_sim in MIN_SIM_VALUES:
            graph = build_mutual_knn_graph(neighbor_idx, neighbor_sim, k, min_sim)
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
                print(
                    f"k={k} min={min_sim:.2f} res={resolution:.2f} "
                    f"clusters={metrics['cluster_count']} largest={metrics['largest_pct']:.2f} "
                    f"coh={metrics['weighted_coherence'] * 100.0:.2f} "
                    f"margin={metrics['weighted_margin'] * 100.0:.2f} "
                    f"score={metrics['score']:.4f}"
                )

    if best is None:
        raise RuntimeError("No candidate partitions were produced.")
    return best, candidates


def ranked_clusters(
    communities: list[list[int]],
    rows: list[dict[str, object]],
    x: np.ndarray,
    total_count: int,
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

        word_counts = Counter()
        for idx in group:
            for token in token_words(str(rows[idx]["coarse_tag"])):
                word_counts[token] += max(1, int(rows[idx]["count"]))

        clusters.append(
            {
                "raw_id": raw_id,
                "members": group,
                "count": count,
                "pct_total": count / total_count * 100.0,
                "center": center,
                "anchor": str(rows[anchor_idx]["coarse_tag"]),
                "weighted_coherence": weighted_coherence,
                "unweighted_coherence": unweighted_coherence,
                "top_words": [word for word, _count in word_counts.most_common(8)],
            }
        )

    clusters.sort(key=lambda cluster: (-int(cluster["count"]), str(cluster["anchor"])))
    for rank, cluster in enumerate(clusters, start=1):
        cluster["rank"] = rank
        words = cluster["top_words"][:4]
        label_hint = "_".join(words) if words else re.sub(r"\W+", "_", str(cluster["anchor"]).lower()).strip("_")
        cluster["stat_label"] = f"C{rank:03d}_{label_hint or 'cluster'}"
    return clusters


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    best: dict[str, object],
    candidates: list[dict[str, object]],
    clusters: list[dict[str, object]],
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
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_coherence_pct",
                "unweighted_coherence_pct",
                "top_words",
                "top_tags",
            ]
        )
        for cluster in clusters:
            top_members = sorted(
                cluster["members"],
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
            )[:35]
            writer.writerow(
                [
                    cluster["rank"],
                    cluster["stat_label"],
                    cluster["anchor"],
                    len(cluster["members"]),
                    cluster["count"],
                    f"{float(cluster['pct_total']):.6f}",
                    f"{float(cluster['weighted_coherence']) * 100.0:.2f}",
                    f"{float(cluster['unweighted_coherence']) * 100.0:.2f}",
                    ", ".join(cluster["top_words"]),
                    "; ".join(f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})" for idx in top_members),
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "count",
                "pct_total",
                "cluster_rank",
                "stat_label",
                "anchor_tag",
                "centroid_similarity_pct",
                "status",
            ]
        )
        for cluster in clusters:
            for idx in sorted(
                cluster["members"],
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
            ):
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        cluster["rank"],
                        cluster["stat_label"],
                        cluster["anchor"],
                        f"{float(np.dot(rows[idx]['vector'], cluster['center'])) * 100.0:.2f}",
                        "clustered",
                    ]
                )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    "",
                    "NO_VECTOR",
                    "NO_VECTOR",
                    "",
                    "no_vector",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Statistical NER Taxonomy, Louvain Full Tagset\n\n")
        handle.write(
            "This expands community discovery to the entire vectorized tag set. "
            "No hand-seeded category labels, no individual tag rules, and no frequency cutoff are used for discovery. "
            "The graph is a mutual-k-nearest-neighbor cosine graph over all vectorized tag labels. "
            "A Louvain grid search selects the partition by a fixed objective: modularity, community margin, coherence, "
            "non-singleton mention coverage, and penalties for giant blobs, singleton excess, and unusable cluster count.\n\n"
        )
        handle.write("## Selected Partition\n\n")
        handle.write(f"- Vectorized tags: {len(rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Selected k: {best['k']}\n")
        handle.write(f"- Selected minimum edge similarity: {float(best['min_sim']) * 100.0:.2f}%\n")
        handle.write(f"- Selected Louvain resolution: {float(best['resolution']):.2f}\n")
        handle.write(f"- Communities: {best['cluster_count']}\n")
        handle.write(f"- Singleton communities: {best['singleton_clusters']}\n")
        handle.write(f"- Largest community: {float(best['largest_pct']):.4f}% of all mentions\n")
        handle.write(f"- Non-singleton community coverage: {float(best['non_singleton_pct']):.4f}% of all mentions\n")
        handle.write(f"- Weighted coherence: {float(best['weighted_coherence']) * 100.0:.2f}%\n")
        handle.write(f"- Weighted margin: {float(best['weighted_margin']) * 100.0:.2f}%\n\n")

        handle.write("## Communities\n\n")
        for cluster in clusters[:160]:
            handle.write(f"### {cluster['rank']}. {cluster['stat_label']}\n\n")
            handle.write(f"Anchor tag: `{cluster['anchor']}`\n\n")
            handle.write(
                f"Coverage: {float(cluster['pct_total']):.4f}% of all mentions; "
                f"{cluster['count']} mentions; {len(cluster['members'])} tags\n\n"
            )
            handle.write(
                f"Weighted coherence: {float(cluster['weighted_coherence']) * 100.0:.2f}%; "
                f"unweighted coherence: {float(cluster['unweighted_coherence']) * 100.0:.2f}%\n\n"
            )
            if cluster["top_words"]:
                handle.write("Top words: " + ", ".join(f"`{word}`" for word in cluster["top_words"]) + "\n\n")
            top_members = sorted(
                cluster["members"],
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
            )[:24]
            for idx in top_members:
                handle.write(f"- `{rows[idx]['coarse_tag']}` ({rows[idx]['count']})\n")
            handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    x = matrix(rows)
    neighbor_idx, neighbor_sim = compute_neighbors(x)
    best, candidates = choose_partition(rows, x, neighbor_idx, neighbor_sim, total_count)
    clusters = ranked_clusters(best["communities"], rows, x, total_count)
    write_outputs(rows, unvectorized, total_count, best, candidates, clusters)

    print(f"full_vectorized_tags={len(rows)}")
    print(f"unvectorized_tags={len(unvectorized)}")
    print(f"selected_k={best['k']}")
    print(f"selected_min_sim={float(best['min_sim']) * 100.0:.2f}")
    print(f"selected_resolution={float(best['resolution']):.2f}")
    print(f"clusters={best['cluster_count']}")
    print(f"singletons={best['singleton_clusters']}")
    print(f"largest_pct={float(best['largest_pct']):.4f}")
    print(f"non_singleton_pct={float(best['non_singleton_pct']):.4f}")
    print(f"weighted_coherence={float(best['weighted_coherence']) * 100.0:.2f}")
    print(f"weighted_margin={float(best['weighted_margin']) * 100.0:.2f}")
    print(f"report={REPORT_OUT}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"candidates={CANDIDATES_OUT}")


if __name__ == "__main__":
    main()
