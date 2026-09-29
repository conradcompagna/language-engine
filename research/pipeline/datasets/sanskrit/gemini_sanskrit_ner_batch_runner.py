from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import json
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import GEMINI_API_KEY, GEMINI_MODEL_PRICING_USD_PER_1M
from training.dcs_sanskrit_trankit_mwt_subset_10pct.gemini_sanskrit_ner_10_sentence_test import (
    ALLOWED_LABELS,
    MODEL,
    build_prompts,
    response_text,
    to_bio,
    validate_output,
)


INPUT_DIR = (
    ROOT
    / "training"
    / "dcs_sanskrit_trankit_mwt_subset_10pct"
    / "train_10k_parent_tokens_unannotated_bio_chunks"
    / "unannotatedchild"
)
OUT_DIR = ROOT / "training" / "dcs_sanskrit_trankit_mwt_subset_10pct" / "gemini_ner_test_10_sentences"
INPUT_OUT_DIR = OUT_DIR / "inputs"
SYSTEM_PROMPT_DIR = OUT_DIR / "prompts" / "system"
USER_PROMPT_DIR = OUT_DIR / "prompts" / "user"
RAW_DIR = OUT_DIR / "raw_atomic"
RESPONSE_DIR = OUT_DIR / "responses"
USAGE_DIR = OUT_DIR / "usage"
DIVERGENCE_DIR = OUT_DIR / "divergences"
VALIDATED_ATOMIC_DIR = OUT_DIR / "validated_atomic"
VALIDATED_BIO_DIR = OUT_DIR / "validated_bio"
SUMMARY_DIR = OUT_DIR / "summaries"
LOG_DIR = OUT_DIR / "logs"
SENTS_PER_JOB = 10


