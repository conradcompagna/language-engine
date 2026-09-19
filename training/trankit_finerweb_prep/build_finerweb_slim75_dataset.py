from __future__ import annotations

import csv
import json
import os
import re
import shutil
import stat
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
SOURCE_ROOT = DATASETS / "finerweb_bucketed_fasttext_by_language_sorted_boundaries"
OUTPUT_BY_LANG = DATASETS / "finerweb_slim75_by_language"
OUTPUT_COMBINED = DATASETS / "finerweb_slim75"
ZIP_BY_LANG = OUTPUT_BY_LANG.with_suffix(".zip")
ZIP_COMBINED = OUTPUT_COMBINED.with_suffix(".zip")

DATASET_NAME = "finerweb_slim75"
DATASET_DISPLAY_NAME = "slim75"
DATASET_DESCRIPTION = (
    "Original fiNERweb labels are reduced to their coarse tag, mapped through the retained map, "
    "and labels outside that map are dropped to `O`. Sentences with no retained entity labels are omitted."
)

RETAINED_MAP = BASE / "derived_fasttext_categories" / "finerweb_selected_manual_seed_regions_threshold75_retained_tag_map.tsv"
LABEL_INVENTORY = BASE / "finerweb_label_inventory.tsv"
SOURCE_FILES = BASE / "finerweb_source_files.tsv"
SPLITS = ("train", "dev", "test", "all")
LABEL_RE = re.compile(r"^(?:O|[BI]-[A-Z_]+)$")

REGION_LABELS = {
    "person": "PERSON",
    "location": "LOCATION",
    "organization": "ORGANIZATION",
    "product": "PRODUCT",
    "money": "MONEY",
    "time": "TIME",
    "event": "EVENT",
    "work of art": "WORK_OF_ART",
    "group": "GROUP",
    "language": "LANGUAGE",
    "quantity": "QUANTITY",
}


def guarded_remove_tree(path: Path) -> None:
    resolved = path.resolve()
    datasets_root = DATASETS.resolve()
    if not str(resolved).startswith(str(datasets_root) + os.sep):
        raise RuntimeError(f"Refusing to remove path outside datasets root: {resolved}")

    def onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=onexc)


def norm_label(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return text.strip()


def split_original_label(label: str) -> tuple[str, str]:
    label = norm_label(label)
    if " / " not in label:
        return label, ""
    coarse, fine = label.split(" / ", 1)
    return coarse.strip(), fine.strip()


def parse_bio(label: str) -> tuple[str, str]:
    if label == "O":
        return "O", ""
    prefix, original = label.split("-", 1)
    return prefix, original


def load_retained_coarse_map() -> dict[str, str]:
    retained = {}
    with RETAINED_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            region = row["retained_region"]
            bio_label = REGION_LABELS.get(region)
            if bio_label is None:
                raise ValueError(f"Unexpected retained region {region!r}")
            retained[norm_label(row["coarse_tag"])] = bio_label
    return retained


def build_original_label_map(retained_coarse: dict[str, str]) -> dict[str, dict[str, str]]:
    label_map = {}
    with LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            coarse, fine = split_original_label(original)
            bucket = retained_coarse.get(coarse)
            label_map[original] = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": bucket or "",
                "status": "retained" if bucket else "dropped",
            }
    return label_map


def map_original_bio(original_bio: str, label_map: dict[str, dict[str, str]]) -> tuple[str, str, str, str]:
    if original_bio == "O":
        return "O", "_", "_", "outside"

    prefix, original_label = parse_bio(original_bio)
    mapped = label_map.get(original_label)
    if mapped is None:
        mapped = label_map.get(norm_label(original_label))
    if mapped is None:
        coarse, _fine = split_original_label(original_label)
        return "O", coarse, "_", "missing_original_label"

    bucket = mapped["retained_label"]
    if not bucket:
        return "O", mapped["coarse_label"], "_", "dropped_unretained_coarse"
    return f"{prefix}-{bucket}", mapped["coarse_label"], bucket, "retained"


