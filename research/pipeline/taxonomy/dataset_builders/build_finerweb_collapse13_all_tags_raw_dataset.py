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

MAP_DIR = BASE / "derived_fasttext_categories" / "collapse13_seed_all_tags"
FULL_MAP = MAP_DIR / "collapse13_seed_all_tags_map.tsv"
FULL_SUMMARY = MAP_DIR / "collapse13_seed_all_tags_summary.tsv"

OUTPUT_BY_LANG = DATASETS / "finerweb_collapse13_all_tags_raw_by_language"
OUTPUT_COMBINED = DATASETS / "finerweb_collapse13_all_tags_raw"
ZIP_BY_LANG = OUTPUT_BY_LANG.with_suffix(".zip")
ZIP_COMBINED = OUTPUT_COMBINED.with_suffix(".zip")

SPLITS = ("train", "dev", "test", "all")
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

FINAL_LABELS = {
    "ACTIVITY_PROCESS",
    "BIO_CHEM_MEDICAL",
    "CONCEPT",
    "DATE_TIME",
    "EVENT",
    "GROUP",
    "LANGUAGE",
    "MANMADE_OBJECT",
    "ORGANIZATION",
    "PERSON",
    "PLACE",
    "TITLE_ROLE",
    "VALUE",
}


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
    return sorted(spans, key=lambda item: (int(item["start"]), int(item["end"]), str(item["label"])))


def best_span_for_token(token_start: int, token_end: int, spans: list[dict[str, object]]) -> tuple[int | None, int]:
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


def load_full_maps() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    coarse_map: dict[str, dict[str, str]] = {}
    exact_map: dict[str, dict[str, str]] = {}
    cultural_child_map: dict[str, dict[str, str]] = {}
    with FULL_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["status"] == "no_vector" or not row["label"]:
                continue
            if row["label"] not in FINAL_LABELS:
                raise ValueError(f"Unexpected final label {row['label']!r}")
            item = {
                "retained_label": row["label"],
                "map_status": row["status"],
                "source_kind": row["source_kind"],
                "map_tag": row["coarse_tag"],
                "map_source_labels": row["source_labels"],
            }
            tag_key = builder.norm_label(row["coarse_tag"])
            if row["source_kind"] == "cultural_child_orphan":
                cultural_child_map[tag_key] = item
                for source in row["source_labels"].split("; "):
                    exact_map[builder.norm_label(source)] = item
            else:
                coarse_map[tag_key] = item
                exact_map[builder.norm_label(row["source_labels"])] = item
    return coarse_map, exact_map, cultural_child_map


