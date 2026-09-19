#!/usr/bin/env python3
"""
Compile per-language simplified fanout TSVs into a single markdown document.

Input files:
  reports/.../<lang>/forms_over_10_distinct_headwords.tsv

Output file:
  reports/.../ALL_FORMS_OVER_10_DISTINCT_HEADWORDS.md

This script only reads and writes report artifacts.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path


INPUT_NAME = "forms_over_10_distinct_headwords.tsv"
OUTPUT_NAME = "ALL_FORMS_OVER_10_DISTINCT_HEADWORDS.md"


def _to_int(value: object) -> int:
    try:
        return int(str(value or "").strip() or "0")
    except Exception:
        return 0


def _esc(text: object) -> str:
    return str(text or "").replace("|", "\\|")


@dataclass
class LanguageList:
    db: str
    path: Path
    rows: list[dict[str, object]]


def _read_one(path: Path) -> LanguageList | None:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = []
        for row in reader:
            form_text = str(row.get("form_text") or "").strip()
            if not form_text:
                continue
            rows.append(
                {
                    "form_text": form_text,
                    "distinct_headword_count": _to_int(row.get("distinct_headword_count")),
                }
            )
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            -_to_int(row.get("distinct_headword_count")),
            str(row.get("form_text") or "").casefold(),
        )
    )
    return LanguageList(db=path.parent.name, path=path, rows=rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile simplified high-fanout TSVs into one markdown document")
    parser.add_argument("report_dir", help="Path to a generated prune audit report directory")
    args = parser.parse_args()

    root = Path(args.report_dir)
    if not root.exists():
        raise SystemExit(f"Report directory not found: {root}")

    lang_lists: list[LanguageList] = []
    for path in sorted(root.rglob(INPUT_NAME)):
        lang_list = _read_one(path)
        if lang_list is not None:
            lang_lists.append(lang_list)

    total_rows = sum(len(item.rows) for item in lang_lists)
    lines = [
        "# Simplified High-Fanout Forms",
        "",
        f"- source_dir: `{root}`",
        "- criterion: form appears in more than `10` distinct headword paradigms",
        f"- languages: `{len(lang_lists)}`",
        f"- total forms listed: `{total_rows:,}`",
        "",
        "## Overview",
        "",
        "| Language | Form Count | Top Form | Top Count |",
        "| --- | ---: | --- | ---: |",
    ]
    for item in lang_lists:
        top = item.rows[0]
        lines.append(
            f"| `{item.db}` | `{len(item.rows):,}` | `{_esc(top['form_text'])}` | `{_to_int(top['distinct_headword_count']):,}` |"
        )

    for item in lang_lists:
        lines.extend(
            [
                "",
                f"## {item.db}",
                "",
                f"Source: `{item.path.relative_to(root)}`",
                "",
                "| Form Text | Distinct Headword Count |",
                "| --- | ---: |",
            ]
        )
        for row in item.rows:
            lines.append(
                f"| `{_esc(row['form_text'])}` | `{_to_int(row['distinct_headword_count']):,}` |"
            )

    out_path = root / OUTPUT_NAME
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[compile] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
