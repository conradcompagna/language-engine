"""
Fill empty romanization on kana form rows in ja.sqlite using Hepburn romaji.

Port of static/romaji.js toRomaji() to Python. Only processes forms whose
form_text is pure kana (hiragana/katakana) and romanization is empty.

Usage:
    python fill_ja_form_romanization.py [--dry-run]
"""

import os
import re
import sqlite3
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(SCRIPT_DIR, "dict_sqlite", "ja.sqlite")

# ---- Romaji engine (port of romaji.js) ----

KATA_HIRA_OFFSET = 0x60

def _kata_to_hira(s):
    out = []
    for ch in s:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            out.append(chr(cp - KATA_HIRA_OFFSET))
        else:
            out.append(ch)
    return "".join(out)

DIGRAPHS = {
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo',
    'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'じゃ': 'ja',  'じゅ': 'ju',  'じょ': 'jo',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho',
    'ぢゃ': 'dya', 'ぢゅ': 'dyu', 'ぢょ': 'dyo',
    'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo',
    'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo',
    'てぃ': 'ti',  'でぃ': 'di',
    'ふぁ': 'fa',  'ふぃ': 'fi',  'ふぇ': 'fe', 'ふぉ': 'fo',
    'うぃ': 'wi',  'うぇ': 'we',  'うぉ': 'wo',
    'ゔぁ': 'va',  'ゔぃ': 'vi',  'ゔぇ': 've', 'ゔぉ': 'vo',
    'つぁ': 'tsa', 'つぃ': 'tsi', 'つぇ': 'tse', 'つぉ': 'tso',
    'ちぇ': 'che', 'しぇ': 'she', 'じぇ': 'je',
    'でゅ': 'dyu',
    'とぅ': 'tu',  'どぅ': 'du',
}

SINGLE = {
    'あ': 'a',  'い': 'i',  'う': 'u',  'え': 'e',  'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'ざ': 'za', 'じ': 'ji',  'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'だ': 'da', 'ぢ': 'di',  'づ': 'du',  'で': 'de', 'ど': 'do',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo',
    'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'ゐ': 'wi', 'ゑ': 'we', 'を': 'wo', 'ん': 'n',
    'ゔ': 'vu',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o',
    'ゃ': 'ya', 'ゅ': 'yu', 'ょ': 'yo',
    'ゎ': 'wa',
}

VOWELS = {'a', 'i', 'u', 'e', 'o'}

def _last_vowel(romaji):
    if not romaji:
        return 'a'
    for ch in reversed(romaji):
        if ch in VOWELS:
            return ch
    return 'a'

def _peek_next_roman(hira, i):
    if i >= len(hira):
        return ''
    if i + 1 < len(hira):
        pair = hira[i] + hira[i + 1]
        if pair in DIGRAPHS:
            return DIGRAPHS[pair]
    return SINGLE.get(hira[i], '')


def to_romaji(inp):
    if not inp:
        return ''
    hira = _kata_to_hira(inp)
    out = []
    last_roman = ''
    i = 0
    while i < len(hira):
        ch = hira[i]
        cp = ord(ch)

        # Small tsu
        if ch == 'っ':
            nxt = _peek_next_roman(hira, i + 1)
            if nxt and nxt[0] not in VOWELS and nxt[0] != 'n':
                out.append(nxt[0])
                last_roman = nxt[0]
            else:
                out.append('tsu')
                last_roman = 'tsu'
            i += 1
            continue

        # Prolonged sound mark
        if ch == 'ー' or cp == 0x30FC:
            vowel = _last_vowel(last_roman or ''.join(out))
            out.append(vowel)
            i += 1
            continue

        # Digraph
        if i + 1 < len(hira):
            pair = hira[i] + hira[i + 1]
            if pair in DIGRAPHS:
                roman = DIGRAPHS[pair]
                out.append(roman)
                last_roman = roman
                i += 2
                continue

        # Single kana
        if ch in SINGLE:
            roman = SINGLE[ch]
            # ん before vowel/y: use n'
            if ch == 'ん' and i + 1 < len(hira):
                nxt_ch = hira[i + 1]
                if nxt_ch in SINGLE:
                    nxt_r = SINGLE[nxt_ch]
                    if nxt_r and nxt_r[0] in VOWELS | {'y'}:
                        out.append("n'")
                        last_roman = 'n'
                        i += 1
                        continue
            out.append(roman)
            last_roman = roman
            i += 1
            continue

        # Non-kana pass through
        out.append(inp[i])  # use original char
        last_roman = ''
        i += 1

    return ''.join(out)


# ---- Kana detection ----

KANA_RE = re.compile(r'^[\u3040-\u309f\u30a0-\u30ff\u30fcー]+$')

def is_pure_kana(s):
    return bool(KANA_RE.match(s))


def main():
    dry_run = "--dry-run" in sys.argv

    print("Opening ja.sqlite...")
    db = sqlite3.connect(SQLITE_PATH)
    db.row_factory = sqlite3.Row

    # Find all forms with empty romanization where form_text is pure kana
    rows = db.execute(
        "SELECT id, form_text FROM forms WHERE (romanization = '' OR romanization IS NULL)"
    ).fetchall()

    print(f"Total forms with empty romanization: {len(rows):,}")

    updates = []
    skipped_not_kana = 0
    for r in rows:
        ft = r["form_text"]
        if not is_pure_kana(ft):
            skipped_not_kana += 1
            continue
        roman = to_romaji(ft)
        if roman:
            updates.append((roman, r["id"]))

    print(f"Kana forms to romanize: {len(updates):,}")
    print(f"Skipped (not pure kana): {skipped_not_kana:,}")

    # Samples
    print("\nSamples:")
    for roman, fid in updates[:20]:
        ft = db.execute("SELECT form_text FROM forms WHERE id = ?", (fid,)).fetchone()["form_text"]
        print(f"  {ft} -> {roman}")

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        db.close()
        return

    print(f"\nUpdating {len(updates):,} rows...")
    db.executemany(
        "UPDATE forms SET romanization = ? WHERE id = ?",
        updates,
    )
    db.commit()

    # Verify
    remaining = db.execute(
        "SELECT COUNT(*) FROM forms WHERE (romanization = '' OR romanization IS NULL)"
    ).fetchone()[0]
    filled = db.execute(
        "SELECT COUNT(*) FROM forms WHERE romanization != '' AND romanization IS NOT NULL"
    ).fetchone()[0]
    print(f"Remaining empty: {remaining:,}")
    print(f"Total with romanization: {filled:,}")

    # Spot-check 頭 redirect forms
    print("\nSpot-check: redirect forms for 頭:")
    rows = db.execute("""
        SELECT f.form_text, f.romanization, e.romanization as entry_roman, e.pos
        FROM forms f JOIN entries e ON e.id = f.entry_id
        WHERE e.headword = '頭' AND f.morph_tags = 'redirect;alternative'
    """).fetchall()
    for r in rows:
        print(f"  {r['form_text']} -> roman={r['romanization']} (entry: {r['entry_roman']}/{r['pos']})")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
