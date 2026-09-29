#!/usr/bin/env python3
"""
Read-only POS candidate audit for SQLite dictionary entries.

Scans dict_sqlite/*.sqlite, classifies suspicious POS labels by regex, and
writes per-database candidate entry lists plus an aggregate summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Iterator


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

CHUNK_SIZE = 5000

CJKISH_DBS = {
    "ja",
    "ja-jmdict",
    "ko",
    "ko-krdict",
    "zh",
    "zh-Hant",
    "zh-cc-cedict",
    "zh-Hant-cc-cedict",
    "lzh",
    "lzh-wiktionary",
    "vi",
}

POS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("symbolish", re.compile(r"^(symbol|symbols|punct|punctuation)$", re.I)),
    ("character_like", re.compile(r"^(char|character)$", re.I)),
    ("syllable_like", re.compile(r"^(syllable|syllabic)$", re.I)),
    ("letter_like", re.compile(r"^(letter|letters)$", re.I)),
]


def _open_db(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _iter_query(conn: sqlite3.Connection, sql: str) -> Iterator[tuple]:
    cur = conn.execute(sql)
    while True:
        rows = cur.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        yield from rows


def _flatten_glosses(raw_glosses: str) -> list[str]:
    text = str(raw_glosses or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text) if text[:1] in "[{" else text
    except Exception:
        parsed = text
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, str):
            s = node.strip()
            if s:
                out.append(s)
            return
        if isinstance(node, dict):
            glosses = node.get("glosses")
            if isinstance(glosses, list):
                for item in glosses:
                    walk(item)
            for key in ("gloss", "text", "definition", "def"):
                val = node.get(key)
                if isinstance(val, str):
                    s = val.strip()
                    if s:
                        out.append(s)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(parsed)
    return out


def _gloss_preview(raw_glosses: str) -> str:
    glosses = _flatten_glosses(raw_glosses)
    if not glosses:
        return ""
    text = " | ".join(glosses[:4]).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return text[:220]


def _classify_pos(db_stem: str, pos: str) -> tuple[str, str] | None:
    pos_text = str(pos or "").strip()
    if not pos_text:
        return None
    for bucket, rx in POS_PATTERNS:
        if rx.match(pos_text):
            if bucket == "symbolish":
                return bucket, "strong_drop_candidate"
            if db_stem in CJKISH_DBS:
                return bucket, "review_cjk_preserve_or_demote"
            return bucket, "strong_drop_candidate_non_cjk"
    return None


def _write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _audit_one(path: Path, out_root: Path) -> dict[str, object]:
    db_stem = path.stem
    out_dir = out_root / db_stem
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "db": db_stem,
        "file_size_bytes": path.stat().st_size,
        "entry_count": 0,
        "distinct_pos_count": 0,
        "candidate_entry_count": 0,
        "candidate_pos_counts": {},
        "candidate_bucket_counts": {},
        "recommendation_counts": {},
        "top_pos": [],
        "skipped_reason": "",
    }

    if path.stat().st_size == 0:
        summary["skipped_reason"] = "zero-byte database"
        (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    conn = _open_db(path)
    try:
        summary["entry_count"] = int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] or 0)
        pos_rows = conn.execute(
            "SELECT pos, COUNT(*) AS c FROM entries GROUP BY pos ORDER BY c DESC, pos"
        ).fetchall()
        summary["distinct_pos_count"] = len(pos_rows)
        summary["top_pos"] = [
            {"pos": str(pos or ""), "count": int(count)}
            for pos, count in pos_rows[:20]
        ]

        all_pos_rows: list[dict[str, object]] = []
        for pos, count in pos_rows:
            cls = _classify_pos(db_stem, str(pos or ""))
            all_pos_rows.append(
                {
                    "db": db_stem,
                    "pos": str(pos or ""),
                    "count": int(count),
                    "candidate_bucket": cls[0] if cls else "",
                    "recommendation": cls[1] if cls else "",
                }
            )
        _write_tsv(
            out_dir / "pos_counts.tsv",
            ["db", "pos", "count", "candidate_bucket", "recommendation"],
            all_pos_rows,
        )

        candidate_rows: list[dict[str, object]] = []
        bucket_counter: Counter[str] = Counter()
        rec_counter: Counter[str] = Counter()
        pos_counter: Counter[str] = Counter()
        for row in _iter_query(
            conn,
            "SELECT id, headword, pos, romanization, source, entry_id, tags, glosses FROM entries WHERE pos IS NOT NULL AND pos != '' ORDER BY id",
        ):
            entry_id, headword, pos, romanization, source, source_entry_id, tags, glosses = row
            cls = _classify_pos(db_stem, str(pos or ""))
            if not cls:
                continue
            bucket, recommendation = cls
            pos_text = str(pos or "")
            candidate_rows.append(
                {
                    "entry_id": entry_id,
                    "headword": str(headword or ""),
                    "pos": pos_text,
                    "candidate_bucket": bucket,
                    "recommendation": recommendation,
                    "romanization": str(romanization or ""),
                    "source": str(source or ""),
                    "source_entry_id": str(source_entry_id or ""),
                    "tags": str(tags or ""),
                    "gloss_preview": _gloss_preview(str(glosses or "")),
                }
            )
            bucket_counter[bucket] += 1
            rec_counter[recommendation] += 1
            pos_counter[pos_text] += 1

        summary["candidate_entry_count"] = len(candidate_rows)
        summary["candidate_bucket_counts"] = dict(sorted(bucket_counter.items()))
        summary["recommendation_counts"] = dict(sorted(rec_counter.items()))
        summary["candidate_pos_counts"] = dict(sorted(pos_counter.items(), key=lambda item: (-item[1], item[0])))

        if candidate_rows:
            _write_tsv(
                out_dir / "candidate_entries.tsv",
                [
                    "entry_id",
                    "headword",
                    "pos",
                    "candidate_bucket",
                    "recommendation",
                    "romanization",
                    "source",
                    "source_entry_id",
                    "tags",
                    "gloss_preview",
                ],
                candidate_rows,
            )
    finally:
        conn.close()

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# {db_stem}",
        "",
        f"- entries: `{summary['entry_count']:,}`",
        f"- distinct pos values: `{summary['distinct_pos_count']:,}`",
        f"- candidate entries: `{summary['candidate_entry_count']:,}`",
        "",
        "## Candidate POS Counts",
        "",
        "| POS | Count | Bucket | Recommendation |",
        "| --- | ---: | --- | --- |",
    ]
    for pos, count in summary["candidate_pos_counts"].items():
        cls = _classify_pos(db_stem, pos)
        bucket = cls[0] if cls else ""
        recommendation = cls[1] if cls else ""
        lines.append(f"| `{pos}` | `{count:,}` | `{bucket}` | `{recommendation}` |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


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


def _write_root_outputs(out_root: Path, summaries: list[dict[str, object]], generated_at: str) -> None:
    (out_root / "overall_summary.json").write_text(
        json.dumps({"generated_at": generated_at, "databases": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tsv_rows: list[dict[str, object]] = []
    all_pos_rows: list[dict[str, object]] = []
    for summary in summaries:
        tsv_rows.append(
            {
                "db": summary["db"],
                "entry_count": summary["entry_count"],
                "distinct_pos_count": summary["distinct_pos_count"],
                "candidate_entry_count": summary["candidate_entry_count"],
                "candidate_pos_counts": json.dumps(summary["candidate_pos_counts"], ensure_ascii=False, sort_keys=True),
                "recommendation_counts": json.dumps(summary["recommendation_counts"], ensure_ascii=False, sort_keys=True),
                "skipped_reason": summary.get("skipped_reason", ""),
            }
        )
        for pos, count in dict(summary.get("candidate_pos_counts") or {}).items():
            cls = _classify_pos(str(summary["db"]), pos)
            all_pos_rows.append(
                {
                    "db": summary["db"],
                    "pos": pos,
                    "count": count,
                    "candidate_bucket": cls[0] if cls else "",
                    "recommendation": cls[1] if cls else "",
                }
            )

    _write_tsv(
        out_root / "overall_summary.tsv",
        ["db", "entry_count", "distinct_pos_count", "candidate_entry_count", "candidate_pos_counts", "recommendation_counts", "skipped_reason"],
        tsv_rows,
    )
    _write_tsv(
        out_root / "candidate_pos_counts.tsv",
        ["db", "pos", "count", "candidate_bucket", "recommendation"],
        sorted(all_pos_rows, key=lambda row: (-int(row["count"]), str(row["db"]), str(row["pos"]))),
    )

    ranked = sorted(summaries, key=lambda row: (-int(row.get("candidate_entry_count") or 0), str(row["db"])))
    lines = [
        "# POS Prune Candidates",
        "",
        f"- generated_at: `{generated_at}`",
        f"- source_dir: `{SQLITE_DIR}`",
        "",
        "Candidate POS regex buckets:",
        "",
        "- `symbolish`: `symbol`, `symbols`, `punct`, `punctuation`",
        "- `character_like`: `char`, `character`",
        "- `syllable_like`: `syllable`, `syllabic`",
        "- `letter_like`: `letter`, `letters`",
        "",
        "Recommendation policy used by the probe:",
        "",
        "- `symbolish` -> `strong_drop_candidate` in every DB",
        "- `character_like` / `syllable_like` / `letter_like` -> `review_cjk_preserve_or_demote` in CJK-ish DBs",
        "- `character_like` / `syllable_like` / `letter_like` -> `strong_drop_candidate_non_cjk` elsewhere",
        "",
        "| DB | Candidate Entries | Candidate POS Buckets |",
        "| --- | ---: | --- |",
    ]
    for summary in ranked:
        bucket_text = ", ".join(
            f"{bucket}:{count}"
            for bucket, count in dict(summary.get("candidate_bucket_counts") or {}).items()
        )
        lines.append(f"| `{summary['db']}` | `{int(summary.get('candidate_entry_count') or 0):,}` | `{bucket_text}` |")
    lines.append("")
    (out_root / "POS_PRUNE_CANDIDATES.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit suspicious POS categories in SQLite dictionaries")
    parser.add_argument("db", nargs="*", help="Optional database stems or filenames")
    parser.add_argument("--output-dir", default="", help="Output directory")
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        raise SystemExit("No matching .sqlite files found in dict_sqlite/")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_root = Path(args.output_dir) if args.output_dir else REPORTS_DIR / f"sqlite_pos_probe_{timestamp}"
    out_root.mkdir(parents=True, exist_ok=True)
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    summaries: list[dict[str, object]] = []
    for path in db_paths:
        print(f"[pos-probe] {path.stem}", flush=True)
        summaries.append(_audit_one(path, out_root))
    _write_root_outputs(out_root, summaries, generated_at)
    print(f"[pos-probe] done: {out_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
