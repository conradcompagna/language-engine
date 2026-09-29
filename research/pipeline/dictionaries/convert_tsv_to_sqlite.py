"""
convert_tsv_to_sqlite.py — One-time import of Wiktionary TSV dictionaries into SQLite.

Reads each TSV from the wiktionary pipeline and creates a .sqlite file in dict_sqlite/.
The original TSV files are NEVER modified — this script only reads them.

Usage:
    python convert_tsv_to_sqlite.py              # convert all languages
    python convert_tsv_to_sqlite.py zh ja de      # convert specific languages
"""

import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

csv.field_size_limit(10 * 1024 * 1024)  # 10 MB — some glosses fields are huge

_ASCII_WORD_RE = re.compile(r"[A-Za-z]")
_KRDICT_UNKNOWN_POS = {"", "[]", "unk", "unknown"}

APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
SQLITE_DIR.mkdir(exist_ok=True)

# Import language registry to discover all TSV paths
sys.path.insert(0, str(APP_ROOT))
from language_registry import LANGUAGE_REGISTRY, APP_ROOT as LR_ROOT


def _split_form_tags(raw_tags: str) -> list[str]:
    return [part.strip().lower() for part in str(raw_tags or "").split(";") if part.strip()]


def _is_relation_form_tag(tag: str) -> bool:
    return str(tag or "").strip().lower().endswith("-of")


def _derive_lemma_from_forms(forms_parsed: list[tuple[str, str, str]]) -> str:
    for form_text, morph, _form_roman in forms_parsed:
        if any(_is_relation_form_tag(tag) for tag in _split_form_tags(morph)):
            return str(form_text or "").strip()
    return ""


def _normalize_korean_syllable_glosses(glosses_raw: str, pos: str) -> str:
    if str(pos or "").strip().lower() != "syllable":
        return glosses_raw
    text = str(glosses_raw or "").strip()
    if not text.startswith("["):
        return glosses_raw
    try:
        parsed = json.loads(text)
    except Exception:
        return glosses_raw
    if not isinstance(parsed, list):
        return glosses_raw

    out = []
    changed = False
    for raw_sense in parsed:
        if not isinstance(raw_sense, dict):
            out.append(raw_sense)
            continue
        glosses = raw_sense.get("glosses")
        if not isinstance(glosses, list):
            out.append(raw_sense)
            continue

        kept = []
        saw_placeholder = False
        for raw_gloss in glosses:
            gloss = str(raw_gloss or "").strip()
            if not gloss:
                continue
            if gloss.lower() == "more information":
                saw_placeholder = True
                changed = True
                continue
            kept.append(gloss)

        qualifier = str(raw_sense.get("qualifier") or "").strip()
        if saw_placeholder and qualifier and not kept:
            kept = [qualifier]
            changed = True

        if saw_placeholder:
            new_sense = dict(raw_sense)
            new_sense.pop("qualifier", None)
            if kept:
                new_sense["glosses"] = kept
                out.append(new_sense)
            else:
                changed = True
            continue

        out.append(raw_sense)

    if not changed:
        return glosses_raw
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def _should_skip_korean_krdict_row(lang_code: str, source_label: str, pos: str, glosses_raw: str) -> bool:
    """Drop KRDict placeholder rows that have no useful English gloss text."""
    if str(lang_code or "").strip().lower() != "ko":
        return False
    if str(source_label or "").strip().lower() != "krdict":
        return False
    if str(pos or "").strip().lower() not in _KRDICT_UNKNOWN_POS:
        return False
    if not glosses_raw:
        return True
    try:
        parsed = json.loads(glosses_raw)
    except Exception:
        return True
    if not isinstance(parsed, list):
        return True

    for raw_sense in parsed:
        if not isinstance(raw_sense, dict):
            continue
        glosses = raw_sense.get("glosses")
        if not isinstance(glosses, list):
            continue
        for raw_gloss in glosses:
            gloss = str(raw_gloss or "").strip()
            if gloss and _ASCII_WORD_RE.search(gloss):
                return False
    return True


