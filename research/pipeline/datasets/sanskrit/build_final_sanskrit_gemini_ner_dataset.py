from __future__ import annotations

import difflib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.dcs_sanskrit_trankit_mwt_subset_10pct.gemini_sanskrit_ner_10_sentence_test import (
    ALLOWED_LABELS,
)


BASE_DIR = (
    ROOT
    / "training"
    / "dcs_sanskrit_trankit_mwt_subset_10pct"
    / "gemini_ner_test_10_sentences"
)
INPUT_DIR = BASE_DIR / "inputs"
RAW_DIR = BASE_DIR / "raw_atomic"
SUMMARY_DIR = BASE_DIR / "summaries"
FINAL_DIR = BASE_DIR / "final"

START_CHUNK = 1
END_CHUNK = 1800


@dataclass
class Run:
    chunk: int
    prefix: str
    retry_no: int
    summary_path: Path | None
    raw_path: Path
    validation: str
    output_rows: int
    non_o_rows: int
    invalid_label_rows: int


def input_path_for(chunk: int) -> Path:
    return INPUT_DIR / f"input_chunk{chunk}_10_sentences.bio"


def raw_path_for(prefix: str) -> Path:
    return RAW_DIR / f"raw_atomic_output_{prefix}.txt"


def parse_prefix(prefix: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"chunk(\d+)(?:_retry(\d+))?", prefix)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2) or 0)


def parse_input_sentences(path: Path) -> list[list[str]]:
    sentences: list[list[str]] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                sentences.append(current)
                current = []
            continue
        current.append(stripped.rsplit(maxsplit=1)[0])
    if current:
        sentences.append(current)
    return sentences