def ensure_output_dirs() -> None:
    for path in [
        INPUT_OUT_DIR,
        SYSTEM_PROMPT_DIR,
        USER_PROMPT_DIR,
        RAW_DIR,
        RESPONSE_DIR,
        USAGE_DIR,
        DIVERGENCE_DIR,
        VALIDATED_ATOMIC_DIR,
        VALIDATED_BIO_DIR,
        SUMMARY_DIR,
        LOG_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def redact_error(text: str) -> str:
    if GEMINI_API_KEY:
        text = text.replace(GEMINI_API_KEY, "<GEMINI_API_KEY>")
    return text.replace("\t", " ").replace("\n", " ")


def all_sentences_from_files() -> list[tuple[str, int, list[str]]]:
    rows: list[tuple[str, int, list[str]]] = []
    for path in sorted(INPUT_DIR.glob("*.bio")):
        current: list[str] = []
        sent_index = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                if current:
                    sent_index += 1
                    rows.append((path.name, sent_index, current))
                    current = []
                continue
            current.append(stripped.rsplit(maxsplit=1)[0])
        if current:
            sent_index += 1
            rows.append((path.name, sent_index, current))
    return rows


def job_sentences(
    all_rows: list[tuple[str, int, list[str]]], job_no: int
) -> list[tuple[str, int, list[str]]]:
    start = (job_no - 1) * SENTS_PER_JOB
    return all_rows[start : start + SENTS_PER_JOB]


def make_user_prompt(job_no: int, rows: list[tuple[str, int, list[str]]], token_count: int) -> str:
    lines = [
        (
            f"Annotate these input tokens. This request has exactly {token_count} input token rows, "
            f"so your answer must have exactly {token_count} non-empty output rows."
        ),
        "Never combine adjacent input tokens into one output row. Never split one input token into multiple rows.",
        "Sentence marker lines are context only and are not tokens. Do not output marker lines.",
        "",
    ]
    for local_index, (source_name, source_sent_index, sentence) in enumerate(rows, start=1):
        lines.append(
            f"[chunk {job_no} sentence {local_index}; source {source_name} sentence {source_sent_index}]"
        )
        lines.extend(sentence)
        lines.append("")
    return "\n".join(lines).strip()


def build_system_prompt(token_count: int) -> str:
    system_prompt, _ = build_prompts([])
    system_prompt = system_prompt.replace(
        "Return exactly one non-empty output row for each input token row.",
        (
            "Return exactly one non-empty output row for each input token row. "
            f"This request has exactly {token_count} input token rows, so your answer must have "
            f"exactly {token_count} non-empty output rows."
        ),
    )
    system_prompt += (
        "\nNever combine adjacent input tokens into one output row. If the input has two rows "
        "`abhyukṣya` and `ca`, output two rows: `abhyukṣya LABEL` and `ca LABEL`.\n"
    )
    return system_prompt


def call_gemini(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "candidateCount": 1,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def output_rows(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.rsplit(" ", 1)
        rows.append((parts[0], parts[1]) if len(parts) == 2 else (stripped, ""))
    return rows


def divergence_tsv(input_tokens: list[str], out_tokens: list[str]) -> str:
    rows = ["op\tinput_start\tinput_end\toutput_start\toutput_end\tinput_tokens\toutput_tokens"]
    matcher = difflib.SequenceMatcher(a=input_tokens, b=out_tokens, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        rows.append(
            "\t".join(
                [
                    op,
                    str(i1 + 1),
                    str(i2),
                    str(j1 + 1),
                    str(j2),
                    " ".join(input_tokens[i1:i2]),
                    " ".join(out_tokens[j1:j2]),
                ]
            )
        )
    return "\n".join(rows) + "\n"


def usage_summary(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usageMetadata") or {}
    pricing = GEMINI_MODEL_PRICING_USD_PER_1M.get(MODEL, {})
    input_tokens = int(usage.get("promptTokenCount") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or 0)
    input_cost = input_tokens * float(pricing.get("input_tokens", 0.0)) / 1_000_000
    output_cost = output_tokens * float(pricing.get("output_tokens", 0.0)) / 1_000_000
    return {
        "model": MODEL,
        "prompt_token_count": input_tokens,
        "candidate_token_count": output_tokens,
        "total_token_count": int(usage.get("totalTokenCount") or 0),
        "estimated_input_cost_usd": input_cost,
        "estimated_output_cost_usd": output_cost,
        "estimated_total_cost_usd": input_cost + output_cost,
        "raw_usage": usage,
    }


def next_retry_prefix(job_no: int) -> str:
    existing = []
    pattern = re.compile(rf"^summary_chunk{job_no}_retry(\d+)\.json$")
    for path in SUMMARY_DIR.glob(f"summary_chunk{job_no}_retry*.json"):
        match = pattern.match(path.name)
        if match:
            existing.append(int(match.group(1)))
    return f"chunk{job_no}_retry{(max(existing) + 1) if existing else 1}"


def canonical_prefix(job_no: int) -> str:
    return f"chunk{job_no}"


def validated_path_for(prefix: str) -> Path:
    return VALIDATED_ATOMIC_DIR / f"validated_atomic_output_{prefix}.txt"


def raw_path_for(prefix: str) -> Path:
    return RAW_DIR / f"raw_atomic_output_{prefix}.txt"


def summary_path_for(prefix: str) -> Path:
    return SUMMARY_DIR / f"summary_{prefix}.json"


def summary_sort_key(path: Path) -> tuple[int, int]:
    retry_match = re.search(r"_retry(\d+)", path.name)
    if retry_match:
        return 1, int(retry_match.group(1))
    return 0, 0


def summaries_for_job(job_no: int) -> list[dict[str, Any]]:
    paths = [SUMMARY_DIR / f"summary_chunk{job_no}.json"]
    paths.extend(SUMMARY_DIR.glob(f"summary_chunk{job_no}_retry*.json"))
    summaries: list[dict[str, Any]] = []
    for path in sorted((p for p in paths if p.exists()), key=summary_sort_key):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        summary["_summary_path"] = str(path)
        summaries.append(summary)
    return summaries


def has_terminal_validation_failure(job_no: int) -> bool:
    for summary in summaries_for_job(job_no):
        if summary.get("validation") == "failed":
            return True
    return False


def has_valid_nonempty_output(job_no: int) -> bool:
    for summary in summaries_for_job(job_no):
        if summary.get("validation") != "passed":
            continue
        non_o_rows = summary.get("non_o_rows")
        if non_o_rows is not None:
            if int(non_o_rows or 0) > 0:
                return True
            continue
        prefix = str(summary.get("prefix") or f"chunk{job_no}")
        path = validated_path_for(prefix)
        if path.exists() and validated_file_non_o_count(path) > 0:
            return True
    return False


def has_empty_retry_output(job_no: int) -> bool:
    for summary in summaries_for_job(job_no):
        prefix = str(summary.get("prefix") or "")
        if "_retry" not in prefix or summary.get("validation") != "passed":
            continue
        non_o_rows = summary.get("non_o_rows")
        if non_o_rows is not None:
            if int(non_o_rows or 0) == 0:
                return True
            continue
        path = validated_path_for(prefix)
        if path.exists() and validated_file_non_o_count(path) == 0:
            return True
    return False


def validated_file_non_o_count(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.rsplit(" ", 1)
        if len(parts) == 2 and parts[1] != "O":
            count += 1
    return count


def has_existing_raw_without_summary(job_no: int) -> bool:
    return raw_path_for(canonical_prefix(job_no)).exists() and not summaries_for_job(job_no)


def write_input_and_prompts(
    prefix: str,
    rows: list[tuple[str, int, list[str]]],
    flat_tokens: list[str],
    system_prompt: str,
    user_prompt: str,
) -> None:
    input_path = INPUT_OUT_DIR / f"input_{prefix}_10_sentences.bio"
    if not input_path.exists():
        input_path.write_text(
            "\n\n".join("\n".join(f"{tok} O" for tok in sent) for _, _, sent in rows) + "\n",
            encoding="utf-8",
        )
    system_path = SYSTEM_PROMPT_DIR / f"system_prompt_{prefix}.txt"
    if not system_path.exists():
        system_path.write_text(system_prompt, encoding="utf-8")
    user_path = USER_PROMPT_DIR / f"user_prompt_{prefix}.txt"
    if not user_path.exists():
        user_path.write_text(user_prompt, encoding="utf-8")


def write_job_attempt(
    job_no: int,
    rows: list[tuple[str, int, list[str]]],
    prefix: str,
    attempt_no: int,
    is_retry: bool,
) -> dict[str, Any]:
    flat_tokens = [tok for _, _, sent in rows for tok in sent]
    system_prompt = build_system_prompt(len(flat_tokens))
    user_prompt = make_user_prompt(job_no, rows, len(flat_tokens))
    write_input_and_prompts(prefix, rows, flat_tokens, system_prompt, user_prompt)

    summary: dict[str, Any] = {
        "chunk": job_no,
        "prefix": prefix,
        "attempt_no": attempt_no,
        "is_retry": is_retry,
        "sentence_count": len(rows),
        "input_token_rows": len(flat_tokens),
        "sources": [
            {"source_file": source_name, "source_sentence": source_sent_index}
            for source_name, source_sent_index, _ in rows
        ],
    }

    try:
        data = call_gemini(system_prompt, user_prompt)
        (RESPONSE_DIR / f"response_{prefix}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        text = response_text(data)
        raw_path_for(prefix).write_text(text, encoding="utf-8")
        usage = usage_summary(data)
        (USAGE_DIR / f"usage_{prefix}.json").write_text(
            json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows_out = output_rows(text)
        out_toks = [tok for tok, _ in rows_out]
        labels = [label for _, label in rows_out]
        non_o_counts = Counter(label for label in labels if label and label != "O")
        divergence_text = divergence_tsv(flat_tokens, out_toks)
        (DIVERGENCE_DIR / f"token_divergence_{prefix}.tsv").write_text(
            divergence_text, encoding="utf-8"
        )
        summary.update(
            {
                "status": "completed",
                "output_token_rows": len(out_toks),
                "divergence_count": max(0, len(divergence_text.splitlines()) - 1),
                "non_o_rows": sum(non_o_counts.values()),
                "non_o_label_counts": dict(non_o_counts.most_common()),
                "usage": usage,
            }
        )
        try:
            parsed = validate_output(text, flat_tokens)
        except Exception as exc:
            summary["validation"] = "failed"
            summary["validation_error"] = redact_error(str(exc))
        else:
            summary["validation"] = "passed"
            validated_path_for(prefix).write_text(
                "\n".join(f"{token} {label}" for token, label in parsed) + "\n",
                encoding="utf-8",
            )
            sentence_lists = [sent for _, _, sent in rows]
            (VALIDATED_BIO_DIR / f"validated_bio_output_{prefix}.bio").write_text(
                to_bio(sentence_lists, parsed), encoding="utf-8"
            )
    except Exception as exc:
        summary["status"] = "error"
        summary["error"] = redact_error(repr(exc))

    summary_path_for(prefix).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def run_job_with_retries(
    job_no: int,
    rows: list[tuple[str, int, list[str]]],
    retry_count: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    if has_valid_nonempty_output(job_no):
        return {"chunk": job_no, "status": "skipped_validated"}
    if has_terminal_validation_failure(job_no):
        return {"chunk": job_no, "status": "skipped_validation_failed"}
    if has_empty_retry_output(job_no):
        return {"chunk": job_no, "status": "skipped_empty_after_retry"}
    if has_existing_raw_without_summary(job_no):
        return {"chunk": job_no, "status": "skipped_existing_raw_without_summary"}

    if raw_path_for(canonical_prefix(job_no)).exists() or summary_path_for(canonical_prefix(job_no)).exists():
        prefix = next_retry_prefix(job_no)
        is_retry = True
    else:
        prefix = canonical_prefix(job_no)
        is_retry = False

    result = write_job_attempt(job_no, rows, prefix, 1, is_retry)
    attempts = [result]
    retryable_status = result.get("status") == "error" or (
        result.get("validation") == "passed" and int(result.get("non_o_rows") or 0) == 0
    )
    for attempt in range(2, retry_count + 2):
        if not retryable_status:
            break
        time.sleep(retry_delay_seconds)
        retry_prefix = next_retry_prefix(job_no)
        result = write_job_attempt(job_no, rows, retry_prefix, attempt, True)
        attempts.append(result)
        retryable_status = result.get("status") == "error" or (
            result.get("validation") == "passed" and int(result.get("non_o_rows") or 0) == 0
        )

    final = attempts[-1].copy()
    final["attempts"] = attempts
    return final


def input_tokens(path: Path) -> list[str]:
    return [
        line.rsplit(maxsplit=1)[0]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def rebuild_issue_files() -> None:
    base_inputs: dict[str, Path] = {}
    for path in INPUT_OUT_DIR.glob("input_chunk*_10_sentences.bio"):
        match = re.match(r"input_(chunk\d+)_10_sentences\.bio$", path.name)
        if match:
            base_inputs[match.group(1)] = path

    runs: dict[str, tuple[Path, Path | None, Path | None]] = {}
    for key, in_path in base_inputs.items():
        runs[key] = (in_path, raw_path_for(key), summary_path_for(key))
    for summary_path in SUMMARY_DIR.glob("summary_chunk*_retry*.json"):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        prefix = summary.get("prefix")
        source_chunk = summary.get("chunk") or summary.get("source_chunk")
        if not prefix or source_chunk is None:
            continue
        runs[prefix] = (
            INPUT_OUT_DIR / f"input_chunk{source_chunk}_10_sentences.bio",
            raw_path_for(prefix),
            summary_path,
        )

    def sort_key(name: str) -> tuple[int, str]:
        match = re.match(r"chunk(\d+)(.*)", name)
        if match:
            return int(match.group(1)), match.group(2)
        return 999999, name

    issue_lines = ["run\tissue_type\tseverity\tinput_rows\toutput_rows\tnon_o_rows\tdetail"]
    count_lines = [
        "run\tinput_rows\toutput_rows\tnon_o_rows\tunique_non_o_labels\ttop_non_o_labels"
    ]

    for run_name in sorted(runs, key=sort_key):
        in_path, out_path, summary_path = runs[run_name]
        if not in_path.exists():
            continue
        in_toks = input_tokens(in_path)
        summary: dict[str, Any] = {}
        if summary_path and summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception as exc:
                issue_lines.append(
                    f"{run_name}\tsummary_parse_error\terror\t{len(in_toks)}\t\t\t{redact_error(repr(exc))}"
                )
        if summary.get("status") == "error":
            issue_lines.append(
                f"{run_name}\tapi_error\terror\t{len(in_toks)}\t0\t0\t{redact_error(str(summary.get('error', '')))}"
            )
        if not out_path or not out_path.exists():
            if summary.get("status") != "error":
                issue_lines.append(
                    f"{run_name}\tmissing_output\terror\t{len(in_toks)}\t0\t0\tmissing raw output"
                )
            count_lines.append(f"{run_name}\t{len(in_toks)}\t0\t0\t0\t")
            continue
        rows_out = output_rows(out_path.read_text(encoding="utf-8"))
        out_toks = [tok for tok, _ in rows_out]
        labels = [label for _, label in rows_out]
        non_o_counts = Counter(label for label in labels if label and label != "O")
        non_o_total = sum(non_o_counts.values())
        count_lines.append(
            f"{run_name}\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\t{len(non_o_counts)}\t"
            + ", ".join(f"{label}:{count}" for label, count in non_o_counts.most_common(12))
        )
        if len(rows_out) != len(in_toks):
            issue_lines.append(
                f"{run_name}\trow_count_mismatch\terror\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\texpected {len(in_toks)} output rows, got {len(rows_out)}"
            )
        divs = []
        matcher = difflib.SequenceMatcher(a=in_toks, b=out_toks, autojunk=False)
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op != "equal":
                divs.append(
                    f"{op} input[{i1 + 1}:{i2}]={' '.join(in_toks[i1:i2])!r} output[{j1 + 1}:{j2}]={' '.join(out_toks[j1:j2])!r}"
                )
        if divs:
            issue_lines.append(
                f"{run_name}\ttoken_divergence\terror\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\t{len(divs)} diff block(s): {redact_error(' | '.join(divs[:5]))}"
            )
        if any(not label for label in labels):
            issue_lines.append(
                f"{run_name}\tinvalid_label\terror\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\tblank/missing label present"
            )
        invalid_labels = sorted({label for label in labels if label and label not in ALLOWED_LABELS})
        if invalid_labels:
            issue_lines.append(
                f"{run_name}\tinvalid_label\terror\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\tinvalid labels: {', '.join(invalid_labels)}"
            )
        if rows_out and non_o_total == 0:
            issue_lines.append(
                f"{run_name}\tno_non_o_annotations\twarn\t{len(in_toks)}\t{len(rows_out)}\t0\tall output labels are O"
            )
        if summary.get("validation") == "failed":
            issue_lines.append(
                f"{run_name}\tvalidation_failed\terror\t{len(in_toks)}\t{len(rows_out)}\t{non_o_total}\t{redact_error(str(summary.get('validation_error', 'validation failed')))}"
            )

    (LOG_DIR / "issues.tsv").write_text("\n".join(issue_lines) + "\n", encoding="utf-8")
    (LOG_DIR / "annotation_counts.tsv").write_text(
        "\n".join(count_lines) + "\n", encoding="utf-8"
    )


def append_progress(row: dict[str, Any]) -> None:
    path = LOG_DIR / "batch_progress.tsv"
    exists = path.exists()
    fields = [
        "timestamp",
        "wave_start",
        "wave_end",
        "completed",
        "passed",
        "failed_validation",
        "errors",
        "skipped_validated",
        "skipped_validation_failed",
        "skipped_empty_after_retry",
        "skipped_existing_raw_without_summary",
        "estimated_total_cost_usd",
    ]
    line = "\t".join(str(row.get(field, "")) for field in fields)
    if not exists:
        path.write_text("\t".join(fields) + "\n" + line + "\n", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1800)
    parser.add_argument("--wave-size", type=int, default=10)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--wave-delay-seconds", type=float, default=3.0)
    parser.add_argument("--retry-count", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=float, default=12.0)
    parser.add_argument("--refresh-issues-every-wave", action="store_true")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is not configured")

    ensure_output_dirs()
    all_rows = all_sentences_from_files()
    if args.end * SENTS_PER_JOB > len(all_rows):
        raise SystemExit(
            f"Requested chunk {args.end}, but only {len(all_rows) // SENTS_PER_JOB} full chunks exist"
        )

    total_results: list[dict[str, Any]] = []
    for wave_start in range(args.start, args.end + 1, args.wave_size):
        wave_end = min(args.end, wave_start + args.wave_size - 1)
        jobs = [
            (job_no, job_sentences(all_rows, job_no))
            for job_no in range(wave_start, wave_end + 1)
        ]
        results: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(
                    run_job_with_retries,
                    job_no,
                    rows,
                    args.retry_count,
                    args.retry_delay_seconds,
                ): job_no
                for job_no, rows in jobs
            }
            for future in concurrent.futures.as_completed(future_map):
                results.append(future.result())
        results.sort(key=lambda row: int(row.get("chunk") or 0))
        total_results.extend(results)
        wave_cost = sum(
            float((row.get("usage") or {}).get("estimated_total_cost_usd") or 0.0)
            for row in results
        )
        wave_summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "wave_start": wave_start,
            "wave_end": wave_end,
            "completed": sum(1 for row in results if row.get("status") == "completed"),
            "passed": sum(1 for row in results if row.get("validation") == "passed"),
            "failed_validation": sum(
                1 for row in results if row.get("validation") == "failed"
            ),
            "errors": sum(1 for row in results if row.get("status") == "error"),
            "skipped_validated": sum(
                1 for row in results if row.get("status") == "skipped_validated"
            ),
            "skipped_validation_failed": sum(
                1 for row in results if row.get("status") == "skipped_validation_failed"
            ),
            "skipped_empty_after_retry": sum(
                1 for row in results if row.get("status") == "skipped_empty_after_retry"
            ),
            "skipped_existing_raw_without_summary": sum(
                1
                for row in results
                if row.get("status") == "skipped_existing_raw_without_summary"
            ),
            "estimated_total_cost_usd": wave_cost,
            "results": results,
        }
        (SUMMARY_DIR / f"summary_chunk{wave_start}_to_chunk{wave_end}.json").write_text(
            json.dumps(wave_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        append_progress(wave_summary)
        print(json.dumps(wave_summary, ensure_ascii=False))
        if args.refresh_issues_every_wave:
            rebuild_issue_files()
        if wave_end < args.end:
            time.sleep(args.wave_delay_seconds)

    rebuild_issue_files()
    final_summary = {
        "start": args.start,
        "end": args.end,
        "jobs_seen": len(total_results),
        "completed": sum(1 for row in total_results if row.get("status") == "completed"),
        "passed": sum(1 for row in total_results if row.get("validation") == "passed"),
        "failed_validation": sum(
            1 for row in total_results if row.get("validation") == "failed"
        ),
        "errors": sum(1 for row in total_results if row.get("status") == "error"),
        "skipped_validated": sum(
            1 for row in total_results if row.get("status") == "skipped_validated"
        ),
        "skipped_validation_failed": sum(
            1 for row in total_results if row.get("status") == "skipped_validation_failed"
        ),
        "skipped_empty_after_retry": sum(
            1 for row in total_results if row.get("status") == "skipped_empty_after_retry"
        ),
        "skipped_existing_raw_without_summary": sum(
            1
            for row in total_results
            if row.get("status") == "skipped_existing_raw_without_summary"
        ),
        "estimated_total_cost_usd": sum(
            float((row.get("usage") or {}).get("estimated_total_cost_usd") or 0.0)
            for row in total_results
        ),
    }
    (SUMMARY_DIR / f"summary_chunk{args.start}_to_chunk{args.end}_final.json").write_text(
        json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(final_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
