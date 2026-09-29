import csv
from pathlib import Path

import numpy as np
from sklearn.cluster import MiniBatchKMeans

from compute_user_category_similarity import (
    BASE,
    OUT as _SIMILARITY_OUT,
    collect_needed_words,
    load_fasttext,
    parse_categories,
    phrase_vector,
    split_items,
)


OUTPUT_DIR = BASE / "derived_fasttext_categories"
ASSIGNMENTS_OUT = OUTPUT_DIR / "user_labels_balanced_fasttext_groups.tsv"
SUMMARY_OUT = OUTPUT_DIR / "user_labels_balanced_fasttext_groups_summary.tsv"
K = 23
RANDOM_STATE = 19


def load_unique_labels():
    seen = set()
    labels = []
    source_categories = {}
    categories = parse_categories()
    for category, text in categories.items():
        for label in split_items(text):
            key = " ".join(label.strip().lower().split())
            if not key:
                continue
            source_categories.setdefault(key, []).append(category)
            if key in seen:
                continue
            seen.add(key)
            labels.append(label.strip())
    return labels, source_categories, categories


def normalize_rows(labels, source_categories, vectors):
    rows = []
    vecs = []
    for label in labels:
        vec, matched = phrase_vector(label, vectors)
        key = " ".join(label.strip().lower().split())
        row = {
            "label": label,
            "label_key": key,
            "source_categories": ",".join(source_categories.get(key, [])),
            "vector_tokens": " ".join(matched),
            "vectorized": vec is not None,
        }
        if vec is not None:
            row["vector_index"] = len(vecs)
            vecs.append(vec)
        else:
            row["vector_index"] = None
        rows.append(row)
    return rows, np.vstack(vecs).astype(np.float32)


def normalized_centers_from_labels(x, labels, k):
    centers = np.zeros((k, x.shape[1]), dtype=np.float32)
    for cluster in range(k):
        idx = np.where(labels == cluster)[0]
        if len(idx):
            center = np.mean(x[idx], axis=0)
            norm = np.linalg.norm(center)
            if norm:
                centers[cluster] = center / norm
    return centers


def balanced_assign(x, centers):
    n = x.shape[0]
    k = centers.shape[0]
    base = n // k
    extra = n % k
    capacities = np.array([base + (1 if cluster < extra else 0) for cluster in range(k)], dtype=np.int32)
    sims = x @ centers.T
    order = np.argsort(-sims.max(axis=1))
    labels = np.full(n, -1, dtype=np.int32)
    for idx in order:
        ranked_clusters = np.argsort(-sims[idx])
        for cluster in ranked_clusters:
            if capacities[cluster] > 0:
                labels[idx] = cluster
                capacities[cluster] -= 1
                break
    return labels


def balanced_kmeans(x, k):
    seed_model = MiniBatchKMeans(
        n_clusters=k,
        random_state=RANDOM_STATE,
        batch_size=2048,
        n_init=20,
        max_iter=300,
    )
    initial = seed_model.fit_predict(x)
    centers = normalized_centers_from_labels(x, initial, k)
    labels = balanced_assign(x, centers)
    for _ in range(12):
        centers = normalized_centers_from_labels(x, labels, k)
        new_labels = balanced_assign(x, centers)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
    centers = normalized_centers_from_labels(x, labels, k)
    sims = np.sum(x * centers[labels], axis=1)
    return labels, centers, sims


def group_name(group_rows, center, vectors):
    scored = []
    seen = set()
    for row in group_rows:
        for word in row["vector_tokens"].split():
            if word in seen:
                continue
            seen.add(word)
            vec = vectors.get(word)
            if vec is not None:
                scored.append((float(np.dot(center, vec)), word))
    scored.sort(reverse=True)
    return scored[0][1] if scored else group_rows[0]["label"]


def pairwise_mean(x):
    if len(x) < 2:
        return 1.0
    sims = []
    for i in range(len(x)):
        sims.extend((x[i] @ x[i + 1:].T).tolist())
    return float(np.mean(sims)) if sims else 1.0


def write_outputs(rows, x, labels, centers, sims, vectors):
    vector_rows = [row for row in rows if row["vectorized"]]
    for row, label, sim in zip(vector_rows, labels, sims):
        row["group_raw"] = int(label)
        row["similarity"] = float(sim)

    raw_groups = {}
    for cluster in range(K):
        group_rows = [row for row in vector_rows if row["group_raw"] == cluster]
        raw_groups[cluster] = group_rows

    summaries = []
    for cluster, group_rows in raw_groups.items():
        group_x = x[[row["vector_index"] for row in group_rows]]
        name = group_name(group_rows, centers[cluster], vectors)
        representative = sorted(group_rows, key=lambda row: row["similarity"], reverse=True)[:12]
        summaries.append(
            {
                "raw": cluster,
                "name": name,
                "size": len(group_rows),
                "mean_centroid_similarity": float(np.mean([row["similarity"] for row in group_rows])),
                "mean_pairwise_similarity": pairwise_mean(group_x),
                "representative": representative,
            }
        )
    summaries.sort(key=lambda item: (-item["size"], item["name"]))
    raw_to_public = {}
    for idx, summary in enumerate(summaries, start=1):
        summary["group_id"] = f"G{idx:02d}"
        raw_to_public[summary["raw"]] = summary["group_id"]

    summary_by_id = {summary["group_id"]: summary for summary in summaries}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "group_name",
                "size",
                "mean_centroid_similarity_pct",
                "mean_pairwise_similarity_pct",
                "representative_labels",
            ]
        )
        for summary in summaries:
            writer.writerow(
                [
                    summary["group_id"],
                    summary["name"],
                    summary["size"],
                    f"{summary['mean_centroid_similarity'] * 100:.2f}",
                    f"{summary['mean_pairwise_similarity'] * 100:.2f}",
                    " | ".join(row["label"] for row in summary["representative"]),
                ]
            )

    with ASSIGNMENTS_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "group_name",
                "label",
                "source_categories",
                "vector_tokens",
                "centroid_similarity_pct",
            ]
        )
        for row in rows:
            if not row["vectorized"]:
                writer.writerow(["UNVECTORIZED", "unvectorized", row["label"], row["source_categories"], "", ""])
                continue
            group_id = raw_to_public[row["group_raw"]]
            writer.writerow(
                [
                    group_id,
                    summary_by_id[group_id]["name"],
                    row["label"],
                    row["source_categories"],
                    row["vector_tokens"],
                    f"{row['similarity'] * 100:.2f}",
                ]
            )


def main():
    labels, source_categories, categories = load_unique_labels()
    vectors = load_fasttext(collect_needed_words(categories))
    rows, x = normalize_rows(labels, source_categories, vectors)
    labels_out, centers, sims = balanced_kmeans(x, K)
    write_outputs(rows, x, labels_out, centers, sims, vectors)


if __name__ == "__main__":
    main()
