"""
Fix Japanese Wiktionary SQLite db redirect forms.

Problem: soft-redirect entries (e.g., ず -> [図,徒,頭,出]) were broadcast
to ALL entries under the target kanji, regardless of reading. So ず got
attached to 頭(atama), 頭(kashira), etc. — not just 頭(zu).

Fix: Delete all redirect;alternative forms, then re-insert them correctly
by matching each soft-redirect's kana against the kana reading extracted
from the JSONL head_templates expansion.

Usage:
    python fix_ja_redirects.py [--dry-run]
"""

import json
import os
import re
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSONL_PATH = os.path.join(
    SCRIPT_DIR,
    "wiktionary general pipeline",
    "kaikki.org-dictionary-Japanese.jsonl",
)
SQLITE_PATH = os.path.join(SCRIPT_DIR, "dict_sqlite", "ja.sqlite")

KANJI_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
KANA_RE = re.compile(r"^[\u3040-\u309f\u30a0-\u30ff\u30fc\uff66-\uff9fー]+$")
# Pattern to extract kana from head_templates expansion like 頭(あたま) • (atama)
KANA_FROM_EXP_RE = re.compile(r"[(（]([^\x00-\x7f]+?)[)）]")


def build_kana_map(jsonl_path: str) -> dict:
    """Build (headword, pos, romanization) -> kana_reading from JSONL."""
    kana_map = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            word = entry.get("word", "").strip()
            pos = entry.get("pos", "")
            if pos == "soft-redirect":
                continue

            ht = entry.get("head_templates", [])
            if not ht:
                continue
            exp = ht[0].get("expansion", "")
            m = KANA_FROM_EXP_RE.search(exp)
            if not m:
                continue
            kana = m.group(1)

            # Get romanization
            roman = ""
            for fm in entry.get("forms", []):
                if fm.get("tags") == ["romanization"]:
                    roman = fm.get("form", "")
                    break
            if roman:
                kana_map[(word, pos, roman)] = kana

    return kana_map


def build_redirect_map(jsonl_path: str) -> list:
    """Collect soft-redirect relationships: [(target_kanji, variant_kana), ...]"""
    redirects = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("pos") != "soft-redirect":
                continue
            word = entry.get("word", "").strip()
            redir_targets = entry.get("redirects", [])
            if not isinstance(redir_targets, list):
                continue
            for target in redir_targets:
                target = str(target or "").strip()
                if target and target != word:
                    redirects.append((target, word))

    return redirects


def collect_alt_of_redirects(jsonl_path: str) -> list:
    """Collect alt_of relationships from non-soft-redirect entries."""
    redirects = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("pos") == "soft-redirect":
                continue
            word = entry.get("word", "").strip()
            if not word:
                continue
            senses = entry.get("senses", [])
            for s in senses:
                has_form_of = bool(s.get("form_of") or s.get("alt_of"))
                tags = set(s.get("tags", []))
                has_form_tag = bool(tags & {"form-of", "alt-of"})
                if not has_form_of and not has_form_tag:
                    # This sense is not a form-of/alt-of — entry is not purely alt
                    break
            else:
                # All senses are form-of/alt-of
                for s in senses:
                    for rel_obj in s.get("alt_of", []):
                        parent = str(rel_obj.get("word", "")).strip()
                        if parent and parent != word:
                            redirects.append((parent, word))
    return redirects


