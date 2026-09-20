#!/usr/bin/env python3
"""
Create distinct-form companion TSVs for existing prune audit reports.

This only reads and rewrites report artifacts. It does not touch the source
SQLite databases.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


TARGET_FILES = {
    "forms_high_fanout_rows.tsv": "forms_high_fanout_distinct.tsv",
    "forms_meta_or_note_text.tsv": "forms_meta_or_note_text_distinct.tsv",
    "forms_no_shared_letters_same_script.tsv": "forms_no_shared_letters_same_script_distinct.tsv",
    "forms_no_shared_letters_cross_script_or_cjk.tsv": "forms_no_shared_letters_cross_script_or_cjk_distinct.tsv",
    "forms_duplicate_groups.tsv": "forms_duplicate_groups_distinct.tsv",
}


def _to_int(value: object) -> int:
    try:
        return int(str(value or "").strip() or "0")
    except Exception:
        return 0


def _push_limited(bucket: list[str], seen: set[str], raw: object, *, limit: int = 8) -> None:
    text = str(raw or "").strip()
    if not text or text in seen or len(bucket) >= limit:
        return
    seen.add(text)
    bucket.append(text)


def _collapse_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []

    for row in rows:
        form_text = str(row.get("form_text") or "").strip()
        if not form_text:
            continue
        group = grouped.get(form_text)
        if group is None:
            group = {
                "form_text": form_text,
                "fanout_entry_count": _to_int(row.get("fanout_entry_count")),
                "fanout_other_entry_count": _to_int(row.get("fanout_other_entry_count")),
                "fanout_row_count": _to_int(row.get("fanout_row_count")),
                "report_row_count": 0,
                "report_distinct_entry_count": 0,
                "sample_headwords": [],
                "_sample_headwords_seen": set(),
                "sample_pos": [],
                "_sample_pos_seen": set(),
                "sample_morph_tags": [],
                "_sample_morph_tags_seen": set(),
                "meta_reasons": [],
                "_meta_reasons_seen": set(),
                "script_pairs": [],
                "_script_pairs_seen": set(),
                "duplicate_group_count": 0,
                "duplicate_extra_rows_total": 0,
                "_entry_ids_seen": set(),
            }
            grouped[form_text] = group
            order.append(form_text)

        group["report_row_count"] = int(group["report_row_count"]) + 1
        group["fanout_entry_count"] = max(int(group["fanout_entry_count"]), _to_int(row.get("fanout_entry_count")))
        group["fanout_other_entry_count"] = max(int(group["fanout_other_entry_count"]), _to_int(row.get("fanout_other_entry_count")))
        group["fanout_row_count"] = max(int(group["fanout_row_count"]), _to_int(row.get("fanout_row_count")))

        entry_id = str(row.get("entry_id") or "").strip()
        if entry_id and entry_id not in group["_entry_ids_seen"]:
            group["_entry_ids_seen"].add(entry_id)
            group["report_distinct_entry_count"] = int(group["report_distinct_entry_count"]) + 1

        _push_limited(group["sample_headwords"], group["_sample_headwords_seen"], row.get("headword"))
        _push_limited(group["sample_pos"], group["_sample_pos_seen"], row.get("pos"))
        _push_limited(group["sample_morph_tags"], group["_sample_morph_tags_seen"], row.get("morph_tags"))
        _push_limited(group["meta_reasons"], group["_meta_reasons_seen"], row.get("meta_reason"))

        head_script = str(row.get("headword_script") or "").strip()
        form_script = str(row.get("form_script") or "").strip()
        if head_script or form_script:
            pair = f"{head_script}->{form_script}".strip("->")
            _push_limited(group["script_pairs"], group["_script_pairs_seen"], pair)

        group["duplicate_group_count"] = int(group["duplicate_group_count"]) + (1 if row.get("duplicate_count") else 0)
        group["duplicate_extra_rows_total"] = int(group["duplicate_extra_rows_total"]) + _to_int(row.get("extra_rows"))

    out: list[dict[str, object]] = []
    for form_text in order:
        group = grouped[form_text]
        out.append(
            {
                "form_text": group["form_text"],
                "fanout_entry_count": group["fanout_entry_count"],
                "fanout_other_entry_count": group["fanout_other_entry_count"],
                "fanout_row_count": group["fanout_row_count"],
                "report_row_count": group["report_row_count"],
                "report_distinct_entry_count": group["report_distinct_entry_count"],
                "duplicate_group_count": group["duplicate_group_count"],
                "duplicate_extra_rows_total": group["duplicate_extra_rows_total"],
                "sample_headwords": " | ".join(group["sample_headwords"]),
                "sample_pos": " | ".join(group["sample_pos"]),
                "sample_morph_tags": " | ".join(group["sample_morph_tags"]),
                "meta_reasons": " | ".join(group["meta_reasons"]),
                "script_pairs": " | ".join(group["script_pairs"]),
            }
        )

    out.sort(
        key=lambda row: (
            -_to_int(row.get("fanout_other_entry_count")),
            -_to_int(row.get("fanout_entry_count")),
            -_to_int(row.get("fanout_row_count")),
            -_to_int(row.get("report_row_count")),
            str(row.get("form_text") or "").casefold(),
        )
    )
    return out


def _process_file(path: Path, output_name: str) -> bool:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = list(reader)
    if not rows:
        return False
    collapsed = _collapse_rows(rows)
    if not collapsed:
        return False

    out_path = path.with_name(output_name)
    headers = [
        "form_text",
        "fanout_entry_count",
        "fanout_other_entry_count",
        "fanout_row_count",
        "report_row_count",
        "report_distinct_entry_count",
        "duplicate_group_count",
        "duplicate_extra_rows_total",
        "sample_headwords",
        "sample_pos",
        "sample_morph_tags",
        "meta_reasons",
        "script_pairs",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(collapsed)
    print(f"[dedupe] {out_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Create deduped distinct-form prune report TSVs")
    parser.add_argument("report_dir", help="Path to a generated prune audit report directory")
    args = parser.parse_args()

    root = Path(args.report_dir)
    if not root.exists():
        raise SystemExit(f"Report directory not found: {root}")

    updated = 0
    for input_name, output_name in TARGET_FILES.items():
        for path in sorted(root.rglob(input_name)):
            if _process_file(path, output_name):
                updated += 1
    print(f"[dedupe] updated_files={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
