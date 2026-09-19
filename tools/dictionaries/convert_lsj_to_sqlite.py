#!/usr/bin/env python3
"""
Convert LSJ (Liddell-Scott-Jones) Greek-English Lexicon from Perseus TEI XML
into the SQLite dictionary format used by the Language Engine app.

Source: lexica-master.zip containing grc.lsj.perseus-eng*.xml files.
Output: dict_sqlite/grc-lsj.sqlite

Usage:
    python convert_lsj_to_sqlite.py
"""

import json
import os
import re
import sqlite3
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import betacode.conv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
ZIP_PATH = BASE_DIR / "wiktionary general pipeline" / "rawjsonforconversion" / "lexica-master.zip"
OUTPUT_DB = BASE_DIR / "dict_sqlite" / "grc-lsj.sqlite"
LSJ_DIR_IN_ZIP = "lexica-master/CTS_XML_TEI/perseus/pdllex/grc/lsj/"

# ---------------------------------------------------------------------------
# Betacode helpers
# ---------------------------------------------------------------------------


def clean_betacode(text: str) -> str:
    """Strip LSJ-specific annotations from betacode before conversion."""
    text = text.replace("^", "").replace("_", "")  # quantity marks
    text = text.replace("-", "")  # morpheme boundaries
    text = text.rstrip(":\u00b7")
    text = re.sub(r"\d+$", "", text)  # trailing homograph numbers
    return text


def beta_to_unicode(text: str) -> str:
    """Convert Perseus betacode to Unicode Greek."""
    if not text:
        return ""
    text = clean_betacode(text)
    if not text:
        return ""
    try:
        result = betacode.conv.beta_to_uni(text)
    except Exception:
        return text
    # Fix digamma: betacode library doesn't handle 'v' (digamma)
    result = result.replace("v", "\u03dd").replace("V", "\u03dc")
    return result


def normalize_greek(text: str) -> str:
    """NFC + collapse whitespace."""
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


_BETA_TO_ROMAN = {
    "a": "a",
    "b": "b",
    "g": "g",
    "d": "d",
    "e": "e",
    "z": "z",
    "h": "e",
    "q": "th",
    "i": "i",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "c": "x",
    "o": "o",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "f": "ph",
    "x": "kh",
    "y": "ps",
    "w": "o",
    "v": "w",
}


