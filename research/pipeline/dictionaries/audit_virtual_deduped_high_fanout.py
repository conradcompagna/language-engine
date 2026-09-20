#!/usr/bin/env python3
"""
Read-only virtual-dedupe audit for high-fanout form texts.

For each live SQLite dictionary:
1. Collapse duplicate entries whose (headword, romanization, pos, glosses) are identical.
2. Virtually migrate form rows from duplicate entries onto the survivor.
3. Deduplicate form rows per survivor entry by (form_text, morph_tags, romanization).
4. Recompute form_text fanout across distinct headwords.

Outputs per-language TSVs and a rebuilt master report. The source databases are
never modified.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

CHUNK_SIZE = 5000
HIGH_FANOUT_OTHER_HEADWORDS = 10
HIGH_FANOUT_HEADWORD_THRESHOLD = HIGH_FANOUT_OTHER_HEADWORDS + 1

PER_DB_OUTPUT_NAME = "forms_over_10_distinct_headwords_virtual_dedupe.tsv"
ROOT_TSV_NAME = "ALL_FORMS_OVER_10_DISTINCT_HEADWORDS_VIRTUAL_DEDUPE.tsv"
ROOT_MD_NAME = "ALL_FORMS_OVER_10_DISTINCT_HEADWORDS_VIRTUAL_DEDUPE.md"


def _log(message: str) -> None:
    print(message, flush=True)


def _open_db(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _iter_query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Iterator[sqlite3.Row]:
    cur = conn.execute(sql, params)
    while True:
        rows = cur.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        for row in rows:
            yield row


def _write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _safe_join(texts: list[str]) -> str:
    return " | ".join(str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip() for text in texts)


def _md_escape(text: object) -> str:
    return str(text or "").replace("|", "\\|")


@dataclass
class DbResult:
    db: str
    rows: list[dict[str, object]]
    duplicate_entry_count: int
    unique_entry_count: int
    scanned_form_row_count: int
    deduped_form_occurrence_count: int


def _discover_db_paths(selected: list[str]) -> list[Path]:
    all_paths = sorted(path for path in SQLITE_DIR.glob("*.sqlite"))
    if not selected:
        return all_paths
    selected_set = {item.strip() for item in selected if item.strip()}
    out: list[Path] = []
    for path in all_paths:
        if path.name in selected_set or path.stem in selected_set:
            out.append(path)
    return out


def _build_survivor_map(conn: sqlite3.Connection) -> tuple[dict[int, int], list[str], int]:
    sql = """
        SELECT
            id,
            TRIM(COALESCE(headword, '')) AS headword,
            TRIM(COALESCE(romanization, '')) AS romanization,
            TRIM(COALESCE(pos, '')) AS pos,
            TRIM(COALESCE(glosses, '')) AS glosses
        FROM entries
        ORDER BY id
    """
    key_to_survivor: dict[tuple[str, str, str, str], int] = {}
    entry_to_survivor: dict[int, int] = {}
    survivor_headwords: list[str] = []
    duplicate_entry_count = 0
    for row in _iter_query(conn, sql):
        headword = str(row["headword"] or "").strip()
        romanization = str(row["romanization"] or "").strip()
        pos = str(row["pos"] or "").strip()
        glosses = str(row["glosses"] or "").strip()
        dedupe_key = (headword, romanization, pos, glosses)
        survivor_id = key_to_survivor.get(dedupe_key)
        if survivor_id is None:
            survivor_id = len(survivor_headwords)
            key_to_survivor[dedupe_key] = survivor_id
            survivor_headwords.append(headword)
        else:
            duplicate_entry_count += 1
        entry_to_survivor[int(row["id"])] = survivor_id
    return entry_to_survivor, survivor_headwords, duplicate_entry_count


def _finalize_form_bucket(
    rows: list[dict[str, object]],
    current_form_text: str,
    entry_fanout_count: int,
    sample_tagsets: list[str],
    sample_headwords: list[str],
) -> None:
    if not current_form_text:
        return
    if entry_fanout_count < HIGH_FANOUT_HEADWORD_THRESHOLD:
        return
    rows.append(
        {
            "form_text": current_form_text,
            "entry_fanout_count": entry_fanout_count,
            "sample_form_tagsets": _safe_join(sample_tagsets),
            "sample_headwords": _safe_join(sample_headwords),
        }
    )


def _scan_high_fanout_forms(
    conn: sqlite3.Connection,
    entry_to_survivor: dict[int, int],
    survivor_headwords: list[str],
) -> tuple[list[dict[str, object]], int]:
    sql = """
        SELECT
            f.entry_id AS entry_id,
            TRIM(COALESCE(f.form_text, '')) AS form_text,
            TRIM(COALESCE(f.morph_tags, '')) AS morph_tags,
            TRIM(COALESCE(f.romanization, '')) AS form_romanization
        FROM forms f
        WHERE TRIM(COALESCE(f.form_text, '')) != ''
        ORDER BY
            TRIM(COALESCE(f.form_text, '')),
            f.entry_id,
            TRIM(COALESCE(f.morph_tags, '')),
            TRIM(COALESCE(f.romanization, ''))
    """

    out_rows: list[dict[str, object]] = []
    deduped_form_occurrence_count = 0

    current_form_text = ""
    seen_variant_keys: set[tuple[int, str, str]] = set()
    seen_survivor_ids: set[int] = set()
    seen_headwords: set[str] = set()
    seen_tagsets: set[str] = set()
    sample_headwords: list[str] = []
    sample_tagsets: list[str] = []
    entry_fanout_count = 0

    for row in _iter_query(conn, sql):
        form_text = str(row["form_text"] or "").strip()
        if not form_text:
            continue
        if current_form_text and form_text != current_form_text:
            _finalize_form_bucket(
                out_rows,
                current_form_text,
                entry_fanout_count,
                sample_tagsets,
                sample_headwords,
            )
            seen_variant_keys = set()
            seen_survivor_ids = set()
            seen_headwords = set()
            seen_tagsets = set()
            sample_headwords = []
            sample_tagsets = []
            entry_fanout_count = 0
        current_form_text = form_text

        entry_id = int(row["entry_id"] or 0)
        survivor_id = entry_to_survivor.get(entry_id)
        if survivor_id is None:
            continue

        morph_tags = str(row["morph_tags"] or "").strip()
        form_romanization = str(row["form_romanization"] or "").strip()
        variant_key = (survivor_id, morph_tags, form_romanization)
        if variant_key in seen_variant_keys:
            continue
        seen_variant_keys.add(variant_key)
        deduped_form_occurrence_count += 1

        if survivor_id not in seen_survivor_ids:
            seen_survivor_ids.add(survivor_id)
            entry_fanout_count += 1
        headword = survivor_headwords[survivor_id] if 0 <= survivor_id < len(survivor_headwords) else ""
        if headword not in seen_headwords:
            seen_headwords.add(headword)
            if len(sample_headwords) < 10:
                sample_headwords.append(headword)
        if morph_tags not in seen_tagsets:
            seen_tagsets.add(morph_tags)
            if len(sample_tagsets) < 10:
                sample_tagsets.append(morph_tags)

    _finalize_form_bucket(
        out_rows,
        current_form_text,
        entry_fanout_count,
        sample_tagsets,
        sample_headwords,
    )

    out_rows.sort(
        key=lambda row: (
            -int(row["entry_fanout_count"]),
            str(row["form_text"] or "").casefold(),
        )
    )
    return out_rows, deduped_form_occurrence_count


def _audit_one_db(path: Path, report_dir: Path) -> DbResult | None:
    if path.stat().st_size == 0:
        _log(f"[virtual-dedupe] {path.stem}: skipped zero-byte database")
        return None

    db_name = path.stem
    _log(f"[virtual-dedupe] {db_name}: opening")
    conn = _open_db(path)
    try:
        _log(f"[virtual-dedupe] {db_name}: building survivor map")
        entry_to_survivor, survivor_headwords, duplicate_entry_count = _build_survivor_map(conn)
        unique_entry_count = len(survivor_headwords)
        scanned_form_row_count = int(conn.execute("SELECT COUNT(*) FROM forms").fetchone()[0] or 0)

        _log(f"[virtual-dedupe] {db_name}: scanning forms")
        rows, deduped_form_occurrence_count = _scan_high_fanout_forms(conn, entry_to_survivor, survivor_headwords)
    finally:
        conn.close()

    if not rows:
        _log(f"[virtual-dedupe] {db_name}: no forms above threshold after virtual dedupe")
        return DbResult(
            db=db_name,
            rows=[],
            duplicate_entry_count=duplicate_entry_count,
            unique_entry_count=unique_entry_count,
            scanned_form_row_count=scanned_form_row_count,
            deduped_form_occurrence_count=deduped_form_occurrence_count,
        )

    out_dir = report_dir / db_name
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        out_dir / PER_DB_OUTPUT_NAME,
        ["form_text", "entry_fanout_count", "sample_form_tagsets", "sample_headwords"],
        rows,
    )
    _log(f"[virtual-dedupe] {db_name}: wrote {len(rows):,} rows")
    return DbResult(
        db=db_name,
        rows=rows,
        duplicate_entry_count=duplicate_entry_count,
        unique_entry_count=unique_entry_count,
        scanned_form_row_count=scanned_form_row_count,
        deduped_form_occurrence_count=deduped_form_occurrence_count,
    )


def _write_root_outputs(report_dir: Path, results: list[DbResult], generated_at: str) -> None:
    flat_rows: list[dict[str, object]] = []
    for result in results:
        for row in result.rows:
            flat_rows.append(
                {
                    "db": result.db,
                    "form_text": row["form_text"],
                    "entry_fanout_count": row["entry_fanout_count"],
                    "sample_form_tagsets": row["sample_form_tagsets"],
                    "sample_headwords": row["sample_headwords"],
                }
            )
    flat_rows.sort(
        key=lambda row: (
            str(row["db"]),
            -int(row["entry_fanout_count"]),
            str(row["form_text"] or "").casefold(),
        )
    )
    _write_tsv(
        report_dir / ROOT_TSV_NAME,
        ["db", "form_text", "entry_fanout_count", "sample_form_tagsets", "sample_headwords"],
        flat_rows,
    )

    total_rows = sum(len(result.rows) for result in results)
    lines = [
        "# Virtually Deduped High-Fanout Forms",
        "",
        f"- generated_at: `{generated_at}`",
        f"- source_dir: `{SQLITE_DIR}`",
        "- virtual dedupe of entries by identical `(headword, romanization, pos, glosses)`",
        "- virtual dedupe of form rows by identical `(form_text, morph_tags, romanization)` per surviving entry",
        f"- threshold: more than `{HIGH_FANOUT_OTHER_HEADWORDS}` surviving entry paradigms",
        f"- languages with results: `{sum(1 for result in results if result.rows):,}`",
        f"- total forms listed: `{total_rows:,}`",
        "",
        "## Overview",
        "",
        "| Language | Form Count | Top Form | Top Count | Duplicate Entries Collapsed |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for result in results:
        if not result.rows:
            continue
        top = result.rows[0]
        lines.append(
            f"| `{result.db}` | `{len(result.rows):,}` | `{_md_escape(top['form_text'])}` | "
            f"`{int(top['entry_fanout_count']):,}` | `{result.duplicate_entry_count:,}` |"
        )

    for result in results:
        if not result.rows:
            continue
        lines.extend(
            [
                "",
                f"## {result.db}",
                "",
                f"Source: `{result.db}/{PER_DB_OUTPUT_NAME}`",
                "",
                "| Form Text | Entry Fanout Count | Sample Form Tagsets | Sample Headwords |",
                "| --- | ---: | --- | --- |",
            ]
        )
        for row in result.rows:
            lines.append(
                f"| `{_md_escape(row['form_text'])}` | `{int(row['entry_fanout_count']):,}` | "
                f"`{_md_escape(row['sample_form_tagsets'])}` | `{_md_escape(row['sample_headwords'])}` |"
            )

    (report_dir / ROOT_MD_NAME).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only virtual-dedupe high-fanout audit")
    parser.add_argument("db", nargs="*", help="Optional database stems or filenames to audit")
    parser.add_argument(
        "--report-dir",
        default="reports/sqlite_prune_probe_full_20260421",
        help="Existing report directory to write outputs into",
    )
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        raise SystemExit("No matching .sqlite files found in dict_sqlite/")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    results: list[DbResult] = []
    for path in db_paths:
        result = _audit_one_db(path, report_dir)
        if result is not None:
            results.append(result)

    _write_root_outputs(report_dir, results, generated_at)
    _log(f"[virtual-dedupe] done: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
