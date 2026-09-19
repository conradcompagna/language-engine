#!/usr/bin/env python3
"""
Resort existing prune-audit TSVs in place using their existing fanout columns.

This does not touch the source SQLite databases. It only rewrites report TSVs
that already contain fanout metadata, primarily the `forms_high_fanout_*`
reports under a generated audit folder.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _to_int(value: object) -> int:
    try:
        return int(str(value or "").strip() or "0")
    except Exception:
        return 0


def _sort_key(row: dict[str, str]) -> tuple[object, ...]:
    return (
        -_to_int(row.get("fanout_other_entry_count")),
        -_to_int(row.get("fanout_entry_count")),
        -_to_int(row.get("fanout_row_count")),
        -_to_int(row.get("duplicate_count")),
        str(row.get("form_text") or "").casefold(),
        str(row.get("headword") or "").casefold(),
        _to_int(row.get("form_id") or row.get("entry_id")),
    )


def _resort_tsv(path: Path) -> bool:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        headers = list(reader.fieldnames or [])
        if "fanout_other_entry_count" not in headers:
            return False
        rows = list(reader)
    rows.sort(key=_sort_key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Resort prune audit TSVs in place")
    parser.add_argument("report_dir", help="Path to a generated prune audit report directory")
    args = parser.parse_args()

    root = Path(args.report_dir)
    if not root.exists():
        raise SystemExit(f"Report directory not found: {root}")

    updated = 0
    for path in sorted(root.rglob("*.tsv")):
        if _resort_tsv(path):
            updated += 1
            print(f"[resort] {path}")
    print(f"[resort] updated_files={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
