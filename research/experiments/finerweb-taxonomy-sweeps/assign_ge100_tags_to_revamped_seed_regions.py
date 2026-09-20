from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import analyze_user_taxonomy_outliers_fasttext_parent_child_25 as pc25
import assign_coarse_tags_to_manual_full_label_child_regions as base


BASE = Path(__file__).resolve().parent
INVENTORY = BASE / "finerweb_label_inventory.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_TSV = OUT_DIR / "revamped_seed_regions_ge100_assignments.tsv"
OUT_MD = OUT_DIR / "revamped_seed_regions_ge100_report.md"

run = pc25.run

RAW_SEEDS = r"""
## Location / Spatial Entity

- location (39110)
- location / country (31286)
- location / city (23849)
- country (12518)
- city (5306)
- location / region (2905)
- location / province (2874)
- location / state (2083)
- region (1625)
- location / district (1236)
- location / village (1010)

## Individual Agent

- person (123246)
- person / football player (1548)
- person / politician (1536)
- person / actor (1223)
--
-----
- deity (2389)

## Organization / Collective Agent

- organization (39535)
- organization / company (3785)
- organization / sports club (3655)
- organization / government organization (3522)
- organization / political organization (2271)
- organization / football club (2167)
- political party (2114)
- government organization (1995)
- organization / government agency (1694)
- political organization (1535)
- organization / educational institution (1528)
- organization / sports team (1398)
- educational institution (1293)
- organization / political party (1242)
- organization / international organization (1188)
- organization / university (1184)
- organization / news agency (1103)
- news agency (1047)
- brand (1921)

## Time Expression

- date (31621)
- time period (8353)
- date / year (3656)
- year (3292)
- time (3278)
- duration (2895)
- day of the week (2393)
- month (1571)
- time period / duration (1048)

cultural reference

- cultural reference (15874)

## Abstract Concept / Mental-Social Construct

- concept (12658)
- scientific concept (9102)
- economic concept (1586)
- legal concept (1560)
- cultural concept (1184)
- financial concept (1089)
- philosophical concept (1016)

LANGUAGE

- language (3184)

## Measurement / Quantity Expression

- quantity (20583)
- measurement (2948)
- age (2443)
- percentage (2437)
- quantity / monetary value (2170)
- monetary value (1367)

## Event, Process, Action, Undertaking

- event (17186)

## Human-Made Artifact / Technology / Product

- product (13714)
- technology (6510)
- website (1692)
- social media platform (1366)

## Organic / Bodily / Natural-Material Entity

- disease (2975)
- medical condition (1908)
- scientific concept / disease (1333)
- animal (1214)
- medical condition / disease (1060)

----------------

- material (1224)

## Classifier / Category / Role / Status / Type

- title (3001)
- profession (2037)
- occupation (1634)
- job title (1457)
- political position (1405)
- position (1127)

----------

- award (1016)

-----

- field of study (1223)
- industry (1370)
- sport (1279)

## Creative Work

- media (1506)

## Money / Financial Asset / Economic Instrument

- currency (1647)

## Group Identity / Non-Institutional Human Collective

- nationality (2652)
- ethnic group (1614)
- group (1180)
- demographic group (1016)
"""

SEED_RE = re.compile(r"^-\s+(?P<tag>.+?)\s*\((?P<count>\d+)\)\s*$")
SEPARATOR_RE = re.compile(r"^-{2,}$")


def parse_seed_text() -> dict[str, list[str]]:
    current = ""
    seeds: dict[str, list[str]] = defaultdict(list)
    for raw_line in RAW_SEEDS.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = re.sub(r"^##\s+", "", line).strip()
            continue
        if SEPARATOR_RE.match(line):
            continue
        match = SEED_RE.match(line)
        if match:
            if not current:
                raise RuntimeError(f"Seed without bucket: {line}")
            seeds[current].append(match.group("tag").strip())
            continue
        current = line
    return dict(seeds)


def load_inventory_ge100() -> list[dict[str, object]]:
    rows = []
    with INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["count"])
            if count <= 100:
                continue
            rows.append({"tag": row["original_label"], "count": count})
    return rows


def vectorize(rows: list[dict[str, object]]) -> None:
    run.vectorize_rows(rows)


def build_seed_centroids(
    rows_by_tag: dict[str, dict[str, object]],
    seeds: dict[str, list[str]],
) -> tuple[dict[str, np.ndarray], dict[str, list[str]]]:
    centroids = {}
    missing: dict[str, list[str]] = defaultdict(list)
    for bucket, seed_tags in seeds.items():
        vecs = []
        weights = []
        for tag in seed_tags:
            row = rows_by_tag.get(tag)
            if row is None or row["vector"] is None:
                missing[bucket].append(tag)
                continue
            vecs.append(row["vector"])
            weights.append(float(row["count"]))
        if not vecs:
            raise RuntimeError(f"No vectorized seeds for {bucket}")
        centroid = np.average(np.stack(vecs).astype(np.float32), axis=0, weights=np.array(weights, dtype=np.float64))
        norm = np.linalg.norm(centroid)
        if not norm:
            raise RuntimeError(bucket)
        centroids[bucket] = (centroid / norm).astype(np.float32)
    return centroids, dict(missing)


