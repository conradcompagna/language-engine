from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import pandas as pd
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

import build_finerweb_slim75_dataset as builder


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
RAW_ROOT = BASE.parent / "nerdump" / "fiNERweb_app_languages"
READY_SPLIT_ROOT = DATASETS / "finerweb_plo75_by_language_ready"
ASSIGNMENT_MAP = (
    BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_bucket_tag_map.tsv"
)
FINAL_TAG_MAP = (
    BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_final12_raw_tag_map.tsv"
)
FINAL_SUMMARY = (
    BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_final12_raw_summary.tsv"
)

OUTPUT_BY_LANG = DATASETS / "finerweb_final12_no_cultural_raw_by_language"
OUTPUT_COMBINED = DATASETS / "finerweb_final12_no_cultural_raw"
ZIP_BY_LANG = OUTPUT_BY_LANG.with_suffix(".zip")
ZIP_COMBINED = OUTPUT_COMBINED.with_suffix(".zip")

SPLITS = ("train", "dev", "test", "all")
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

REGION_TO_FINAL = {
    "person | deity | religious figure | character": "PERSON",
    "location | country | city | region": "LOCATION",
    "organization | media | political/government/sports/web": "ORGANIZATION",
    "concept | science | medical/legal/economic": "CONCEPT",
    "product | technology | brand | food": "PRODUCT",
    "date | time period | year | duration": "TIME",
    "quantity | measurement | currency | percentage": "QUANTITY",
    "event": "EVENT",
    "title | profession | position": "TITLE",
    "work of art | film": "WORK_OF_ART",
    "nationality | group | ethnic/demographic": "GROUP",
    "legal document | document": "MISC",
    "language": "MISC",
    "animal": "MISC",
    "material": "MISC",
    "industry": "MISC",
    "program": "MISC",
    "award": "MISC",
    "sport": "MISC",
    "UNVECTORIZED": "MISC",
}

FINAL_LABELS = {
    "LOCATION",
    "PERSON",
    "ORGANIZATION",
    "CONCEPT",
    "PRODUCT",
    "TIME",
    "QUANTITY",
    "EVENT",
    "TITLE",
    "WORK_OF_ART",
    "GROUP",
    "MISC",
}


def final_label_for_region(region: str) -> str:
    label = REGION_TO_FINAL.get(region)
    if label is None:
        raise ValueError(f"Unexpected vector region {region!r}")
    return label


def load_assignment_rows() -> list[dict[str, str]]:
    with ASSIGNMENT_MAP.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_final_vector_sheets(rows: list[dict[str, str]]) -> None:
    with FINAL_TAG_MAP.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "row_id",
            "display_tag",
            "source_label",
            "source_kind",
            "count",
            "pct_total",
            "vector_region",
            "final_label",
            "assignment_source",
            "similarity_pct",
            "runner_up_region",
            "runner_up_similarity_pct",
            "margin_pct",
        ]
        writer = csv.DictWriter(handle, delimiter="\t", lineterminator="\n", fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "row_id": row["row_id"],
                    "display_tag": row["display_tag"],
                    "source_label": row["source_label"],
                    "source_kind": row["source_kind"],
                    "count": row["count"],
                    "pct_total": row["pct_total"],
                    "vector_region": row["assigned_region"],
                    "final_label": final_label_for_region(row["assigned_region"]),
                    "assignment_source": row["assignment_source"],
                    "similarity_pct": row["similarity_pct"],
                    "runner_up_region": row["runner_up_region"],
                    "runner_up_similarity_pct": row["runner_up_similarity_pct"],
                    "margin_pct": row["margin_pct"],
                }
            )

    summary: dict[str, dict[str, object]] = {}
    for row in rows:
        final_label = final_label_for_region(row["assigned_region"])
        item = summary.setdefault(final_label, {"rows": 0, "mentions": 0, "regions": Counter()})
        item["rows"] = int(item["rows"]) + 1
        item["mentions"] = int(item["mentions"]) + int(row["count"])
        item["regions"][row["assigned_region"]] += int(row["count"])

    total = sum(int(item["mentions"]) for item in summary.values())
    with FINAL_SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["final_label", "candidate_rows", "mentions", "pct_total", "source_vector_regions"]
        )
        for label, item in sorted(summary.items(), key=lambda kv: (-int(kv[1]["mentions"]), kv[0])):
            regions = "; ".join(
                f"{region} ({count})" for region, count in item["regions"].most_common()
            )
            writer.writerow(
                [
                    label,
                    item["rows"],
                    item["mentions"],
                    f"{int(item['mentions']) / total * 100:.6f}",
                    regions,
                ]
            )