def normalize_sentence_bio(rows: list[dict[str, str]]) -> None:
    previous_bucket = ""
    for row in rows:
        bio = row["slim_bio"]
        if bio == "O":
            previous_bucket = ""
            continue
        prefix, bucket = bio.split("-", 1)
        if prefix == "I" and previous_bucket != bucket:
            row["slim_bio"] = f"B-{bucket}"
            row["transition_fixed"] = "yes"
        previous_bucket = bucket


def write_sentence(
    rows: list[dict[str, str]],
    bio_handle,
    conllu_handle,
    span_handle,
    side_writer,
) -> None:
    for idx, row in enumerate(rows, start=1):
        bio_handle.write(f"{row['token']}\t{row['slim_bio']}\n")
        conllu_handle.write(
            f"{idx}\t{row['token']}\t_\t_\t_\t_\t0\t_\t_\tNER={row['slim_bio']}\n"
        )
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


def span_original_tags(rows: list[dict[str, str]]) -> str:
    seen = set()
    tags = []
    for row in rows:
        original_bio = row["original_bio"]
        if original_bio == "O":
            continue
        _prefix, original_label = parse_bio(original_bio)
        if original_label not in seen:
            seen.add(original_label)
            tags.append(original_label)
    return " | ".join(tags) if tags else "_"


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
        original_tags = span_original_tags(span_rows)
        span_handle.write(f"{idx}\t{span_text}\t_\t{bucket}\t{original_tags}\t_\t0\t_\t_\t_\n")
    span_handle.write("\n")


def convert_split(
    src_file: Path,
    bio_out: Path,
    conllu_out: Path,
    span_out: Path,
    side_out: Path,
    label_map: dict[str, dict[str, str]],
) -> dict[str, object]:
    source_sentences = 0
    written_sentences = 0
    source_tokens = 0
    written_tokens = 0
    source_spans = 0
    retained_spans = 0
    dropped_spans = 0
    missing_spans = 0
    dropped_empty_sentences = 0
    transition_fixes = 0
    label_token_counts = Counter()
    label_span_counts = Counter()
    original_label_counts = Counter()
    dropped_coarse_counts = Counter()
    retained_coarse_counts = Counter()

    def flush(sentence: list[dict[str, str]]) -> None:
        nonlocal source_sentences, written_sentences, written_tokens, dropped_empty_sentences, transition_fixes
        if not sentence:
            return
        source_sentences += 1
        normalize_sentence_bio(sentence)
        transition_fixes += sum(1 for row in sentence if row["transition_fixed"] == "yes")
        if not any(row["slim_bio"] != "O" for row in sentence):
            dropped_empty_sentences += 1
            return
        write_sentence(sentence, bio_handle, conllu_handle, span_handle, side_writer)
        written_sentences += 1
        written_tokens += len(sentence)

    with src_file.open("r", encoding="utf-8", newline="") as src_handle, bio_out.open(
        "w", encoding="utf-8", newline=""
    ) as bio_handle, conllu_out.open("w", encoding="utf-8", newline="") as conllu_handle, span_out.open(
        "w", encoding="utf-8", newline=""
    ) as span_handle, side_out.open("w", encoding="utf-8", newline="") as side_handle:
        header = src_handle.readline().rstrip("\n").split("\t")
        if header[:2] != ["token", "original_bio"]:
            raise ValueError(f"Unexpected header in {src_file}: {header}")
        side_writer = csv.writer(side_handle, delimiter="\t", lineterminator="\n")
        side_writer.writerow(["token", "original_bio", "coarse_label", "retained_label", "mapping_status", "slim_bio"])

        sentence = []
        for lineno, raw in enumerate(src_handle, start=2):
            line = raw.rstrip("\n")
            if not line:
                flush(sentence)
                sentence = []
                continue

            parts = line.split("\t")
            if len(parts) != len(header):
                raise ValueError(f"Bad TSV row in {src_file}:{lineno}: expected {len(header)} columns, got {len(parts)}")
            row = dict(zip(header, parts))
            token = row["token"]
            original_bio = row["original_bio"]
            slim_bio, coarse_label, retained_label, status = map_original_bio(original_bio, label_map)
            if not LABEL_RE.match(slim_bio):
                raise ValueError(f"Bad slim BIO in {src_file}:{lineno}: {slim_bio!r}")

            source_tokens += 1
            if original_bio != "O":
                prefix, original_label = parse_bio(original_bio)
                if prefix == "B":
                    source_spans += 1
                    if status == "retained":
                        retained_spans += 1
                        label_span_counts[retained_label] += 1
                        original_label_counts[(original_label, coarse_label, retained_label)] += 1
                        retained_coarse_counts[(coarse_label, retained_label)] += 1
                    elif status == "missing_original_label":
                        missing_spans += 1
                        dropped_coarse_counts[(coarse_label, status)] += 1
                    else:
                        dropped_spans += 1
                        dropped_coarse_counts[(coarse_label, status)] += 1
                if status == "retained":
                    label_token_counts[retained_label] += 1

            sentence.append(
                {
                    "token": token,
                    "original_bio": original_bio,
                    "coarse_label": coarse_label,
                    "retained_label": retained_label,
                    "mapping_status": status,
                    "slim_bio": slim_bio,
                    "transition_fixed": "no",
                }
            )

        flush(sentence)

    return {
        "source_sentences": source_sentences,
        "written_sentences": written_sentences,
        "dropped_empty_sentences": dropped_empty_sentences,
        "source_tokens": source_tokens,
        "written_tokens": written_tokens,
        "source_spans": source_spans,
        "retained_spans": retained_spans,
        "dropped_spans": dropped_spans,
        "missing_spans": missing_spans,
        "transition_fixes": transition_fixes,
        "label_token_counts": label_token_counts,
        "label_span_counts": label_span_counts,
        "original_label_counts": original_label_counts,
        "dropped_coarse_counts": dropped_coarse_counts,
        "retained_coarse_counts": retained_coarse_counts,
    }


