import csv
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import MiniBatchKMeans


BASE = Path(__file__).resolve().parent
INVENTORY = BASE / "finerweb_label_inventory.tsv"
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
OUTPUT_DIR = BASE / "derived_fasttext_categories"
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k50_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k50_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k50.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k50.json"

VECTOR_GROUPS = 50
RANDOM_STATES = (3, 7, 13, 19, 29)
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
    "about",
    "related",
    "type",
    "types",
    "category",
    "categories",
    "entity",
    "entities",
    "item",
    "items",
    "misc",
    "other",
    "reference",
    "references",
}


def strip_accents(text):
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def norm_text(text):
    text = strip_accents((text or "").strip().lower())
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def text_tokens(text):
    return [tok for tok in TOKEN_RE.findall(norm_text(text)) if tok not in STOPWORDS and len(tok) > 1]


def variants(token):
    yielded = {token}
    yield token
    if token.endswith("ies") and len(token) > 4:
        candidate = token[:-3] + "y"
        if candidate not in yielded:
            yielded.add(candidate)
            yield candidate
    if token.endswith("es") and len(token) > 3:
        candidate = token[:-2]
        if candidate not in yielded:
            yielded.add(candidate)
            yield candidate
    if token.endswith("s") and len(token) > 3:
        candidate = token[:-1]
        if candidate not in yielded:
            yield candidate


def load_rows():
    rows = []
    with INVENTORY.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            label = row["original_label"]
            rows.append(
                {
                    "original_label": label,
                    "tokens": text_tokens(label),
                }
            )
    return rows


def collect_needed_words(rows):
    needed = set()
    for row in rows:
        for token in row["tokens"]:
            needed.update(variants(token))
    return needed


def load_fasttext(needed):
    needed_bytes = {word.encode("utf-8") for word in needed}
    vectors = {}
    with zipfile.ZipFile(FASTTEXT_ZIP, "r") as zf:
        vec_name = next(name for name in zf.namelist() if name.endswith(".vec"))
        with zf.open(vec_name, "r") as f:
            f.readline()
            for line in f:
                word, _, rest = line.partition(b" ")
                if word not in needed_bytes:
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm:
                    vectors[word.decode("utf-8")] = arr / norm
    return vectors


def token_vector(token, vectors):
    for candidate in variants(token):
        vec = vectors.get(candidate)
        if vec is not None:
            return candidate, vec
    return "", None