def load_vector_maps() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    rows = load_assignment_rows()
    write_final_vector_sheets(rows)

    coarse_to_label: dict[str, str] = {}
    exact_to_label: dict[str, str] = {}
    coarse_to_region: dict[str, str] = {}
    exact_to_region: dict[str, str] = {}
    for row in rows:
        region = row["assigned_region"]
        final_label = final_label_for_region(region)
        source_label = builder.norm_label(row["source_label"])
        if row["source_kind"] == "coarse":
            coarse = builder.norm_label(row["display_tag"])
            coarse_to_label[coarse] = final_label
            coarse_to_region[coarse] = region
        else:
            exact_to_label[source_label] = final_label
            exact_to_region[source_label] = region
    return coarse_to_label, exact_to_label, coarse_to_region, exact_to_region


def build_original_label_maps(
    coarse_to_label: dict[str, str],
    exact_to_label: dict[str, str],
    coarse_to_region: dict[str, str],
    exact_to_region: dict[str, str],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    label_map: dict[str, dict[str, str]] = {}
    lookup_map: dict[str, dict[str, str]] = {}
    with builder.LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            original_norm = builder.norm_label(original)
            coarse, fine = builder.split_original_label(original)
            if original_norm in exact_to_label:
                bucket = exact_to_label[original_norm]
                vector_region = exact_to_region[original_norm]
                status = "retained"
            else:
                bucket = coarse_to_label.get(coarse)
                vector_region = coarse_to_region.get(coarse, "")
                status = "retained" if bucket else "dropped"
            item = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": bucket or "",
                "vector_region": vector_region,
                "status": status if bucket else "dropped",
            }
            label_map[original] = item
            lookup_map[original] = item
            lookup_map[original_norm] = item
    return label_map, lookup_map


def raw_files() -> list[Path]:
    return sorted(RAW_ROOT.glob("*.parquet"))


def lang_from_raw_file(path: Path) -> str:
    return path.name.split("-", 1)[0]


def load_split_bounds(lang: str, total_rows: int) -> dict[str, tuple[int, int]]:
    summary_path = READY_SPLIT_ROOT / lang / "split_summary.tsv"
    if summary_path.exists():
        counts = {}
        with summary_path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["split"] != "all":
                    counts[row["split"]] = int(row["source_sentences"])
        train_n = counts.get("train", int(total_rows * 0.8))
        dev_n = counts.get("dev", int(total_rows * 0.1))
        test_n = counts.get("test", total_rows - train_n - dev_n)
    else:
        train_n = int(total_rows * 0.8)
        dev_n = int(total_rows * 0.1)
        test_n = total_rows - train_n - dev_n

    train_end = min(train_n, total_rows)
    dev_end = min(train_end + dev_n, total_rows)
    test_end = min(dev_end + test_n, total_rows)
    return {
        "train": (0, train_end),
        "dev": (train_end, dev_end),
        "test": (dev_end, test_end),
        "all": (0, total_rows),
    }


def tokenize_with_offsets(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in TOKEN_RE.finditer(text or "")]


def normalize_span(span: object) -> dict[str, object] | None:
    if not isinstance(span, dict):
        try:
            span = dict(span)
        except Exception:
            return None
    try:
        start = int(span["start"])
        end = int(span["end"])
        label = str(span["label"])
    except Exception:
        return None
    if start >= end or not label:
        return None
    return {"start": start, "end": end, "label": label}


def sentence_spans(raw_spans: object) -> list[dict[str, object]]:
    if raw_spans is None:
        return []
    spans = []
    for span in list(raw_spans):
        normalized = normalize_span(span)
        if normalized is not None:
            spans.append(normalized)
    return sorted(
        spans, key=lambda item: (int(item["start"]), int(item["end"]), str(item["label"]))
    )


def best_span_for_token(
    token_start: int,
    token_end: int,
    spans: list[dict[str, object]],
) -> tuple[int | None, int]:
    best_idx = None
    best_overlap = 0
    overlap_count = 0
    for idx, span in enumerate(spans):
        start = int(span["start"])
        end = int(span["end"])
        overlap = min(token_end, end) - max(token_start, start)
        if overlap <= 0:
            continue
        overlap_count += 1
        if overlap > best_overlap:
            best_idx = idx
            best_overlap = overlap
    return best_idx, overlap_count


