import csv
import json
from collections import defaultdict

import numpy as np
from sklearn.cluster import MiniBatchKMeans

import cluster_all_finerweb_labels_fasttext as base


OUTPUT_DIR = base.OUTPUT_DIR
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_flat_k20_explaining_tags_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_flat_k20_explaining_tags_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_flat_k20_explaining_tags.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_flat_k20_explaining_tags.json"

K = 20
RANDOM_STATES = (3, 7, 13, 19, 29)
MAX_REFINEMENT_STEPS = 12


def normalized_centers(model):
    centers = model.cluster_centers_.astype(np.float32)
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def nearest_points_to_centers(x, centers):
    sims = x @ centers.T
    used = set()
    nearest = []
    for cluster in range(centers.shape[0]):
        for idx in np.argsort(-sims[:, cluster]):
            candidate = int(idx)
            if candidate not in used:
                used.add(candidate)
                nearest.append(candidate)
                break
    return np.array(nearest, dtype=np.int32)


def assign_to_medoids(x, medoid_indices):
    medoid_vectors = x[medoid_indices]
    sims = x @ medoid_vectors.T
    labels = np.argmax(sims, axis=1).astype(np.int32)
    assigned_sims = sims[np.arange(x.shape[0]), labels]
    return labels, assigned_sims


def update_medoids(x, labels, medoid_indices):
    new_medoids = medoid_indices.copy()
    used = set()
    for cluster in range(K):
        idx = np.where(labels == cluster)[0]
        if len(idx) == 0:
            continue
        centroid = np.mean(x[idx], axis=0)
        norm = np.linalg.norm(centroid)
        if not norm:
            continue
        centroid = centroid / norm
        local_sims = x[idx] @ centroid
        for local_idx in np.argsort(-local_sims):
            candidate = int(idx[local_idx])
            if candidate not in used:
                new_medoids[cluster] = candidate
                used.add(candidate)
                break
    return new_medoids


def cluster_quality(labels, sims):
    cluster_means = []
    cluster_sizes = []
    for cluster in range(K):
        idx = np.where(labels == cluster)[0]
        if len(idx) == 0:
            continue
        cluster_means.append(float(np.mean(sims[idx])))
        cluster_sizes.append(len(idx))
    mean = float(np.mean(sims))
    p10 = float(np.percentile(sims, 10))
    cluster_mean_std = float(np.std(cluster_means)) if cluster_means else 1.0
    size_cv = float(np.std(cluster_sizes) / np.mean(cluster_sizes)) if cluster_sizes else 1.0
    score = mean + 0.20 * p10 - 0.35 * cluster_mean_std - 0.03 * size_cv
    return {
        "score": score,
        "mean_similarity": mean,
        "median_similarity": float(np.median(sims)),
        "p10_similarity": p10,
        "cluster_mean_std": cluster_mean_std,
        "size_cv": size_cv,
        "min_cluster_size": min(cluster_sizes) if cluster_sizes else 0,
        "max_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
    }


def fit_seed(x, random_state):
    model = MiniBatchKMeans(
        n_clusters=K,
        random_state=random_state,
        batch_size=4096,
        n_init=8,
        max_iter=350,
        reassignment_ratio=0.0,
    )
    model.fit(x)
    medoids = nearest_points_to_centers(x, normalized_centers(model))
    previous = None
    for _ in range(MAX_REFINEMENT_STEPS):
        labels, sims = assign_to_medoids(x, medoids)
        new_medoids = update_medoids(x, labels, medoids)
        if previous is not None and np.array_equal(new_medoids, medoids):
            break
        previous = medoids
        medoids = new_medoids
    labels, sims = assign_to_medoids(x, medoids)
    quality = cluster_quality(labels, sims)
    quality["random_state"] = random_state
    return medoids, labels, sims, quality