def parse_raw_rows(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.rsplit(" ", 1)
        if len(parts) == 2:
            token, label = parts
        else:
            token, label = stripped, ""
        rows.append((token, normalize_label(label), stripped))
    return rows


def normalize_label(label: str) -> str:
    if label in ALLOWED_LABELS:
        return label
    if label.startswith(("B-", "I-")) and label[2:] in ALLOWED_LABELS:
        return label[2:]
    return ""


def raw_non_o_count(path: Path) -> tuple[int, int, int]:
    rows = parse_raw_rows(path)
    non_o = sum(1 for _, label, _ in rows if label and label != "O")
    invalid = sum(1 for _, label, _ in rows if not label)
    return len(rows), non_o, invalid


def load_runs() -> dict[int, list[Run]]:
    runs: dict[int, list[Run]] = {chunk: [] for chunk in range(START_CHUNK, END_CHUNK + 1)}
    summary_by_prefix: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in SUMMARY_DIR.glob("summary_chunk*.json"):
        if re.fullmatch(r"summary_chunk\d+_to_chunk\d+(?:_final)?\.json", path.name):
            continue
        match = re.fullmatch(r"summary_(chunk\d+(?:_retry\d+)?)\.json", path.name)
        if not match:
            continue
        prefix = match.group(1)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        summary_by_prefix[prefix] = (path, data)

    for raw_path in RAW_DIR.glob("raw_atomic_output_chunk*.txt"):
        match = re.fullmatch(r"raw_atomic_output_(chunk\d+(?:_retry\d+)?)\.txt", raw_path.name)
        if not match:
            continue
        prefix = match.group(1)
        parsed = parse_prefix(prefix)
        if not parsed:
            continue
        chunk, retry_no = parsed
        if not (START_CHUNK <= chunk <= END_CHUNK):
            continue
        rows, non_o, invalid = raw_non_o_count(raw_path)
        summary_path, summary = summary_by_prefix.get(prefix, (None, {}))
        validation = str(summary.get("validation") or "")
        runs[chunk].append(
            Run(
                chunk=chunk,
                prefix=prefix,
                retry_no=retry_no,
                summary_path=summary_path,
                raw_path=raw_path,
                validation=validation,
                output_rows=rows,
                non_o_rows=non_o,
                invalid_label_rows=invalid,
            )
        )
    for chunk_runs in runs.values():
        chunk_runs.sort(key=lambda run: run.retry_no)
    return runs


def choose_run(chunk_runs: list[Run]) -> Run | None:
    nonempty = [run for run in chunk_runs if run.non_o_rows > 0]
    if not nonempty:
        return None
    valid = [run for run in nonempty if run.validation == "passed" and run.invalid_label_rows == 0]
    if valid:
        return max(valid, key=lambda run: (run.non_o_rows, run.retry_no))
    return max(nonempty, key=lambda run: (run.non_o_rows, run.retry_no))


def align_and_repair(
    chunk: int,
    prefix: str,
    input_tokens: list[str],
    output_rows: list[tuple[str, str, str]],
) -> tuple[list[str], list[list[str]]]:
    output_tokens = [row[0] for row in output_rows]
    output_labels = [row[1] or "O" for row in output_rows]
    repaired: list[str] = ["O"] * len(input_tokens)
    fix_rows: list[list[str]] = []
    matcher = difflib.SequenceMatcher(a=input_tokens, b=output_tokens, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for offset, label in enumerate(output_labels[j1:j2]):
                repaired[i1 + offset] = label
            continue

        in_span = input_tokens[i1:i2]
        out_span = output_tokens[j1:j2]
        out_label_span = output_labels[j1:j2]
        detail = {
            "input_tokens": in_span,
            "output_tokens": out_span,
            "output_labels": out_label_span,
        }

        if op == "delete":
            for index in range(i1, i2):
                repaired[index] = "O"
            fix_rows.append(
                [
                    str(chunk),
                    prefix,
                    "missing_output_rows_inserted_as_O",
                    str(i1 + 1),
                    str(i2),
                    str(j1 + 1),
                    str(j2),
                    json.dumps(detail, ensure_ascii=False),
                ]
            )
            continue

        if op == "insert":
            fix_rows.append(
                [
                    str(chunk),
                    prefix,
                    "extra_output_rows_dropped",
                    str(i1 + 1),
                    str(i2),
                    str(j1 + 1),
                    str(j2),
                    json.dumps(detail, ensure_ascii=False),
                ]
            )
            continue

        if len(in_span) == len(out_span):
            for offset, label in enumerate(out_label_span):
                repaired[i1 + offset] = label
            fix_type = "token_spelling_canonicalized"
        elif len(out_span) == 1 and len(in_span) > 1:
            label = out_label_span[0] if out_label_span else "O"
            for index in range(i1, i2):
                repaired[index] = label
            fix_type = "merged_output_row_split"
        else:
            overlap = min(len(in_span), len(out_span))
            for offset in range(overlap):
                repaired[i1 + offset] = out_label_span[offset]
            for index in range(i1 + overlap, i2):
                repaired[index] = "O"
            fix_type = "unequal_replace_positionally_mapped_missing_as_O"
        fix_rows.append(
            [
                str(chunk),
                prefix,
                fix_type,
                str(i1 + 1),
                str(i2),
                str(j1 + 1),
                str(j2),
                json.dumps(detail, ensure_ascii=False),
            ]
        )

    return repaired, fix_rows


def atomic_to_bio(sentences: list[list[str]], labels: list[str]) -> list[str]:
    rows: list[str] = []
    cursor = 0
    for sentence in sentences:
        previous_label = "O"
        for token in sentence:
            label = labels[cursor]
            if label == "O":
                tag = "O"
            else:
                prefix = "I" if label == previous_label else "B"
                tag = f"{prefix}-{label}"
            rows.append(f"{token} {tag}")
            previous_label = label
            cursor += 1
        rows.append("")
    return rows


def main() -> None:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    runs_by_chunk = load_runs()

    atomic_lines: list[str] = []
    bio_lines: list[str] = []
    manifest_rows: list[list[str]] = [
        [
            "chunk",
            "status",
            "selected_prefix",
            "input_tokens",
            "output_rows",
            "non_o_rows",
            "validation",
            "repair_count",
        ]
    ]
    fix_rows: list[list[str]] = [
        [
            "chunk",
            "selected_prefix",
            "fix_type",
            "input_start",
            "input_end",
            "output_start",
            "output_end",
            "detail_json",
        ]
    ]
    tag_counts: Counter[str] = Counter()
    included_chunks = 0
    skipped_empty = 0
    missing = 0
    total_input_tokens = 0
    total_non_o = 0

    for chunk in range(START_CHUNK, END_CHUNK + 1):
        input_path = input_path_for(chunk)
        if not input_path.exists():
            missing += 1
            manifest_rows.append([str(chunk), "missing_input", "", "0", "0", "0", "", "0"])
            continue
        sentences = parse_input_sentences(input_path)
        input_tokens = [token for sentence in sentences for token in sentence]
        selected = choose_run(runs_by_chunk.get(chunk, []))
        if selected is None:
            skipped_empty += 1
            manifest_rows.append(
                [str(chunk), "skipped_empty_or_missing", "", str(len(input_tokens)), "0", "0", "", "0"]
            )
            continue

        output_rows = parse_raw_rows(selected.raw_path)
        labels, fixes = align_and_repair(chunk, selected.prefix, input_tokens, output_rows)
        fix_rows.extend(fixes)
        non_o = sum(1 for label in labels if label != "O")
        if non_o == 0:
            skipped_empty += 1
            manifest_rows.append(
                [
                    str(chunk),
                    "skipped_empty_after_repair",
                    selected.prefix,
                    str(len(input_tokens)),
                    str(selected.output_rows),
                    "0",
                    selected.validation,
                    str(len(fixes)),
                ]
            )
            continue

        included_chunks += 1
        total_input_tokens += len(input_tokens)
        total_non_o += non_o
        for token, label in zip(input_tokens, labels):
            atomic_lines.append(f"{token} {label}")
            tag_counts[label] += 1
        atomic_lines.append("")
        bio_rows = atomic_to_bio(sentences, labels)
        bio_lines.extend(bio_rows)
        manifest_rows.append(
            [
                str(chunk),
                "included",
                selected.prefix,
                str(len(input_tokens)),
                str(selected.output_rows),
                str(non_o),
                selected.validation,
                str(len(fixes)),
            ]
        )

    atomic_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_atomic.txt"
    bio_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed.bio"
    manifest_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_manifest.tsv"
    fix_log_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_fix_log.tsv"
    tag_counts_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_tag_counts.tsv"
    summary_path = FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_summary.json"

    atomic_path.write_text("\n".join(atomic_lines).rstrip() + "\n", encoding="utf-8")
    bio_path.write_text("\n".join(bio_lines).rstrip() + "\n", encoding="utf-8")
    manifest_path.write_text(
        "\n".join("\t".join(row) for row in manifest_rows) + "\n", encoding="utf-8"
    )
    fix_log_path.write_text(
        "\n".join("\t".join(row) for row in fix_rows) + "\n", encoding="utf-8"
    )
    tag_counts_path.write_text(
        "tag\tcount\n" + "\n".join(f"{tag}\t{count}" for tag, count in tag_counts.most_common()) + "\n",
        encoding="utf-8",
    )
    summary = {
        "chunk_start": START_CHUNK,
        "chunk_end": END_CHUNK,
        "included_chunks": included_chunks,
        "skipped_empty_chunks": skipped_empty,
        "missing_input_chunks": missing,
        "token_rows": total_input_tokens,
        "non_o_atomic_rows": total_non_o,
        "fix_log_rows": max(0, len(fix_rows) - 1),
        "atomic_file": str(atomic_path),
        "bio_file": str(bio_path),
        "manifest_file": str(manifest_path),
        "fix_log_file": str(fix_log_path),
        "tag_counts_file": str(tag_counts_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
