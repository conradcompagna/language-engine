from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import cluster_all_finerweb_labels_fasttext as ft


BASE_DIR = Path(__file__).resolve().parent
IN_FINE = BASE_DIR / "finerweb_label_inventory.tsv"
IN_COARSE = BASE_DIR / "finerweb_label_inventory_coarse.tsv"
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
SUMMARY_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_report.md"

TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)
FUNCTION_STOPWORDS = {
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
}

MANUAL_REGIONS = {
    "person": ["person", "religious figure", "character"],
    "location": ["location", "country", "city", "region", "infrastructure", "continent", "building", "province"],
    "organization": [
        "organization",
        "political party",
        "government organization",
        "political organization",
        "educational institution",
        "sports team",
        "news agency",
        "government agency",
        "political entity",
        "company",
        "state",
        "government",
    ],
    "time": ["time", "date", "time period", "year", "duration", "day of the week", "month"],
    "cultural reference": ["cultural reference"],
    "quantity": ["quantity", "measurement", "percentage", "age", "statistic", "monetary value", "score", "number"],
    "event": ["event"],
    "product": ["product", "technology", "brand", "financial product"],
    "concept": [
        "concept",
        "scientific concept",
        "legal concept",
        "economic concept",
        "cultural concept",
        "financial concept",
        "philosophical concept",
        "political concept",
    ],
    "media": ["media", "social media platform", "website", "platform"],
    "title": [
        "title",
        "profession",
        "position",
        "occupation",
        "job title",
        "political position",
        "award",
        "role",
        "government position",
    ],
    "deity": ["deity"],
    "currency": ["currency", "cryptocurrency", "financial instrument"],
    "language": ["language"],
    "group": ["group", "nationality", "ethnic group", "demographic group", "social group"],
    "work of art": ["work of art", "film", "literary work", "video game"],
    "document": ["document", "legal document"],
    "program": ["program", "service", "activity", "field of study", "industry", "sport", "game"],
    "medical condition": ["medical condition", "disease", "body part", "animal"],
    "material": ["material", "food"],
}


def strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def text_tokens(text: str) -> list[str]:
    text = (text or "").lower().replace("_", " ").replace("/", " ")
    return [tok for tok in TOKEN_RE.findall(text) if tok not in FUNCTION_STOPWORDS]


def vector_variants(token: str):
    seen = set()
    for base in (token, strip_accents(token)):
        if not base:
            continue
        for candidate in ft.variants(base):
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def token_vector(token: str, vectors: dict[str, np.ndarray]):
    for candidate in vector_variants(token):
        vec = vectors.get(candidate)
        if vec is not None:
            return candidate, vec
    return "", None


def split_original_label(label: str) -> tuple[str, str]:
    if "/" not in label:
        stripped = label.strip()
        return stripped, stripped
    coarse, fine = label.split("/", 1)
    return coarse.strip(), fine.strip()


def label_vector(item: dict[str, object], vectors: dict[str, np.ndarray]) -> tuple[np.ndarray | None, list[str]]:
    found = []
    matched = []
    for token in item["tokens"]:
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
    return (vec / norm).astype(np.float32), matched


def pooled_vector(items: list[dict[str, object]], vectors: dict[str, np.ndarray]):
    found = []
    weights = []
    matched_tokens: Counter[str] = Counter()
    vectorized_count = 0
    vectorized_mentions = 0

    for item in items:
        vec, matched = label_vector(item, vectors)
        if vec is None:
            continue
        count = int(item["count"])
        found.append(vec)
        weights.append(float(count))
        vectorized_count += 1
        vectorized_mentions += count
        for word in matched:
            matched_tokens[word] += count

    if not found:
        return None, vectorized_count, vectorized_mentions, ""

    pooled = np.average(np.stack(found).astype(np.float32), axis=0, weights=np.array(weights, dtype=np.float64))
    norm = np.linalg.norm(pooled)
    if not norm:
        return None, vectorized_count, vectorized_mentions, ""
    top_matched = "; ".join(f"{word} ({count})" for word, count in matched_tokens.most_common(20))
    return (pooled / norm).astype(np.float32), vectorized_count, vectorized_mentions, top_matched


