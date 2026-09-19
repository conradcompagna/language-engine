from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import build_finerweb_final12_no_cultural_raw_dataset as raw_builder
import build_finerweb_slim75_dataset as generic_builder


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"

OUTPUT_BY_LANG = DATASETS / "finerweb_manual12_direct_raw_by_language"
OUTPUT_COMBINED = DATASETS / "finerweb_manual12_direct_raw"
ZIP_BY_LANG = OUTPUT_BY_LANG.with_suffix(".zip")
ZIP_COMBINED = OUTPUT_COMBINED.with_suffix(".zip")

DIRECT_MAP = BASE / "derived_fasttext_categories" / "manual12_direct_raw_map.tsv"
DIRECT_SUMMARY = BASE / "derived_fasttext_categories" / "manual12_direct_raw_summary.tsv"

LABEL_TO_TAGS = {
    "INDIVIDUAL": [
        "person",
        "deity",
        "god",
        "religious figure",
        "character",
        "mythological figure",
        "historical figure",
    ],
    "GROUP": [
        "nationality",
        "group",
        "group of people",
        "persons",
        "people",
        "ethnic group",
        "demographic group",
        "demographic",
        "social group",
        "religious group",
        "political group",
    ],
    "TITLE_ROLE": [
        "title",
        "profession",
        "position",
        "occupation",
        "job title",
        "political position",
        "role",
        "government position",
        "religious title",
        "academic degree",
    ],
    "ORGANIZATION": [
        "organization",
        "media",
        "media outlet",
        "media organization",
        "brand",
        "political party",
        "government organization",
        "political organization",
        "government agency",
        "government ministry",
        "government",
        "sports team",
        "sports league",
        "sports club",
        "football club",
        "educational institution",
        "university",
        "institution",
        "news agency",
        "news organization",
        "company",
        "military organization",
        "military unit",
        "religious organization",
        "international organization",
        "law enforcement agency",
        "court",
        "government body",
        "legislative body",
        "financial institution",
        "business type",
    ],
    "PLACE": [
        "location",
        "country",
        "city",
        "region",
        "geographic region",
        "geographical region",
        "political entity",
        "geopolitical entity",
        "geopolitical region",
        "state",
        "province",
        "district",
        "administrative region",
        "administrative division",
        "continent",
        "village",
        "place",
        "facility",
        "infrastructure",
        "building",
        "river",
        "geographical feature",
    ],
    "DATE_TIME": [
        "date",
        "time period",
        "historical period",
        "year",
        "time",
        "duration",
        "time duration",
        "day of the week",
        "day of week",
        "month",
    ],
    "QUANTITY": [
        "quantity",
        "measurement",
        "currency",
        "currency amount",
        "monetary value",
        "price",
        "percentage",
        "age",
        "statistic",
        "score",
        "number",
        "distance",
    ],
    "EVENT": [
        "event",
        "historical event",
        "cultural event",
        "festival",
        "sports event",
    ],
    "PRODUCT": [
        "product",
        "technology",
        "website",
        "film",
        "tv show",
        "song",
        "literary work",
        "video game",
        "publication",
        "social media platform",
        "platform",
        "operating system",
        "software",
        "application",
        "service",
        "financial instrument",
        "financial product",
        "cryptocurrency",
        "vehicle",
        "vehicle type",
        "weapon",
        "object",
        "food",
        "food product",
        "musical instrument",
        "ingredient",
        "drug",
        "agricultural product",
        "fruit",
        "product category",
    ],
    "BIO_CHEM_MEDICAL": [
        "medical condition",
        "disease",
        "chemical compound",
        "chemical substance",
        "material",
        "substance",
        "animal",
        "species",
        "plant",
        "biological entity",
        "body part",
        "anatomical structure",
        "virus",
    ],
    "CULTURAL_REFERENCE": [
        "cultural reference",
        "religious text",
        "religion",
        "religious concept",
        "work of art",
        "music genre",
        "art form",
    ],
    "CONCEPT": [
        "scientific concept",
        "concept",
        "abstract concept",
        "legal concept",
        "legal term",
        "economic concept",
        "economic sector",
        "cultural concept",
        "social issue",
        "social concept",
        "financial concept",
        "financial term",
        "financial market",
        "philosophical concept",
        "political concept",
        "political ideology",
        "academic discipline",
    ],
}

TAG_TO_LABEL = {
    generic_builder.norm_label(tag): label
    for label, tags in LABEL_TO_TAGS.items()
    for tag in tags
}
FINAL_LABELS = set(LABEL_TO_TAGS)


def build_original_label_maps() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    label_map: dict[str, dict[str, str]] = {}
    lookup_map: dict[str, dict[str, str]] = {}
    with generic_builder.LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            original_norm = generic_builder.norm_label(original)
            coarse, fine = generic_builder.split_original_label(original)
            retained = TAG_TO_LABEL.get(coarse, "")
            item = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": retained,
                "vector_region": retained or "_",
                "status": "retained" if retained else "dropped",
            }
            label_map[original] = item
            lookup_map[original] = item
            lookup_map[original_norm] = item
    return label_map, lookup_map