def build_original_label_maps(
    coarse_map: dict[str, dict[str, str]],
    exact_map: dict[str, dict[str, str]],
    cultural_child_map: dict[str, dict[str, str]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    label_map: dict[str, dict[str, str]] = {}
    lookup_map: dict[str, dict[str, str]] = {}
    with builder.LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            original_norm = builder.norm_label(original)
            coarse, fine = builder.split_original_label(original)

            mapped = None
            assignment_source = ""
            if original_norm in exact_map:
                mapped = exact_map[original_norm]
                assignment_source = f"exact_{mapped['source_kind']}"
            elif coarse == "cultural reference" and fine:
                mapped = cultural_child_map.get(fine)
                assignment_source = "masked_cultural_child" if mapped else ""
            else:
                mapped = coarse_map.get(coarse)
                assignment_source = f"coarse_{mapped['source_kind']}" if mapped else ""

            bucket = mapped["retained_label"] if mapped else ""
            item = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": bucket,
                "status": "retained" if bucket else "dropped",
                "assignment_source": assignment_source or "unmapped",
                "map_tag": mapped["map_tag"] if mapped else "",
                "map_source_kind": mapped["source_kind"] if mapped else "",
            }
            label_map[original] = item
            lookup_map[original] = item
            lookup_map[original_norm] = item
    return label_map, lookup_map


def map_original_bio(original_bio: str, label_map: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    if original_bio == "O":
        return "O", {
            "coarse_label": "_",
            "fine_label": "_",
            "retained_label": "_",
            "mapping_status": "outside",
            "assignment_source": "_",
            "map_tag": "_",
            "map_source_kind": "_",
        }

    prefix, original_label = builder.parse_bio(original_bio)
    mapped = label_map.get(original_label)
    if mapped is None:
        mapped = label_map.get(builder.norm_label(original_label))
    if mapped is None:
        coarse, fine = builder.split_original_label(original_label)
        return "O", {
            "coarse_label": coarse,
            "fine_label": fine,
            "retained_label": "_",
            "mapping_status": "missing_original_label",
            "assignment_source": "missing_original_label",
            "map_tag": "_",
            "map_source_kind": "_",
        }

    bucket = mapped["retained_label"]
    if not bucket:
        return "O", {
            "coarse_label": mapped["coarse_label"],
            "fine_label": mapped["fine_label"],
            "retained_label": "_",
            "mapping_status": "dropped_unmapped_or_unvectorized",
            "assignment_source": mapped["assignment_source"],
            "map_tag": mapped["map_tag"],
            "map_source_kind": mapped["map_source_kind"],
        }
    return f"{prefix}-{bucket}", {
        "coarse_label": mapped["coarse_label"],
        "fine_label": mapped["fine_label"],
        "retained_label": bucket,
        "mapping_status": "retained",
        "assignment_source": mapped["assignment_source"],
        "map_tag": mapped["map_tag"],
        "map_source_kind": mapped["map_source_kind"],
    }


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

        slim_bio, mapped = map_original_bio(original_bio, label_map)
        if not builder.LABEL_RE.match(slim_bio):
            raise ValueError(f"Bad generated BIO label {slim_bio!r}")
        rows.append(
            {
                "token": output_token(lang, token),
                "original_bio": original_bio,
                "coarse_label": mapped["coarse_label"],
                "fine_label": mapped["fine_label"],
                "retained_label": mapped["retained_label"],
                "mapping_status": mapped["mapping_status"],
                "assignment_source": mapped["assignment_source"],
                "map_tag": mapped["map_tag"],
                "map_source_kind": mapped["map_source_kind"],
                "slim_bio": slim_bio,
                "transition_fixed": "no",
            }
        )
    return rows


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
        map_tags = []
        seen = set()
        for row in span_rows:
            map_tag = row.get("map_tag", "")
            if map_tag and map_tag != "_" and map_tag not in seen:
                seen.add(map_tag)
                map_tags.append(map_tag)
        misc = "MapTag=" + ",".join(tag.replace(" ", "_").replace("/", "-") for tag in map_tags) if map_tags else "_"
        span_handle.write(f"{idx}\t{span_text}\t_\t{bucket}\t{original_tags}\t_\t0\t_\t_\t{misc}\n")
    span_handle.write("\n")


def write_sentence(rows: list[dict[str, str]], bio_handle, conllu_handle, span_handle, side_writer) -> None:
    for idx, row in enumerate(rows, start=1):
        bio_handle.write(f"{row['token']}\t{row['slim_bio']}\n")
        conllu_handle.write(f"{idx}\t{row['token']}\t_\t_\t_\t_\t0\t_\t_\tNER={row['slim_bio']}\n")
        side_writer.writerow(
            [
                row["token"],
                row["original_bio"],
                row["coarse_label"],
                row["fine_label"],
                row["retained_label"],
                row["mapping_status"],
                row["assignment_source"],
                row["map_tag"],
                row["map_source_kind"],
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
        "assignment_source_counts": Counter(),
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
            report["original_label_counts"][(original_label, row["coarse_label"], retained_label)] += 1
            report["retained_coarse_counts"][(row["coarse_label"], retained_label)] += 1
            report["assignment_source_counts"][row["assignment_source"]] += 1
        elif status == "missing_original_label":
            report["missing_spans"] += 1
            report["dropped_coarse_counts"][(row["coarse_label"], status)] += 1
        else:
            report["dropped_spans"] += 1
            report["dropped_coarse_counts"][(row["coarse_label"], status)] += 1

    if not any(row["slim_bio"] != "O" for row in sentence):
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
    with bio_path.open("w", encoding="utf-8", newline="") as bio_handle, conllu_path.open(
        "w", encoding="utf-8", newline=""
    ) as conllu_handle, span_path.open("w", encoding="utf-8", newline="") as span_handle, side_path.open(
        "w", encoding="utf-8", newline=""
    ) as side_handle:
        side_writer = csv.writer(side_handle, delimiter="\t", lineterminator="\n")
        side_writer.writerow(
            [
                "token",
                "original_bio",
                "coarse_label",
                "fine_label",
                "retained_label",
                "mapping_status",
                "assignment_source",
                "map_tag",
                "map_source_kind",
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


def write_language_reports(lang_dir: Path, lang: str, split_reports: dict[str, dict[str, object]]) -> dict[str, object]:
    report = builder.write_language_reports(lang_dir, lang, split_reports)
    for split, split_report in split_reports.items():
        report["splits"][split]["overlap_conflict_tokens"] = split_report["overlap_conflict_tokens"]
        report["splits"][split]["assignment_source_counts"] = dict(split_report["assignment_source_counts"])
    (lang_dir / "dataset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if lang == "san":
        (lang_dir / "iast_conversion_report.json").write_text(
            json.dumps({"method": "tokenwise indic_transliteration DEVANAGARI to IAST"}, ensure_ascii=False, indent=2),
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
            split_reports[split] = write_split(rows, lang, out_lang_dir, split, bounds[split], label_map)
        lang_reports[lang] = write_language_reports(out_lang_dir, lang, split_reports)
    return lang_reports


def configure_builder() -> None:
    builder.DATASET_NAME = "finerweb_collapse13_all_tags_raw"
    builder.DATASET_DISPLAY_NAME = "collapse13_all_tags_raw"
    builder.DATASET_DESCRIPTION = (
        "Raw fiNERweb parquet character spans are projected to BIO, then mapped through the full-coverage "
        "13-label collapse. Every vectorized coarse/masked-cultural tag is assigned to one of the 13 labels; "
        "unvectorized labels are dropped, and sentences with no retained labels are omitted."
    )
    builder.SOURCE_ROOT = RAW_ROOT
    builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    builder.ZIP_BY_LANG = ZIP_BY_LANG
    builder.ZIP_COMBINED = ZIP_COMBINED
    builder.RETAINED_MAP = FULL_MAP
    builder.REGION_LABELS = {label: label for label in FINAL_LABELS}


def main() -> None:
    configure_builder()
    coarse_map, exact_map, cultural_child_map = load_full_maps()
    original_label_map, lookup_label_map = build_original_label_maps(coarse_map, exact_map, cultural_child_map)

    builder.guarded_remove_tree(OUTPUT_BY_LANG)
    builder.guarded_remove_tree(OUTPUT_COMBINED)
    OUTPUT_BY_LANG.mkdir(parents=True, exist_ok=True)

    lang_reports = build_by_language(lookup_label_map)
    langs = sorted(lang_reports)
    builder.build_combined_files(langs)
    builder.write_root_reports(langs, lang_reports, {key: value["retained_label"] for key, value in coarse_map.items()}, original_label_map)
    shutil.copy2(FULL_MAP, OUTPUT_BY_LANG / FULL_MAP.name)
    shutil.copy2(FULL_SUMMARY, OUTPUT_BY_LANG / FULL_SUMMARY.name)
    shutil.copy2(FULL_MAP, OUTPUT_COMBINED / FULL_MAP.name)
    shutil.copy2(FULL_SUMMARY, OUTPUT_COMBINED / FULL_SUMMARY.name)

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
    (OUTPUT_BY_LANG / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_COMBINED / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