def row_vector(row, vectors):
    found = []
    matched = []
    for token in row["tokens"]:
        word, vec = token_vector(token, vectors)
        if vec is not None:
            found.append(vec)
            matched.append(word)
    if not found:
        return None, matched
    vec = np.mean(found, axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return None, matched
    return vec / norm, matched


def normalized_centers(model):
    centers = model.cluster_centers_.astype(np.float32)
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def fit_once(x, random_state):
    model = MiniBatchKMeans(
        n_clusters=VECTOR_GROUPS,
        random_state=random_state,
        batch_size=4096,
        n_init=8,
        max_iter=350,
        reassignment_ratio=0.0,
    )
    labels = model.fit_predict(x)
    centers = normalized_centers(model)
    sims = np.sum(x * centers[labels], axis=1)
    return labels, centers, sims


def choose_best_fit(x):
    attempts = []
    best = None
    for random_state in RANDOM_STATES:
        labels, centers, sims = fit_once(x, random_state)
        score = float(np.mean(sims))
        sizes = Counter(labels)
        attempt = {
            "random_state": random_state,
            "mean_centroid_similarity": score,
            "median_centroid_similarity": float(np.median(sims)),
            "p10_centroid_similarity": float(np.percentile(sims, 10)),
            "min_cluster_size": min(sizes.values()),
            "max_cluster_size": max(sizes.values()),
        }
        attempts.append(attempt)
        if best is None or score > best[0]:
            best = (score, labels, centers, sims, random_state)
    return best[1], best[2], best[3], best[4], attempts


def pairwise_mean_sample(x, max_items=1500):
    if len(x) < 2:
        return 1.0
    if len(x) > max_items:
        rng = np.random.default_rng(31)
        idx = rng.choice(len(x), size=max_items, replace=False)
        x = x[idx]
    sims = []
    for start in range(0, len(x), 256):
        block = x[start:start + 256]
        sim = block @ x.T
        for i in range(sim.shape[0]):
            global_i = start + i
            sims.extend(sim[i, global_i + 1:].tolist())
    return float(np.mean(np.array(sims, dtype=np.float32))) if sims else 1.0


def category_name(group_rows, center, vectors, used):
    support = Counter()
    for row in group_rows:
        for word in row["matched_tokens"]:
            if word in STOPWORDS:
                continue
            support[word] += 1
    candidates = []
    for word, count in support.items():
        vec = vectors.get(word)
        if vec is None:
            continue
        cosine = float(np.dot(center, vec))
        score = cosine + 0.035 * math.log1p(count)
        candidates.append((score, cosine, count, word))
    candidates.sort(reverse=True)
    chosen = ""
    for _score, _cosine, _count, word in candidates:
        if word not in used:
            chosen = word
            break
    if not chosen and candidates:
        chosen = candidates[0][3]
    if not chosen:
        chosen = "group"
    used.add(chosen)
    return chosen, candidates[:12]


def write_outputs(rows, vector_positions, x, labels, centers, sims, best_state, attempts, vectors):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pos_to_cluster = {pos: int(label) for pos, label in zip(vector_positions, labels)}
    pos_to_sim = {pos: float(sim) for pos, sim in zip(vector_positions, sims)}
    pos_to_x = {pos: idx for idx, pos in enumerate(vector_positions)}
    clusters = defaultdict(list)
    for pos, cluster in pos_to_cluster.items():
        clusters[cluster].append(pos)

    used_names = set()
    summaries = []
    for cluster, positions in clusters.items():
        center = centers[cluster]
        group_rows = [rows[pos] for pos in positions]
        name, top_words = category_name(group_rows, center, vectors, used_names)
        local_x = x[[pos_to_x[pos] for pos in positions]]
        nearest = sorted(positions, key=lambda pos: pos_to_sim[pos], reverse=True)[:16]
        sample = sorted(positions, key=lambda pos: rows[pos]["original_label"])[:16]
        summaries.append(
            {
                "raw_cluster": cluster,
                "category_word": name,
                "tag_count": len(positions),
                "mean_centroid_similarity": float(np.mean([pos_to_sim[pos] for pos in positions])),
                "mean_pairwise_similarity_sample": pairwise_mean_sample(local_x),
                "top_words": [
                    {
                        "word": word,
                        "score": round(score, 4),
                        "cosine": round(cosine, 4),
                        "support": count,
                    }
                    for score, cosine, count, word in top_words
                ],
                "nearest_tags": [
                    {
                        "tag": rows[pos]["original_label"],
                        "similarity": round(pos_to_sim[pos], 4),
                    }
                    for pos in nearest
                ],
                "sample_tags": [
                    {
                        "tag": rows[pos]["original_label"],
                    }
                    for pos in sample
                ],
            }
        )

    summaries.sort(key=lambda item: (-item["tag_count"], item["category_word"]))
    raw_to_group = {}
    for idx, summary in enumerate(summaries, start=1):
        summary["group_id"] = f"K{idx:02d}"
        raw_to_group[summary["raw_cluster"]] = summary["group_id"]

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "category_word",
                "tag_count",
                "mean_centroid_similarity_pct",
                "mean_pairwise_similarity_sample_pct",
                "top_words",
                "nearest_tags",
                "sample_tags",
            ]
        )
        for summary in summaries:
            writer.writerow(
                [
                    summary["group_id"],
                    summary["category_word"],
                    summary["tag_count"],
                    f"{summary['mean_centroid_similarity'] * 100:.2f}",
                    f"{summary['mean_pairwise_similarity_sample'] * 100:.2f}",
                    ", ".join(item["word"] for item in summary["top_words"][:10]),
                    " | ".join(item["tag"] for item in summary["nearest_tags"][:10]),
                    " | ".join(item["tag"] for item in summary["sample_tags"][:10]),
                ]
            )

    summary_by_raw = {summary["raw_cluster"]: summary for summary in summaries}
    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "group_id",
                "category_word",
                "original_label",
                "vector_tokens",
                "centroid_similarity_pct",
            ]
        )
        for pos, row in enumerate(rows):
            if pos not in pos_to_cluster:
                writer.writerow(
                    [
                        "UNVECTORIZED",
                        "unvectorized",
                        row["original_label"],
                        "",
                        "",
                    ]
                )
                continue
            cluster = pos_to_cluster[pos]
            summary = summary_by_raw[cluster]
            writer.writerow(
                [
                    raw_to_group[cluster],
                    summary["category_word"],
                    row["original_label"],
                    " ".join(row["matched_tokens"]),
                    f"{pos_to_sim[pos] * 100:.2f}",
                ]
            )

    report = {
        "source": str(INVENTORY.relative_to(BASE)),
        "source_column": "original_label",
        "ignored_columns": ["count", "bucket"],
        "labels_total": len(rows),
        "vectorized_labels": len(vector_positions),
        "unvectorized_labels": len(rows) - len(vector_positions),
        "vector_groups": VECTOR_GROUPS,
        "best_random_state": best_state,
        "attempts": attempts,
        "overall_mean_centroid_similarity": float(np.mean(sims)),
        "overall_median_centroid_similarity": float(np.median(sims)),
        "overall_p10_centroid_similarity": float(np.percentile(sims, 10)),
        "groups": summaries,
    }
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# All fiNERweb Labels: FastText Similarity-Max K50\n\n")
        f.write(f"- Source: `{INVENTORY.relative_to(BASE)}` column `original_label`\n")
        f.write("- Ignored source columns: `count`, `bucket`\n")
        f.write(f"- Labels total: {len(rows)}\n")
        f.write(f"- Vectorized labels: {len(vector_positions)}\n")
        f.write(f"- Unvectorized labels: {len(rows) - len(vector_positions)}\n")
        f.write(f"- Vector groups: {VECTOR_GROUPS}\n")
        f.write(f"- Best random state: {best_state}\n")
        f.write(f"- Overall mean centroid similarity: {np.mean(sims) * 100:.2f}%\n\n")
        f.write("## Attempts\n\n")
        f.write("| random_state | mean | median | p10 | min size | max size |\n")
        f.write("|---:|---:|---:|---:|---:|---:|\n")
        for attempt in attempts:
            f.write(
                f"| {attempt['random_state']} | {attempt['mean_centroid_similarity'] * 100:.2f}% | "
                f"{attempt['median_centroid_similarity'] * 100:.2f}% | "
                f"{attempt['p10_centroid_similarity'] * 100:.2f}% | "
                f"{attempt['min_cluster_size']} | {attempt['max_cluster_size']} |\n"
            )
        f.write("\n## Groups\n\n")
        for summary in summaries:
            f.write(
                f"### {summary['group_id']} `{summary['category_word']}` "
                f"({summary['tag_count']} tags, centroid {summary['mean_centroid_similarity'] * 100:.2f}%)\n\n"
            )
            f.write("Top words: " + ", ".join(item["word"] for item in summary["top_words"][:10]) + "\n\n")
            f.write("Nearest tags: " + "; ".join(item["tag"] for item in summary["nearest_tags"][:8]) + "\n\n")
            f.write("Sample tags: " + "; ".join(item["tag"] for item in summary["sample_tags"][:8]) + "\n\n")


def main():
    rows = load_rows()
    vectors = load_fasttext(collect_needed_words(rows))
    vector_positions = []
    vecs = []
    for pos, row in enumerate(rows):
        vec, matched = row_vector(row, vectors)
        row["matched_tokens"] = matched
        if vec is None:
            continue
        vector_positions.append(pos)
        vecs.append(vec)
    x = np.vstack(vecs).astype(np.float32)
    labels, centers, sims, best_state, attempts = choose_best_fit(x)
    write_outputs(rows, vector_positions, x, labels, centers, sims, best_state, attempts, vectors)


if __name__ == "__main__":
    main()
