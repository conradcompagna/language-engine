"""
diagnose_ccedict_index.py

Reproduces and diagnoses the suspected desync between the compact key index
and the actual SQLite row IDs for zh-cc-cedict (Simplified Chinese).

Test strategy:
  1. Load the pre-built gzip index from runtime_cache/js_index/zh-cc-cedict.json.gz
  2. Open dict_sqlite/zh-cc-cedict.sqlite directly
  3. For a sample of hw entries: fetch the row from entries by id, check
     that entries.headword_key == the key that points to it
  4. Report mismatches -> these are the "broken matches"
"""

import gzip
import json
import sqlite3
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "runtime_cache" / "js_index" / "zh-cc-cedict.json.gz"
DB_PATH = ROOT / "dict_sqlite" / "zh-cc-cedict.sqlite"


def load_index(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def diagnose():
    print(f"Loading index: {INDEX_PATH}")
    index = load_index(INDEX_PATH)

    hw: dict = index.get("hw", {})
    fw: dict = index.get("fw", {})
    db_aliases: dict = index.get("db_aliases", {})

    print(f"Index metadata:")
    print(f"  version : {index.get('version', '?')}")
    print(f"  lang    : {index.get('lang', '?')}")
    print(f"  db_aliases: {db_aliases}")
    print(f"  hw keys : {len(hw):,}")
    print(f"  fw keys : {len(fw):,}")
    print()

    print(f"Opening DB: {DB_PATH}")
    conn = open_db(DB_PATH)

    # ------------------------------------------------------------------ #
    # 1. Verify that the db alias in the index actually maps to zh-cc-cedict
    # ------------------------------------------------------------------ #
    cedict_alias = None
    for alias, label in db_aliases.items():
        if "cc-cedict" in label.lower() and "hant" not in label.lower():
            cedict_alias = alias
            break

    if cedict_alias is None:
        print("ERROR: Could not find a zh-cc-cedict alias in db_aliases!")
        print("  db_aliases =", db_aliases)
        return

    print(f"Using alias '{cedict_alias}' -> '{db_aliases[cedict_alias]}' for zh-cc-cedict")
    print()

    # ------------------------------------------------------------------ #
    # 2. Get the actual row count from the DB
    # ------------------------------------------------------------------ #
    (total_entries,) = conn.execute("SELECT COUNT(*) FROM entries").fetchone()
    (max_id,) = conn.execute("SELECT MAX(id) FROM entries").fetchone()
    (min_id,) = conn.execute("SELECT MIN(id) FROM entries").fetchone()
    print(f"DB entries table: count={total_entries:,}, id range=[{min_id}, {max_id}]")
    print()

    # ------------------------------------------------------------------ #
    # 3. Check hw: does each row_id in the index map to the right key?
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("HEADWORD (hw) KEY vs ROW CHECK")
    print("=" * 60)

    mismatch_count = 0
    missing_count = 0
    match_count = 0
    total_checked = 0
    id_out_of_range = 0

    # Collect all (key, row_id) pairs that belong to the cedict alias
    all_hw_pairs = []
    for key, refs in hw.items():
        for ref in refs:
            alias = ref[0]
            row_id = ref[1]
            if alias == cedict_alias:
                all_hw_pairs.append((key, row_id))

    print(f"Total hw refs for alias '{cedict_alias}': {len(all_hw_pairs):,}")

    # Check ALL pairs exhaustively
    sample_pairs = all_hw_pairs

    print(f"Checking ALL {len(sample_pairs):,} hw pairs (exhaustive)...")
    print()

    mismatches = []
    for key, row_id in sample_pairs:
        total_checked += 1
        if row_id < min_id or row_id > max_id:
            id_out_of_range += 1
            mismatches.append((key, row_id, None, "OUT_OF_RANGE"))
            continue
        row = conn.execute(
            "SELECT id, headword, headword_key FROM entries WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None:
            missing_count += 1
            mismatches.append((key, row_id, None, "MISSING_ROW"))
        elif row["headword_key"] == key:
            match_count += 1
        else:
            mismatch_count += 1
            mismatches.append((key, row_id, dict(row), "MISMATCH"))

    print(f"Results ({total_checked} checked):")
    print(f"  MATCH       : {match_count}")
    print(f"  MISMATCH    : {mismatch_count}")
    print(f"  MISSING ROW : {missing_count}")
    print(f"  OUT OF RANGE: {id_out_of_range}")
    print()

    if mismatches:
        print("First 20 mismatches:")
        for idx, item in enumerate(mismatches[:20]):
            index_key, row_id, row, reason = item
            if row:
                actual_key = row.get("headword_key", "?")
                actual_hw = row.get("headword", "?")
                print(f"  [{idx + 1}] reason={reason}")
                print(f"       index_key='{index_key}'  row_id={row_id}")
                print(f"       actual headword='{actual_hw}'  actual_key='{actual_key}'")
            else:
                print(f"  [{idx + 1}] reason={reason}  index_key='{index_key}'  row_id={row_id}")
        print()

    # ------------------------------------------------------------------ #
    # 4. Spot-check specific Chinese words
    # ------------------------------------------------------------------ #
    print("=" * 60)
    print("SPOT CHECK: lookup specific words in both index and DB")
    print("=" * 60)

    test_words = ["你好", "中国", "学习", "电脑", "语言", "词典", "安装", "汉字", "普通话", "北京"]
    for word in test_words:
        index_refs = hw.get(word, [])
        db_row = conn.execute(
            "SELECT id, headword, headword_key FROM entries WHERE headword_key = ? LIMIT 3",
            (word,),
        ).fetchall()

        if index_refs:
            for ref in index_refs:
                alias, rid = ref[0], ref[1]
                if alias != cedict_alias:
                    continue
                actual_row = conn.execute(
                    "SELECT id, headword, headword_key FROM entries WHERE id = ?", (rid,)
                ).fetchone()
                if actual_row:
                    match = actual_row["headword_key"] == word
                    status = "OK" if match else "MISMATCH"
                    print(
                        f"  '{word}': index->id={rid}, actual_key='{actual_row['headword_key']}', actual_hw='{actual_row['headword']}' [{status}]"
                    )
                else:
                    print(f"  '{word}': index->id={rid} -> NO ROW IN DB [MISSING]")
        else:
            print(f"  '{word}': NOT IN INDEX")
            if db_row:
                print(f"    (DB has it: id={db_row[0]['id']}, hw='{db_row[0]['headword']}')")

    # ------------------------------------------------------------------ #
    # 5. Offset analysis: is the desync a constant shift?
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("OFFSET ANALYSIS: is the desync a constant shift?")
    print("=" * 60)

    offsets = []
    for item in mismatches[:100]:
        if item[3] != "MISMATCH":
            continue
        index_key, row_id, row, _ = item
        real_rows = conn.execute(
            "SELECT id FROM entries WHERE headword_key = ? LIMIT 1", (index_key,)
        ).fetchall()
        if real_rows:
            real_id = real_rows[0]["id"]
            offsets.append(real_id - row_id)

    if offsets:
        from collections import Counter

        c = Counter(offsets)
        print(f"Offset distribution (real_id - index_id), top 10:")
        for offset, cnt in c.most_common(10):
            print(f"  offset={offset:+d}  count={cnt}")

        if len(c) == 1:
            print(f"\nCONCLUSION: Systematic constant offset of {offsets[0]:+d}")
        elif max(c.values()) / len(offsets) > 0.8:
            dominant = c.most_common(1)[0][0]
            print(
                f"\nCONCLUSION: Mostly systematic offset of {dominant:+d} ({c[dominant]}/{len(offsets)} cases)"
            )
        else:
            print("\nCONCLUSION: No single constant offset - more complex desync")
    else:
        print("No MISMATCH rows available for offset analysis.")

    # ------------------------------------------------------------------ #
    # 6. Cross-DB check: do the index row IDs match zh.sqlite instead?
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("CROSS-DB CHECK: do index row IDs match zh.sqlite (Wiktionary)?")
    print("=" * 60)

    other_db = ROOT / "dict_sqlite" / "zh.sqlite"
    if other_db.exists():
        conn2 = open_db(other_db)
        (other_count,) = conn2.execute("SELECT COUNT(*) FROM entries").fetchone()
        (other_max,) = conn2.execute("SELECT MAX(id) FROM entries").fetchone()
        print(f"zh.sqlite has {other_count:,} entries, max id={other_max}")

        cross_match = 0
        cross_checked = 0
        for item in mismatches[:50]:
            if item[3] != "MISMATCH":
                continue
            index_key, row_id, row, _ = item
            other_row = conn2.execute(
                "SELECT id, headword, headword_key FROM entries WHERE id = ?", (row_id,)
            ).fetchone()
            cross_checked += 1
            if other_row and other_row["headword_key"] == index_key:
                cross_match += 1

        if cross_checked > 0:
            pct = 100 * cross_match / cross_checked
            print(f"Cross-match with zh.sqlite: {cross_match}/{cross_checked} ({pct:.0f}%)")
            if pct > 70:
                print("\nCONCLUSION: Index row IDs point into zh.sqlite, NOT zh-cc-cedict.sqlite!")
                print("  The index was built against the wrong database.")
        else:
            print("No mismatches to cross-check.")
        conn2.close()
    else:
        print("zh.sqlite not found, skipping cross-DB check.")

    # ------------------------------------------------------------------ #
    # 7. Inspect _resolve_all_db_paths ordering: which db gets alias db0?
    # ------------------------------------------------------------------ #
    print()
    print("=" * 60)
    print("ALIAS ORDER CHECK: what order does _resolve_all_db_paths return?")
    print("=" * 60)

    sqlite_dir = ROOT / "dict_sqlite"
    # Replicate _resolve_all_db_paths("zh") logic
    zh_paths = []
    p = sqlite_dir / "zh.sqlite"
    if p.exists():
        zh_paths.append(p)
    for f in sorted(sqlite_dir.glob("zh-*.sqlite")):
        if f not in zh_paths:
            zh_paths.append(f)

    print("Paths returned by _resolve_all_db_paths('zh') order:")
    for i, p in enumerate(zh_paths):
        alias = f"db{i}"
        print(f"  {alias} -> {p.name}")

    print()
    print("Index db_aliases (from the stored index file):")
    for alias, label in sorted(db_aliases.items()):
        print(f"  {alias} -> {label}")

    print()
    print("If these disagree, the index was built under a different path ordering.")

    conn.close()
    print()
    print("Done.")


if __name__ == "__main__":
    diagnose()
