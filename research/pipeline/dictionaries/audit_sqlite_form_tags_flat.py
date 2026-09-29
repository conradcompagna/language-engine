#!/usr/bin/env python3
"""
Read-only flat audit of SQLite form tags.

For each dict_sqlite/*.sqlite database:
- dedupe exact duplicate form rows by (entry_id, form_text, morph_tags, romanization)
- count individual form tags
- count full form tag combinations
- keep up to 5 representative examples as `headword -> form_text`

Outputs per DB:
- form_tags_flat.tsv
- form_tag_combinations_flat.tsv

Optionally creates a sibling .zip archive of the whole output folder.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from sqlite_prune_policy import split_tags


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

CHUNK_SIZE = 5000
SAMPLE_LIMIT = 5
DEFAULT_OUT_DIR_NAME = f"sqlite_form_tags_flat_{time.strftime('%Y%m%d')}"


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


def _safe_text(text: str) -> str:
    return str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _example_label(headword: str, form_text: str) -> str:
    head = _safe_text(headword) or "(blank headword)"
    form = _safe_text(form_text) or "(blank form)"
    return f"{head} -> {form}"


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


def _fold_tag(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "").strip()).casefold()


@dataclass
class StatBucket:
    count: int = 0
    examples: list[str] = field(default_factory=list)
    _seen_examples: set[str] = field(default_factory=set)

    def add(self, example: str) -> None:
        self.count += 1
        if example in self._seen_examples:
            return
        self._seen_examples.add(example)
        if len(self.examples) < SAMPLE_LIMIT:
            self.examples.append(example)


@dataclass
class DbResult:
    db: str
    deduped_form_rows: int
    distinct_tags: int
    distinct_tag_combinations: int


def _iter_deduped_form_rows(conn: sqlite3.Connection) -> Iterator[sqlite3.Row]:
    sql = """
        SELECT
            f.entry_id AS entry_id,
            TRIM(COALESCE(e.headword, '')) AS headword,
            TRIM(COALESCE(f.form_text, '')) AS form_text,
            TRIM(COALESCE(f.morph_tags, '')) AS morph_tags,
            TRIM(COALESCE(f.romanization, '')) AS form_romanization
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        WHERE TRIM(COALESCE(f.form_text, '')) != ''
        GROUP BY
            f.entry_id,
            TRIM(COALESCE(f.form_text, '')),
            TRIM(COALESCE(f.morph_tags, '')),
            TRIM(COALESCE(f.romanization, ''))
        ORDER BY
            f.entry_id,
            TRIM(COALESCE(f.form_text, '')),
            TRIM(COALESCE(f.morph_tags, '')),
            TRIM(COALESCE(f.romanization, ''))
    """
    yield from _iter_query(conn, sql)


def _audit_one_db(path: Path, out_root: Path) -> DbResult:
    db_name = path.stem
    db_dir = out_root / db_name
    headers_tags = ["form_tag", "occurrence_count", "sample_examples"]
    headers_combos = ["tag_combination", "occurrence_count", "sample_examples"]

    if path.stat().st_size == 0:
        _log(f"[form-tags] {db_name}: zero-byte database, writing empty outputs")
        _write_tsv(db_dir / "form_tags_flat.tsv", headers_tags, [])
        _write_tsv(db_dir / "form_tag_combinations_flat.tsv", headers_combos, [])
        return DbResult(
            db=db_name,
            deduped_form_rows=0,
            distinct_tags=0,
            distinct_tag_combinations=0,
        )

    _log(f"[form-tags] {db_name}: opening")
    conn = _open_db(path)
    try:
        tag_display_by_key: dict[str, str] = {}
        tag_buckets: dict[str, StatBucket] = {}
        combo_buckets: dict[tuple[str, ...], StatBucket] = {}
        deduped_form_rows = 0

        for row in _iter_deduped_form_rows(conn):
            deduped_form_rows += 1
            headword = str(row["headword"] or "").strip()
            form_text = str(row["form_text"] or "").strip()
            raw_tags = str(row["morph_tags"] or "").strip()
            example = _example_label(headword, form_text)

            tags = split_tags(raw_tags)
            tag_keys: list[str] = []
            for tag in tags:
                tag_key = _fold_tag(tag)
                if not tag_key:
                    continue
                tag_keys.append(tag_key)
                tag_display_by_key.setdefault(tag_key, tag)
                bucket = tag_buckets.get(tag_key)
                if bucket is None:
                    bucket = StatBucket()
                    tag_buckets[tag_key] = bucket
                bucket.add(example)

            combo_key = tuple(sorted(set(tag_keys)))
            combo_bucket = combo_buckets.get(combo_key)
            if combo_bucket is None:
                combo_bucket = StatBucket()
                combo_buckets[combo_key] = combo_bucket
            combo_bucket.add(example)

        tag_rows = [
            {
                "form_tag": tag_display_by_key.get(tag_key, tag_key),
                "occurrence_count": bucket.count,
                "sample_examples": " | ".join(bucket.examples),
            }
            for tag_key, bucket in tag_buckets.items()
        ]
        tag_rows.sort(
            key=lambda row: (
                -int(row["occurrence_count"]),
                str(row["form_tag"] or "").casefold(),
            )
        )

        combo_rows = []
        for combo_key, bucket in combo_buckets.items():
            if combo_key:
                combo_display = ";".join(tag_display_by_key.get(tag_key, tag_key) for tag_key in combo_key)
            else:
                combo_display = "(none)"
            combo_rows.append(
                {
                    "tag_combination": combo_display,
                    "occurrence_count": bucket.count,
                    "sample_examples": " | ".join(bucket.examples),
                }
            )
        combo_rows.sort(
            key=lambda row: (
                -int(row["occurrence_count"]),
                str(row["tag_combination"] or "").casefold(),
            )
        )

        _write_tsv(db_dir / "form_tags_flat.tsv", headers_tags, tag_rows)
        _write_tsv(db_dir / "form_tag_combinations_flat.tsv", headers_combos, combo_rows)

        _log(
            f"[form-tags] {db_name}: wrote {len(tag_rows):,} tags, "
            f"{len(combo_rows):,} combinations from {deduped_form_rows:,} deduped form rows"
        )
        return DbResult(
            db=db_name,
            deduped_form_rows=deduped_form_rows,
            distinct_tags=len(tag_rows),
            distinct_tag_combinations=len(combo_rows),
        )
    finally:
        conn.close()


def _write_readme(path: Path) -> None:
    lines = [
        "# SQLite Form Tags Flat Audit",
        "",
        "This folder is a read-only audit. The source `.sqlite` files were not modified.",
        "",
        "Per DB files:",
        "- `form_tags_flat.tsv`: individual form tags, counts, and up to 5 `headword -> form_text` examples",
        "- `form_tag_combinations_flat.tsv`: normalized full tag combinations, counts, and up to 5 examples",
        "",
        "Deduping:",
        "- exact duplicate form rows are collapsed by `(entry_id, form_text, morph_tags, romanization)` before counting",
        "- individual tags are counted once per deduped form row",
        "- full tag combinations are normalized by splitting on `;`, deduping repeated tags, and sorting the tag keys",
        "- blank tagsets are kept in the combinations file as `(none)`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_summary(path: Path, results: list[DbResult]) -> None:
    rows = [
        {
            "db": item.db,
            "deduped_form_rows": item.deduped_form_rows,
            "distinct_tags": item.distinct_tags,
            "distinct_tag_combinations": item.distinct_tag_combinations,
        }
        for item in sorted(results, key=lambda item: item.db)
    ]
    _write_tsv(
        path,
        ["db", "deduped_form_rows", "distinct_tags", "distinct_tag_combinations"],
        rows,
    )


def _make_zip(out_root: Path) -> Path:
    archive_base = out_root.resolve()
    zip_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=out_root.parent, base_dir=out_root.name))
    return zip_path


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
        help="Output directory. Default: reports/sqlite_form_tags_flat_YYYYMMDD",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Do not create a sibling .zip archive of the output folder.",
    )
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        _log("[form-tags] no matching sqlite databases found")
        return 1

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    _write_readme(out_root / "README.md")

    started = time.perf_counter()
    results: list[DbResult] = []
    for path in db_paths:
        results.append(_audit_one_db(path, out_root))

    _write_summary(out_root / "SUMMARY.tsv", results)

    zip_path: Path | None = None
    if not args.no_zip:
        _log(f"[form-tags] creating zip archive for {out_root}")
        zip_path = _make_zip(out_root)

    elapsed = time.perf_counter() - started
    if zip_path is not None:
        _log(f"[form-tags] completed {len(results)} DBs in {elapsed:.1f}s -> {out_root} and {zip_path}")
    else:
        _log(f"[form-tags] completed {len(results)} DBs in {elapsed:.1f}s -> {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