def load_label_sets() -> dict[str, list[dict[str, object]]]:
    csv.field_size_limit(2**31 - 1)
    label_sets: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    with IN_FINE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"].strip()
            coarse, _fine = split_original_label(original)
            label_sets[coarse].append(
                {
                    "original_label": original,
                    "count": int(row["count"]),
                    "tokens": text_tokens(original),
                }
            )
    return label_sets


def load_rows(label_sets: dict[str, list[dict[str, object]]]) -> tuple[list[dict[str, object]], int]:
    csv.field_size_limit(2**31 - 1)
    rows = []
    with IN_COARSE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["total_count"])
            tag = row["coarse_label"]
            rows.append(
                {
                    "coarse_tag": tag,
                    "count": count,
                    "original_labels": label_sets.get(tag, []),
                }
            )
    total_count = sum(int(row["count"]) for row in rows)
    for row in rows:
        row["percent"] = int(row["count"]) / total_count * 100.0
    rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    return rows, total_count


def collect_needed_words(label_sets: dict[str, list[dict[str, object]]]) -> set[str]:
    needed = set()
    for items in label_sets.values():
        for item in items:
            for token in item["tokens"]:
                needed.update(vector_variants(token))
    return needed


def seed_lookup() -> dict[str, str]:
    lookup = {}
    for region, seeds in MANUAL_REGIONS.items():
        for seed in seeds:
            lookup[seed] = region
    return lookup


def build_region_vectors(label_sets: dict[str, list[dict[str, object]]], vectors: dict[str, np.ndarray]):
    region_vectors = {}
    region_evidence = {}
    missing = {}

    for region, seeds in MANUAL_REGIONS.items():
        items = []
        missing_seeds = []
        for seed in seeds:
            seed_items = label_sets.get(seed, [])
            if not seed_items:
                missing_seeds.append(seed)
            items.extend(seed_items)
        vec, vectorized_count, vectorized_mentions, matched = pooled_vector(items, vectors)
        if vec is None:
            raise RuntimeError(f"No vectorized original-label evidence for region {region!r}")
        region_vectors[region] = vec
        region_evidence[region] = {
            "original_label_count": len(items),
            "vectorized_original_label_count": vectorized_count,
            "vectorized_original_label_mentions": vectorized_mentions,
            "matched_words": matched,
        }
        if missing_seeds:
            missing[region] = missing_seeds
    return region_vectors, region_evidence, missing


def associated_words(rows: list[dict[str, object]], limit: int = 24) -> str:
    counts: Counter[str] = Counter()
    for row in rows:
        for item in row["original_labels"]:
            count = int(item["count"])
            for token in item["tokens"]:
                counts[token] += count
    return "; ".join(f"{word} ({count})" for word, count in counts.most_common(limit))


def assign_rows(rows: list[dict[str, object]], region_vectors: dict[str, np.ndarray]) -> None:
    seeds = seed_lookup()
    regions = list(MANUAL_REGIONS)
    matrix = np.stack([region_vectors[region] for region in regions]).astype(np.float32)

    for row in rows:
        vec = row.get("vector")
        if vec is None:
            seed_region = seeds.get(str(row["coarse_tag"]))
            row["assigned_region"] = seed_region or "NO_VECTOR"
            row["assignment_source"] = "manual_seed_no_vector" if seed_region else "no_vector"
            row["similarity"] = ""
            row["runner_up_region"] = ""
            row["runner_up_similarity"] = ""
            row["margin"] = ""
            continue

        sims = matrix @ vec
        order = np.argsort(-sims)
        best_region = regions[int(order[0])]
        best_similarity = float(sims[int(order[0])])
        runner_region = regions[int(order[1])]
        runner_similarity = float(sims[int(order[1])])

        seed_region = seeds.get(str(row["coarse_tag"]))
        if seed_region:
            assigned_region = seed_region
            assigned_similarity = float(np.dot(region_vectors[seed_region], vec))
            row["assignment_source"] = "manual_seed"
        else:
            assigned_region = best_region
            assigned_similarity = best_similarity
            row["assignment_source"] = "nearest_region"

        row["assigned_region"] = assigned_region
        row["similarity"] = assigned_similarity
        row["runner_up_region"] = runner_region
        row["runner_up_similarity"] = runner_similarity
        row["margin"] = assigned_similarity - runner_similarity