def output_token(lang: str, token: str) -> str:
    if lang != "san":
        return token
    return transliterate(token, sanscript.DEVANAGARI, sanscript.IAST)


def map_original_bio(
    original_bio: str, label_map: dict[str, dict[str, str]]
) -> tuple[str, str, str, str, str]:
    if original_bio == "O":
        return "O", "_", "_", "outside", "_"

    prefix, original_label = builder.parse_bio(original_bio)
    mapped = label_map.get(original_label)
    if mapped is None:
        mapped = label_map.get(builder.norm_label(original_label))
    if mapped is None:
        coarse, _fine = builder.split_original_label(original_label)
        return "O", coarse, "_", "missing_original_label", "_"

    bucket = mapped["retained_label"]
    if not bucket:
        return (
            "O",
            mapped["coarse_label"],
            "_",
            "dropped_unretained_coarse",
            mapped.get("vector_region", "_"),
        )
    return (
        f"{prefix}-{bucket}",
        mapped["coarse_label"],
        bucket,
        "retained",
        mapped.get("vector_region", "_"),
    )


def build_sentence_rows(
    lang: str,
    text: str,
    raw_spans: object,
    label_map: dict[str, dict[str, str]],
    stats: Counter,
) -> list[dict[str, str]]:
    spans = sentence_spans(raw_spans)
    tokens = tokenize_with_offsets(text)
    rows = []
    previous_span_idx = None
    for token, start, end in tokens:
        span_idx, overlap_count = best_span_for_token(start, end, spans)
        if overlap_count > 1:
            stats["overlap_conflict_tokens"] += 1
        if span_idx is None:
            original_bio = "O"
            previous_span_idx = None
        else:
            prefix = "I" if previous_span_idx == span_idx else "B"
            original_bio = f"{prefix}-{spans[span_idx]['label']}"
            previous_span_idx = span_idx

        slim_bio, coarse_label, retained_label, status, vector_region = map_original_bio(
            original_bio, label_map
        )
        if not builder.LABEL_RE.match(slim_bio):
            raise ValueError(f"Bad generated BIO label {slim_bio!r}")
        rows.append(
            {
                "token": output_token(lang, token),
                "original_bio": original_bio,
                "coarse_label": coarse_label,
                "retained_label": retained_label,
                "vector_region": vector_region,
                "mapping_status": status,
                "slim_bio": slim_bio,
                "transition_fixed": "no",
            }
        )
    return rows


def sanitize_misc_value(value: str) -> str:
    value = value.replace(" | ", "|")
    value = re.sub(r"\s+", "_", value)
    value = value.replace("/", "-")
    value = value.replace(",", "_")
    value = value.replace(";", "_")
    return value or "_"


def span_misc_origin(bucket: str, rows: list[dict[str, str]]) -> str:
    if bucket != "MISC":
        return "_"
    origins = []
    seen = set()
    for row in rows:
        if row["original_bio"] == "O":
            continue
        origin = row.get("vector_region", "_")
        if not origin or origin == "_":
            continue
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    if not origins:
        return "_"
    return "MiscOrigin=" + ",".join(sanitize_misc_value(origin) for origin in origins)


def write_span_sentence(rows: list[dict[str, str]], span_handle) -> None:
    spans = []
    current = []
    current_bucket = ""

    def flush_span() -> None:
        nonlocal current, current_bucket
        if current:
            spans.append((current_bucket, current))
        current = []
        current_bucket = ""

    for row in rows:
        bio = row["slim_bio"]
        if bio == "O":
            flush_span()
            continue
        prefix, bucket = bio.split("-", 1)
        if prefix == "B" or current_bucket != bucket:
            flush_span()
            current = [row]
            current_bucket = bucket
        else:
            current.append(row)
    flush_span()

    for idx, (bucket, span_rows) in enumerate(spans, start=1):
        span_text = " ".join(row["token"] for row in span_rows)
        original_tags = builder.span_original_tags(span_rows)
        misc_origin = span_misc_origin(bucket, span_rows)
        span_handle.write(
            f"{idx}\t{span_text}\t_\t{bucket}\t{original_tags}\t_\t0\t_\t_\t{misc_origin}\n"
        )
    span_handle.write("\n")