def choose_best(x):
    attempts = []
    best = None
    for random_state in RANDOM_STATES:
        medoids, labels, sims, quality = fit_seed(x, random_state)
        attempts.append(quality)
        if best is None or quality["score"] > best[0]["score"]:
            best = (quality, medoids, labels, sims)
    return best[1], best[2], best[3], best[0], attempts


def pairwise_mean_sample(x, max_items=1500):
    if len(x) < 2:
        return 1.0
    if len(x) > max_items:
        rng = np.random.default_rng(37)
        x = x[rng.choice(len(x), size=max_items, replace=False)]
    sims = []
    for start in range(0, len(x), 256):
        block = x[start:start + 256]
        sim = block @ x.T
        for i in range(sim.shape[0]):
            global_i = start + i
            sims.extend(sim[i, global_i + 1:].tolist())
    return float(np.mean(np.array(sims, dtype=np.float32))) if sims else 1.0


def prepare_vectors():
    rows = base.load_rows()
    vectors = base.load_fasttext(base.collect_needed_words(rows))
    vector_positions = []
    vecs = []
    for pos, row in enumerate(rows):
        vec, matched = base.row_vector(row, vectors)
        row["matched_tokens"] = matched
        if vec is None:
            continue
        vector_positions.append(pos)
        vecs.append(vec)
    return rows, vector_positions, np.vstack(vecs).astype(np.float32)