def assign_rows(
    rows: list[dict[str, object]],
    centroids: dict[str, np.ndarray],
    seed_lookup: dict[str, str],
) -> None:
    buckets = list(centroids)
    matrix = np.stack([centroids[bucket] for bucket in buckets]).astype(np.float32)
    for row in rows:
        vec = row["vector"]
        if vec is None:
            row["assigned_bucket"] = "NO_VECTOR"
            row["assigned_similarity"] = ""
            continue
        forced_bucket = seed_lookup.get(str(row["tag"]))
        if forced_bucket:
            row["assigned_bucket"] = forced_bucket
            row["assigned_similarity"] = float(np.dot(centroids[forced_bucket], vec))
            continue
        sims = matrix @ vec
        best_idx = int(np.argmax(sims))
        row["assigned_bucket"] = buckets[best_idx]
        row["assigned_similarity"] = float(sims[best_idx])


def pct(value: object) -> str:
    if value == "":
        return ""
    return f"{float(value) * 100:.2f}"


def write_outputs(
    rows: list[dict[str, object]],
    seeds: dict[str, list[str]],
    missing: dict[str, list[str]],
) -> None:
    seed_lookup = {tag: bucket for bucket, tags in seeds.items() for tag in tags}
    by_bucket: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_bucket[str(row["assigned_bucket"])].append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "assigned_bucket",
                "type",
                "tag",
                "count",
                "similarity_pct",
                "vector_text",
                "matched_words",
            ]
        )
        for bucket in seeds:
            for row in sorted(by_bucket.get(bucket, []), key=lambda item: -int(item["count"])):
                writer.writerow(
                    [
                        bucket,
                        "seed" if row["tag"] in seed_lookup else "new",
                        row["tag"],
                        row["count"],
                        pct(row["assigned_similarity"]),
                        row["vector_text"],
                        row["matched_words"],
                    ]
                )
        for row in by_bucket.get("NO_VECTOR", []):
            writer.writerow(["NO_VECTOR", "new", row["tag"], row["count"], "", "", ""])

    total_count = sum(int(row["count"]) for row in rows)
    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Revamped Seed Region Assignment, Tags >100 Mentions\n\n")
        handle.write(
            "Seed regions come from the revamped list in the prompt. All labels in "
            "`finerweb_label_inventory.tsv` with count >100 are assigned to the nearest seed-region centroid. "
            "Slash labels use the current 25% parent / 75% child vector rule.\n\n"
        )
        handle.write(f"- Input tags >100: {len(rows)}\n")
        handle.write(f"- Input mention count: {total_count}\n")
        handle.write(f"- Seed buckets: {len(seeds)}\n")
        handle.write(f"- Seed tags: {sum(len(tags) for tags in seeds.values())}\n\n")
        if missing:
            handle.write("## Missing Seed Tags\n\n")
            for bucket, tags in missing.items():
                handle.write(f"- **{bucket}**: {', '.join(tags)}\n")
            handle.write("\n")

        for bucket, seed_tags in seeds.items():
            bucket_rows = sorted(by_bucket.get(bucket, []), key=lambda item: -int(item["count"]))
            seed_rows = [row for row in bucket_rows if row["tag"] in seed_lookup]
            new_rows = [row for row in bucket_rows if row["tag"] not in seed_lookup]
            bucket_count = sum(int(row["count"]) for row in bucket_rows)
            handle.write(f"## {bucket}\n\n")
            handle.write(f"{len(bucket_rows)} tags, {bucket_count} mentions\n\n")
            handle.write("### Seed tags\n\n")
            for row in seed_rows:
                handle.write(
                    f"- {row['tag']} ({row['count']}), sim {pct(row['assigned_similarity'])}%\n"
                )
            handle.write("\n### New tags included\n\n")
            for row in new_rows:
                handle.write(
                    f"- {row['tag']} ({row['count']}), sim {pct(row['assigned_similarity'])}%\n"
                )
            handle.write("\n")

        no_vector = by_bucket.get("NO_VECTOR", [])
        if no_vector:
            handle.write("## NO_VECTOR\n\n")
            for row in sorted(no_vector, key=lambda item: -int(item["count"])):
                handle.write(f"- {row['tag']} ({row['count']})\n")

    print(f"input_tags_gt100\t{len(rows)}")
    print(f"seed_buckets\t{len(seeds)}")
    print(f"seed_tags\t{sum(len(tags) for tags in seeds.values())}")
    print(f"tsv\t{OUT_TSV}")
    print(f"report\t{OUT_MD}")


def main() -> None:
    seeds = parse_seed_text()
    rows = load_inventory_ge100()
    vectorize(rows)
    rows_by_tag = {str(row["tag"]): row for row in rows}
    centroids, missing = build_seed_centroids(rows_by_tag, seeds)
    seed_lookup = {tag: bucket for bucket, tags in seeds.items() for tag in tags}
    assign_rows(rows, centroids, seed_lookup)
    write_outputs(rows, seeds, missing)


if __name__ == "__main__":
    main()