def betacode_to_romanization(beta: str) -> str:
    """Rough Latin-alphabet romanization from betacode."""
    if not beta:
        return ""
    beta_clean = clean_betacode(beta).lower()
    beta_clean = re.sub(r"[/\\=\(\)\+\|]", "", beta_clean)
    result = []
    capitalize_next = False
    for ch in beta_clean:
        if ch == "*":
            capitalize_next = True
            continue
        roman = _BETA_TO_ROMAN.get(ch, ch)
        if capitalize_next:
            roman = roman.capitalize()
            capitalize_next = False
        result.append(roman)
    return re.sub(r"\s+", " ", "".join(result)).strip()


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def get_all_text(elem) -> str:
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(get_all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def get_direct_text(elem) -> str:
    return (elem.text or "").strip()


# ---------------------------------------------------------------------------
# Glosses — only from <tr> elements
# ---------------------------------------------------------------------------


def build_glosses(entry_elem) -> list[dict]:
    """
    Build glosses strictly from <tr> elements.
    Each sense's own <tr> elements (not from nested sub-senses) are grouped.
    """
    senses = entry_elem.findall(".//sense")
    glosses = []

    if senses:
        # Collect all <tr> belonging to nested senses so we can exclude them
        nested_tr_ids: set[int] = set()
        for sense in senses:
            for child_sense in sense.findall(".//sense"):
                for t in child_sense.findall(".//tr"):
                    nested_tr_ids.add(id(t))

        for sense in senses:
            sense_n = sense.get("n", "")
            own_trs = []
            for tr in sense.findall(".//tr"):
                if id(tr) in nested_tr_ids:
                    continue
                text = get_all_text(tr).strip().strip(",;:. ")
                if text:
                    own_trs.append(text)
            if own_trs:
                entry = {"glosses": own_trs}
                if sense_n:
                    entry["tags"] = [sense_n]
                glosses.append(entry)
    else:
        # No <sense> — grab <tr> at top level
        trs = []
        for tr in entry_elem.findall(".//tr"):
            text = get_all_text(tr).strip().strip(",;:. ")
            if text:
                trs.append(text)
        if trs:
            glosses.append({"glosses": trs})

    return glosses


# ---------------------------------------------------------------------------
# POS
# ---------------------------------------------------------------------------

_POS_PATTERNS = {
    "noun": re.compile(r"\b(Subst|noun)\b", re.I),
    "verb": re.compile(r"\b(Verb|vb)\b", re.I),
    "adj": re.compile(r"\b(Adj|adjective)\b", re.I),
    "adv": re.compile(r"\b(Adv|adverb)\b", re.I),
    "prep": re.compile(r"\b(Prep|preposition)\b", re.I),
    "conj": re.compile(r"\b(Conj|conjunction)\b", re.I),
    "pron": re.compile(r"\b(Pron|pronoun)\b", re.I),
    "particle": re.compile(r"\b(Particle|part)\b", re.I),
    "interjection": re.compile(r"\b(Interj|exclamation)\b", re.I),
}


def extract_pos(entry_elem, key: str) -> str:
    for gram in entry_elem.findall(".//gramGrp/gram"):
        if gram.get("type") == "pos":
            text = get_direct_text(gram).strip()
            if text:
                return text.lower()

    # <itype> with non-greek text
    for it in entry_elem.findall("itype"):
        if it.get("lang", "") != "greek":
            text = get_direct_text(it).strip().lower()
            if "indecl" in text:
                return "indeclinable"

    # <gen> implies noun
    if entry_elem.findall("gen"):
        gen_text = get_direct_text(entry_elem.findall("gen")[0]).strip()
        if gen_text:
            return "noun"

    if key.lower().endswith("-"):
        return "prefix"

    full_text = get_all_text(entry_elem)
    for pos, pattern in _POS_PATTERNS.items():
        if pattern.search(full_text[:500]):
            return pos

    return ""


# ---------------------------------------------------------------------------
# Gender
# ---------------------------------------------------------------------------

_GENDER_MAP = {
    "o(": "masculine",
    "h(": "feminine",
    "to/": "neuter",
}


def extract_gender(entry_elem) -> str:
    genders = []
    for g in entry_elem.findall("gen"):
        text = get_direct_text(g).strip().rstrip(",")
        if text in _GENDER_MAP:
            genders.append(_GENDER_MAP[text])
    seen = set()
    return "; ".join(g for g in genders if not (g in seen or seen.add(g)))


# ---------------------------------------------------------------------------
# Forms — orth variants + preamble <foreign> inflected forms
# ---------------------------------------------------------------------------

# Case/number labels that precede inflected forms in preamble text
_CASE_LABEL_RE = re.compile(
    r"\b(acc|gen|dat|nom|voc|dual|pl|sg|"
    r"acc\.|gen\.|dat\.|nom\.|voc\.|"
    r"nom\. pl|acc\. pl|gen\. pl|dat\. pl|"
    r"nom\. sg|acc\. sg|gen\. sg|dat\. sg|"
    r"also|contr)\b\.?\s*$",
    re.I,
)


def _is_full_greek_word(beta: str) -> bool:
    """Check if betacode represents a full word (not a fragment/ending)."""
    beta = beta.strip().rstrip(",;:")
    if not beta:
        return False
    # Check for fragment markers BEFORE cleaning
    if beta.startswith("-") or beta.endswith("-"):
        return False
    # Must contain at least one vowel-like letter
    if not re.search(r"[aeiouhw]", beta, re.I):
        return False
    # Must be at least 2 chars of actual Greek (ignoring diacritics and markers)
    letters = re.sub(r"[/\\=\(\)\+\|\^\*_\d\-]", "", beta)
    return len(letters) >= 2


def extract_forms(entry_elem, primary_orth_beta: str) -> list[list[str]]:
    """
    Extract forms that are legitimate lookup targets for segmentation:
    1. <orth> variant spellings (with dialect tags)
    2. <foreign> inflected forms from preamble (before first <sense>),
       only when preceded by case/number labels and representing full words.

    Excludes: <itype> (partial endings), fragments starting with '-',
    single-character forms.
    """
    forms = []
    primary_clean = clean_betacode(primary_orth_beta).strip().rstrip(",").lower()
    seen_forms: set[str] = set()  # deduplicate by unicode text

    def _add_form(beta_text: str, tags: str):
        beta_text = beta_text.strip().rstrip(",;")
        if not beta_text:
            return
        if not _is_full_greek_word(beta_text):
            return
        uni = normalize_greek(beta_to_unicode(beta_text))
        if not uni or len(uni) < 2:
            return
        # Skip if same as headword
        if clean_betacode(beta_text).lower() == primary_clean:
            return
        # Deduplicate by (unicode, tags)
        dedup_key = f"{uni}|{tags}"
        if dedup_key in seen_forms:
            return
        seen_forms.add(dedup_key)
        roman = betacode_to_romanization(beta_text)
        forms.append([uni, tags, roman])

    # Known dialect abbreviations found in LSJ text/tails
    _DIALECT_NAMES = {
        "Aeol",
        "Att",
        "Boeot",
        "Cret",
        "Cypr",
        "Dor",
        "Ep",
        "Ion",
        "Lacon",
        "Lesb",
        "Pamph",
        "Thess",
        "Arcad",
    }

    def _extract_dialect_from_text(text: str) -> str:
        """Find dialect label like 'Cret.' or 'Dor.' in trailing text."""
        m = re.search(r"\b(" + "|".join(_DIALECT_NAMES) + r")\.?\s*$", text.strip())
        if m:
            return m.group(1)
        return ""

    # Walk direct children of entry, stop at first <sense>
    current_dialect = ""
    preceding_text = ""

    if entry_elem.text:
        preceding_text = entry_elem.text

    for child in entry_elem:
        tag = child.tag

        if tag == "sense":
            break

        if tag == "gramGrp":
            for gram in child.findall("gram"):
                gtype = gram.get("type", "")
                if gtype == "dialect":
                    dt = get_direct_text(gram).strip().rstrip(".")
                    if dt:
                        current_dialect = dt

        elif tag == "orth":
            extent = child.get("extent", "full")
            # Skip prefix/suffix orth elements — they're stems, not full words
            if extent in ("pref", "suff"):
                if child.tail:
                    preceding_text = child.tail
                continue
            beta_text = get_direct_text(child).strip().rstrip(",")
            if beta_text and clean_betacode(beta_text).lower() != primary_clean:
                if not current_dialect:
                    current_dialect = _extract_dialect_from_text(preceding_text)
                form_tags = "variant=orth"
                if current_dialect:
                    form_tags += f"; dialect={current_dialect}"
                _add_form(beta_text, form_tags)
            current_dialect = ""

        elif tag == "foreign":
            lang = child.get("lang", "")
            if lang == "greek":
                beta_text = get_direct_text(child).strip().rstrip(",")
                if beta_text and _is_full_greek_word(beta_text):
                    context = preceding_text.strip()
                    if _CASE_LABEL_RE.search(context):
                        m = _CASE_LABEL_RE.search(context)
                        case_label = m.group(0).strip().rstrip(".")
                        form_tags = f"inflection={case_label}"
                        if current_dialect:
                            form_tags += f"; dialect={current_dialect}"
                        _add_form(beta_text, form_tags)
                        current_dialect = ""

        elif tag == "bibl":
            # Check <bibl><author> for dialect labels like "Cypr."
            author = child.find("author")
            if author is not None:
                auth_text = get_direct_text(author).strip().rstrip(".")
                if auth_text in _DIALECT_NAMES:
                    current_dialect = auth_text

        # Accumulate text for context tracking
        if child.tail:
            preceding_text = child.tail
            # Also check tail for dialect labels
            dt = _extract_dialect_from_text(child.tail)
            if dt:
                current_dialect = dt
        else:
            preceding_text = ""

    return forms


# ---------------------------------------------------------------------------
# Entry processing
# ---------------------------------------------------------------------------


def process_entry(entry_elem) -> dict | None:
    entry_id = entry_elem.get("id", "")
    key_beta = entry_elem.get("key", "")
    entry_type = entry_elem.get("type", "")

    if entry_type == "xref":
        if not entry_elem.findall(".//sense") and not entry_elem.findall(".//tr"):
            return None

    orths = entry_elem.findall("orth")
    primary_beta = get_direct_text(orths[0]).strip().rstrip(",") if orths else key_beta
    if not primary_beta:
        return None

    headword = normalize_greek(beta_to_unicode(primary_beta))
    if not headword:
        return None

    romanization = betacode_to_romanization(primary_beta)
    pos = extract_pos(entry_elem, key_beta)
    gender = extract_gender(entry_elem)
    glosses = build_glosses(entry_elem)
    forms_list = extract_forms(entry_elem, primary_beta)

    return {
        "headword": headword,
        "romanization": romanization,
        "pos": pos,
        "glosses": json.dumps(glosses, ensure_ascii=False),
        "forms": json.dumps(forms_list, ensure_ascii=False),
        "commentary": "",
        "lemma": "",
        "etymology": "",
        "etymology_number": 0,
        "source": "lsj",
        "entry_id": entry_id,
        "tags": gender,
        "format": "compact",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("LSJ XML -> SQLite converter")
    print(f"Source: {ZIP_PATH}")
    print(f"Output: {OUTPUT_DB}")

    if not ZIP_PATH.exists():
        print(f"ERROR: Source zip not found: {ZIP_PATH}")
        sys.exit(1)

    if OUTPUT_DB.exists():
        bak = OUTPUT_DB.with_suffix(".sqlite.bak")
        print(f"Backing up existing DB to {bak.name}")
        import shutil

        shutil.copy2(OUTPUT_DB, bak)

    z = zipfile.ZipFile(ZIP_PATH)
    xml_files = sorted(
        [n for n in z.namelist() if n.startswith(LSJ_DIR_IN_ZIP) and n.endswith(".xml")]
    )
    print(f"Found {len(xml_files)} XML files")

    if OUTPUT_DB.exists():
        os.remove(OUTPUT_DB)

    conn = sqlite3.connect(str(OUTPUT_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        CREATE TABLE entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            headword    TEXT NOT NULL,
            romanization TEXT NOT NULL DEFAULT '',
            pos         TEXT NOT NULL DEFAULT '',
            glosses     TEXT NOT NULL DEFAULT '[]',
            forms       TEXT NOT NULL DEFAULT '[]',
            commentary  TEXT NOT NULL DEFAULT '',
            lemma       TEXT NOT NULL DEFAULT '',
            etymology   TEXT NOT NULL DEFAULT '',
            etymology_number INTEGER NOT NULL DEFAULT 0,
            source      TEXT NOT NULL DEFAULT '',
            entry_id    TEXT NOT NULL DEFAULT '',
            tags        TEXT NOT NULL DEFAULT '',
            format      TEXT NOT NULL DEFAULT 'compact'
        );

        CREATE TABLE forms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id    INTEGER NOT NULL REFERENCES entries(id),
            form_text   TEXT NOT NULL,
            morph_tags  TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    total_entries = 0
    total_forms = 0
    skipped = 0

    for xml_file in xml_files:
        fname = xml_file.split("/")[-1]
        print(f"  Processing {fname}...", end=" ", flush=True)

        content = z.read(xml_file).decode("utf-8")
        tree = ET.fromstring(content)
        entry_elems = tree.findall(".//entryFree")

        file_entries = 0
        file_forms = 0

        for elem in entry_elems:
            entry_data = process_entry(elem)
            if entry_data is None:
                skipped += 1
                continue

            cur = conn.execute(
                """INSERT INTO entries
                   (headword, romanization, pos, glosses, forms, commentary,
                    lemma, etymology, etymology_number, source, entry_id, tags, format)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry_data["headword"],
                    entry_data["romanization"],
                    entry_data["pos"],
                    entry_data["glosses"],
                    entry_data["forms"],
                    entry_data["commentary"],
                    entry_data["lemma"],
                    entry_data["etymology"],
                    entry_data["etymology_number"],
                    entry_data["source"],
                    entry_data["entry_id"],
                    entry_data["tags"],
                    entry_data["format"],
                ),
            )
            row_id = cur.lastrowid
            file_entries += 1

            # Insert forms into forms table — only legitimate lookup forms
            forms_list = json.loads(entry_data["forms"])
            for form_item in forms_list:
                form_text = form_item[0]
                morph_tags = form_item[1] if len(form_item) > 1 else ""
                form_roman = form_item[2] if len(form_item) > 2 else ""
                if form_text:
                    conn.execute(
                        "INSERT INTO forms (entry_id, form_text, morph_tags, romanization) VALUES (?,?,?,?)",
                        (row_id, form_text, morph_tags, form_roman),
                    )
                    file_forms += 1

        total_entries += file_entries
        total_forms += file_forms
        print(f"{file_entries} entries, {file_forms} forms")

    print("Creating indices...")
    conn.execute("CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != ''")
    conn.execute("CREATE INDEX idx_forms_entry_id ON forms(entry_id)")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "lang_code": "grc",
        "source_label": "lsj",
        "entry_count": str(total_entries),
        "form_count": str(total_forms),
        "created_at": now,
        "source_db": str(OUTPUT_DB),
    }
    for k, v in meta.items():
        conn.execute("INSERT INTO meta (key, value) VALUES (?,?)", (k, v))

    conn.execute("ANALYZE")
    conn.commit()
    conn.close()

    print(f"\nDone!")
    print(f"  Entries: {total_entries}")
    print(f"  Forms:   {total_forms}")
    print(f"  Skipped: {skipped}")
    print(f"  Output:  {OUTPUT_DB}")


if __name__ == "__main__":
    main()
