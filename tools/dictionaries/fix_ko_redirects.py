"""
Fix Korean Wiktionary SQLite db redirect forms.

Problem: redirect;alternative rows were broadcast to every entry under the
same headword. That is wrong for Korean headwords that have multiple Hanja
readings, because a redirect like 長 should only attach to the entry whose
Hanja form is 長.

Fix: delete all redirect;alternative forms, then reinsert them narrowly:
- If the redirect variant is Hanja/CJK, only attach it to entries whose
  existing Hanja form matches the variant.
- If the entry headword itself is Hanja, keep the redirect variant for that
  headword group.
- Non-Hanja redirects are kept broad, matching the existing behavior.

This script also rewrites entries.forms so the payload rendered by the app
stays in sync with the forms table.

Usage:
    python fix_ko_redirects.py [--dry-run]
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from typing import Iterable

from dict_lookup_sqlite import _normalize_key

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SQLITE_PATH = os.path.join(SCRIPT_DIR, "dict_sqlite", "ko.sqlite")


def _is_cjk_ideograph(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2EBEF
    )


def _is_hanjaish(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return all(_is_cjk_ideograph(ch) for ch in value)


def _chunked(items: Iterable[int], size: int = 900) -> Iterable[list[int]]:
    batch: list[int] = []
    for item in items:
        batch.append(int(item))
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _load_entries(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("SELECT id, headword, romanization, pos FROM entries ORDER BY id").fetchall()


def _load_hanja_form_keys(db: sqlite3.Connection) -> dict[int, set[str]]:
    out: dict[int, set[str]] = defaultdict(set)
    rows = db.execute(
        """
        SELECT entry_id, form_text, form_key
        FROM forms
        WHERE morph_tags LIKE '%hanja%'
        """
    ).fetchall()
    for row in rows:
        entry_id = int(row["entry_id"])
        form_key = str(row["form_key"] or "").strip()
        form_text = str(row["form_text"] or "").strip()
        if not form_key and form_text:
            form_key = _normalize_key(form_text, "ko")
        if form_key:
            out[entry_id].add(form_key)
    return out


def _load_redirect_pairs(db: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Return unique (parent_word, variant_word, variant_key) redirect pairs."""
    rows = db.execute(
        """
        SELECT DISTINCT e.headword AS parent_word, f.form_text, f.form_key
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        WHERE f.morph_tags = 'redirect;alternative'
        ORDER BY e.headword, f.form_text, f.form_key
        """
    ).fetchall()

    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for row in rows:
        parent_word = str(row["parent_word"] or "").strip()
        variant_word = str(row["form_text"] or "").strip()
        variant_key = str(row["form_key"] or "").strip()
        if not parent_word or not variant_word:
            continue
        if parent_word == variant_word:
            continue
        if not variant_key:
            variant_key = _normalize_key(variant_word, "ko")
        ident = (parent_word, variant_word, variant_key)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(ident)
    return out


def _parse_forms_json(raw: str) -> list[list[str]]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []

    out: list[list[str]] = []
    for item in parsed:
        if isinstance(item, list) and item:
            form_text = str(item[0] or "").strip()
            tags = str(item[1] or "").strip() if len(item) > 1 else ""
            roman = str(item[2] or "").strip() if len(item) > 2 else ""
        elif isinstance(item, dict):
            form_text = str(item.get("form") or item.get("text") or "").strip()
            tags = str(
                item.get("tags") or item.get("label") or item.get("commentary") or ""
            ).strip()
            roman = str(item.get("romanization") or "").strip()
        else:
            continue
        if form_text:
            out.append([form_text, tags, roman])
    return out


def _build_redirect_insert_rows(
    entries: list[sqlite3.Row],
    hanja_form_keys: dict[int, set[str]],
    redirect_pairs: list[tuple[str, str, str]],
):
    entry_index: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for entry in entries:
        entry_index[str(entry["headword"] or "").strip()].append(entry)

    insert_rows: list[tuple[int, str, str, str, str]] = []
    additions_by_entry: dict[int, list[list[str]]] = defaultdict(list)
    matched_pairs = 0
    skipped_no_entries = 0
    skipped_hanja_mismatch = 0
    broad_rows = 0

    for parent_word, variant_word, variant_key in redirect_pairs:
        candidates = entry_index.get(parent_word, [])
        if not candidates:
            skipped_no_entries += 1
            continue

        variant_is_hanja = _is_hanjaish(variant_word)
        if not variant_is_hanja:
            broad_rows += len(candidates)

        for entry in candidates:
            entry_id = int(entry["id"])
            headword = str(entry["headword"] or "")
            keep = False

            if variant_is_hanja:
                if _is_hanjaish(headword):
                    keep = True
                else:
                    keep = variant_key in hanja_form_keys.get(entry_id, set())
            else:
                keep = True

            if not keep:
                skipped_hanja_mismatch += 1
                continue

            insert_rows.append((entry_id, variant_word, variant_key, "redirect;alternative", ""))
            additions_by_entry[entry_id].append([variant_word, "redirect;alternative", ""])
            matched_pairs += 1

    return (
        insert_rows,
        additions_by_entry,
        {
            "matched_pairs": matched_pairs,
            "skipped_no_entries": skipped_no_entries,
            "skipped_hanja_mismatch": skipped_hanja_mismatch,
            "broad_rows": broad_rows,
        },
    )


