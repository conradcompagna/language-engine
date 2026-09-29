#!/usr/bin/env python3
"""
Read-only audit for form rows whose form text shares no significant character
with the parent headword.

Exclusions:
- East Asian / CJK-family databases are skipped entirely.
- Romanization-like / transliteration-like form rows are skipped.

Output:
- reports/sqlite_nonshared_form_chars_<date>/SUMMARY.tsv
- reports/sqlite_nonshared_form_chars_<date>/SUMMARY.md
- reports/sqlite_nonshared_form_chars_<date>/<db>/nonshared_forms.tsv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Iterator

from sqlite_prune_policy import normalize_db_name, split_tags_casefold


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"
CHUNK_SIZE = 5000
DEFAULT_OUT_DIR_NAME = f"sqlite_nonshared_form_chars_{time.strftime('%Y%m%d')}"

EXCLUDED_DBS = frozenset({
    "ja",
    "ja-jmdict",
    "ko",
    "ko-krdict",
    "zh",
    "zh-hant",
    "zh-cc-cedict",
    "zh-hant-cc-cedict",
    "lzh",
    "lzh-wiktionary",
    "vi",
})

ROMANIZATION_TAG_NEEDLES = (
    "romanization",
    "romanisation",
    "transliteration",
    "transcription",
    "romaji",
    "pinyin",
    "bopomofo",
    "jyutping",
    "mccune",
    "yale",
    "revised romanization",
)


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


def _has_required_tables(conn: sqlite3.Connection) -> bool:
    names = {str(row[0] or "").strip().casefold() for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return "entries" in names and "forms" in names


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


def _safe_cell(text: str) -> str:
    return str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _is_romanization_like(raw_tags: str) -> bool:
    for tag in split_tags_casefold(raw_tags):
        for needle in ROMANIZATION_TAG_NEEDLES:
            if needle in tag:
                return True
    return False


def _significant_chars(text: str) -> set[str]:
    out: set[str] = set()
    normalized = unicodedata.normalize("NFKD", str(text or "")).casefold()
    for ch in normalized:
        category = unicodedata.category(ch)
        if category.startswith("L") or category.startswith("N"):
            out.add(ch)
    return out


def _share_any_significant_char(headword: str, form_text: str) -> bool:
    left = _significant_chars(headword)
    right = _significant_chars(form_text)
    if not left or not right:
        return False
    return bool(left & right)


def _scan_db(path: Path) -> tuple[str, list[dict[str, object]], bool] | None:
    db_name = normalize_db_name(path.stem)
    if db_name in EXCLUDED_DBS:
        return None

    conn = _open_db(path)
    try:
        if not _has_required_tables(conn):
            return db_name, [], True
        sql = """
            SELECT
                TRIM(COALESCE(e.headword, '')) AS headword,
                TRIM(COALESCE(f.form_text, '')) AS form_text,
                TRIM(COALESCE(f.morph_tags, '')) AS morph_tags
            FROM forms f
            JOIN entries e ON e.id = f.entry_id
            WHERE TRIM(COALESCE(e.headword, '')) != ''
              AND TRIM(COALESCE(f.form_text, '')) != ''
            ORDER BY
                TRIM(COALESCE(e.headword, '')),
                TRIM(COALESCE(f.form_text, '')),
                TRIM(COALESCE(f.morph_tags, ''))
        """

        out_rows: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in _iter_query(conn, sql):
            headword = _safe_cell(row["headword"])
            form_text = _safe_cell(row["form_text"])
            morph_tags = _safe_cell(row["morph_tags"])
            if not headword or not form_text:
                continue
            if _is_romanization_like(morph_tags):
                continue
            if _share_any_significant_char(headword, form_text):
                continue
            dedupe_key = (headword, form_text, morph_tags)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out_rows.append(
                {
                    "headword": headword,
                    "form_text": form_text,
                    "morph_tags": morph_tags,
                }
            )
        return db_name, out_rows, False
    finally:
        conn.close()


def _write_summary_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    _write_tsv(path, ["db", "nonshared_form_count"], rows)


def _write_summary_md(
    path: Path,
    rows: list[dict[str, object]],
    *,
    excluded_dbs: list[str],
    scanned_db_count: int,
    overall_count: int,
    schema_missing_dbs: list[str],
) -> None:
    lines = [
        "# Nonshared Form Character Audit",
        "",
        "Read-only report of form rows where the form text shares no significant character with the parent headword.",
        "",
        "Rules:",
        "- compare after Unicode NFKD + casefold",
        "- only letters and digits count as significant characters",
        "- skip East Asian / CJK-family DBs entirely",
        "- skip romanization-like / transliteration-like rows by tag",
        "",
        f"Scanned DBs: `{scanned_db_count}`",
        f"Overall nonshared rows: `{overall_count}`",
        "",
        "Excluded DBs:",
        f"- `{', '.join(excluded_dbs)}`",
        "",
        "Schema-missing / empty DBs treated as zero:",
        f"- `{', '.join(schema_missing_dbs) if schema_missing_dbs else '(none)'}`",
        "",
        "Per-DB counts:",
        "",
        "| DB | Nonshared Form Count |",
        "|---|---:|",
    ]
    for row in rows:
        lines.append(f"| `{row['db']}` | {row['nonshared_form_count']} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", action="append", default=[], help="Optional DB stem or filename to scan.")
    parser.add_argument("--out-dir", default="", help="Optional explicit output directory.")
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        raise SystemExit("No matching .sqlite files found in dict_sqlite/")

    out_dir = Path(args.out_dir) if args.out_dir else (REPORTS_DIR / DEFAULT_OUT_DIR_NAME)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    scanned_db_count = 0
    overall_count = 0
    schema_missing_dbs: list[str] = []

    for path in db_paths:
        result = _scan_db(path)
        if result is None:
            continue
        db_name, rows, schema_missing = result
        scanned_db_count += 1
        overall_count += len(rows)
        if schema_missing:
            schema_missing_dbs.append(db_name)
        rows.sort(key=lambda row: (str(row["headword"]).casefold(), str(row["form_text"]).casefold(), str(row["morph_tags"]).casefold()))
        _write_tsv(
            out_dir / db_name / "nonshared_forms.tsv",
            ["headword", "form_text", "morph_tags"],
            rows,
        )
        summary_rows.append({"db": db_name, "nonshared_form_count": len(rows)})

    summary_rows.sort(key=lambda row: (-int(row["nonshared_form_count"]), str(row["db"]).casefold()))
    _write_summary_tsv(out_dir / "SUMMARY.tsv", summary_rows)
    _write_summary_md(
        out_dir / "SUMMARY.md",
        summary_rows,
        excluded_dbs=sorted(EXCLUDED_DBS),
        scanned_db_count=scanned_db_count,
        overall_count=overall_count,
        schema_missing_dbs=sorted(schema_missing_dbs),
    )


if __name__ == "__main__":
    main()