def write_direct_maps(original_label_map: dict[str, dict[str, str]]) -> None:
    DIRECT_MAP.parent.mkdir(parents=True, exist_ok=True)
    coarse_counts: Counter[tuple[str, str]] = Counter()
    label_counts: Counter[str] = Counter()
    dropped_counts: Counter[str] = Counter()

    for row in original_label_map.values():
        count = int(row["count"])
        if row["status"] == "retained":
            coarse_counts[(row["coarse_label"], row["retained_label"])] += count
            label_counts[row["retained_label"]] += count
        else:
            dropped_counts[row["coarse_label"]] += count

    with DIRECT_MAP.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["coarse_label", "retained_label", "count"])
        for (coarse, label), count in sorted(coarse_counts.items(), key=lambda item: (-item[1], item[0])):
            writer.writerow([coarse, label, count])

    total = sum(label_counts.values()) + sum(dropped_counts.values())
    with DIRECT_SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["label", "coarse_tags", "mentions", "pct_total"])
        for label, tags in sorted(LABEL_TO_TAGS.items()):
            count = label_counts[label]
            present_tags = sum(1 for tag in tags if (generic_builder.norm_label(tag), label) in coarse_counts)
            writer.writerow([label, present_tags, count, f"{count / total * 100.0:.6f}"])
        writer.writerow(["__TOTAL_RETAINED__", len(coarse_counts), sum(label_counts.values()), f"{sum(label_counts.values()) / total * 100.0:.6f}"])
        writer.writerow(["__TOTAL_DROPPED__", len(dropped_counts), sum(dropped_counts.values()), f"{sum(dropped_counts.values()) / total * 100.0:.6f}"])


def configure_builders() -> None:
    raw_builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    raw_builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    raw_builder.ZIP_BY_LANG = ZIP_BY_LANG
    raw_builder.ZIP_COMBINED = ZIP_COMBINED
    raw_builder.FINAL_LABELS = FINAL_LABELS

    generic_builder.DATASET_NAME = "finerweb_manual12_direct_raw"
    generic_builder.DATASET_DISPLAY_NAME = "manual12_direct_raw"
    generic_builder.DATASET_DESCRIPTION = (
        "Raw fiNERweb parquet character spans are projected to BIO, then mapped directly by exact coarse "
        "tag membership in the manually supplied 12-label tagset. No fastText/vector expansion is used. "
        "Tags outside the manual set are dropped, and sentences with no retained labels are omitted."
    )
    generic_builder.SOURCE_ROOT = raw_builder.RAW_ROOT
    generic_builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    generic_builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    generic_builder.ZIP_BY_LANG = ZIP_BY_LANG
    generic_builder.ZIP_COMBINED = ZIP_COMBINED
    generic_builder.RETAINED_MAP = DIRECT_MAP
    generic_builder.REGION_LABELS = {label: label for label in FINAL_LABELS}


def main() -> None:
    configure_builders()
    original_label_map, lookup_label_map = build_original_label_maps()
    write_direct_maps(original_label_map)

    generic_builder.guarded_remove_tree(OUTPUT_BY_LANG)
    generic_builder.guarded_remove_tree(OUTPUT_COMBINED)
    OUTPUT_BY_LANG.mkdir(parents=True, exist_ok=True)

    lang_reports = raw_builder.build_by_language(lookup_label_map)
    langs = sorted(lang_reports)
    generic_builder.build_combined_files(langs)
    generic_builder.write_root_reports(langs, lang_reports, TAG_TO_LABEL, original_label_map)

    for root in (OUTPUT_BY_LANG, OUTPUT_COMBINED):
        shutil.copy2(DIRECT_MAP, root / DIRECT_MAP.name)
        shutil.copy2(DIRECT_SUMMARY, root / DIRECT_SUMMARY.name)

    health_by_lang = generic_builder.validate_tree(OUTPUT_BY_LANG, by_language=True)
    health_combined = generic_builder.validate_tree(OUTPUT_COMBINED, by_language=False)
    zip_by_lang = generic_builder.make_zip(OUTPUT_BY_LANG, ZIP_BY_LANG)
    zip_combined = generic_builder.make_zip(OUTPUT_COMBINED, ZIP_COMBINED)

    summary = {
        "by_language": str(OUTPUT_BY_LANG),
        "combined": str(OUTPUT_COMBINED),
        "manual_map": str(DIRECT_MAP),
        "manual_summary": str(DIRECT_SUMMARY),
        "health_by_language": health_by_lang,
        "health_combined": health_combined,
        "zip_by_language": zip_by_lang,
        "zip_combined": zip_combined,
    }
    (OUTPUT_BY_LANG / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_COMBINED / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