def write_sentence(
    rows: list[dict[str, str]],
    bio_handle,
    conllu_handle,
    span_handle,
    side_writer,
) -> None:
    for idx, row in enumerate(rows, start=1):
        bio_handle.write(f"{row['token']}\t{row['slim_bio']}\n")
        conllu_handle.write(f"{idx}\t{row['token']}\t_\t_\t_\t_\t0\t_\t_\tNER={row['slim_bio']}\n")
        side_writer.writerow(
            [
                row["token"],
                row["original_bio"],
                row["coarse_label"],
                row["retained_label"],
                row["mapping_status"],
                row["slim_bio"],
            ]
        )
    bio_handle.write("\n")
    conllu_handle.write("\n")
    write_span_sentence(rows, span_handle)
    side_writer.writerow([])


def report_template() -> dict[str, object]:
    return {
        "source_sentences": 0,
        "written_sentences": 0,
        "dropped_empty_sentences": 0,
        "source_tokens": 0,
        "written_tokens": 0,
        "source_spans": 0,
        "retained_spans": 0,
        "dropped_spans": 0,
        "missing_spans": 0,
        "transition_fixes": 0,
        "overlap_conflict_tokens": 0,
        "label_token_counts": Counter(),
        "label_span_counts": Counter(),
        "original_label_counts": Counter(),
        "dropped_coarse_counts": Counter(),
        "retained_coarse_counts": Counter(),
    }


def update_report_from_sentence(report: dict[str, object], sentence: list[dict[str, str]]) -> None:
    report["source_sentences"] += 1
    report["source_tokens"] += len(sentence)
    builder.normalize_sentence_bio(sentence)
    report["transition_fixes"] += sum(1 for row in sentence if row["transition_fixed"] == "yes")

    for row in sentence:
        original_bio = row["original_bio"]
        status = row["mapping_status"]
        retained_label = row["retained_label"]
        if row["slim_bio"] != "O":
            report["label_token_counts"][retained_label] += 1
        if original_bio == "O":
            continue
        prefix, original_label = builder.parse_bio(original_bio)
        if prefix != "B":
            continue
        report["source_spans"] += 1
        if status == "retained":
            report["retained_spans"] += 1
            report["label_span_counts"][retained_label] += 1
            report["original_label_counts"][
                (original_label, row["coarse_label"], retained_label)
            ] += 1
            report["retained_coarse_counts"][(row["coarse_label"], retained_label)] += 1
        elif status == "missing_original_label":
            report["missing_spans"] += 1
            report["dropped_coarse_counts"][(row["coarse_label"], status)] += 1
        else:
            report["dropped_spans"] += 1
            report["dropped_coarse_counts"][(row["coarse_label"], status)] += 1

    has_retained = any(row["slim_bio"] != "O" for row in sentence)
    if not has_retained:
        report["dropped_empty_sentences"] += 1
        return

    report["written_sentences"] += 1
    report["written_tokens"] += len(sentence)


def write_split(
    rows,
    lang: str,
    out_lang_dir: Path,
    split: str,
    bounds: tuple[int, int],
    label_map: dict[str, dict[str, str]],
) -> dict[str, object]:
    report = report_template()
    stats = Counter()
    start, end = bounds
    bio_path = out_lang_dir / f"{split}.bio"
    conllu_path = out_lang_dir / f"{split}.conllu"
    span_path = out_lang_dir / f"{split}.ner_spans.conllu"
    side_path = out_lang_dir / f"{split}.original_vs_bucket.tsv"
    with (
        bio_path.open("w", encoding="utf-8", newline="") as bio_handle,
        conllu_path.open("w", encoding="utf-8", newline="") as conllu_handle,
        span_path.open("w", encoding="utf-8", newline="") as span_handle,
        side_path.open("w", encoding="utf-8", newline="") as side_handle,
    ):
        side_writer = csv.writer(side_handle, delimiter="\t", lineterminator="\n")
        side_writer.writerow(
            [
                "token",
                "original_bio",
                "coarse_label",
                "retained_label",
                "mapping_status",
                "slim_bio",
            ]
        )
        for row in rows[start:end]:
            sentence = build_sentence_rows(lang, row.text, row.char_spans, label_map, stats)
            update_report_from_sentence(report, sentence)
            if any(token_row["slim_bio"] != "O" for token_row in sentence):
                write_sentence(sentence, bio_handle, conllu_handle, span_handle, side_writer)
    report["overlap_conflict_tokens"] = stats["overlap_conflict_tokens"]
    return report