def _rewrite_entry_forms(
    db: sqlite3.Connection,
    additions_by_entry: dict[int, list[list[str]]],
    affected_entry_ids: set[int],
) -> int:
    if not affected_entry_ids:
        return 0

    updated = 0
    for chunk in _chunked(sorted(affected_entry_ids)):
        placeholders = ",".join("?" * len(chunk))
        rows = db.execute(
            f"SELECT id, forms FROM entries WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            entry_id = int(row["id"])
            forms = _parse_forms_json(str(row["forms"] or "[]"))
            filtered = [
                item
                for item in forms
                if len(item) >= 2 and str(item[1] or "").strip() != "redirect;alternative"
            ]

            seen = {(f[0], f[1], f[2] if len(f) > 2 else "") for f in filtered}
            for form_text, tags, roman in additions_by_entry.get(entry_id, []):
                ident = (form_text, tags, roman)
                if ident in seen:
                    continue
                filtered.append([form_text, tags, roman])
                seen.add(ident)

            new_json = json.dumps(filtered, ensure_ascii=False)
            if new_json != str(row["forms"] or ""):
                db.execute("UPDATE entries SET forms = ? WHERE id = ?", (new_json, entry_id))
                updated += 1
    return updated


def _sample_entry_report(db: sqlite3.Connection, headword: str) -> None:
    rows = db.execute(
        """
        SELECT e.id, e.headword, e.romanization, e.pos, f.form_text
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        WHERE e.headword = ? AND f.morph_tags = 'redirect;alternative'
        ORDER BY e.id, f.form_text
        """,
        (headword,),
    ).fetchall()
    print(
        f"  Sample headword {json.dumps(headword, ensure_ascii=True)}: {len(rows):,} redirect rows"
    )
    for row in rows[:20]:
        print(
            "    "
            + json.dumps(
                {
                    "id": row["id"],
                    "headword": row["headword"],
                    "romanization": row["romanization"],
                    "pos": row["pos"],
                    "form_text": row["form_text"],
                },
                ensure_ascii=True,
            )
        )


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    db = sqlite3.connect(SQLITE_PATH)
    db.row_factory = sqlite3.Row

    entries = _load_entries(db)
    hanja_form_keys = _load_hanja_form_keys(db)
    redirect_pairs = _load_redirect_pairs(db)

    old_redirect_rows = db.execute(
        "SELECT COUNT(*) FROM forms WHERE morph_tags = 'redirect;alternative'"
    ).fetchone()[0]

    print(f"Entries: {len(entries):,}")
    print(f"Hanja-form entries tracked: {len(hanja_form_keys):,}")
    print(f"Unique redirect pairs: {len(redirect_pairs):,}")
    print(f"Existing redirect rows: {old_redirect_rows:,}")

    insert_rows, additions_by_entry, stats = _build_redirect_insert_rows(
        entries,
        hanja_form_keys,
        redirect_pairs,
    )
    rewrite_entry_ids = {
        int(row["id"])
        for row in db.execute(
            "SELECT id FROM entries WHERE forms LIKE '%redirect;alternative%'"
        ).fetchall()
    }

    print(f"Matched redirect rows to insert: {len(insert_rows):,}")
    print(f"Entries that will be rewritten: {len(rewrite_entry_ids):,}")
    print(f"Skipped (no target entries): {stats['skipped_no_entries']:,}")
    print(f"Skipped (Hanja mismatch): {stats['skipped_hanja_mismatch']:,}")
    print(f"Broad non-Hanja redirect attachments kept: {stats['broad_rows']:,}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        for sample_headword in ["장", "과", "국"]:
            _sample_entry_report(db, sample_headword)
        db.close()
        return

    print("Deleting old redirect;alternative rows...")
    db.execute("DELETE FROM forms WHERE morph_tags = 'redirect;alternative'")
    deleted = db.execute("SELECT changes()").fetchone()[0]
    print(f"  Deleted {deleted:,} rows")

    print("Inserting corrected redirect rows...")
    db.executemany(
        "INSERT INTO forms (entry_id, form_text, form_key, morph_tags, romanization) VALUES (?, ?, ?, ?, ?)",
        insert_rows,
    )
    print(f"  Inserted {len(insert_rows):,} rows")

    print("Rewriting entries.forms JSON payloads...")
    updated_entries = _rewrite_entry_forms(db, additions_by_entry, rewrite_entry_ids)
    print(f"  Updated {updated_entries:,} entries")

    db.commit()

    final_redirect_rows = db.execute(
        "SELECT COUNT(*) FROM forms WHERE morph_tags = 'redirect;alternative'"
    ).fetchone()[0]
    print(f"Final redirect rows: {final_redirect_rows:,}")

    print("\nPost-fix samples:")
    for sample_headword in ["장", "과", "국"]:
        _sample_entry_report(db, sample_headword)

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
