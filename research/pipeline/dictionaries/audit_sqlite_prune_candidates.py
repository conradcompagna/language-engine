#!/usr/bin/env python3
"""
Read-only SQLite dictionary audit for postprocessing/pruning candidates.

Scans every live dict_sqlite/*.sqlite file, looks for suspicious headwords and
form rows, and writes per-database findings under reports/.

The script never mutates the source databases.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

CHUNK_SIZE = 5000
HIGH_FANOUT_OTHER_ENTRIES = 10
HIGH_FANOUT_ENTRY_THRESHOLD = HIGH_FANOUT_OTHER_ENTRIES + 1
FANOUT_QUERY_BATCH_SIZE = 800

ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
META_FORM_RE = re.compile(
    r"""
    ^
    (?:
        \d+\s+strong
        |
        (?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)
        (?:\s+and\s+(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth))?
        \s+(?:declension|conjugation)
        |
        declension
        |
        conjugation
        |
        (?:vowel|consonant|velar|palatal|dental|guttural|nasal|liquid|strong|weak)[ -]stem
        |
        (?:transitive|intransitive)\s+(?:godan|ichidan|yodan|suru|kuru)
        |
        haben(?:\s+or\s+sein)?
        |
        sein(?:\s+or\s+haben)?
        |
        for\s+other\s+.+\s+forms?
        |
        quoted\s+by\s+.+ 
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

RELATION_GLOSS_RE = re.compile(
    r"""
    ^
    (?:
        alternative(?:\s+(?:form|spelling))?
        |archaic(?:\s+(?:form|spelling))?
        |dated(?:\s+(?:form|spelling))?
        |obsolete(?:\s+(?:form|spelling))?
        |informal(?:\s+(?:form|spelling))?
        |misspelling
        |nonstandard\s+spelling
        |eye\s+dialect\s+spelling
        |synonym
        |variant
        |romanization
        |transliteration
        |hanja\s+form
        |hiragana\s+spelling
        |katakana\s+spelling
        |kyujitai\s+spelling
        |shinjitai\s+spelling
        |simplified\s+form
        |traditional\s+form
        |short\s+for
        |clipping
        |abbreviation
        |acronym
        |initialism
        |ellipsis
        |contraction
        |aphetic\s+form
        |elongated\s+form
        |plural
        |present\s+participle
        |past\s+participle
        |comparative
        |superlative
        |feminine
        |masculine
        |neuter
        |inflection
        |form
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _log(message: str) -> None:
    print(message, flush=True)


def _safe_preview(text: str, *, limit: int = 220) -> str:
    s = str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "..."


def _open_db(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _fetch_count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _iter_query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Iterator[tuple]:
    cur = conn.execute(sql, params)
    while True:
        rows = cur.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        for row in rows:
            yield row


def _flatten_gloss_node(node: object, out: list[str]) -> None:
    if isinstance(node, str):
        text = node.strip()
        if text:
            out.append(text)
        return
    if isinstance(node, dict):
        glosses = node.get("glosses")
        if isinstance(glosses, list):
            for item in glosses:
                _flatten_gloss_node(item, out)
        for key in ("gloss", "text", "definition", "def"):
            value = node.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    out.append(text)
        return
    if isinstance(node, list):
        for item in node:
            _flatten_gloss_node(item, out)


def _parse_glosses(raw_glosses: str) -> tuple[list[str], bool]:
    text = str(raw_glosses or "").strip()
    if not text:
        return [], False
    parse_error = False
    parsed: object = text
    if text[:1] in "[{":
        try:
            parsed = json.loads(text)
        except Exception:
            parse_error = True
            parsed = text
    out: list[str] = []
    _flatten_gloss_node(parsed, out)
    if out:
        return out, parse_error
    if isinstance(parsed, str):
        parts = [part.strip() for part in parsed.split(";") if part.strip()]
        return parts, parse_error
    return out, parse_error


@lru_cache(maxsize=250000)
def _has_any_letter(text: str) -> bool:
    for ch in str(text or ""):
        if unicodedata.category(ch).startswith("L"):
            return True
    return False


@lru_cache(maxsize=250000)
def _has_latin_letter(text: str) -> bool:
    s = str(text or "")
    if ASCII_LETTER_RE.search(s):
        return True
    for ch in s:
        if not unicodedata.category(ch).startswith("L"):
            continue
        if _char_script(ch) == "Latin":
            return True
    return False


def _gloss_bucket(glosses: list[str]) -> str:
    if not glosses:
        return "missing"
    has_letter = any(_has_any_letter(gloss) for gloss in glosses)
    has_latin = any(_has_latin_letter(gloss) for gloss in glosses)
    if not has_letter:
        return "symbol_only"
    if not has_latin:
        return "non_latin_only"
    return "ok"


def _is_relation_only_glosses(glosses: list[str]) -> bool:
    if not glosses:
        return False
    return all(RELATION_GLOSS_RE.match(gloss.strip()) for gloss in glosses if gloss.strip())


def _strip_combining_and_non_letters(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text or "").casefold())
    out_chars: list[str] = []
    for ch in norm:
        cat = unicodedata.category(ch)
        if cat.startswith("M"):
            continue
        if cat.startswith("L"):
            out_chars.append(ch)
    return "".join(out_chars)


@lru_cache(maxsize=250000)
def _letter_char_set(text: str) -> frozenset[str]:
    return frozenset(_strip_combining_and_non_letters(text))


def _is_cjk_script(script: str) -> bool:
    return script in {"Han", "Hiragana", "Katakana", "Bopomofo", "CJK"}


@lru_cache(maxsize=250000)
def _char_script(ch: str) -> str:
    code = ord(ch)
    if 0x0041 <= code <= 0x024F or 0x1E00 <= code <= 0x1EFF or 0x2C60 <= code <= 0x2C7F or 0xA720 <= code <= 0xA7FF:
        return "Latin"
    if 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF:
        return "Greek"
    if 0x0400 <= code <= 0x052F or 0x2DE0 <= code <= 0x2DFF or 0xA640 <= code <= 0xA69F or 0x1C80 <= code <= 0x1C8F:
        return "Cyrillic"
    if 0x0590 <= code <= 0x05FF or 0xFB1D <= code <= 0xFB4F:
        return "Hebrew"
    if (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0x0870 <= code <= 0x089F
        or 0x08A0 <= code <= 0x08FF
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    ):
        return "Arabic"
    if 0x0900 <= code <= 0x097F or 0xA8E0 <= code <= 0xA8FF:
        return "Devanagari"
    if 0x0980 <= code <= 0x09FF:
        return "Bengali"
    if 0x0A00 <= code <= 0x0A7F:
        return "Gurmukhi"
    if 0x0B80 <= code <= 0x0BFF:
        return "Tamil"
    if 0x0E00 <= code <= 0x0E7F:
        return "Thai"
    if 0x0530 <= code <= 0x058F or 0xFB13 <= code <= 0xFB17:
        return "Armenian"
    if (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2CEB0 <= code <= 0x2EBEF
        or 0x30000 <= code <= 0x3134F
    ):
        return "Han"
    if 0x3040 <= code <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
        return "Katakana"
    if 0x3100 <= code <= 0x312F or 0x31A0 <= code <= 0x31BF:
        return "Bopomofo"
    if 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F or 0xAC00 <= code <= 0xD7AF:
        return "Hangul"
    return "Other"


@lru_cache(maxsize=250000)
def _primary_script(text: str) -> str:
    counts: Counter[str] = Counter()
    for ch in str(text or ""):
        if not unicodedata.category(ch).startswith("L"):
            continue
        script = _char_script(ch)
        counts[script] += 1
    if not counts:
        return "Unknown"
    if counts["Han"] or counts["Hiragana"] or counts["Katakana"] or counts["Bopomofo"]:
        return "CJK"
    top_two = counts.most_common(2)
    if len(top_two) > 1 and top_two[0][1] == top_two[1][1]:
        return "Mixed"
    return top_two[0][0]


@lru_cache(maxsize=250000)
def _looks_meta_form(form_text: str, morph_tags: str) -> str:
    tags = str(morph_tags or "").strip().casefold()
    text = str(form_text or "").strip()
    folded = text.casefold()
    if not text:
        return "blank"
    if "class" in {part.strip() for part in tags.split(";") if part.strip()}:
        return "class-tag"
    if META_FORM_RE.match(folded):
        return "meta-regex"
    if len(text.split()) >= 4 and any(token in folded for token in ("for other", "quoted by", "appendix")):
        return "note-text"
    if tags == "auxiliary" and folded in {"haben", "sein", "haben or sein", "sein or haben"}:
        return "auxiliary-metadata"
    return ""


def _write_tsv(path: Path, headers: list[str], rows: Iterable[dict[str, object]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


@dataclass
class DbSummary:
    db: str
    file_size_bytes: int
    entry_count: int = 0
    form_count: int = 0
    skipped_reason: str = ""
    headword_missing_glosses: int = 0
    headword_symbol_only_glosses: int = 0
    headword_non_latin_only_glosses: int = 0
    headword_relation_only_glosses: int = 0
    headword_gloss_parse_errors: int = 0
    form_high_fanout_texts: int = 0
    form_high_fanout_rows: int = 0
    form_no_shared_same_script_rows: int = 0
    form_no_shared_cross_script_rows: int = 0
    form_meta_or_note_rows: int = 0
    form_duplicate_groups: int = 0
    form_duplicate_extra_rows: int = 0
    top_high_fanout: list[dict[str, object]] = field(default_factory=list)
    top_meta_forms: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "db": self.db,
            "file_size_bytes": self.file_size_bytes,
            "entry_count": self.entry_count,
            "form_count": self.form_count,
            "skipped_reason": self.skipped_reason,
            "headword_missing_glosses": self.headword_missing_glosses,
            "headword_symbol_only_glosses": self.headword_symbol_only_glosses,
            "headword_non_latin_only_glosses": self.headword_non_latin_only_glosses,
            "headword_relation_only_glosses": self.headword_relation_only_glosses,
            "headword_gloss_parse_errors": self.headword_gloss_parse_errors,
            "form_high_fanout_texts": self.form_high_fanout_texts,
            "form_high_fanout_rows": self.form_high_fanout_rows,
            "form_no_shared_same_script_rows": self.form_no_shared_same_script_rows,
            "form_no_shared_cross_script_rows": self.form_no_shared_cross_script_rows,
            "form_meta_or_note_rows": self.form_meta_or_note_rows,
            "form_duplicate_groups": self.form_duplicate_groups,
            "form_duplicate_extra_rows": self.form_duplicate_extra_rows,
            "top_high_fanout": self.top_high_fanout,
            "top_meta_forms": self.top_meta_forms,
        }


def _scan_entries(conn: sqlite3.Connection, out_dir: Path, summary: DbSummary) -> None:
    missing_rows: list[dict[str, object]] = []
    symbol_rows: list[dict[str, object]] = []
    non_latin_rows: list[dict[str, object]] = []
    relation_rows: list[dict[str, object]] = []

    sql = """
        SELECT id, headword, romanization, pos, glosses, source, entry_id, tags
        FROM entries
        ORDER BY id
    """
    for row in _iter_query(conn, sql):
        entry_id, headword, romanization, pos, glosses_raw, source, source_entry_id, tags = row
        glosses, parse_error = _parse_glosses(glosses_raw)
        if parse_error:
            summary.headword_gloss_parse_errors += 1
        bucket = _gloss_bucket(glosses)
        base_payload = {
            "entry_id": entry_id,
            "headword": headword,
            "pos": pos,
            "romanization": romanization,
            "source": source,
            "source_entry_id": source_entry_id,
            "tags": tags,
            "gloss_count": len(glosses),
            "gloss_preview": " | ".join(_safe_preview(gloss, limit=120) for gloss in glosses[:4]),
            "gloss_parse_error": int(parse_error),
        }
        if bucket == "missing":
            missing_rows.append(base_payload)
            summary.headword_missing_glosses += 1
        elif bucket == "symbol_only":
            symbol_rows.append(base_payload)
            summary.headword_symbol_only_glosses += 1
        elif bucket == "non_latin_only":
            non_latin_rows.append(base_payload)
            summary.headword_non_latin_only_glosses += 1
        if _is_relation_only_glosses(glosses):
            relation_rows.append(base_payload)
            summary.headword_relation_only_glosses += 1

    headword_headers = [
        "entry_id",
        "headword",
        "pos",
        "romanization",
        "source",
        "source_entry_id",
        "tags",
        "gloss_count",
        "gloss_parse_error",
        "gloss_preview",
    ]
    if missing_rows:
        _write_tsv(out_dir / "headwords_missing_glosses.tsv", headword_headers, missing_rows)
    if symbol_rows:
        _write_tsv(out_dir / "headwords_symbol_only_glosses.tsv", headword_headers, symbol_rows)
    if non_latin_rows:
        _write_tsv(out_dir / "headwords_non_latin_only_glosses.tsv", headword_headers, non_latin_rows)
    if relation_rows:
        _write_tsv(out_dir / "headwords_relation_only_glosses.tsv", headword_headers, relation_rows)


def _collect_high_fanout(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    sql = f"""
        SELECT form_text, COUNT(DISTINCT entry_id) AS entry_count, COUNT(*) AS row_count
        FROM forms
        WHERE TRIM(form_text) != ''
        GROUP BY form_text
        HAVING entry_count >= {HIGH_FANOUT_ENTRY_THRESHOLD}
        ORDER BY entry_count DESC, row_count DESC, form_text
    """
    out: dict[str, tuple[int, int]] = {}
    for form_text, entry_count, row_count in conn.execute(sql):
        out[str(form_text)] = (int(entry_count), int(row_count))
    return out


def _collect_form_fanout_for_texts(
    conn: sqlite3.Connection,
    texts: Iterable[str],
) -> dict[str, tuple[int, int]]:
    unique_texts = sorted({str(text or "") for text in texts})
    if not unique_texts:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for start in range(0, len(unique_texts), FANOUT_QUERY_BATCH_SIZE):
        batch = unique_texts[start : start + FANOUT_QUERY_BATCH_SIZE]
        placeholders = ",".join("?" for _ in batch)
        sql = f"""
            SELECT form_text, COUNT(DISTINCT entry_id) AS entry_count, COUNT(*) AS row_count
            FROM forms
            WHERE form_text IN ({placeholders})
            GROUP BY form_text
        """
        for form_text, entry_count, row_count in conn.execute(sql, batch):
            out[str(form_text)] = (int(entry_count), int(row_count))
    return out


def _attach_fanout_counts(
    rows: list[dict[str, object]],
    fanout_counts: dict[str, tuple[int, int]],
) -> None:
    for row in rows:
        form_text = str(row.get("form_text") or "")
        entry_count, row_count = fanout_counts.get(form_text, (0, 0))
        row["fanout_entry_count"] = entry_count
        row["fanout_other_entry_count"] = max(0, entry_count - 1)
        row["fanout_row_count"] = row_count


def _sort_rows_by_cross_entry_fanout(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("fanout_other_entry_count") or 0),
            -int(row.get("fanout_entry_count") or 0),
            -int(row.get("fanout_row_count") or 0),
            str(row.get("form_text") or "").casefold(),
            str(row.get("headword") or "").casefold(),
            int(row.get("form_id") or row.get("entry_id") or 0),
        ),
    )


def _scan_duplicate_form_groups(conn: sqlite3.Connection, out_dir: Path, summary: DbSummary) -> None:
    sql = """
        SELECT
            f.entry_id,
            e.headword,
            e.pos,
            f.form_text,
            f.morph_tags,
            f.romanization,
            COUNT(*) AS duplicate_count
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        GROUP BY f.entry_id, f.form_text, f.morph_tags, f.romanization
        HAVING duplicate_count > 1
        ORDER BY duplicate_count DESC, f.entry_id, f.form_text
    """
    rows: list[dict[str, object]] = []
    for entry_id, headword, pos, form_text, morph_tags, romanization, dup_count in conn.execute(sql):
        duplicate_count = int(dup_count)
        rows.append(
            {
                "entry_id": entry_id,
                "headword": headword,
                "pos": pos,
                "form_text": form_text,
                "morph_tags": morph_tags,
                "romanization": romanization,
                "duplicate_count": duplicate_count,
                "extra_rows": duplicate_count - 1,
            }
        )
        summary.form_duplicate_groups += 1
        summary.form_duplicate_extra_rows += duplicate_count - 1
    if rows:
        fanout_counts = _collect_form_fanout_for_texts(conn, (row["form_text"] for row in rows))
        _attach_fanout_counts(rows, fanout_counts)
        rows = sorted(
            rows,
            key=lambda row: (
                -int(row.get("fanout_other_entry_count") or 0),
                -int(row.get("fanout_row_count") or 0),
                -int(row.get("duplicate_count") or 0),
                str(row.get("form_text") or "").casefold(),
                str(row.get("headword") or "").casefold(),
                int(row.get("entry_id") or 0),
            ),
        )
        _write_tsv(
            out_dir / "forms_duplicate_groups.tsv",
            [
                "entry_id",
                "headword",
                "pos",
                "form_text",
                "morph_tags",
                "romanization",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
                "duplicate_count",
                "extra_rows",
            ],
            rows,
        )


def _scan_forms(
    conn: sqlite3.Connection,
    out_dir: Path,
    summary: DbSummary,
    high_fanout: dict[str, tuple[int, int]],
) -> None:
    high_fanout_rows: list[dict[str, object]] = []
    no_shared_same_rows: list[dict[str, object]] = []
    no_shared_cross_rows: list[dict[str, object]] = []
    meta_rows: list[dict[str, object]] = []
    meta_counter: Counter[tuple[str, str]] = Counter()

    sql = """
        SELECT
            f.id,
            f.entry_id,
            f.form_text,
            f.morph_tags,
            f.romanization,
            e.headword,
            e.pos
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        ORDER BY f.id
    """
    for row in _iter_query(conn, sql):
        form_id, entry_id, form_text, morph_tags, romanization, headword, pos = row
        form_text = str(form_text or "")
        headword = str(headword or "")
        morph_tags = str(morph_tags or "")
        romanization = str(romanization or "")

        fanout_info = high_fanout.get(form_text)
        if fanout_info:
            entry_count, row_count = fanout_info
            high_fanout_rows.append(
                {
                    "form_id": form_id,
                    "entry_id": entry_id,
                    "headword": headword,
                    "pos": pos,
                    "form_text": form_text,
                    "morph_tags": morph_tags,
                    "romanization": romanization,
                    "fanout_entry_count": entry_count,
                    "fanout_other_entry_count": entry_count - 1,
                    "fanout_row_count": row_count,
                }
            )
            summary.form_high_fanout_rows += 1

        meta_reason = _looks_meta_form(form_text, morph_tags)
        if meta_reason:
            meta_rows.append(
                {
                    "form_id": form_id,
                    "entry_id": entry_id,
                    "headword": headword,
                    "pos": pos,
                    "form_text": form_text,
                    "morph_tags": morph_tags,
                    "romanization": romanization,
                    "meta_reason": meta_reason,
                }
            )
            meta_counter[(form_text, meta_reason)] += 1
            summary.form_meta_or_note_rows += 1

        head_chars = _letter_char_set(headword)
        form_chars = _letter_char_set(form_text)
        if head_chars and form_chars and head_chars.isdisjoint(form_chars):
            head_script = _primary_script(headword)
            form_script = _primary_script(form_text)
            payload = {
                "form_id": form_id,
                "entry_id": entry_id,
                "headword": headword,
                "pos": pos,
                "form_text": form_text,
                "morph_tags": morph_tags,
                "romanization": romanization,
                "headword_script": head_script,
                "form_script": form_script,
                "headword_letters": "".join(sorted(head_chars))[:80],
                "form_letters": "".join(sorted(form_chars))[:80],
            }
            if head_script == form_script and head_script not in {"Mixed", "Unknown"} and not _is_cjk_script(head_script):
                no_shared_same_rows.append(payload)
                summary.form_no_shared_same_script_rows += 1
            else:
                no_shared_cross_rows.append(payload)
                summary.form_no_shared_cross_script_rows += 1

    candidate_texts = {
        str(row["form_text"])
        for row in meta_rows + no_shared_same_rows + no_shared_cross_rows
    }
    candidate_fanout = _collect_form_fanout_for_texts(conn, candidate_texts)
    _attach_fanout_counts(meta_rows, candidate_fanout)
    _attach_fanout_counts(no_shared_same_rows, candidate_fanout)
    _attach_fanout_counts(no_shared_cross_rows, candidate_fanout)

    high_fanout_rows = _sort_rows_by_cross_entry_fanout(high_fanout_rows)
    no_shared_same_rows = _sort_rows_by_cross_entry_fanout(no_shared_same_rows)
    no_shared_cross_rows = _sort_rows_by_cross_entry_fanout(no_shared_cross_rows)
    meta_rows = _sort_rows_by_cross_entry_fanout(meta_rows)

    if high_fanout_rows:
        _write_tsv(
            out_dir / "forms_high_fanout_rows.tsv",
            [
                "form_id",
                "entry_id",
                "headword",
                "pos",
                "form_text",
                "morph_tags",
                "romanization",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
            ],
            high_fanout_rows,
        )
    if no_shared_same_rows:
        _write_tsv(
            out_dir / "forms_no_shared_letters_same_script.tsv",
            [
                "form_id",
                "entry_id",
                "headword",
                "pos",
                "form_text",
                "morph_tags",
                "romanization",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
                "headword_script",
                "form_script",
                "headword_letters",
                "form_letters",
            ],
            no_shared_same_rows,
        )
    if no_shared_cross_rows:
        _write_tsv(
            out_dir / "forms_no_shared_letters_cross_script_or_cjk.tsv",
            [
                "form_id",
                "entry_id",
                "headword",
                "pos",
                "form_text",
                "morph_tags",
                "romanization",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
                "headword_script",
                "form_script",
                "headword_letters",
                "form_letters",
            ],
            no_shared_cross_rows,
        )
    if meta_rows:
        _write_tsv(
            out_dir / "forms_meta_or_note_text.tsv",
            [
                "form_id",
                "entry_id",
                "headword",
                "pos",
                "form_text",
                "morph_tags",
                "romanization",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
                "meta_reason",
            ],
            meta_rows,
        )

    summary.top_meta_forms = [
        {"form_text": form_text, "meta_reason": reason, "row_count": count}
        for (form_text, reason), count in meta_counter.most_common(20)
    ]


def _write_high_fanout_groups(out_dir: Path, summary: DbSummary, high_fanout: dict[str, tuple[int, int]]) -> None:
    rows = [
        {
            "form_text": form_text,
            "fanout_entry_count": entry_count,
            "fanout_other_entry_count": entry_count - 1,
            "fanout_row_count": row_count,
        }
        for form_text, (entry_count, row_count) in sorted(
            high_fanout.items(),
            key=lambda item: (-item[1][0], -item[1][1], item[0]),
        )
    ]
    summary.form_high_fanout_texts = len(rows)
    summary.top_high_fanout = rows[:20]
    if rows:
        _write_tsv(
            out_dir / "forms_high_fanout_groups.tsv",
            [
                "form_text",
                "fanout_entry_count",
                "fanout_other_entry_count",
                "fanout_row_count",
            ],
            rows,
        )


def _write_db_summary(out_dir: Path, summary: DbSummary) -> None:
    (out_dir / "summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        f"# {summary.db}",
        "",
        f"- file size: `{summary.file_size_bytes:,}` bytes",
        f"- entries: `{summary.entry_count:,}`",
        f"- forms: `{summary.form_count:,}`",
    ]
    if summary.skipped_reason:
        lines.append(f"- skipped: `{summary.skipped_reason}`")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            f"- headwords missing glosses: `{summary.headword_missing_glosses:,}`",
            f"- headwords with symbol-only glosses: `{summary.headword_symbol_only_glosses:,}`",
            f"- headwords with non-Latin-only glosses: `{summary.headword_non_latin_only_glosses:,}`",
            f"- headwords with relation-only glosses: `{summary.headword_relation_only_glosses:,}`",
            f"- headword gloss parse errors: `{summary.headword_gloss_parse_errors:,}`",
            f"- high-fanout form texts: `{summary.form_high_fanout_texts:,}`",
            f"- rows using those high-fanout form texts: `{summary.form_high_fanout_rows:,}`",
            f"- no-shared-letter same-script forms: `{summary.form_no_shared_same_script_rows:,}`",
            f"- no-shared-letter cross-script/CJK forms: `{summary.form_no_shared_cross_script_rows:,}`",
            f"- meta/note-like form rows: `{summary.form_meta_or_note_rows:,}`",
            f"- duplicate form groups: `{summary.form_duplicate_groups:,}`",
            f"- duplicate extra rows: `{summary.form_duplicate_extra_rows:,}`",
        ]
    )

    if summary.top_high_fanout:
        lines.extend(["", "## Top High-Fanout Forms", "", "| Form | Entry Count | Row Count |", "| --- | ---: | ---: |"])
        for item in summary.top_high_fanout[:15]:
            lines.append(
                f"| `{_safe_preview(str(item['form_text']), limit=80)}` | `{item['fanout_entry_count']:,}` | `{item['fanout_row_count']:,}` |"
            )

    if summary.top_meta_forms:
        lines.extend(["", "## Top Meta/Note Forms", "", "| Form | Reason | Rows |", "| --- | --- | ---: |"])
        for item in summary.top_meta_forms[:15]:
            lines.append(
                f"| `{_safe_preview(str(item['form_text']), limit=80)}` | `{item['meta_reason']}` | `{item['row_count']:,}` |"
            )

    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_root_summary(root_dir: Path, summaries: list[DbSummary], generated_at: str) -> None:
    rows = [summary.to_dict() for summary in summaries]
    (root_dir / "overall_summary.json").write_text(
        json.dumps({"generated_at": generated_at, "databases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tsv_headers = [
        "db",
        "file_size_bytes",
        "entry_count",
        "form_count",
        "headword_missing_glosses",
        "headword_symbol_only_glosses",
        "headword_non_latin_only_glosses",
        "headword_relation_only_glosses",
        "headword_gloss_parse_errors",
        "form_high_fanout_texts",
        "form_high_fanout_rows",
        "form_no_shared_same_script_rows",
        "form_no_shared_cross_script_rows",
        "form_meta_or_note_rows",
        "form_duplicate_groups",
        "form_duplicate_extra_rows",
        "skipped_reason",
    ]
    _write_tsv(root_dir / "overall_summary.tsv", tsv_headers, rows)

    ranked = sorted(
        summaries,
        key=lambda item: (
            -item.form_meta_or_note_rows,
            -item.form_high_fanout_rows,
            -item.headword_non_latin_only_glosses,
            item.db,
        ),
    )

    lines = [
        "# SQLite Prune Candidate Audit",
        "",
        f"- generated_at: `{generated_at}`",
        f"- source_dir: `{SQLITE_DIR}`",
        f"- high-fanout threshold: form appears in at least `{HIGH_FANOUT_ENTRY_THRESHOLD}` entries (`>{HIGH_FANOUT_OTHER_ENTRIES}` other entries)",
        "",
        "## Heuristics",
        "",
        "- `headwords_missing_glosses.tsv`: entry has no usable gloss text after JSON flattening.",
        "- `headwords_symbol_only_glosses.tsv`: glosses contain no letters at all.",
        "- `headwords_non_latin_only_glosses.tsv`: glosses have letters, but no Latin-script letters.",
        "- `headwords_relation_only_glosses.tsv`: every gloss starts like a redirect/relation gloss (`alternative form`, `inflection of`, `synonym`, etc.).",
        "- `forms_high_fanout_groups.tsv` / `forms_high_fanout_rows.tsv`: the exact `form_text` recurs in more than 10 other entries.",
        "- `forms_no_shared_letters_same_script.tsv`: headword and form share zero normalized letters after casefold + NFKD + mark stripping, while staying in the same non-CJK script.",
        "- `forms_no_shared_letters_cross_script_or_cjk.tsv`: same zero-share condition, but cross-script or CJK-sensitive; this is a caution bucket, not a delete recommendation.",
        "- `forms_meta_or_note_text.tsv`: form rows that look like grammar-table metadata or note text.",
        "- `forms_duplicate_groups.tsv`: exact duplicate `(entry_id, form_text, morph_tags, romanization)` groups.",
        "",
        "## Ranked Databases",
        "",
        "| DB | Entries | Forms | Missing Gloss | Non-Latin Gloss | Meta/Note Forms | High-Fanout Rows | No-Share Same Script | Duplicate Extra Rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for summary in ranked:
        lines.append(
            f"| `{summary.db}` | `{summary.entry_count:,}` | `{summary.form_count:,}` | "
            f"`{summary.headword_missing_glosses:,}` | `{summary.headword_non_latin_only_glosses:,}` | "
            f"`{summary.form_meta_or_note_rows:,}` | `{summary.form_high_fanout_rows:,}` | "
            f"`{summary.form_no_shared_same_script_rows:,}` | `{summary.form_duplicate_extra_rows:,}` |"
        )
    lines.append("")
    (root_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")

    master_lines = [
        "# SQLite Prune Candidate Master Report",
        "",
        "## Overview",
        "",
        f"- generated_at: `{generated_at}`",
        f"- source_dir: `{SQLITE_DIR}`",
        f"- databases_scanned: `{len(summaries)}`",
        f"- high-fanout threshold: at least `{HIGH_FANOUT_ENTRY_THRESHOLD}` entries (`>{HIGH_FANOUT_OTHER_ENTRIES}` other entries)",
        "",
        "Root-level files here are overview-only. All row-level findings remain inside each language/database subfolder.",
        "",
        "## Heuristics",
        "",
        "- Missing glosses: no usable gloss text after flattening the JSON/text payload.",
        "- Symbol-only glosses: glosses contain no letters at all.",
        "- Non-Latin-only glosses: glosses have letters, but no Latin-script letters.",
        "- Relation-only glosses: glosses are redirect/relation style only (`alternative form`, `inflection of`, `synonym of`, etc.).",
        "- High-fanout forms: exact `form_text` recurs in more than 10 other entries.",
        "- No-shared-letter same-script forms: headword and form share zero normalized letters in the same non-CJK script.",
        "- No-shared-letter cross-script/CJK forms: same zero-share condition, but script-sensitive and lower-confidence.",
        "- Meta/note forms: grammar labels or note text fossilized into `form_text`.",
        "- Duplicate form groups: exact duplicate `(entry_id, form_text, morph_tags, romanization)` rows.",
        "",
        "## Per-Language Sections",
        "",
    ]
    for summary in sorted(summaries, key=lambda item: item.db):
        master_lines.extend(
            [
                f"### {summary.db}",
                "",
                f"- entries: `{summary.entry_count:,}`",
                f"- forms: `{summary.form_count:,}`",
                f"- missing glosses: `{summary.headword_missing_glosses:,}`",
                f"- symbol-only glosses: `{summary.headword_symbol_only_glosses:,}`",
                f"- non-Latin-only glosses: `{summary.headword_non_latin_only_glosses:,}`",
                f"- relation-only glosses: `{summary.headword_relation_only_glosses:,}`",
                f"- meta/note form rows: `{summary.form_meta_or_note_rows:,}`",
                f"- high-fanout form texts: `{summary.form_high_fanout_texts:,}`",
                f"- high-fanout form rows: `{summary.form_high_fanout_rows:,}`",
                f"- no-shared-letter same-script rows: `{summary.form_no_shared_same_script_rows:,}`",
                f"- no-shared-letter cross-script/CJK rows: `{summary.form_no_shared_cross_script_rows:,}`",
                f"- duplicate form groups: `{summary.form_duplicate_groups:,}`",
                f"- duplicate extra rows: `{summary.form_duplicate_extra_rows:,}`",
            ]
        )
        if summary.top_high_fanout:
            master_lines.extend(["", "Top high-fanout forms:", ""])
            for item in summary.top_high_fanout[:5]:
                master_lines.append(
                    f"- `{_safe_preview(str(item['form_text']), limit=80)}`: `{item['fanout_entry_count']:,}` entries / `{item['fanout_row_count']:,}` rows"
                )
        if summary.top_meta_forms:
            master_lines.extend(["", "Top meta/note forms:", ""])
            for item in summary.top_meta_forms[:5]:
                master_lines.append(
                    f"- `{_safe_preview(str(item['form_text']), limit=80)}` ({item['meta_reason']}): `{item['row_count']:,}` rows"
                )
        master_lines.extend(
            [
                "",
                f"Detail folder: `{summary.db}/`",
                "",
            ]
        )
    (root_dir / "MASTER_REPORT.md").write_text("\n".join(master_lines), encoding="utf-8")


def _audit_db(path: Path, root_dir: Path) -> DbSummary:
    db_name = path.stem
    out_dir = root_dir / db_name
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = DbSummary(db=db_name, file_size_bytes=path.stat().st_size)

    if path.stat().st_size == 0:
        summary.skipped_reason = "zero-byte database"
        _write_db_summary(out_dir, summary)
        return summary

    _log(f"[audit] {db_name}: opening")
    conn = _open_db(path)
    try:
        summary.entry_count = _fetch_count(conn, "SELECT COUNT(*) FROM entries")
        summary.form_count = _fetch_count(conn, "SELECT COUNT(*) FROM forms")
        _log(f"[audit] {db_name}: entries={summary.entry_count:,} forms={summary.form_count:,}")

        _log(f"[audit] {db_name}: scanning headwords")
        _scan_entries(conn, out_dir, summary)

        _log(f"[audit] {db_name}: collecting high-fanout forms")
        high_fanout = _collect_high_fanout(conn)
        _write_high_fanout_groups(out_dir, summary, high_fanout)

        _log(f"[audit] {db_name}: scanning form rows")
        _scan_forms(conn, out_dir, summary, high_fanout)

        _log(f"[audit] {db_name}: scanning duplicate form groups")
        _scan_duplicate_form_groups(conn, out_dir, summary)
    finally:
        conn.close()

    _write_db_summary(out_dir, summary)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only SQLite pruning audit")
    parser.add_argument("db", nargs="*", help="Optional database stems or filenames to audit")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory. Defaults to reports/sqlite_prune_probe_<timestamp>",
    )
    args = parser.parse_args()

    db_paths = _discover_db_paths(args.db)
    if not db_paths:
        raise SystemExit("No matching .sqlite files found in dict_sqlite/")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else REPORTS_DIR / f"sqlite_prune_probe_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    _log(f"[audit] output_dir={output_dir}")
    _log(f"[audit] databases={len(db_paths)}")

    summaries: list[DbSummary] = []
    for path in db_paths:
        summaries.append(_audit_db(path, output_dir))

    _write_root_summary(output_dir, summaries, generated_at)
    _log(f"[audit] done: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
