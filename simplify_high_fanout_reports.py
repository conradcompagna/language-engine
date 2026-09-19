#!/usr/bin/env python3
"""
Create minimal per-language high-fanout TSVs from existing grouped reports.

Input: forms_high_fanout_groups.tsv
Output: forms_over_10_distinct_headwords.tsv

Only touches report artifacts, never the source SQLite databases.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


INPUT_NAME = "forms_high_fanout_groups.tsv"
OUTPUT_NAME = "forms_over_10_distinct_headwords.tsv"


def _to_int(value: object) -> int:
    try:
        return int(str(value or "").strip() or "0")
    except Exception:
        return 0


def _process_file(path: Path) -> bool:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
    if not rows:
        return False

    simple_rows = [
        {
            "form_text": str(row.get("form_text") or "").strip(),
            "distinct_headword_count": _to_int(row.get("fanout_entry_count")),
        }
        for row in rows
        if str(row.get("form_text") or "").strip()
    ]
    simple_rows.sort(
        key=lambda row: (
            -_to_int(row.get("distinct_headword_count")),
            str(row.get("form_text") or "").casefold(),
        )
    )

    out_path = path.with_name(OUTPUT_NAME)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["form_text", "distinct_headword_count"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(simple_rows)
    print(f"[simplify] {out_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Create minimal high-fanout report TSVs")
    parser.add_argument("report_dir", help="Path to a generated prune audit report directory")
    args = parser.parse_args()

    root = Path(args.report_dir)
    if not root.exists():
        raise SystemExit(f"Report directory not found: {root}")

    updated = 0
    for path in sorted(root.rglob(INPUT_NAME)):
        if _process_file(path):
            updated += 1
    print(f"[simplify] updated_files={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