def write_outputs(rows, vector_positions, x, medoids, labels, sims, best_quality, attempts):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    vector_rows = [rows[pos] for pos in vector_positions]
    pos_to_vec_idx = {pos: idx for idx, pos in enumerate(vector_positions)}
    group_to_indices = defaultdict(list)
    for vec_idx, group in enumerate(labels):
        group_to_indices[int(group)].append(vec_idx)

    summaries = []
    for group in range(K):
        indices = group_to_indices[group]
        group_x = x[indices]
        medoid_vec_idx = int(medoids[group])
        medoid_row = vector_rows[medoid_vec_idx]
        nearest = sorted(indices, key=lambda idx: sims[idx], reverse=True)[:16]
        weakest = sorted(indices, key=lambda idx: sims[idx])[:12]
        summaries.append(
            {
                "raw_group": group,
                "explaining_tag": medoid_row["original_label"],
                "tag_count": len(indices),
                "mean_similarity": float(np.mean(sims[indices])),
                "median_similarity": float(np.median(sims[indices])),
                "p10_similarity": float(np.percentile(sims[indices], 10)),
                "mean_pairwise_similarity_sample": pairwise_mean_sample(group_x),
                "nearest_tags": [
                    {
                        "tag": vector_rows[idx]["original_label"],
                        "similarity": round(float(sims[idx]), 4),
                    }
                    for idx in nearest
                ],
                "weakest_tags": [
                    {
                        "tag": vector_rows[idx]["original_label"],
                        "similarity": round(float(sims[idx]), 4),
                    }
                    for idx in weakest
                ],
            }
        )

    summaries.sort(key=lambda item: (-item["tag_count"], item["explaining_tag"]))
    raw_to_group_id = {}
    for idx, summary in enumerate(summaries, start=1):
        summary["group_id"] = f"M{idx:02d}"
        raw_to_group_id[summary["raw_group"]] = summary["group_id"]

    summary_by_raw = {summary["raw_group"]: summary for summary in summaries}
    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "explaining_tag",
                "tag_count",
                "mean_similarity_pct",
                "median_similarity_pct",
                "p10_similarity_pct",
                "mean_pairwise_similarity_sample_pct",
                "nearest_tags",
                "weakest_tags",
            ]
        )
        for summary in summaries:
            writer.writerow(
                [
                    summary["group_id"],
                    summary["explaining_tag"],
                    summary["tag_count"],
                    f"{summary['mean_similarity'] * 100:.2f}",
                    f"{summary['median_similarity'] * 100:.2f}",
                    f"{summary['p10_similarity'] * 100:.2f}",
                    f"{summary['mean_pairwise_similarity_sample'] * 100:.2f}",
                    " | ".join(item["tag"] for item in summary["nearest_tags"][:10]),
                    " | ".join(item["tag"] for item in summary["weakest_tags"][:10]),
                ]
            )

    assigned_positions = set(vector_positions)
    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "explaining_tag",
                "original_label",
                "vector_tokens",
                "similarity_to_explaining_tag_pct",
            ]
        )
        for pos, row in enumerate(rows):
            if pos not in assigned_positions:
                writer.writerow(["UNVECTORIZED", "unvectorized", row["original_label"], "", ""])
                continue
            vec_idx = pos_to_vec_idx[pos]
            raw_group = int(labels[vec_idx])
            summary = summary_by_raw[raw_group]
            writer.writerow(
                [
                    raw_to_group_id[raw_group],
                    summary["explaining_tag"],
                    row["original_label"],
                    " ".join(row["matched_tokens"]),
                    f"{float(sims[vec_idx]) * 100:.2f}",
                ]
            )

    payload = {
        "source": "finerweb_label_inventory.tsv",
        "source_column": "original_label",
        "embedding_rule": "flat full original_label phrase vector; no parent/child weighting",
        "selection_rule": "automatic k=20 cosine medoids; explaining tags must be actual original_label strings",
        "labels_total": len(rows),
        "vectorized_labels": len(vector_positions),
        "unvectorized_labels": len(rows) - len(vector_positions),
        "best_quality": best_quality,
        "attempts": attempts,
        "groups": summaries,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# fiNERweb Explaining Tags K20\n\n")
        f.write("- Centers are actual `original_label` strings selected automatically from the full tagset.\n")
        f.write("- Embedding rule: flat full fine-grained label vector; no parent/child weighting.\n")
        f.write("- Assignment rule: every vectorized label is assigned to exactly one nearest explaining tag.\n\n")
        f.write(f"- Labels total: {len(rows)}\n")
        f.write(f"- Vectorized labels: {len(vector_positions)}\n")
        f.write(f"- Unvectorized labels: {len(rows) - len(vector_positions)}\n")
        f.write(f"- Overall mean similarity to explaining tag: {best_quality['mean_similarity'] * 100:.2f}%\n")
        f.write(f"- P10 similarity to explaining tag: {best_quality['p10_similarity'] * 100:.2f}%\n")
        f.write(f"- Cluster mean similarity std: {best_quality['cluster_mean_std'] * 100:.2f}%\n")
        f.write(f"- Size CV: {best_quality['size_cv']:.3f}\n\n")
        f.write("## Attempts\n\n")
        f.write("| seed | score | mean | median | p10 | similarity std | size cv | min size | max size |\n")
        f.write("|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for attempt in attempts:
            f.write(
                f"| {attempt['random_state']} | {attempt['score']:.4f} | "
                f"{attempt['mean_similarity'] * 100:.2f}% | "
                f"{attempt['median_similarity'] * 100:.2f}% | "
                f"{attempt['p10_similarity'] * 100:.2f}% | "
                f"{attempt['cluster_mean_std'] * 100:.2f}% | "
                f"{attempt['size_cv']:.3f} | "
                f"{attempt['min_cluster_size']} | {attempt['max_cluster_size']} |\n"
            )
        f.write("\n## Explaining Tags\n\n")
        for summary in summaries:
            f.write(
                f"### {summary['group_id']} `{summary['explaining_tag']}` "
                f"({summary['tag_count']} tags, mean {summary['mean_similarity'] * 100:.2f}%)\n\n"
            )
            f.write("Nearest tags: " + "; ".join(item["tag"] for item in summary["nearest_tags"][:8]) + "\n\n")
            f.write("Weakest assigned tags: " + "; ".join(item["tag"] for item in summary["weakest_tags"][:8]) + "\n\n")


def main():
    rows, vector_positions, x = prepare_vectors()
    medoids, labels, sims, best_quality, attempts = choose_best(x)
    write_outputs(rows, vector_positions, x, medoids, labels, sims, best_quality, attempts)


if __name__ == "__main__":
    main()
