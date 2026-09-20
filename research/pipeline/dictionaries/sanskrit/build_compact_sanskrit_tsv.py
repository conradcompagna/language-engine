#!/usr/bin/env python3
"""Build a compact Sanskrit TSV from MW plus generated inflected forms.

Output columns:
  headword  pos  romanization  glosses  forms

This matches the compact TSV shape used by the app's Wiktionary-based
pipelines. Alternative headword variants are folded into ``forms`` with the
``alternative`` tag, and generated inflected forms are merged into the same
column with brief morphological tags.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from convert_mw_to_tsv import parse_mw_file


SCRIPT_DIR = Path(__file__).resolve().parent
MW_PATH = SCRIPT_DIR / "txt" / "mw.txt"
INFLECTED_PATH = SCRIPT_DIR / "sanskrit_all_forms.tsv"
OUT_PATH = SCRIPT_DIR / "dict-sanskrit.tsv"

TSV_HEADERS = ["headword", "pos", "romanization", "glosses", "forms"]

NOMINAL_CASE_MAP = {
    "1": "nominative",
    "2": "accusative",
    "3": "instrumental",
    "4": "dative",
    "5": "ablative",
    "6": "genitive",
    "7": "locative",
    "8": "vocative",
}
NUMBER_MAP = {
    "s": "singular",
    "d": "dual",
    "p": "plural",
}
PERSON_MAP = {
    "1": "first-person",
    "2": "second-person",
    "3": "third-person",
}
VOICE_MAP = {
    "a": "active",
    "m": "middle",
    "p": "passive",
}
VERB_TAM_MAP = {
    "aor": "aorist",
    "ben": "benedictive",
    "con": "conditional",
    "fut": "future",
    "inj": "injunctive",
    "ipf": "imperfect",
    "ipv": "imperative",
    "opt": "optative",
    "pft": "periphrastic-future",
    "ppf": "periphrastic-perfect",
    "pre": "present",
    "prf": "perfect",
}

RE_GLOSS_ADJ_PREFIX = re.compile(r"^(?:mfn|mf(?:\([^)]*\))?n)\.", re.IGNORECASE)
RE_GLOSS_NOUN_PREFIX = re.compile(
    r"^(?:m(?:\([^)]*\))?|f(?:\([^)]*\))?|n(?:\([^)]*\))?|mn)\.",
    re.IGNORECASE,
)
RE_NAME_GLOSS = re.compile(r"\bN\. of\b")


def sanitize_text(text: str) -> str:
    """Collapse whitespace so values stay safe in raw tab-joined TSV rows."""
    return " ".join(str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").split()).strip()


def clean_glosses(glosses: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for gloss in glosses:
        cleaned = sanitize_text(gloss)
        if not cleaned or len(cleaned) <= 1:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def split_form_targets(mw_lnums: str, mw_headwords: str) -> List[Tuple[str, str]]:
    """Split multi-target rows while preserving literal pipes inside headwords."""
    lid_text = sanitize_text(mw_lnums)
    head_text = sanitize_text(mw_headwords)
    if not lid_text:
        return []

    lparts = [sanitize_text(part) for part in lid_text.split("|") if sanitize_text(part)]
    hparts = [sanitize_text(part) for part in head_text.split("|") if sanitize_text(part)]

    if len(lparts) > 1:
        if len(hparts) == len(lparts):
            return list(zip(lparts, hparts))
        if len(hparts) == 1:
            return [(lid, hparts[0]) for lid in lparts]

    return [(lid_text, head_text)]


def build_nominal_tags(slot_label: str) -> List[str]:
    slot = sanitize_text(slot_label)
    if slot == "ind":
        return ["indeclinable"]
    if len(slot) != 2:
        return [slot] if slot else []

    case_label = NOMINAL_CASE_MAP.get(slot[0], "")
    number_label = NUMBER_MAP.get(slot[1], "")
    return [tag for tag in (case_label, number_label) if tag]


def build_verb_tags(slot_label: str, model: str) -> List[str]:
    tags: List[str] = []

    parts = [sanitize_text(part) for part in sanitize_text(model).split(",")]
    if len(parts) == 3:
        voice = VOICE_MAP.get(parts[1], parts[1])
        tam = VERB_TAM_MAP.get(parts[2], parts[2])
        if tam:
            tags.append(tam)
        if voice:
            tags.append(voice)

    slot = sanitize_text(slot_label)
    if len(slot) == 2:
        person = PERSON_MAP.get(slot[0], "")
        number = NUMBER_MAP.get(slot[1], "")
        if person:
            tags.append(person)
        if number:
            tags.append(number)
    elif slot:
        tags.append(slot)

    return tags


def build_form_tag_string(form_type: str, slot_label: str, model: str) -> str:
    form_kind = sanitize_text(form_type)
    if form_kind == "nominal":
        tags = build_nominal_tags(slot_label)
    elif form_kind == "verb":
        tags = build_verb_tags(slot_label, model)
    else:
        tags = [sanitize_text(slot_label)] if sanitize_text(slot_label) else []
    return ";".join(tag for tag in tags if tag)


def normalize_pos(
    raw_pos: str,
    headword: str,
    glosses: Sequence[str],
    lid: str,
    form_types_by_lid: Dict[str, set],
) -> str:
    pos = sanitize_text(raw_pos)
    if pos:
        return pos

    first_gloss = glosses[0] if glosses else ""
    first_gloss_lc = first_gloss.lower()
    form_types = form_types_by_lid.get(lid, set())

    if "verb" in form_types:
        return "verb"
    if RE_NAME_GLOSS.search(first_gloss):
        return "name"
    if len(headword) == 1 and "letter" in first_gloss_lc:
        return "character"
    if "interjection" in first_gloss_lc:
        return "intj"
    if "vocative particle" in first_gloss_lc or " particle" in first_gloss_lc:
        return "particle"
    if "prefix" in first_gloss_lc or "prefixed to" in first_gloss_lc:
        return "prefix"
    if first_gloss_lc.startswith("the suffix") or " suffix " in first_gloss_lc:
        return "suffix"
    if "pronoun" in first_gloss_lc or "pronom." in first_gloss_lc:
        return "pron"
    if "conjunction" in first_gloss_lc:
        return "conj"
    if "adverb" in first_gloss_lc or "indeclinable" in first_gloss_lc or "indecl." in first_gloss_lc:
        return "adv"
    if RE_GLOSS_ADJ_PREFIX.match(first_gloss):
        return "adj"
    if RE_GLOSS_NOUN_PREFIX.match(first_gloss):
        return "noun"
    if "nominal" in form_types:
        return "noun"
    if first_gloss_lc.startswith("see ") or first_gloss_lc.startswith("[cf.") or first_gloss_lc.startswith("cf. "):
        return ""
    if first_gloss_lc.startswith("a g. of"):
        return "name"
    return "noun"


def build_forms_db(entry_variants_by_lid: Dict[str, Tuple[str, ...]]):
    """Store generated forms on disk so we can merge 7M rows safely."""
    tmp_file = tempfile.NamedTemporaryFile(
        prefix="sa_forms_",
        suffix=".sqlite3",
        dir=SCRIPT_DIR,
        delete=False,
    )
    tmp_file.close()
    db_path = Path(tmp_file.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -200000")
    conn.execute("CREATE TABLE forms (lid TEXT NOT NULL, form TEXT NOT NULL, tags TEXT NOT NULL)")

    known_lids = set(entry_variants_by_lid)
    form_types_by_lid: Dict[str, set] = defaultdict(set)
    stats = Counter()
    batch: List[Tuple[str, str, str]] = []

    def flush_batch() -> None:
        if not batch:
            return
        conn.executemany(
            "INSERT INTO forms (lid, form, tags) VALUES (?, ?, ?)",
            batch,
        )
        batch.clear()

    with INFLECTED_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            stats["rows_seen"] += 1
            form_text = sanitize_text(row.get("form", ""))
            if not form_text:
                stats["blank_form_skipped"] += 1
                continue

            tags = build_form_tag_string(
                row.get("type", ""),
                row.get("slot_label", ""),
                row.get("model", ""),
            )
            if not tags:
                stats["blank_tags_skipped"] += 1
                continue

            targets = split_form_targets(
                row.get("mw_lnums", ""),
                row.get("mw_headwords", ""),
            )
            if not targets:
                stats["untargeted_rows"] += 1
                continue

            for lid, _headword in targets:
                if lid not in known_lids:
                    stats["unknown_lid_skipped"] += 1
                    continue
                form_type = sanitize_text(row.get("type", ""))
                if form_type:
                    form_types_by_lid[lid].add(form_type)
                if form_text in entry_variants_by_lid[lid]:
                    stats["same_as_headword_skipped"] += 1
                    continue
                batch.append((lid, form_text, tags))
                stats["rows_inserted"] += 1
                if len(batch) >= 5000:
                    flush_batch()

    flush_batch()
    conn.commit()
    conn.execute("CREATE INDEX idx_forms_lid ON forms(lid)")
    conn.commit()
    return conn, db_path, form_types_by_lid, stats


def collect_forms(conn: sqlite3.Connection, lid: str, alt_forms: Iterable[str]) -> List[List[str]]:
    forms: List[List[str]] = []
    seen = set()

    for alt in alt_forms:
        alt_text = sanitize_text(alt)
        if not alt_text:
            continue
        triple = (alt_text, "alternative", "")
        if triple in seen:
            continue
        seen.add(triple)
        forms.append([alt_text, "alternative", ""])

    rows = conn.execute(
        "SELECT form, tags FROM forms WHERE lid = ? ORDER BY rowid",
        (lid,),
    )
    for form_text, tags in rows:
        cleaned_form = sanitize_text(form_text)
        cleaned_tags = sanitize_text(tags)
        if not cleaned_form or not cleaned_tags:
            continue
        triple = (cleaned_form, cleaned_tags, "")
        if triple in seen:
            continue
        seen.add(triple)
        forms.append([cleaned_form, cleaned_tags, ""])

    return forms


def main() -> int:
    if not MW_PATH.exists():
        print(f"Error: {MW_PATH} not found", file=sys.stderr)
        return 1
    if not INFLECTED_PATH.exists():
        print(f"Error: {INFLECTED_PATH} not found", file=sys.stderr)
        return 1

    print(f"Parsing {MW_PATH}...")
    grouped, order = parse_mw_file(MW_PATH)

    entries = []
    entry_variants_by_lid: Dict[str, Tuple[str, ...]] = {}
    for key in order:
        raw_entry = grouped[key]
        lid = sanitize_text(raw_entry.get("lid", ""))
        headword = sanitize_text(raw_entry.get("headword", "")).replace("/", "")
        k1 = sanitize_text(raw_entry.get("k1", "")).replace("/", "")
        glosses = clean_glosses(raw_entry.get("glosses", []))
        if not lid or not headword or not glosses:
            continue

        variants = [headword]
        if k1 and k1 != headword:
            variants.append(k1)

        entry_variants_by_lid[lid] = tuple(dict.fromkeys(variants))
        entries.append(
            {
                "lid": lid,
                "headword": headword,
                "k1": k1,
                "raw_pos": sanitize_text(raw_entry.get("pos_raw", "")),
                "glosses": glosses,
            }
        )

    print(f"Prepared {len(entries):,} MW entries for compact export")

    conn = None
    db_path: Path | None = None
    try:
        print(f"Ingesting {INFLECTED_PATH}...")
        conn, db_path, form_types_by_lid, form_stats = build_forms_db(entry_variants_by_lid)
        print(
            "Indexed inflected forms: "
            f"{form_stats['rows_inserted']:,} rows kept, "
            f"{form_stats['same_as_headword_skipped']:,} same-as-lemma rows skipped"
        )

        written = 0
        blank_pos = 0
        pos_counter = Counter()

        with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
            f.write("\t".join(TSV_HEADERS) + "\n")
            for entry in entries:
                lid = entry["lid"]
                headword = entry["headword"]
                pos = normalize_pos(
                    entry["raw_pos"],
                    headword,
                    entry["glosses"],
                    lid,
                    form_types_by_lid,
                )
                if not pos:
                    blank_pos += 1
                else:
                    pos_counter[pos] += 1

                glosses_json = json.dumps(
                    [{"glosses": [gloss]} for gloss in entry["glosses"]],
                    ensure_ascii=False,
                )
                alt_forms = []
                if entry["k1"] and entry["k1"] != headword:
                    alt_forms.append(entry["k1"])
                forms_json = json.dumps(
                    collect_forms(conn, lid, alt_forms),
                    ensure_ascii=False,
                )

                row = [
                    headword,
                    pos,
                    "",
                    glosses_json,
                    forms_json,
                ]
                f.write("\t".join(row) + "\n")
                written += 1

        print(f"Wrote {written:,} entries to {OUT_PATH}")
        print(f"Blank POS entries remaining: {blank_pos:,}")
        print(f"Top POS values: {pos_counter.most_common(10)}")
        return 0
    finally:
        if conn is not None:
            conn.close()
        if db_path is not None and db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