def format_top_tags(rows: list[dict[str, object]], limit: int = 50) -> str:
    pieces = []
    for row in rows[:limit]:
        if row["similarity"] == "":
            pieces.append(f"{row['coarse_tag']} ({row['percent']:.4f}%, {row['assignment_source']})")
        else:
            pieces.append(
                f"{row['coarse_tag']} ({row['percent']:.4f}%, sim={float(row['similarity']) * 100:.2f}%, "
                f"{row['assignment_source']})"
            )
    return "; ".join(pieces)


def write_outputs(
    rows: list[dict[str, object]],
    total_count: int,
    region_evidence: dict[str, dict[str, object]],
    missing: dict[str, list[str]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_region: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_region[str(row["assigned_region"])].append(row)

    summaries = []
    for region in MANUAL_REGIONS:
        region_rows = sorted(by_region.get(region, []), key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
        sims = [float(row["similarity"]) for row in region_rows if row["similarity"] != ""]
        weights = [float(row["percent"]) for row in region_rows if row["similarity"] != ""]
        mention_count = sum(int(row["count"]) for row in region_rows)
        summaries.append(
            {
                "region": region,
                "rows": region_rows,
                "tag_count": len(region_rows),
                "mention_count": mention_count,
                "percent": mention_count / total_count * 100.0,
                "weighted_mean_similarity": float(np.average(sims, weights=weights)) if sims else 0.0,
                "p10_similarity": float(np.percentile(sims, 10)) if sims else 0.0,
                "min_similarity": float(np.min(sims)) if sims else 0.0,
                "associated_words": associated_words(region_rows),
            }
        )
    summaries.sort(key=lambda item: (-item["percent"], item["region"]))

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "region",
                "grouped_seed_tags",
                "region_seed_original_label_count",
                "region_seed_vectorized_original_label_count",
                "assigned_tag_count",
                "mention_count",
                "percent_of_total",
                "weighted_mean_similarity_pct",
                "p10_similarity_pct",
                "min_similarity_pct",
                "top_associated_words_from_assigned_whole_original_tags",
                "top_assigned_tags",
            ]
        )
        for summary in summaries:
            evidence = region_evidence[summary["region"]]
            writer.writerow(
                [
                    summary["region"],
                    "; ".join(MANUAL_REGIONS[summary["region"]]),
                    evidence["original_label_count"],
                    evidence["vectorized_original_label_count"],
                    summary["tag_count"],
                    summary["mention_count"],
                    f"{summary['percent']:.6f}",
                    f"{summary['weighted_mean_similarity'] * 100:.2f}",
                    f"{summary['p10_similarity'] * 100:.2f}",
                    f"{summary['min_similarity'] * 100:.2f}",
                    summary["associated_words"],
                    format_top_tags(summary["rows"], 60),
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "count",
                "percent_of_total",
                "original_label_count",
                "vectorized_original_label_count",
                "vectorized_original_label_mentions",
                "assigned_region",
                "assignment_source",
                "similarity_to_region_pct",
                "runner_up_region",
                "runner_up_similarity_pct",
                "margin_pct",
                "top_matched_words_in_own_original_tags",
            ]
        )
        for row in rows:
            if row["similarity"] == "":
                writer.writerow(
                    [
                        row["coarse_tag"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        len(row["original_labels"]),
                        row.get("vectorized_original_label_count", 0),
                        row.get("vectorized_original_label_mentions", 0),
                        row["assigned_region"],
                        row["assignment_source"],
                        "",
                        "",
                        "",
                        "",
                        row.get("matched_words", ""),
                    ]
                )
            else:
                writer.writerow(
                    [
                        row["coarse_tag"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        len(row["original_labels"]),
                        row["vectorized_original_label_count"],
                        row["vectorized_original_label_mentions"],
                        row["assigned_region"],
                        row["assignment_source"],
                        f"{float(row['similarity']) * 100:.2f}",
                        row["runner_up_region"],
                        f"{float(row['runner_up_similarity']) * 100:.2f}",
                        f"{float(row['margin']) * 100:.2f}",
                        row["matched_words"],
                    ]
                )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Manual Full Original-Label Region Assignment\n\n")
        handle.write(
            "Manual grouped seed regions are anchors. Region vectors use the actual original-label rows under "
            "the grouped seed coarse tags, including standalone labels like `politician` and full slash labels "
            "like `location / township` vectorized as `location township`. Manual region titles are not separately "
            "injected. Each remaining coarse tag is represented by the same full original-label centroid and "
            "assigned to the nearest manual region by cosine similarity. Seed coarse tags are forced to their "
            "specified region.\n\n"
        )
        handle.write(f"- Total coarse tags: {len(rows)}\n")
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Manual regions: {len(MANUAL_REGIONS)}\n")
        handle.write(f"- No-vector tags: {len(by_region.get('NO_VECTOR', []))}\n")
        if missing:
            handle.write("- Seed tags without original-label rows: ")
            handle.write("; ".join(f"{region}: {', '.join(tags)}" for region, tags in missing.items()))
            handle.write("\n")
        handle.write("\n## Region Summaries\n\n")
        for summary in summaries:
            evidence = region_evidence[summary["region"]]
            handle.write(f"### {summary['region']}\n\n")
            handle.write(f"Grouped seeds: {', '.join(f'`{tag}`' for tag in MANUAL_REGIONS[summary['region']])}\n\n")
            handle.write(
                f"Region seed evidence: {evidence['vectorized_original_label_count']} vectorized original labels "
                f"from {evidence['original_label_count']} original labels.\n\n"
            )
            handle.write(
                f"Assigned tags: {summary['tag_count']}; coverage: {summary['percent']:.4f}% "
                f"({summary['mention_count']} mentions)\n\n"
            )
            handle.write(
                f"Similarity: weighted mean {summary['weighted_mean_similarity'] * 100:.2f}%, "
                f"p10 {summary['p10_similarity'] * 100:.2f}%, min {summary['min_similarity'] * 100:.2f}%\n\n"
            )
            handle.write(f"Top associated words: {summary['associated_words']}\n\n")
            handle.write("Top assigned coarse tags:\n")
            for row in summary["rows"][:45]:
                if row["similarity"] == "":
                    handle.write(f"- `{row['coarse_tag']}`: {row['percent']:.4f}%, {row['assignment_source']}\n")
                else:
                    handle.write(
                        f"- `{row['coarse_tag']}`: {row['percent']:.4f}%, "
                        f"sim={float(row['similarity']) * 100:.2f}%, {row['assignment_source']}\n"
                    )
            handle.write("\n")


def main() -> None:
    label_sets = load_label_sets()
    rows, total_count = load_rows(label_sets)
    vectors = ft.load_fasttext(collect_needed_words(label_sets))

    for row in rows:
        vec, vectorized_count, vectorized_mentions, matched = pooled_vector(row["original_labels"], vectors)
        row["vector"] = vec
        row["vectorized_original_label_count"] = vectorized_count
        row["vectorized_original_label_mentions"] = vectorized_mentions
        row["matched_words"] = matched

    region_vectors, region_evidence, missing = build_region_vectors(label_sets, vectors)
    assign_rows(rows, region_vectors)
    write_outputs(rows, total_count, region_evidence, missing)

    assigned = Counter(str(row["assigned_region"]) for row in rows)
    print(f"total={total_count}")
    print(f"tags={len(rows)}")
    print(f"regions={len(MANUAL_REGIONS)}")
    print(f"no_vector={assigned.get('NO_VECTOR', 0)}")
    print(f"wrote={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")
    for region, count in assigned.most_common():
        print(f"{region}\t{count}")


if __name__ == "__main__":
    main()