def write_language_reports(
    lang_dir: Path, lang: str, split_reports: dict[str, dict[str, object]]
) -> dict[str, object]:
    report = builder.write_language_reports(lang_dir, lang, split_reports)
    for split, split_report in split_reports.items():
        report["splits"][split]["overlap_conflict_tokens"] = split_report["overlap_conflict_tokens"]
    (lang_dir / "dataset_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if lang == "san":
        (lang_dir / "iast_conversion_report.json").write_text(
            json.dumps(
                {"method": "tokenwise indic_transliteration DEVANAGARI to IAST"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return report


def build_by_language(label_map: dict[str, dict[str, str]]) -> dict[str, dict[str, object]]:
    lang_reports = {}
    for raw_file in raw_files():
        lang = lang_from_raw_file(raw_file)
        print(f"building {lang} from {raw_file.name}", flush=True)
        df = pd.read_parquet(raw_file)
        bounds = load_split_bounds(lang, len(df))
        out_lang_dir = OUTPUT_BY_LANG / lang
        out_lang_dir.mkdir(parents=True, exist_ok=True)
        rows = list(df.itertuples(index=False))
        split_reports = {}
        for split in SPLITS:
            split_reports[split] = write_split(
                rows, lang, out_lang_dir, split, bounds[split], label_map
            )
        lang_reports[lang] = write_language_reports(out_lang_dir, lang, split_reports)
    return lang_reports


def configure_builder() -> None:
    builder.DATASET_NAME = "finerweb_final12_no_cultural_raw"
    builder.DATASET_DISPLAY_NAME = "final12_no_cultural_raw"
    builder.DATASET_DESCRIPTION = (
        "Raw fiNERweb parquet character spans are projected to BIO, then mapped through the full 50/50 "
        "parent-child FastText assignment. The `cultural reference` aggregate is not a vector seed bucket; "
        "its child labels are mapped by child text. Low singleton/vector buckets and legal-document/document "
        "are collapsed to MISC after vector assignment."
    )
    builder.SOURCE_ROOT = RAW_ROOT
    builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    builder.ZIP_BY_LANG = ZIP_BY_LANG
    builder.ZIP_COMBINED = ZIP_COMBINED
    builder.RETAINED_MAP = FINAL_TAG_MAP
    builder.REGION_LABELS = {label: label for label in FINAL_LABELS}


def main() -> None:
    configure_builder()
    coarse_to_label, exact_to_label, coarse_to_region, exact_to_region = load_vector_maps()
    original_label_map, lookup_label_map = build_original_label_maps(
        coarse_to_label,
        exact_to_label,
        coarse_to_region,
        exact_to_region,
    )

    builder.guarded_remove_tree(OUTPUT_BY_LANG)
    builder.guarded_remove_tree(OUTPUT_COMBINED)
    OUTPUT_BY_LANG.mkdir(parents=True, exist_ok=True)

    lang_reports = build_by_language(lookup_label_map)
    langs = sorted(lang_reports)
    builder.build_combined_files(langs)
    builder.write_root_reports(langs, lang_reports, coarse_to_label, original_label_map)
    shutil.copy2(FINAL_TAG_MAP, OUTPUT_BY_LANG / FINAL_TAG_MAP.name)
    shutil.copy2(FINAL_SUMMARY, OUTPUT_BY_LANG / FINAL_SUMMARY.name)
    shutil.copy2(FINAL_TAG_MAP, OUTPUT_COMBINED / FINAL_TAG_MAP.name)
    shutil.copy2(FINAL_SUMMARY, OUTPUT_COMBINED / FINAL_SUMMARY.name)

    health_by_lang = builder.validate_tree(OUTPUT_BY_LANG, by_language=True)
    health_combined = builder.validate_tree(OUTPUT_COMBINED, by_language=False)
    zip_by_lang = builder.make_zip(OUTPUT_BY_LANG, ZIP_BY_LANG)
    zip_combined = builder.make_zip(OUTPUT_COMBINED, ZIP_COMBINED)

    summary = {
        "by_language": str(OUTPUT_BY_LANG),
        "combined": str(OUTPUT_COMBINED),
        "health_by_language": health_by_lang,
        "health_combined": health_combined,
        "zip_by_language": zip_by_lang,
        "zip_combined": zip_combined,
    }
    (OUTPUT_BY_LANG / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_COMBINED / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
