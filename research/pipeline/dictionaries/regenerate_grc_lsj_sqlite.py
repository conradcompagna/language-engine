#!/usr/bin/env python3
"""Regenerate the LSJ Ancient Greek SQLite database."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dict_lookup_sqlite import _normalize_key


ROOT = Path(__file__).resolve().parent
SOURCE_DB_PATH = ROOT / "dict_sqlite" / "grc-lsj.rebuilt.sqlite"
TSV_PATH = ROOT / "reports" / "grc_lsj_greek_inflexion.tsv"
DEFAULT_OUTPUT_DB_PATH = ROOT / "dict_sqlite" / "grc-lsj.regenerated.sqlite"
DEFAULT_CLEANUP_REPORT_PATH = ROOT / "reports" / "grc_lsj_regeneration_cleanup.tsv"
DEFAULT_SUMMARY_PATH = ROOT / "reports" / "grc_lsj_regeneration_summary.json"
LANG_CODE = "grc"


CASE_MAP = {
    "N": "nominative",
    "G": "genitive",
    "D": "dative",
    "A": "accusative",
    "V": "vocative",
}

NUMBER_MAP = {
    "S": "singular",
    "D": "dual",
    "P": "plural",
}

GENDER_MAP = {
    "M": "masculine",
    "F": "feminine",
    "N": "neuter",
}

PERSON_MAP = {
    "1": "first",
    "2": "second",
    "3": "third",
}

TENSE_MAP = {
    "P": "present",
    "I": "imperfect",
    "F": "future",
    "A": "aorist",
    "X": "perfect",
    "Y": "pluperfect",
    "Z": "future perfect",
}

VOICE_MAP = {
    "A": "active",
    "M": "middle",
    "P": "passive",
    "E": "middle",
}

MOOD_MAP = {
    "I": "indicative",
    "D": "imperative",
    "N": "infinitive",
    "P": "participle",
    "S": "subjunctive",
    "O": "optative",
}

BAD_GLOSS_WORDS = {
    "",
    "cf",
    "cf.",
    "qv",
    "q.v",
    "q.v.",
    "n",
    "n.",
    "n^",
    "ne",
    "sm-",
    "sems",
}

RE_GREEK_ONLY = re.compile(r"^[\u0370-\u03ff\u1f00-\u1fff\s\W_]+$")
RE_LATIN_LETTERS = re.compile(r"[A-Za-z]")
RE_ONLY_NUMERIC = re.compile(r"^[0-9ivxlcdmIVXLCDM\s\W_]+$")

ENTRY_BATCH_SIZE = 2000
GENERATED_STAGE_BATCH_SIZE = 10000


@dataclass
class EntryRow:
    id: int
    headword: str
    headword_key: str
    romanization: str
    pos: str
    glosses: str
    forms: str
    commentary: str
    lemma: str
    etymology: str
    etymology_number: int
    source: str
    entry_id: str
    tags: str
    format: str
    gloss_texts: list[str] = field(default_factory=list)
    usable_gloss_texts: list[str] = field(default_factory=list)
    parsed_forms: list[tuple[str, str, str]] = field(default_factory=list)
    usable: bool = False

    @property
    def kind(self) -> str:
        pos = self.pos.strip().lower()
        if pos == "verb":
            return "verb"
        if pos in {"noun", "adj"}:
            return "nominal"
        return "other"

    @property
    def gloss_score(self) -> tuple[int, int, int, int]:
        usable_count = len(self.usable_gloss_texts)
        usable_chars = sum(len(text) for text in self.usable_gloss_texts)
        total_chars = sum(len(text) for text in self.gloss_texts)
        return (usable_count, usable_chars, total_chars, -self.id)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_gloss_texts(raw_glosses: str) -> list[str]:
    try:
        parsed = json.loads(raw_glosses or "[]")
    except Exception:
        parsed = []

    out: list[str] = []

    def add_text(text: Any) -> None:
        value = unicodedata.normalize("NFKC", str(text or "")).strip()
        if value:
            out.append(value)

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                glosses = item.get("glosses") or []
                if isinstance(glosses, list):
                    for gloss in glosses:
                        add_text(gloss)
                else:
                    add_text(glosses)
            else:
                add_text(item)
    elif isinstance(parsed, dict):
        glosses = parsed.get("glosses") or []
        if isinstance(glosses, list):
            for gloss in glosses:
                add_text(gloss)
        else:
            add_text(glosses)
    elif isinstance(parsed, str):
        add_text(parsed)
    return out


def is_usable_gloss_text(text: str) -> bool:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    if not value:
        return False
    lowered = re.sub(r"[\s\W_]+", "", value.lower())
    if lowered in BAD_GLOSS_WORDS:
        return False
    if RE_ONLY_NUMERIC.fullmatch(value):
        return False
    if RE_GREEK_ONLY.fullmatch(value):
        return False
    if not RE_LATIN_LETTERS.search(value):
        return False
    if sum(1 for ch in value if ch.isalpha()) < 2:
        return False
    return True


def parse_forms_json(raw_forms: str) -> list[tuple[str, str, str]]:
    try:
        parsed = json.loads(raw_forms or "[]")
    except Exception:
        return []

    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    if not isinstance(parsed, list):
        return out

    for item in parsed:
        form_text = ""
        morph_tags = ""
        romanization = ""
        if isinstance(item, (list, tuple)):
            form_text = str(item[0] if len(item) > 0 else "").strip()
            morph_tags = str(item[1] if len(item) > 1 else "").strip()
            romanization = str(item[2] if len(item) > 2 else "").strip()
        elif isinstance(item, dict):
            form_text = str(item.get("form") or item.get("text") or "").strip()
            morph_tags = str(item.get("tags") or item.get("label") or item.get("commentary") or "").strip()
            romanization = str(
                item.get("romanization") or item.get("reading") or item.get("pronunciation") or ""
            ).strip()
        if not form_text:
            continue
        ident = (form_text, morph_tags, romanization)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(ident)
    return out


def build_form_list(form_rows: list[tuple[str, str, str]]) -> list[list[str]]:
    out: list[list[str]] = []
    seen: set[tuple[str, str, str]] = set()
    for form_text, morph_tags, romanization in form_rows:
        ident = (form_text, morph_tags, romanization)
        if ident in seen:
            continue
        seen.add(ident)
        out.append([form_text, morph_tags, romanization])
    return out


def score_entry(entry: EntryRow) -> tuple[int, int, int, int]:
    return entry.gloss_score


def choose_best_entry(entries: list[EntryRow]) -> EntryRow:
    return max(entries, key=score_entry)


def decode_nominal_key(key: str) -> list[str]:
    if len(key) != 3:
        return [key.lower()]
    out: list[str] = []
    case = CASE_MAP.get(key[0])
    number = NUMBER_MAP.get(key[1])
    gender = GENDER_MAP.get(key[2])
    if case:
        out.append(case)
    if number:
        out.append(number)
    if gender:
        out.append(gender)
    return out or [key.lower()]


def decode_person_number(key: str) -> list[str]:
    if len(key) != 2:
        return [key.lower()]
    out: list[str] = []
    person = PERSON_MAP.get(key[0])
    number = NUMBER_MAP.get(key[1])
    if person:
        out.append(person)
    if number:
        out.append(number)
    return out or [key.lower()]


def decode_verb_prefix(prefix: str) -> list[str]:
    prefix = (prefix or "").strip().upper()
    if len(prefix) != 3:
        return [prefix.lower()] if prefix else []
    out: list[str] = []
    tense = TENSE_MAP.get(prefix[0])
    voice = VOICE_MAP.get(prefix[1])
    mood = MOOD_MAP.get(prefix[2])
    if tense:
        out.append(tense)
    if voice:
        out.append(voice)
    if mood:
        out.append(mood)
    return out or [prefix.lower()]


def expand_generated_tags(engine_kind: str, generated_key: str) -> str:
    engine_kind = str(engine_kind or "").strip().lower()
    generated_key = str(generated_key or "").strip()
    if not generated_key:
        return ""

    if engine_kind == "nominal":
        return "; ".join(decode_nominal_key(generated_key))

    if "." in generated_key:
        prefix, suffix = generated_key.split(".", 1)
    else:
        prefix, suffix = generated_key, ""

    tags = decode_verb_prefix(prefix)

    if suffix:
        if re.fullmatch(r"[123][SDP]", suffix):
            tags.extend(decode_person_number(suffix))
        elif re.fullmatch(r"[NGDAV][SP][MFN]", suffix):
            tags.extend(decode_nominal_key(suffix))
        else:
            tags.append(suffix.lower())

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        tag = str(tag or "").strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        deduped.append(tag)
    return "; ".join(deduped)


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS forms;
        DROP TABLE IF EXISTS entries;
        DROP TABLE IF EXISTS meta;

        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headword TEXT NOT NULL,
            headword_key TEXT NOT NULL,
            romanization TEXT NOT NULL DEFAULT '',
            pos TEXT NOT NULL DEFAULT '',
            glosses TEXT NOT NULL DEFAULT '[]',
            forms TEXT NOT NULL DEFAULT '[]',
            commentary TEXT NOT NULL DEFAULT '',
            lemma TEXT NOT NULL DEFAULT '',
            etymology TEXT NOT NULL DEFAULT '',
            etymology_number INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT '',
            entry_id TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT 'compact'
        );

        CREATE TABLE forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id),
            form_text TEXT NOT NULL,
            form_key TEXT NOT NULL,
            morph_tags TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )


def load_source_entries(conn: sqlite3.Connection) -> list[EntryRow]:
    conn.row_factory = sqlite3.Row
    rows: list[EntryRow] = []
    for row in conn.execute("SELECT * FROM entries ORDER BY headword, id"):
        entry = EntryRow(
            id=int(row["id"]),
            headword=str(row["headword"] or "").strip(),
            headword_key=str(row["headword_key"] or "").strip(),
            romanization=str(row["romanization"] or "").strip(),
            pos=str(row["pos"] or "").strip(),
            glosses=str(row["glosses"] or "[]"),
            forms=str(row["forms"] or "[]"),
            commentary=str(row["commentary"] or "").strip(),
            lemma=str(row["lemma"] or "").strip(),
            etymology=str(row["etymology"] or "").strip(),
            etymology_number=int(row["etymology_number"] or 0),
            source=str(row["source"] or "").strip(),
            entry_id=str(row["entry_id"] or "").strip(),
            tags=str(row["tags"] or "").strip(),
            format=str(row["format"] or "").strip(),
        )
        entry.gloss_texts = parse_gloss_texts(entry.glosses)
        entry.usable_gloss_texts = [text for text in entry.gloss_texts if is_usable_gloss_text(text)]
        entry.usable = bool(entry.usable_gloss_texts)
        entry.parsed_forms = parse_forms_json(entry.forms)
        rows.append(entry)
    return rows


def build_form_key_cache(entries: list[EntryRow]) -> dict[str, str]:
    cache: dict[str, str] = {}
    for entry in entries:
        for form_text, _tag, _roman in entry.parsed_forms:
            if form_text and form_text not in cache:
                cache[form_text] = _normalize_key(form_text, LANG_CODE)
    return cache


def resolve_redirect_target(
    entry: EntryRow,
    usable_by_headword: dict[str, list[EntryRow]],
    canonical_by_headword: dict[str, EntryRow],
    canonical_by_key: dict[str, EntryRow],
    form_key_cache: dict[str, str],
) -> tuple[EntryRow | None, str]:
    same_headword = usable_by_headword.get(entry.headword) or []
    if same_headword:
        return canonical_by_headword[entry.headword], "same_headword"

    for form_text, morph_tags, _romanization in entry.parsed_forms:
        tag = str(morph_tags or "").strip().lower()
        if not tag.startswith("variant=orth"):
            continue
        exact = canonical_by_headword.get(form_text)
        if exact is not None:
            return exact, "variant_orth_exact"
        form_key = form_key_cache.get(form_text)
        if form_key is None:
            form_key = _normalize_key(form_text, LANG_CODE)
            form_key_cache[form_text] = form_key
        keyed = canonical_by_key.get(form_key)
        if keyed is not None:
            return keyed, "variant_orth_key"

    keyed = canonical_by_key.get(entry.headword_key)
    if keyed is not None:
        return keyed, "same_key"

    return None, ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate the Ancient Greek LSJ SQLite database")
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB_PATH, help="Input LSJ SQLite database")
    parser.add_argument("--tsv", type=Path, default=TSV_PATH, help="greek-inflexion TSV export")
    parser.add_argument("--output-db", type=Path, default=DEFAULT_OUTPUT_DB_PATH, help="Output regenerated SQLite database")
    parser.add_argument("--cleanup-report", type=Path, default=DEFAULT_CLEANUP_REPORT_PATH, help="TSV report of deletions and redirects")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="JSON summary of the rebuild")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.source_db.exists():
        raise FileNotFoundError(f"Source database not found: {args.source_db}")
    if not args.tsv.exists():
        raise FileNotFoundError(f"Inflection TSV not found: {args.tsv}")

    args.output_db.parent.mkdir(parents=True, exist_ok=True)
    args.cleanup_report.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    temp_output = args.output_db.with_name(args.output_db.name + ".tmp.sqlite")
    if temp_output.exists():
        temp_output.unlink()
    if args.output_db.exists():
        args.output_db.unlink()

    started = time.time()

    source_conn = sqlite3.connect(str(args.source_db))
    try:
        source_entries = load_source_entries(source_conn)
    finally:
        source_conn.close()

    usable_by_headword: dict[str, list[EntryRow]] = defaultdict(list)
    usable_by_key: dict[str, list[EntryRow]] = defaultdict(list)
    for entry in source_entries:
        if entry.usable:
            usable_by_headword[entry.headword].append(entry)
            usable_by_key[entry.headword_key].append(entry)

    canonical_by_headword: dict[str, EntryRow] = {
        headword: choose_best_entry(group) for headword, group in usable_by_headword.items()
    }
    canonical_by_key: dict[str, EntryRow] = {
        key: choose_best_entry(group) for key, group in usable_by_key.items()
    }
    form_key_cache = build_form_key_cache(source_entries)

    # Redirect individual unusable rows when the target is clear.
    alias_forms_by_target_id: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
    redirect_target_headwords_by_source: defaultdict[str, Counter[str]] = defaultdict(Counter)
    cleanup_rows: list[list[str]] = []
    deleted_unusable = 0
    redirected_unusable = 0

    for entry in source_entries:
        if entry.usable:
            continue
        target, reason = resolve_redirect_target(
            entry,
            usable_by_headword,
            canonical_by_headword,
            canonical_by_key,
            form_key_cache,
        )
        if target is None:
            cleanup_rows.append(
                [
                    str(entry.id),
                    entry.headword,
                    entry.headword_key,
                    entry.pos,
                    "delete",
                    "",
                    "",
                    "",
                    reason or "no_clear_target",
                    compact_json(entry.gloss_texts),
                    compact_json(entry.parsed_forms),
                ]
            )
            deleted_unusable += 1
            continue

        redirected_unusable += 1
        if entry.headword and entry.headword != target.headword:
            redirect_target_headwords_by_source[entry.headword][target.headword] += 1

        alias_forms = list(entry.parsed_forms)
        if entry.headword and entry.headword != target.headword:
            alias_form = (entry.headword, "variant=orth", entry.romanization)
            if alias_form not in alias_forms:
                alias_forms.append(alias_form)
        for form in alias_forms:
            alias_forms_by_target_id[target.id].append(form)

        cleanup_rows.append(
            [
                str(entry.id),
                entry.headword,
                entry.headword_key,
                entry.pos,
                "redirect",
                str(target.id),
                target.headword,
                target.kind,
                reason,
                compact_json(entry.gloss_texts),
                compact_json(alias_forms),
            ]
        )

    # Source headwords that disappear entirely can inherit a redirect target for
    # the generated paradigms, but only when the target is unambiguous.
    redirect_headword_map: dict[str, str] = {}
    for source_headword, counts in redirect_target_headwords_by_source.items():
        if source_headword in usable_by_headword:
            continue
        if len(counts) != 1:
            continue
        redirect_headword_map[source_headword] = next(iter(counts.keys()))

    canonical_survivor_by_headword: dict[str, EntryRow] = {
        headword: choose_best_entry(group) for headword, group in usable_by_headword.items()
    }

    conn = sqlite3.connect(str(temp_output))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-200000")
    create_schema(conn)

    entry_insert_batch: list[tuple[Any, ...]] = []
    form_insert_batch: list[tuple[Any, ...]] = []
    inserted_entries = 0
    inserted_source_form_rows = 0

    def flush_batches() -> None:
        nonlocal entry_insert_batch, form_insert_batch, inserted_entries, inserted_source_form_rows
        if entry_insert_batch:
            conn.executemany(
                """
                INSERT INTO entries (
                    id, headword, headword_key, romanization, pos, glosses, forms,
                    commentary, lemma, etymology, etymology_number, source, entry_id,
                    tags, format
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                entry_insert_batch,
            )
            inserted_entries += len(entry_insert_batch)
            entry_insert_batch = []
        if form_insert_batch:
            conn.executemany(
                """
                INSERT INTO forms (entry_id, form_text, form_key, morph_tags, romanization)
                VALUES (?,?,?,?,?)
                """,
                form_insert_batch,
            )
            inserted_source_form_rows += len(form_insert_batch)
            form_insert_batch = []
        conn.commit()

    for entry in source_entries:
        if not entry.usable:
            continue

        base_forms = list(entry.parsed_forms)
        extra_forms = alias_forms_by_target_id.get(entry.id, [])
        merged_forms = base_forms[:]
        seen_forms = {(ft, mt, rom) for ft, mt, rom in merged_forms}
        for form_text, morph_tags, romanization in extra_forms:
            ident = (form_text, morph_tags, romanization)
            if ident in seen_forms:
                continue
            seen_forms.add(ident)
            merged_forms.append(ident)

        forms_json = compact_json(build_form_list(merged_forms))
        entry_insert_batch.append(
            (
                entry.id,
                entry.headword,
                entry.headword_key,
                entry.romanization,
                entry.pos,
                entry.glosses,
                forms_json,
                entry.commentary,
                entry.lemma,
                entry.etymology,
                entry.etymology_number,
                entry.source,
                entry.entry_id,
                entry.tags,
                entry.format or "compact",
            )
        )

        for form_text, morph_tags, romanization in merged_forms:
            form_key = form_key_cache.get(form_text)
            if form_key is None:
                form_key = _normalize_key(form_text, LANG_CODE)
                form_key_cache[form_text] = form_key
            if not form_key:
                continue
            form_insert_batch.append((entry.id, form_text, form_key, morph_tags, romanization))

        if len(entry_insert_batch) >= ENTRY_BATCH_SIZE or len(form_insert_batch) >= 50000:
            flush_batches()

    flush_batches()

    conn.execute(
        """
        CREATE TEMP TABLE generated_forms_stage (
            entry_id INTEGER NOT NULL,
            form_text TEXT NOT NULL,
            form_key TEXT NOT NULL,
            morph_tags TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT '',
            UNIQUE(entry_id, form_text, form_key, morph_tags, romanization)
        )
        """
    )
    conn.execute(
        "CREATE INDEX idx_generated_forms_stage_entry_id ON generated_forms_stage(entry_id)"
    )

    stage_batch: list[tuple[Any, ...]] = []
    stage_rows_inserted = 0
    stage_rows_skipped_no_target = 0
    generated_forms_seen: set[str] = set()

    with args.tsv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames or "headword" not in reader.fieldnames:
            raise ValueError(f"TSV missing expected columns: {args.tsv}")

        for row in reader:
            headword = str(row.get("headword") or "").strip()
            engine_kind = str(row.get("engine_kind") or "").strip().lower()
            generated_form = str(row.get("generated_form") or "").strip()
            generated_key = str(row.get("generated_key") or "").strip()
            if not headword or not generated_form or not engine_kind:
                continue

            target_headword = headword if headword in canonical_survivor_by_headword else redirect_headword_map.get(headword)
            target_entry = canonical_survivor_by_headword.get(target_headword or "")
            if target_entry is None:
                stage_rows_skipped_no_target += 1
                continue

            morph_tags = expand_generated_tags(engine_kind, generated_key)
            form_key = form_key_cache.get(generated_form)
            if form_key is None:
                form_key = _normalize_key(generated_form, LANG_CODE)
                form_key_cache[generated_form] = form_key
            if not form_key:
                continue

            ident = f"{target_entry.id}\u241f{generated_form}\u241f{form_key}\u241f{morph_tags}"
            if ident in generated_forms_seen:
                continue
            generated_forms_seen.add(ident)
            stage_batch.append((target_entry.id, generated_form, form_key, morph_tags, ""))

            if len(stage_batch) >= GENERATED_STAGE_BATCH_SIZE:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO generated_forms_stage
                        (entry_id, form_text, form_key, morph_tags, romanization)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    stage_batch,
                )
                stage_rows_inserted += len(stage_batch)
                stage_batch = []
                if stage_rows_inserted % 100000 == 0:
                    print(
                        f"staged_generated={stage_rows_inserted:,} skipped_no_target={stage_rows_skipped_no_target:,}",
                        file=sys.stderr,
                    )

    if stage_batch:
        conn.executemany(
            """
            INSERT OR IGNORE INTO generated_forms_stage
                (entry_id, form_text, form_key, morph_tags, romanization)
            VALUES (?, ?, ?, ?, ?)
            """,
            stage_batch,
        )
        stage_rows_inserted += len(stage_batch)
        stage_batch = []

    conn.commit()

    generated_rows_inserted = 0
    generated_targets_seen = 0
    stage_cur = conn.execute(
        """
        SELECT entry_id, form_text, form_key, morph_tags, romanization
        FROM generated_forms_stage
        ORDER BY entry_id, form_text, form_key, morph_tags, romanization
        """
    )

    current_entry_id: int | None = None
    current_rows: list[sqlite3.Row] = []

    def flush_generated_group(entry_id: int, rows: list[sqlite3.Row]) -> None:
        nonlocal generated_rows_inserted, generated_targets_seen
        if not rows:
            return
        generated_targets_seen += 1
        entry_row = conn.execute(
            "SELECT forms FROM entries WHERE id = ?",
            (int(entry_id),),
        ).fetchone()
        if entry_row is None:
            return
        existing_forms = parse_forms_json(str(entry_row["forms"] or "[]"))
        seen = {(ft, mt, rom) for ft, mt, rom in existing_forms}
        generated_form_triplets: list[tuple[str, str, str]] = []
        generated_form_quads: list[tuple[str, str, str, str]] = []
        for row in rows:
            form_tuple = (
                str(row["form_text"] or "").strip(),
                str(row["form_key"] or "").strip(),
                str(row["morph_tags"] or "").strip(),
                str(row["romanization"] or "").strip(),
            )
            if not form_tuple[0]:
                continue
            triplet = (form_tuple[0], form_tuple[2], form_tuple[3])
            if triplet in seen:
                continue
            seen.add(triplet)
            generated_form_triplets.append(triplet)
            generated_form_quads.append(form_tuple)
        if not generated_form_quads:
            return

        merged_forms = existing_forms + generated_form_triplets
        conn.execute(
            "UPDATE entries SET forms = ? WHERE id = ?",
            (compact_json(build_form_list(merged_forms)), int(entry_id)),
        )
        conn.executemany(
            """
            INSERT INTO forms (entry_id, form_text, form_key, morph_tags, romanization)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    int(entry_id),
                    form_text,
                    form_key,
                    morph_tags,
                    romanization,
                )
                for form_text, form_key, morph_tags, romanization in generated_form_quads
            ],
        )
        generated_rows_inserted += len(generated_form_quads)

    for row in stage_cur:
        entry_id = int(row["entry_id"] or 0)
        if current_entry_id is None:
            current_entry_id = entry_id
        if entry_id != current_entry_id:
            flush_generated_group(current_entry_id, current_rows)
            current_entry_id = entry_id
            current_rows = [row]
        else:
            current_rows.append(row)
    if current_entry_id is not None:
        flush_generated_group(current_entry_id, current_rows)

    conn.commit()

    conn.execute("DROP TABLE generated_forms_stage")
    conn.execute("CREATE INDEX idx_entries_headword_key ON entries(headword_key)")
    conn.execute("CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != ''")
    conn.execute("CREATE INDEX idx_forms_form_key ON forms(form_key)")
    conn.execute("CREATE INDEX idx_forms_entry_id ON forms(entry_id)")

    meta_values = {
        "lang_code": LANG_CODE,
        "source_label": "lsj",
        "source_db": str(args.source_db),
        "source_tsv": str(args.tsv),
        "entry_count": str(int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] or 0)),
        "form_count": str(int(conn.execute("SELECT COUNT(*) FROM forms").fetchone()[0] or 0)),
        "generated_targets": str(generated_targets_seen),
        "generated_rows_inserted": str(generated_rows_inserted),
        "deleted_unusable": str(deleted_unusable),
        "redirected_unusable": str(redirected_unusable),
        "redirectable_source_headwords": str(len(redirect_headword_map)),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "regenerated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        list(meta_values.items()),
    )
    conn.commit()

    cleanup_report_headers = [
        "id",
        "headword",
        "headword_key",
        "pos",
        "action",
        "target_id",
        "target_headword",
        "target_kind",
        "reason",
        "glosses_json",
        "forms_json",
    ]
    with args.cleanup_report.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(cleanup_report_headers)
        writer.writerows(cleanup_rows)

    summary = {
        "source_db": str(args.source_db),
        "source_tsv": str(args.tsv),
        "output_db": str(args.output_db),
        "total_source_entries": len(source_entries),
        "usable_source_entries": sum(1 for entry in source_entries if entry.usable),
        "deleted_unusable": deleted_unusable,
        "redirected_unusable": redirected_unusable,
        "redirectable_source_headwords": len(redirect_headword_map),
        "canonical_surviving_headwords": len(canonical_survivor_by_headword),
        "generated_targets_seen": generated_targets_seen,
        "generated_rows_inserted": generated_rows_inserted,
        "generated_rows_staged": stage_rows_inserted,
        "generated_rows_skipped_no_target": stage_rows_skipped_no_target,
        "final_entry_count": int(meta_values["entry_count"]),
        "final_form_count": int(meta_values["form_count"]),
        "elapsed_seconds": round(time.time() - started, 2),
    }
    args.summary.write_text(compact_json(summary), encoding="utf-8")

    conn.execute("PRAGMA optimize")
    conn.commit()
    conn.close()

    if temp_output.exists():
        temp_output.replace(args.output_db)

    print(compact_json(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