def write_counts(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_language_reports(lang_dir: Path, lang: str, split_reports: dict[str, dict[str, object]]) -> dict[str, object]:
    all_report = split_reports["all"]
    write_counts(
        lang_dir / "split_summary.tsv",
        [
            "split",
            "source_sentences",
            "written_sentences",
            "dropped_empty_sentences",
            "source_tokens",
            "written_tokens",
            "source_spans",
            "retained_spans",
            "dropped_spans",
            "missing_spans",
        ],
        [
            [
                split,
                report["source_sentences"],
                report["written_sentences"],
                report["dropped_empty_sentences"],
                report["source_tokens"],
                report["written_tokens"],
                report["source_spans"],
                report["retained_spans"],
                report["dropped_spans"],
                report["missing_spans"],
            ]
            for split, report in split_reports.items()
        ],
    )

    write_counts(
        lang_dir / "label_token_counts.tsv",
        ["label", "entity_token_count", "entity_span_count"],
        [
            [label, all_report["label_token_counts"][label], all_report["label_span_counts"][label]]
            for label in sorted(set(all_report["label_token_counts"]) | set(all_report["label_span_counts"]))
        ],
    )

    write_counts(
        lang_dir / "original_label_bucket_counts.tsv",
        ["original_label", "coarse_label", "retained_label", "span_count"],
        [
            [original, coarse, label, count]
            for (original, coarse, label), count in sorted(
                all_report["original_label_counts"].items(), key=lambda item: (-item[1], item[0])
            )
        ],
    )

    write_counts(
        lang_dir / "dropped_coarse_label_counts.tsv",
        ["coarse_label", "drop_reason", "span_count"],
        [
            [coarse, reason, count]
            for (coarse, reason), count in sorted(all_report["dropped_coarse_counts"].items(), key=lambda item: (-item[1], item[0]))
        ],
    )

    report = {
        "lang": lang,
        "splits": {
            split: {
                key: value
                for key, value in split_reports[split].items()
                if not isinstance(value, Counter)
            }
            for split in SPLITS
        },
        "labels": sorted(all_report["label_span_counts"]),
    }
    (lang_dir / "dataset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (lang_dir / "README.md").write_text(
        f"# fiNERweb {DATASET_DISPLAY_NAME} BIO/CoNLL-U dataset: {lang}\n\n"
        f"Labels use the {len(REGION_LABELS)} retained {DATASET_DISPLAY_NAME} categories. "
        f"{DATASET_DESCRIPTION}\n",
        encoding="utf-8",
    )
    return report


def append_file(src: Path, dst_handle) -> None:
    with src.open("r", encoding="utf-8", newline="") as handle:
        shutil.copyfileobj(handle, dst_handle)


def build_combined_files(langs: list[str]) -> None:
    OUTPUT_COMBINED.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        with (OUTPUT_COMBINED / f"{split}.bio").open("w", encoding="utf-8", newline="") as bio_out, (
            OUTPUT_COMBINED / f"{split}.conllu"
        ).open("w", encoding="utf-8", newline="") as conllu_out, (
            OUTPUT_COMBINED / f"{split}.ner_spans.conllu"
        ).open("w", encoding="utf-8", newline="") as span_out:
            for lang in langs:
                append_file(OUTPUT_BY_LANG / lang / f"{split}.bio", bio_out)
                append_file(OUTPUT_BY_LANG / lang / f"{split}.conllu", conllu_out)
                append_file(OUTPUT_BY_LANG / lang / f"{split}.ner_spans.conllu", span_out)


def write_root_reports(
    langs: list[str],
    lang_reports: dict[str, dict[str, object]],
    retained_coarse: dict[str, str],
    label_map: dict[str, dict[str, str]],
) -> None:
    totals = defaultdict(int)
    label_token_counts = Counter()
    label_span_counts = Counter()
    original_label_counts = Counter()
    dropped_coarse_counts = Counter()
    retained_coarse_counts = Counter()

    for lang in langs:
        report = lang_reports[lang]["splits"]["all"]
        for key in [
            "source_sentences",
            "written_sentences",
            "dropped_empty_sentences",
            "source_tokens",
            "written_tokens",
            "source_spans",
            "retained_spans",
            "dropped_spans",
            "missing_spans",
            "transition_fixes",
        ]:
            totals[key] += int(report[key])

        lang_dir = OUTPUT_BY_LANG / lang
        with (lang_dir / "label_token_counts.tsv").open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                label_token_counts[row["label"]] += int(row["entity_token_count"])
                label_span_counts[row["label"]] += int(row["entity_span_count"])
        with (lang_dir / "original_label_bucket_counts.tsv").open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                original_label_counts[(row["original_label"], row["coarse_label"], row["retained_label"])] += int(row["span_count"])
        with (lang_dir / "dropped_coarse_label_counts.tsv").open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                dropped_coarse_counts[(row["coarse_label"], row["drop_reason"])] += int(row["span_count"])

    for row in label_map.values():
        if row["status"] == "retained":
            retained_coarse_counts[(row["coarse_label"], row["retained_label"])] += int(row["count"])

    for root in (OUTPUT_BY_LANG, OUTPUT_COMBINED):
        write_counts(
            root / "label_token_counts.tsv",
            ["label", "entity_token_count", "entity_span_count"],
            [
                [label, label_token_counts[label], label_span_counts[label]]
                for label in sorted(set(label_token_counts) | set(label_span_counts))
            ],
        )
        write_counts(
            root / "original_label_bucket_counts.tsv",
            ["original_label", "coarse_label", "retained_label", "span_count"],
            [
                [original, coarse, label, count]
                for (original, coarse, label), count in sorted(original_label_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        )
        write_counts(
            root / "dropped_coarse_label_counts.tsv",
            ["coarse_label", "drop_reason", "span_count"],
            [
                [coarse, reason, count]
                for (coarse, reason), count in sorted(dropped_coarse_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
        )
        write_counts(
            root / "coarse_bucket_map_used.tsv",
            ["coarse_label", "retained_label"],
            [[coarse, label] for coarse, label in sorted(retained_coarse.items())],
        )
        write_counts(
            root / f"original_label_{DATASET_NAME}_map.tsv",
            ["original_label", "coarse_label", "fine_label", "count", "retained_label", "status"],
            [
                [row["original_label"], row["coarse_label"], row["fine_label"], row["count"], row["retained_label"], row["status"]]
                for row in sorted(label_map.values(), key=lambda item: (-int(item["count"]), item["original_label"]))
            ],
        )
        if SOURCE_FILES.exists():
            shutil.copy2(SOURCE_FILES, root / "source_files.tsv")

    split_summary_rows = []
    for split in SPLITS:
        split_totals = defaultdict(int)
        for lang in langs:
            report = lang_reports[lang]["splits"][split]
            for key in [
                "source_sentences",
                "written_sentences",
                "dropped_empty_sentences",
                "source_tokens",
                "written_tokens",
                "source_spans",
                "retained_spans",
                "dropped_spans",
                "missing_spans",
            ]:
                split_totals[key] += int(report[key])
        split_summary_rows.append(
            [
                split,
                split_totals["source_sentences"],
                split_totals["written_sentences"],
                split_totals["dropped_empty_sentences"],
                split_totals["source_tokens"],
                split_totals["written_tokens"],
                split_totals["source_spans"],
                split_totals["retained_spans"],
                split_totals["dropped_spans"],
                split_totals["missing_spans"],
            ]
        )
    for root in (OUTPUT_BY_LANG, OUTPUT_COMBINED):
        write_counts(
            root / "split_summary.tsv",
            [
                "split",
                "source_sentences",
                "written_sentences",
                "dropped_empty_sentences",
                "source_tokens",
                "written_tokens",
                "source_spans",
                "retained_spans",
                "dropped_spans",
                "missing_spans",
            ],
            split_summary_rows,
        )

    dataset_report = {
        "dataset": DATASET_NAME,
        "source_dataset": str(SOURCE_ROOT),
        "retained_map": str(RETAINED_MAP),
        "labels": sorted(REGION_LABELS.values()),
        "retained_coarse_tags": len(retained_coarse),
        "original_label_rows": len(label_map),
        "retained_original_label_rows": sum(1 for row in label_map.values() if row["status"] == "retained"),
        "dropped_original_label_rows": sum(1 for row in label_map.values() if row["status"] == "dropped"),
        "languages": langs,
        "totals": dict(totals),
        "label_span_counts": dict(label_span_counts),
        "label_token_counts": dict(label_token_counts),
        "language_reports": {
            lang: {
                "all": lang_reports[lang]["splits"]["all"],
            }
            for lang in langs
        },
    }
    for root in (OUTPUT_BY_LANG, OUTPUT_COMBINED):
        (root / "dataset_report.json").write_text(json.dumps(dataset_report, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "README.md").write_text(
            f"# fiNERweb {DATASET_DISPLAY_NAME} Trankit NER BIO/CoNLL-U dataset\n\n"
            f"This dataset uses the {len(REGION_LABELS)}-category {DATASET_DISPLAY_NAME} retained map. "
            f"{DATASET_DESCRIPTION}\n\n"
            "Files include `train/dev/test/all.bio`, matching `.conllu` files with `NER=` in MISC, side-by-side "
            "`original_vs_bucket.tsv` files in the by-language tree, span-only debug files named "
            "`*.ner_spans.conllu`, and audit TSVs.\n",
            encoding="utf-8",
        )


def validate_tree(root: Path, by_language: bool) -> dict[str, object]:
    issues = []
    files_checked = 0
    dirs = [p for p in sorted(root.iterdir()) if p.is_dir()] if by_language else [root]
    for directory in dirs:
        lang = directory.name if by_language else "combined"
        for split in SPLITS:
            for filename in (f"{split}.bio", f"{split}.conllu", f"{split}.ner_spans.conllu"):
                path = directory / filename
                files_checked += 1
                if not path.exists():
                    issues.append([lang, split, str(path), 0, "missing_file", ""])
                    continue
            prev = "O"
            with (directory / f"{split}.bio").open("r", encoding="utf-8", newline="") as handle:
                for lineno, line in enumerate(handle, start=1):
                    line = line.rstrip("\n")
                    if not line:
                        prev = "O"
                        continue
                    parts = line.split("\t")
                    if len(parts) != 2:
                        issues.append([lang, split, str(directory / f"{split}.bio"), lineno, "bad_columns", line[:80]])
                        continue
                    label = parts[1]
                    if not LABEL_RE.match(label):
                        issues.append([lang, split, str(directory / f"{split}.bio"), lineno, "bad_label", label])
                    if label.startswith("I-") and prev not in {label, "B-" + label[2:]}:
                        issues.append([lang, split, str(directory / f"{split}.bio"), lineno, "bad_i_transition", label])
                    prev = label
            with (directory / f"{split}.ner_spans.conllu").open("r", encoding="utf-8", newline="") as handle:
                for lineno, line in enumerate(handle, start=1):
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) != 10:
                        issues.append([lang, split, str(directory / f"{split}.ner_spans.conllu"), lineno, "bad_span_columns", line[:80]])
                        continue
                    if parts[3] not in REGION_LABELS.values():
                        issues.append([lang, split, str(directory / f"{split}.ner_spans.conllu"), lineno, "bad_span_bucket", parts[3]])
    issue_path = root / "archive_health_issues.tsv"
    with issue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["lang", "split", "file", "line", "issue", "detail"])
        writer.writerows(issues)
    report = {"files_checked": files_checked, "issue_count": len(issues), "issues_tsv": str(issue_path)}
    (root / "archive_health_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def make_zip(root: Path, zip_path: Path) -> dict[str, object]:
    tmp = zip_path.with_suffix(".zip.tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root.parent).as_posix())
    os.replace(tmp, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        return {"zip": str(zip_path), "members": len(zf.namelist()), "size_bytes": zip_path.stat().st_size}


def main() -> None:
    retained_coarse = load_retained_coarse_map()
    label_map = build_original_label_map(retained_coarse)

    guarded_remove_tree(OUTPUT_BY_LANG)
    guarded_remove_tree(OUTPUT_COMBINED)
    OUTPUT_BY_LANG.mkdir(parents=True, exist_ok=True)

    langs = sorted(path.name for path in SOURCE_ROOT.iterdir() if path.is_dir())
    lang_reports = {}
    for lang in langs:
        src_lang_dir = SOURCE_ROOT / lang
        out_lang_dir = OUTPUT_BY_LANG / lang
        out_lang_dir.mkdir(parents=True, exist_ok=True)
        split_reports = {}
        for split in SPLITS:
            split_reports[split] = convert_split(
                src_lang_dir / f"{split}.original_vs_bucket.tsv",
                out_lang_dir / f"{split}.bio",
                out_lang_dir / f"{split}.conllu",
                out_lang_dir / f"{split}.ner_spans.conllu",
                out_lang_dir / f"{split}.original_vs_bucket.tsv",
                label_map,
            )
        lang_reports[lang] = write_language_reports(out_lang_dir, lang, split_reports)

    build_combined_files(langs)
    write_root_reports(langs, lang_reports, retained_coarse, label_map)
    health_by_lang = validate_tree(OUTPUT_BY_LANG, by_language=True)
    health_combined = validate_tree(OUTPUT_COMBINED, by_language=False)
    zip_by_lang = make_zip(OUTPUT_BY_LANG, ZIP_BY_LANG)
    zip_combined = make_zip(OUTPUT_COMBINED, ZIP_COMBINED)

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