def _iter_tsv_rows(tsv_path: Path):
    """Yield dicts from a TSV file with a header row. Read-only on the source file."""
    with open(tsv_path, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            yield row


def _detect_format(row: dict) -> str:
    """Detect if a row is compact (new) or legacy format."""
    glosses = (row.get("glosses") or "").strip()
    if "romanization" in row or (glosses and glosses.startswith("[")):
        return "compact"
    return "legacy"


def convert_one(lang_code: str, tsv_path: Path, source_label: str = "default") -> Path:
    """Convert a single TSV to SQLite. Returns the output .sqlite path."""
    suffix = f"-{source_label}" if source_label != "default" else ""
    db_path = SQLITE_DIR / f"{lang_code}{suffix}.sqlite"

    print(f"  [{lang_code}{suffix}] Reading {tsv_path.name} ({tsv_path.stat().st_size / 1e6:.1f} MB)...")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    conn.executescript("""
        DROP TABLE IF EXISTS forms;
        DROP TABLE IF EXISTS entries;

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
    """)

    entry_count = 0
    form_count = 0
    BATCH_SIZE = 5000

    # --- Pass 1: collect all rows ---
    print(f"  [{lang_code}{suffix}] Parsing rows...")
    parsed_rows = []

    for row in _iter_tsv_rows(tsv_path):
        headword = (row.get("headword") or "").strip()
        if not headword:
            continue
        glosses = (row.get("glosses") or "").strip()
        if not glosses:
            continue

        fmt = _detect_format(row)
        if fmt == "compact":
            romanization = (row.get("romanization") or "").strip()
            pos = (row.get("pos") or row.get("pos_raw") or "").strip()
        else:
            romanization = (row.get("reading") or "").strip()
            pos = (row.get("pos_raw") or "").strip()

        if _should_skip_korean_krdict_row(lang_code, source_label, pos, glosses):
            continue

        if lang_code == "ko":
            glosses = _normalize_korean_syllable_glosses(glosses, pos)

        commentary = (row.get("commentary") or "").strip()
        lemma = (row.get("lemma") or "").strip()
        etymology = (row.get("etymology") or "").strip()
        etym_num_raw = (row.get("etymology_number") or "").strip()
        etym_num = int(etym_num_raw) if etym_num_raw.isdigit() else 0
        source = (row.get("source") or row.get("_source") or "").strip()
        entry_id_str = (row.get("entry_id") or "").strip()
        tags = (row.get("tags") or "").strip()
        forms_raw = (row.get("forms") or "").strip()
        forms_out = forms_raw

        # Collect forms for normalization
        forms_parsed = []
        if forms_raw and forms_raw.startswith("["):
            try:
                forms_list = json.loads(forms_raw)
                filtered_forms = []
                for form_item in forms_list:
                    if isinstance(form_item, list) and len(form_item) >= 1:
                        form_text = str(form_item[0]).strip()
                        morph = str(form_item[1]).strip() if len(form_item) > 1 else ""
                        form_roman = str(form_item[2]).strip() if len(form_item) > 2 else ""
                    elif isinstance(form_item, dict):
                        form_text = str(form_item.get("form") or form_item.get("text") or "").strip()
                        morph = str(form_item.get("tags") or "").strip()
                        form_roman = str(form_item.get("romanization") or "").strip()
                    else:
                        continue
                    if form_text:
                        morph_parts = {part.strip().lower() for part in morph.split(";") if part.strip()}
                        # Korean exact-self forms create duplicate surface
                        # matches with no extra lookup value; keep only the
                        # headword row and drop the redundant form rows.
                        if lang_code == "ko" and form_text == headword:
                            continue
                        # A form identical to the headword and tagged as an
                        # alternative only creates a duplicate surface match
                        # that can override the actual headword entry.
                        if form_text == headword and "alternative" in morph_parts:
                            continue
                        forms_parsed.append((form_text, morph, form_roman))
                        filtered_forms.append([form_text, morph, form_roman])
                forms_out = json.dumps(filtered_forms, ensure_ascii=False, separators=(",", ":"))
            except (json.JSONDecodeError, TypeError):
                pass

        if lang_code == "ko" and not lemma:
            inferred_lemma = _derive_lemma_from_forms(forms_parsed)
            if inferred_lemma:
                lemma = inferred_lemma

        parsed_rows.append((headword, romanization, pos, glosses, forms_out,
                             commentary, lemma, etymology, etym_num,
                             source, entry_id_str, tags, fmt, forms_parsed))

    # --- Pass 2: insert rows ---
    batch_entries = []
    batch_forms = []
    next_id = 1

    def flush():
        nonlocal batch_entries, batch_forms, entry_count, form_count
        if batch_entries:
            conn.executemany(
                "INSERT INTO entries (headword, romanization, pos, glosses, forms, commentary, lemma, etymology, etymology_number, source, entry_id, tags, format) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch_entries,
            )
            entry_count += len(batch_entries)
            batch_entries = []
        if batch_forms:
            conn.executemany(
                "INSERT INTO forms (entry_id, form_text, morph_tags, romanization) VALUES (?,?,?,?)",
                batch_forms,
            )
            form_count += len(batch_forms)
            batch_forms = []
        conn.commit()

    for (headword, romanization, pos, glosses, forms_raw,
         commentary, lemma, etymology, etym_num,
         source, entry_id_str, tags, fmt, forms_parsed) in parsed_rows:

        current_id = next_id
        next_id += 1

        batch_entries.append((
            headword, romanization, pos, glosses, forms_raw, commentary, lemma,
            etymology, etym_num, source, entry_id_str, tags, fmt
        ))

        for form_text, morph, form_roman in forms_parsed:
            batch_forms.append((current_id, form_text, morph, form_roman))

        if next_id % BATCH_SIZE == 0:
            flush()

    flush()

    # Create indexes AFTER bulk insert for speed
    print(f"  [{lang_code}{suffix}] Building indexes...")
    conn.execute("CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != ''")
    conn.execute("CREATE INDEX idx_forms_entry_id ON forms(entry_id)")
    conn.commit()

    # Store metadata
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)
    """)
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('lang_code', ?)", (lang_code,))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('source_label', ?)", (source_label,))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('source_tsv', ?)", (str(tsv_path),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('entry_count', ?)", (str(entry_count),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('form_count', ?)", (str(form_count),))
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('created_at', ?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ"),))
    conn.commit()

    conn.execute("PRAGMA optimize")
    conn.close()

    size_mb = db_path.stat().st_size / 1e6
    print(f"  [{lang_code}{suffix}] Done: {entry_count:,} entries, {form_count:,} forms -> {db_path.name} ({size_mb:.1f} MB)")
    return db_path


def main():
    requested = set(a.lower() for a in sys.argv[1:])
    total_start = time.time()
    converted = 0

    for code, info in sorted(LANGUAGE_REGISTRY.items()):
        if requested and code not in requested:
            continue

        # Default dict
        dict_file = info.get("dict_file", "")
        if dict_file and dict_file.endswith(".tsv"):
            tsv_path = LR_ROOT / dict_file
            if tsv_path.exists():
                convert_one(code, tsv_path, "default")
                converted += 1

        # Alternative sources (jmdict, cc-cedict, krdict, etc.)
        for src_name, src_info in info.get("dict_sources", {}).items():
            src_file = src_info.get("dict_file", "")
            if not src_file or not src_file.endswith(".tsv"):
                continue
            src_path = LR_ROOT / src_file
            if not src_path.exists():
                continue
            # Skip if it's the same file as the default
            default_path = LR_ROOT / dict_file if dict_file else None
            if default_path and src_path.resolve() == default_path.resolve():
                continue
            convert_one(code, src_path, src_name)
            converted += 1

    elapsed = time.time() - total_start
    print(f"\nAll done: {converted} database(s) in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
