#!/usr/bin/env python3
"""
Phase 1 read-only pruning dry run.

This script does not mutate any SQLite database. It:
1. Drops bunk headwords by gloss quality.
2. Virtually deduplicates surviving entries by (headword, romanization, pos, glosses).
3. Virtually deduplicates surviving form rows by (form_text, morph_tags, romanization) per survivor entry.
4. Applies form pruning rules and writes per-database cut lists.

Per database output:
- cut_headwords.tsv
- cut_forms.tsv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sqlite_prune_policy import (
    choose_bucket_cut_reason,
    entry_cut_reason,
    occurrence_cut_reason,
    parse_glosses,
    surface_fanout_cut_reason,
)


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

CHUNK_SIZE = 5000
SAMPLE_LIMIT = 10
DEFAULT_OUT_DIR_NAME = f"sqlite_prune_phase1_{time.strftime('%Y%m%d')}"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _safe_preview(text: str, *, limit: int = 120) -> str:
    s = str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "..."


def _safe_join(texts: list[str]) -> str:
    cleaned: list[str] = []
    for text in texts:
        item = str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
        if not item:
            item = "(none)"
        cleaned.append(item)
    return " | ".join(cleaned)


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


def _gloss_preview(raw_glosses: str) -> str:
    glosses, _parse_error = parse_glosses(raw_glosses)
    if not glosses:
        return ""
    return " | ".join(_safe_preview(gloss, limit=90) for gloss in glosses[:4])


@dataclass
class DbResult:
    db: str
    entry_count: int
    surviving_entry_count: int
    cut_headword_count: int
    cut_form_count: int


def _build_survivor_context(
    conn: sqlite3.Connection,
) -> tuple[dict[int, int], list[str], list[dict[str, object]], int]:
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
    cut_headwords_by_key: dict[tuple[str, str, str, str], dict[str, object]] = {}
    entry_count = 0

    for row in _iter_query(conn, sql):
        entry_count += 1
        entry_id = int(row["id"] or 0)
        headword = str(row["headword"] or "").strip()
        romanization = str(row["romanization"] or "").strip()
        pos = str(row["pos"] or "").strip()
        glosses = str(row["glosses"] or "").strip()

        cut_reason = entry_cut_reason(glosses)
        if cut_reason:
            cut_key = (headword, romanization, pos, cut_reason)
            if cut_key not in cut_headwords_by_key:
                cut_headwords_by_key[cut_key] = {
                    "headword": headword,
                    "romanization": romanization,
                    "pos": pos,
                    "cut_reason": cut_reason,
                    "gloss_preview": _gloss_preview(glosses),
                }
            continue

        dedupe_key = (headword, romanization, pos, glosses)
        survivor_id = key_to_survivor.get(dedupe_key)
        if survivor_id is None:
            survivor_id = len(survivor_headwords)
            key_to_survivor[dedupe_key] = survivor_id
            survivor_headwords.append(headword)
        entry_to_survivor[entry_id] = survivor_id

    cut_headword_rows = sorted(
        cut_headwords_by_key.values(),
        key=lambda row: (
            str(row["cut_reason"] or ""),
            str(row["headword"] or "").casefold(),
            str(row["romanization"] or "").casefold(),
            str(row["pos"] or "").casefold(),
        ),
    )
    return entry_to_survivor, survivor_headwords, cut_headword_rows, entry_count


def _finalize_form_bucket(
    rows: list[dict[str, object]],
    db_name: str,
    current_form_text: str,
    total_survivor_ids: set[int],
    live_survivor_ids: set[int],
    occurrence_cut_reasons: list[str],
    sample_tagsets: list[str],
    sample_headwords: list[str],
) -> None:
    if not current_form_text or not total_survivor_ids:
        return

    final_reason = ""
    if live_survivor_ids:
        fanout_reason = surface_fanout_cut_reason(db_name, current_form_text, len(live_survivor_ids))
        if fanout_reason == "fanout_gt_10":
            final_reason = fanout_reason
    else:
        final_reason = choose_bucket_cut_reason(occurrence_cut_reasons)

    if not final_reason:
        return

    rows.append(
        {
            "form_text": current_form_text,
            "entry_fanout_count": len(total_survivor_ids),
            "cut_reason": final_reason,
            "sample_form_tagsets": _safe_join(sample_tagsets),
            "sample_headwords": _safe_join(sample_headwords),
        }
    )


def _scan_form_cuts(
    conn: sqlite3.Connection,
    db_name: str,
    entry_to_survivor: dict[int, int],
    survivor_headwords: list[str],
) -> list[dict[str, object]]:
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

    current_form_text = ""
    seen_variant_keys: set[tuple[int, str, str]] = set()
    total_survivor_ids: set[int] = set()
    live_survivor_ids: set[int] = set()
    occurrence_cut_reasons: list[str] = []
    seen_headwords: set[str] = set()
    seen_tagsets: set[str] = set()
    sample_headwords: list[str] = []
    sample_tagsets: list[str] = []

    def reset_bucket() -> None:
        nonlocal seen_variant_keys
        nonlocal total_survivor_ids
        nonlocal live_survivor_ids
        nonlocal occurrence_cut_reasons
        nonlocal seen_headwords
        nonlocal seen_tagsets
        nonlocal sample_headwords
        nonlocal sample_tagsets
        seen_variant_keys = set()
        total_survivor_ids = set()
        live_survivor_ids = set()
        occurrence_cut_reasons = []
        seen_headwords = set()
        seen_tagsets = set()
        sample_headwords = []
        sample_tagsets = []

    for row in _iter_query(conn, sql):
        form_text = str(row["form_text"] or "").strip()
        if not form_text:
            continue

        if current_form_text and form_text != current_form_text:
            _finalize_form_bucket(
                out_rows,
                db_name,
                current_form_text,
                total_survivor_ids,
                live_survivor_ids,
                occurrence_cut_reasons,
                sample_tagsets,
                sample_headwords,
            )
            reset_bucket()
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

        total_survivor_ids.add(survivor_id)
        headword = survivor_headwords[survivor_id] if 0 <= survivor_id < len(survivor_headwords) else ""

        if headword not in seen_headwords and len(sample_headwords) < SAMPLE_LIMIT:
            seen_headwords.add(headword)
            sample_headwords.append(headword)
        else:
            seen_headwords.add(headword)

        tag_label = morph_tags or "(none)"
        if tag_label not in seen_tagsets and len(sample_tagsets) < SAMPLE_LIMIT:
            seen_tagsets.add(tag_label)
            sample_tagsets.append(tag_label)
        else:
            seen_tagsets.add(tag_label)

        occurrence_reason = occurrence_cut_reason(db_name, form_text, headword, morph_tags)
        if occurrence_reason:
            occurrence_cut_reasons.append(occurrence_reason)
        else:
            live_survivor_ids.add(survivor_id)

    _finalize_form_bucket(
        out_rows,
        db_name,
        current_form_text,
        total_survivor_ids,
        live_survivor_ids,
        occurrence_cut_reasons,
        sample_tagsets,
        sample_headwords,
    )

    out_rows.sort(
        key=lambda row: (
            -int(row["entry_fanout_count"]),
            str(row["cut_reason"] or ""),
            str(row["form_text"] or "").casefold(),
        )
    )
    return out_rows


def _write_readme(path: Path) -> None:
    lines = [
        "# SQLite Prune Phase 1",
        "",
        "This folder is a read-only dry run. The source `.sqlite` files were not modified.",
        "",
        "Pipeline order:",
        "1. Cut headwords with missing, symbol-only, or non-Latin-only glosses.",
        "2. Virtually dedupe surviving entries by `(headword, romanization, pos, glosses)`.",
        "3. Virtually dedupe form rows per survivor by `(form_text, morph_tags, romanization)`.",
        "4. Cut form rows by exact blacklists, hard tags, text rules, Rule A, then default `fanout > 10`.",
        "",
        "Per-DB files:",
        "- `cut_headwords.tsv`: `headword`, `romanization`, `pos`, `cut_reason`, `gloss_preview`",
        "- `cut_forms.tsv`: `form_text`, `entry_fanout_count`, `cut_reason`, `sample_form_tagsets`, `sample_headwords`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _audit_one_db(path: Path, out_root: Path) -> DbResult | None:
    db_name = path.stem
    db_dir = out_root / db_name
    if path.stat().st_size == 0:
        _log(f"[phase1] {db_name}: zero-byte database, writing empty cut lists")
        _write_tsv(
            db_dir / "cut_headwords.tsv",
            ["headword", "romanization", "pos", "cut_reason", "gloss_preview"],
            [],
        )
        _write_tsv(
            db_dir / "cut_forms.tsv",
            ["form_text", "entry_fanout_count", "cut_reason", "sample_form_tagsets", "sample_headwords"],
            [],
        )
        return DbResult(
            db=db_name,
            entry_count=0,
            surviving_entry_count=0,
            cut_headword_count=0,
            cut_form_count=0,
        )

    _log(f"[phase1] {db_name}: opening")
    conn = _open_db(path)
    try:
        _log(f"[phase1] {db_name}: scanning headwords")
        entry_to_survivor, survivor_headwords, cut_headword_rows, entry_count = _build_survivor_context(conn)

        _log(f"[phase1] {db_name}: scanning forms")
        cut_form_rows = _scan_form_cuts(conn, db_name, entry_to_survivor, survivor_headwords)

        _write_tsv(
            db_dir / "cut_headwords.tsv",
            ["headword", "romanization", "pos", "cut_reason", "gloss_preview"],
            cut_headword_rows,
        )
        _write_tsv(
            db_dir / "cut_forms.tsv",
            ["form_text", "entry_fanout_count", "cut_reason", "sample_form_tagsets", "sample_headwords"],
            cut_form_rows,
        )

        _log(
            f"[phase1] {db_name}: wrote {len(cut_headword_rows):,} cut headwords, "
            f"{len(cut_form_rows):,} cut forms"
        )
        return DbResult(
            db=db_name,
            entry_count=entry_count,
            surviving_entry_count=len(survivor_headwords),
            cut_headword_count=len(cut_headword_rows),
            cut_form_count=len(cut_form_rows),
        )
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        action="append",
        default=[],
        help="Limit to a specific DB stem or filename. Repeatable.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPORTS_DIR / DEFAULT_OUT_DIR_NAME),
        help="Output directory. Default: reports/sqlite_prune_phase1_YYYYMMDD",
    )
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        _log("[phase1] no matching sqlite databases found")
        return 1

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    _write_readme(out_root / "README.md")

    results: list[DbResult] = []
    started = time.perf_counter()
    for path in db_paths:
        result = _audit_one_db(path, out_root)
        if result is not None:
            results.append(result)

    summary_rows = [
        {
            "db": item.db,
            "entry_count": item.entry_count,
            "surviving_entry_count": item.surviving_entry_count,
            "cut_headword_count": item.cut_headword_count,
            "cut_form_count": item.cut_form_count,
        }
        for item in sorted(results, key=lambda item: item.db)
    ]
    _write_tsv(
        out_root / "SUMMARY.tsv",
        ["db", "entry_count", "surviving_entry_count", "cut_headword_count", "cut_form_count"],
        summary_rows,
    )

    elapsed = time.perf_counter() - started
    _log(
        f"[phase1] completed {len(results)} DBs in {elapsed:.1f}s -> {out_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
