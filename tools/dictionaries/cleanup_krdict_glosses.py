#!/usr/bin/env python3
"""
Copy-edit the Korean KRDict SQLite glosses in place.

This does not rebuild the database. It rewrites the human-facing gloss strings
inside entries.glosses from the raw "label; definition" style into a cleaner
sentence-cased form:

    bring; take; To go with someone...
    -> Bring; take - to go with someone...

The database schema, ids, forms, and lookup indexes are left untouched.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = APP_ROOT / "dict_sqlite" / "ko-krdict.sqlite"


def _capitalize_first_alpha(text: str) -> str:
    if text and text[0].isalpha() and text[0].islower():
        return text[0].upper() + text[1:]
    return text


def _lowercase_first_alpha(text: str) -> str:
    if not text:
        return text
    m = re.match(r"^([^A-Za-z]*)([A-Z])(.*)$", text)
    if not m:
        return text
    return m.group(1) + m.group(2).lower() + m.group(3)


def clean_gloss_text(text: str) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw or ";" not in raw:
        return raw

    # If the row was already cleaned, leave it alone.
    if " - " in raw.rsplit(";", 1)[-1]:
        return raw

    prefix, definition = raw.rsplit(";", 1)
    prefix = prefix.strip()
    definition = definition.strip()
    if not prefix or not definition:
        return raw

    prefix = _capitalize_first_alpha(prefix)
    definition = _lowercase_first_alpha(definition)
    return f"{prefix} - {definition}"


def clean_glosses_json(glosses_json: str) -> tuple[str, int]:
    data = json.loads(glosses_json or "[]")
    if not isinstance(data, list):
        return glosses_json, 0

    changed = 0
    for sense in data:
        if not isinstance(sense, dict):
            continue
        glosses = sense.get("glosses")
        if not isinstance(glosses, list):
            continue
        new_glosses = []
        for gloss in glosses:
            original = str(gloss or "")
            cleaned = clean_gloss_text(original)
            if cleaned != original:
                changed += 1
            new_glosses.append(cleaned)
        sense["glosses"] = new_glosses

    return json.dumps(data, ensure_ascii=False, separators=(",", ":")), changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy-edit KRDict gloss strings in ko-krdict.sqlite."
    )
    parser.add_argument(
        "db",
        nargs="?",
        default=str(DEFAULT_DB),
        help=f"Path to ko-krdict.sqlite (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create a .bak copy next to the database before modifying it.",
    )
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    if args.backup:
        backup_path = db_path.with_suffix(db_path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(db_path, backup_path)
            print(f"[backup] wrote {backup_path.name}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, glosses FROM entries WHERE glosses IS NOT NULL AND glosses != '[]'"
        ).fetchall()

        updates: list[tuple[str, int]] = []
        row_changes = 0
        gloss_changes = 0

        for row in rows:
            cleaned_json, changed = clean_glosses_json(row["glosses"])
            if changed <= 0:
                continue
            updates.append((cleaned_json, int(row["id"])))
            row_changes += 1
            gloss_changes += changed

        if updates:
            conn.executemany("UPDATE entries SET glosses = ? WHERE id = ?", updates)
            conn.commit()

        print(f"Updated {row_changes:,} rows and {gloss_changes:,} gloss strings in {db_path.name}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
