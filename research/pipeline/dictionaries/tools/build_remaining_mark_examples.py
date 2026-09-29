#!/usr/bin/env python3
"""Build filtered high-frequency mark reports with real TSV examples."""

from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import probe_headword_non_script_marks as probe
from wiktionary_general.dictionary import _normalize_affix_markers, _normalize_lookup_text


@dataclass(frozen=True)
class MarkRow:
    char: str
    total: int
    dicts: int
    category: str
    name: str


def _normalized_out(ch: str) -> bool:
    norm = _normalize_lookup_text(ch, "").strip()
    if not norm:
        return True
    norm = _normalize_affix_markers(norm)
    return norm.replace("-", "").casefold() == ""


def _hash_score(seed: int, mark: str, label: str, surface: str) -> int:
    payload = f"{seed}|{mark}|{label}|{surface}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _scan_headwords_only(
    seed: int,
    examples_per_mark: int,
) -> tuple[
    Counter[str],
    Dict[str, Dict[str, int]],
    Dict[str, List[Tuple[int, str, str]]],
]:
    total_counts: Counter[str] = Counter()
    per_dict_counts: DefaultDict[str, Dict[str, int]] = defaultdict(dict)
    best_examples: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)
    seen_examples: DefaultDict[str, set[str]] = defaultdict(set)

    specs = probe._build_batch_specs(ROOT / "reports" / "headword_non_script_marks")
    for spec in specs:
        with spec.path.open("r", encoding="utf-8", newline="") as handle:
            reader = probe.csv.DictReader(handle, delimiter="\t")
            local_counts: Counter[str] = Counter()
            for row in reader:
                for source, surface in probe._iter_surfaces(row):
                    if source != "headword":
                        continue
                    marks_here = {
                        ch for ch in set(surface)
                        if probe._should_count_char(ch, spec.script_family.checker)
                    }
                    if not marks_here:
                        continue
                    for ch in surface:
                        if ch not in marks_here:
                            continue
                        total_counts[ch] += 1
                        local_counts[ch] += 1
                    for ch in marks_here:
                        key = f"{spec.label}|{surface}"
                        if key in seen_examples[ch]:
                            continue
                        seen_examples[ch].add(key)
                        score = _hash_score(seed, ch, spec.label, surface)
                        bucket = best_examples[ch]
                        bucket.append((score, spec.label, surface))
                        bucket.sort(key=lambda item: item[0])
                        if len(bucket) > examples_per_mark:
                            bucket.pop()
            for ch, count in local_counts.items():
                per_dict_counts[ch][spec.label] = count

    return total_counts, dict(per_dict_counts), dict(best_examples)


def _build_rows(total_counts: Counter[str], per_dict_counts: Dict[str, Dict[str, int]]) -> List[MarkRow]:
    rows: List[MarkRow] = []
    for ch, total in total_counts.items():
        rows.append(
            MarkRow(
                char=ch,
                total=total,
                dicts=len(per_dict_counts.get(ch, {})),
                category=unicodedata.category(ch),
                name=unicodedata.name(ch, "<unnamed>"),
            )
        )
    rows.sort(key=lambda row: (-row.total, f"U+{ord(row.char):04X}"))
    return rows


def _display_char(ch: str) -> str:
    named = {
        " ": "[space]",
        "\t": "[tab]",
        "\n": "[newline]",
        "\r": "[carriage return]",
    }
    if ch in named:
        return named[ch]
    if unicodedata.category(ch).startswith("C"):
        return "[control/format]"
    return ch


def _write_report(
    output_path: Path,
    threshold: int,
    excluded_rows: List[MarkRow],
    kept_rows: List[MarkRow],
    per_dict_counts: Dict[str, Dict[str, int]],
    examples: Dict[str, List[Tuple[int, str, str]]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# Remaining High-frequency Headword Marks Not Already Normalized Out\n\n")
        out.write("- Source: headwords only across all real TSV dictionaries in `wiktionary general pipeline/converted_tsv`\n")
        out.write("- Forms are excluded from this report\n")
        out.write(f"- Included only when total headword hits > {threshold}\n")
        out.write("- Excluded as already normalized out when the current lookup normalization collapses the standalone mark to an empty key\n")
        out.write("- Lookup normalization basis: NFKC, affix-marker translation, then hyphen removal\n")
        out.write("- Script-family filtering uses the same language-specific codepoint families as the main batch probe\n")
        out.write("- Examples: 10 deterministic pseudo-random real headword surfaces per remaining mark\n")
        out.write(f"- High-frequency headword marks considered: {len(excluded_rows) + len(kept_rows):,}\n")
        out.write(f"- Excluded as already normalized out: {len(excluded_rows):,}\n")
        out.write(f"- Remaining marks in this file: {len(kept_rows):,}\n\n")

        if excluded_rows:
            out.write("## Excluded Already-normalized Marks\n\n")
            for row in excluded_rows:
                out.write(
                    f"- `U+{ord(row.char):04X}` {_escape_inline(_display_char(row.char))} "
                    f"({row.name}) - headword hits {row.total:,}\n"
                )
            out.write("\n")

        for row in kept_rows:
            codepoint = f"U+{ord(row.char):04X}"
            out.write(f"## `{codepoint}` {_escape_inline(_display_char(row.char))}\n\n")
            out.write(f"- Unicode name: {row.name}\n")
            out.write(f"- Category: `{row.category}`\n")
            out.write(f"- Headword hits: {row.total:,}\n")
            out.write(f"- Dictionaries containing it: {row.dicts:,}\n")
            per_dict = "; ".join(
                f"{label}: {count:,}"
                for label, count in sorted(
                    per_dict_counts.get(row.char, {}).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            out.write(f"- Per-dictionary headword totals: {per_dict}\n")
            out.write("- Examples:\n")
            sample_rows = examples.get(row.char, [])
            for idx, (_, label, surface) in enumerate(sample_rows[:10], 1):
                out.write(f"  {idx}. `{label}` | {_escape_inline(surface)}\n")
            out.write("\n")


def _escape_inline(text: str) -> str:
    return str(text or "").replace("`", "\\`")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a headword-only high-frequency mark report with examples.",
    )
    parser.add_argument(
        "--out",
        default="reports/headword_non_script_marks_headwords_only_remaining_over_100_examples.md",
        help="Output markdown path",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="Only consider marks whose headword-only total is strictly greater than this value",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=10,
        help="Number of real headword surfaces to include per remaining mark",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed used for deterministic pseudo-random example sampling",
    )
    args = parser.parse_args()

    probe._set_csv_limit()
    total_counts, per_dict_counts, examples = _scan_headwords_only(
        seed=int(args.seed),
        examples_per_mark=int(args.examples),
    )
    rows = _build_rows(total_counts, per_dict_counts)
    candidates = [row for row in rows if row.total > int(args.threshold)]
    excluded = [row for row in candidates if _normalized_out(row.char)]
    kept = [row for row in candidates if not _normalized_out(row.char)]
    _write_report(
        output_path=(ROOT / args.out).resolve(),
        threshold=int(args.threshold),
        excluded_rows=excluded,
        kept_rows=kept,
        per_dict_counts=per_dict_counts,
        examples=examples,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