def main():
    dry_run = "--dry-run" in sys.argv

    print("Step 1: Building kana map from JSONL...")
    kana_map = build_kana_map(JSONL_PATH)
    print(f"  {len(kana_map):,} entries with kana readings")

    print("Step 2: Collecting redirect relationships...")
    soft_redirects = build_redirect_map(JSONL_PATH)
    alt_redirects = collect_alt_of_redirects(JSONL_PATH)
    all_redirects = soft_redirects + alt_redirects
    print(f"  {len(soft_redirects):,} soft-redirect links")
    print(f"  {len(alt_redirects):,} alt-of redirect links")
    print(f"  {len(all_redirects):,} total")

    print("Step 3: Opening SQLite database...")
    db = sqlite3.connect(SQLITE_PATH)
    db.row_factory = sqlite3.Row

    # Count existing redirect;alternative forms
    old_count = db.execute(
        "SELECT COUNT(*) FROM forms WHERE morph_tags = 'redirect;alternative'"
    ).fetchone()[0]
    print(f"  Existing redirect;alternative forms: {old_count:,}")

    # Load all entries for matching
    entries = db.execute(
        "SELECT id, headword, romanization, pos FROM entries"
    ).fetchall()

    # Build index: headword_lower -> list of (id, headword, pos, romanization)
    entry_index = {}
    for e in entries:
        key = e["headword"].lower()
        entry_index.setdefault(key, []).append(
            (e["id"], e["headword"], e["pos"], e["romanization"])
        )

    # Get the normalization key function from the db (we need form_key)
    # We'll read existing form_keys for known kana to build a cache
    existing_kana_keys = {}
    rows = db.execute(
        "SELECT DISTINCT form_text, form_key FROM forms WHERE form_key != ''"
    ).fetchall()
    for r in rows:
        existing_kana_keys[r["form_text"]] = r["form_key"]
    print(f"  Cached {len(existing_kana_keys):,} form_text -> form_key mappings")

    # Also grab headword_key mappings
    for e in entries:
        existing_kana_keys.setdefault(e["headword"], "")
    hw_keys = {}
    for r in db.execute("SELECT headword, headword_key FROM entries").fetchall():
        hw_keys[r["headword"]] = r["headword_key"]

    print("Step 4: Computing correct redirect forms...")
    new_forms = []  # (entry_id, form_text, form_key, morph_tags, romanization)
    skipped_no_match = 0
    skipped_no_entries = 0
    skipped_no_kana_key = 0

    for parent_word, variant_word in all_redirects:
        target_entries = entry_index.get(parent_word.lower(), [])
        if not target_entries:
            skipped_no_entries += 1
            continue

        # Is the variant a kana word pointing to a kanji target?
        variant_is_kana = bool(KANA_RE.match(variant_word))
        target_has_kanji = bool(KANJI_RE.search(parent_word))

        if variant_is_kana and target_has_kanji:
            # Kana -> kanji: only attach to entries whose kana reading matches
            for entry_id, headword, pos, roman in target_entries:
                kana_reading = kana_map.get((headword, pos, roman))
                if kana_reading and kana_reading == variant_word:
                    form_key = existing_kana_keys.get(variant_word, variant_word)
                    new_forms.append(
                        (entry_id, variant_word, form_key, "redirect;alternative", "")
                    )
                # else: skip — this entry's reading doesn't match the redirect kana
                else:
                    skipped_no_match += 1
        else:
            # Non-kana redirects (kanji->kanji, romaji->kana, etc.): broadcast as before
            for entry_id, headword, pos, roman in target_entries:
                form_key = existing_kana_keys.get(variant_word, variant_word)
                if not form_key:
                    skipped_no_kana_key += 1
                    continue
                new_forms.append(
                    (entry_id, variant_word, form_key, "redirect;alternative", "")
                )

    print(f"  New redirect forms to insert: {len(new_forms):,}")
    print(f"  Skipped (kana didn't match entry reading): {skipped_no_match:,}")
    print(f"  Skipped (no target entries found): {skipped_no_entries:,}")
    print(f"  Skipped (no form_key): {skipped_no_kana_key:,}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        # Show a sample of what would change for 頭
        print("\nSample: redirect forms for 頭 entries:")
        head_entries = entry_index.get("頭", [])
        for eid, hw, pos, roman in head_entries:
            matches = [f for f in new_forms if f[0] == eid]
            if matches:
                for m in matches:
                    print(f"  entry {eid} ({hw}/{roman}/{pos}) <- form: {m[1]}")
            else:
                print(f"  entry {eid} ({hw}/{roman}/{pos}) <- NO redirect form")
        db.close()
        return

    print("Step 5: Deleting old redirect;alternative forms...")
    db.execute("DELETE FROM forms WHERE morph_tags = 'redirect;alternative'")
    deleted = db.execute("SELECT changes()").fetchone()[0]
    print(f"  Deleted {deleted:,} rows")

    print("Step 6: Inserting corrected redirect forms...")
    db.executemany(
        "INSERT INTO forms (entry_id, form_text, form_key, morph_tags, romanization) "
        "VALUES (?, ?, ?, ?, ?)",
        new_forms,
    )
    print(f"  Inserted {len(new_forms):,} rows")

    db.commit()

    # Verify
    final_count = db.execute(
        "SELECT COUNT(*) FROM forms WHERE morph_tags = 'redirect;alternative'"
    ).fetchone()[0]
    print(f"\nFinal redirect;alternative count: {final_count:,} (was {old_count:,})")

    # Spot-check 頭
    print("\nSpot-check: forms linking to 頭 entries via redirect;alternative:")
    rows = db.execute("""
        SELECT e.id, e.headword, e.romanization, e.pos, f.form_text
        FROM forms f JOIN entries e ON e.id = f.entry_id
        WHERE e.headword = '頭' AND f.morph_tags = 'redirect;alternative'
    """).fetchall()
    for r in rows:
        print(f"  entry {r[0]} ({r['headword']}/{r['romanization']}/{r['pos']}) <- {r['form_text']}")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
