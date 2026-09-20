#!/usr/bin/env python3
"""In-place cleanup of dict_sqlite/sa.sqlite forms table.

Three deletion passes (no rebuild):

  1) Sandhied duplicates: drop any row whose morph_tags ends in ';sandhied'
     (or equals 'sandhied') when an identical (entry_id, form_text, base_tags)
     row already exists without the sandhied tag.
  2) Empty rows: drop rows where form_text is empty / '_' / only whitespace,
     or morph_tags is empty.
  3) Character-overlap filter: drop any form whose character set shares NO
     character with its headword's character set (NFC-normalized). These are
     DCS annotator errors linking function-word tokens to unrelated lemmas.
"""

import os
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parent.parent
DB_PATH = ROOT / "dict_sqlite" / "sa.sqlite"


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def log(msg):
    print(msg, flush=True)


def backup(db_path: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = db_path.with_suffix(f".sqlite.bak_before_cleanup_{ts}")
    import shutil
    shutil.copy2(db_path, bak)
    log(f"backup -> {bak}")
    return bak


def count(cur, sql, params=()):
    return cur.execute(sql, params).fetchone()[0]


def main():
    if not DB_PATH.exists():
        print(f"missing DB: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    backup(DB_PATH)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA temp_store=MEMORY")
    cur = conn.cursor()

    before = count(cur, "SELECT COUNT(*) FROM forms")
    log(f"forms rows before: {before:,}")

    # --------------------------------------------------------------
    # Step 1: sandhied duplicates
    # --------------------------------------------------------------
    t0 = time.time()
    # Helpful temporary index for the correlated subqueries
    cur.execute(
        "CREATE INDEX IF NOT EXISTS tmp_forms_ef ON forms(entry_id, form_text, morph_tags)"
    )
    conn.commit()

    # 1a) morph_tags == 'sandhied' and a plain ('' tags) row exists
    cur.execute(
        """
        DELETE FROM forms
        WHERE morph_tags = 'sandhied'
          AND EXISTS (
            SELECT 1 FROM forms f2
            WHERE f2.entry_id = forms.entry_id
              AND f2.form_text = forms.form_text
              AND f2.morph_tags = ''
          )
        """
    )
    deleted_1a = cur.rowcount
    conn.commit()

    # 1b) morph_tags ends with ';sandhied' and base-tags counterpart exists
    cur.execute(
        """
        DELETE FROM forms
        WHERE morph_tags LIKE '%;sandhied'
          AND EXISTS (
            SELECT 1 FROM forms f2
            WHERE f2.entry_id = forms.entry_id
              AND f2.form_text = forms.form_text
              AND f2.morph_tags = substr(
                forms.morph_tags, 1, length(forms.morph_tags) - 9
              )
          )
        """
    )
    deleted_1b = cur.rowcount
    conn.commit()

    log(f"step 1 sandhied-dup deletes: {deleted_1a:,} exact + {deleted_1b:,} suffix "
        f"({time.time()-t0:.1f}s)")

    # --------------------------------------------------------------
    # Step 2: empty rows
    # --------------------------------------------------------------
    t0 = time.time()
    cur.execute(
        """
        DELETE FROM forms
        WHERE TRIM(form_text) = ''
           OR form_text = '_'
           OR morph_tags = ''
        """
    )
    deleted_2 = cur.rowcount
    conn.commit()
    log(f"step 2 empty-row deletes: {deleted_2:,} ({time.time()-t0:.1f}s)")

    # --------------------------------------------------------------
    # Step 3: character-overlap filter vs headword
    # --------------------------------------------------------------
    t0 = time.time()
    # Pull headwords into memory (180k rows, tiny)
    headword_chars = {}
    for row_id, hw in cur.execute("SELECT id, headword FROM entries"):
        headword_chars[row_id] = set(nfc(hw))

    # Stream forms; collect ids to delete
    to_delete = []
    CHUNK = 50000
    total_scanned = 0
    for row in cur.execute("SELECT id, entry_id, form_text FROM forms"):
        fid, eid, ft = row
        total_scanned += 1
        hw_set = headword_chars.get(eid)
        if not hw_set:
            # No headword? drop defensively
            to_delete.append(fid)
            continue
        ft_set = set(nfc(ft))
        if not (ft_set & hw_set):
            to_delete.append(fid)

    log(f"step 3 scan: {total_scanned:,} rows, flagged {len(to_delete):,} for deletion "
        f"({time.time()-t0:.1f}s)")

    # Batch delete by rowid
    t0 = time.time()
    del_cur = conn.cursor()
    for i in range(0, len(to_delete), CHUNK):
        chunk = to_delete[i:i + CHUNK]
        placeholders = ",".join("?" * len(chunk))
        del_cur.execute(f"DELETE FROM forms WHERE id IN ({placeholders})", chunk)
    conn.commit()
    log(f"step 3 char-overlap deletes: {len(to_delete):,} ({time.time()-t0:.1f}s)")

    # --------------------------------------------------------------
    # Cleanup: drop tmp index, ANALYZE, VACUUM
    # --------------------------------------------------------------
    cur.execute("DROP INDEX IF EXISTS tmp_forms_ef")
    conn.commit()
    log("ANALYZE...")
    cur.execute("ANALYZE")
    conn.commit()
    log("VACUUM...")
    conn.isolation_level = None
    conn.execute("VACUUM")
    conn.isolation_level = ""

    after = count(cur, "SELECT COUNT(*) FROM forms")
    log(f"forms rows after:  {after:,}  (removed {before - after:,})")

    # Update meta form_count
    cur.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('form_count', ?)",
        (str(after),),
    )
    conn.commit()

    conn.close()
    log("DONE")


if __name__ == "__main__":
    main()
