from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import audit_cleaned_tag_grouping_text as audit


OUT_DIR = audit.OUT_DIR
OUT_MD = OUT_DIR / "cleaned_tag_grouping_ge100_corrected.md"
OUT_TSV = OUT_DIR / "cleaned_tag_grouping_ge100_corrected.tsv"

BUCKET_ORDER = [
    "Location / Spatial Entity",
    "Individual Agent",
    "Organization / Collective Agent",
    "Time Expression",
    "cultural reference (RELIGION)",
    "Abstract Concept / Mental-Social Construct",
    "LANGUAGE",
    "Measurement / Quantity Expression",
    "Event, Process, Action, Undertaking",
    "Human-Made Artifact / Technology / Product",
    "Organic / Bodily / Natural-Material Entity",
    "Classifier / Category / Role / Status / Type",
    "Creative Work",
    "Money / Financial Asset / Economic Instrument",
    "Group Identity / Non-Institutional Human Collective",
    "Law / Government / Policy",
    "Economy / Finance",
    "Science / Knowledge / Academic",
    "Identifier / Contact / Reference",
    "Action / Process",
    "cultural reference",
    "Other",
    "NO_VECTOR",
]

FORCED_BUCKETS = {
    "award": "Other",
    "clothing": "Human-Made Artifact / Technology / Product",
    "document type": "Law / Government / Policy",
    "event / award": "Event, Process, Action, Undertaking",
    "field of study": "Science / Knowledge / Academic",
    "financial institution": "Organization / Collective Agent",
    "philosophical school": "Science / Knowledge / Academic",
    "religion": "cultural reference (RELIGION)",
    "religious practice": "cultural reference (RELIGION)",
    "score": "Measurement / Quantity Expression",
    "sport": "Other",
    "statistics": "Measurement / Quantity Expression",
    "cultural reference": "cultural reference",
}

SOURCE_BUCKET_RENAMES = {
    "ART": "Creative Work",
}


def build_mapping() -> tuple[dict[str, str], dict[str, int]]:
    required = audit.load_required()
    occurrences, _ignored, _case_only = audit.parse(required)
    mapping: dict[str, str] = {}
    for item in occurrences:
        tag = str(item["tag"])
        if tag not in mapping:
            bucket = SOURCE_BUCKET_RENAMES.get(str(item["bucket"]), str(item["bucket"]))
            mapping[tag] = bucket

    for tag, bucket in FORCED_BUCKETS.items():
        if tag not in required:
            raise RuntimeError(f"Forced tag is not in required inventory: {tag}")
        mapping[tag] = bucket

    missing = sorted(set(required) - set(mapping))
    if missing:
        raise RuntimeError(f"Missing after forced placement: {missing}")
    return mapping, required


def write_outputs(mapping: dict[str, str], required: dict[str, int]) -> None:
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for tag, bucket in mapping.items():
        by_bucket[bucket].append(tag)

    for tags in by_bucket.values():
        tags.sort(key=lambda tag: (-required[tag], tag))
    unordered = sorted(set(by_bucket) - set(BUCKET_ORDER))
    if unordered:
        raise RuntimeError(f"Buckets missing from BUCKET_ORDER: {unordered}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Cleaned Tag Grouping Corrected\n\n")
        handle.write("All FinerWeb labels with count >100 are present exactly once.\n\n")
        for bucket in BUCKET_ORDER:
            tags = by_bucket.get(bucket, [])
            if not tags:
                continue
            handle.write(f"## {bucket}\n\n")
            for tag in tags:
                handle.write(f"- {tag}\n")
            handle.write("\n")

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["bucket", "tag", "count"])
        for bucket in BUCKET_ORDER:
            for tag in by_bucket.get(bucket, []):
                writer.writerow([bucket, tag, required[tag]])


def main() -> None:
    mapping, required = build_mapping()
    counts = defaultdict(int)
    for tag in mapping:
        counts[tag] += 1
    duplicates = [tag for tag, count in counts.items() if count > 1]
    missing = sorted(set(required) - set(mapping))
    extra = sorted(set(mapping) - set(required))
    if duplicates or missing or extra:
        raise RuntimeError({"duplicates": duplicates, "missing": missing, "extra": extra})
    write_outputs(mapping, required)
    print(f"required_gt100\t{len(required)}")
    print(f"mapped_unique\t{len(mapping)}")
    print(f"duplicates\t{len(duplicates)}")
    print(f"missing\t{len(missing)}")
    print(f"md\t{OUT_MD}")
    print(f"tsv\t{OUT_TSV}")


if __name__ == "__main__":
    main()
