"""
apply_romaji.py — Reads jmdict_upload.tsv and fills the romanization column
using logic ported directly from static/romaji.js (Hepburn romanization).
Overwrites the TSV in-place.
"""
from __future__ import annotations
import json
from pathlib import Path

TSV_PATH = Path(__file__).resolve().parent / "jmdict_upload.tsv"

# ---------------------------------------------------------------------------
# Romaji engine — ported from static/romaji.js
# ---------------------------------------------------------------------------

KATA_HIRA_OFFSET = 0x60  # ア(0x30A1) − あ(0x3041)

def _katakana_to_hiragana(s: str) -> str:
    out = []
    for ch in s:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            out.append(chr(cp - KATA_HIRA_OFFSET))
        else:
            out.append(ch)
    return "".join(out)

DIGRAPHS: dict[str, str] = {
    # k-row
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    # s-row
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "じゃ": "ja",  "じゅ": "ju",  "じょ": "jo",
    # t-row
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "ぢゃ": "dya", "ぢゅ": "dyu", "ぢょ": "dyo",
    # n-row
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    # h-row
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
    # m-row
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    # r-row
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    # extended / foreign-loan
    "てぃ": "ti",  "でぃ": "di",
    "ふぁ": "fa",  "ふぃ": "fi",  "ふぇ": "fe",  "ふぉ": "fo",
    "うぃ": "wi",  "うぇ": "we",  "うぉ": "wo",
    "ゔぁ": "va",  "ゔぃ": "vi",  "ゔぇ": "ve",  "ゔぉ": "vo",
    "つぁ": "tsa", "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
    "ちぇ": "che", "しぇ": "she", "じぇ": "je",
    "でゅ": "dyu",
    "とぅ": "tu",  "どぅ": "du",
}

SINGLE: dict[str, str] = {
    "あ": "a",  "い": "i",  "う": "u",  "え": "e",  "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "さ": "sa", "し": "shi","す": "su", "せ": "se", "そ": "so",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "た": "ta", "ち": "chi","つ": "tsu","て": "te", "と": "to",
    "だ": "da", "ぢ": "di", "づ": "du", "で": "de", "ど": "do",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "wi", "ゑ": "we", "を": "wo", "ん": "n",
    "ゔ": "vu",
    # small vowels
    "ぁ": "a",  "ぃ": "i",  "ぅ": "u",  "ぇ": "e",  "ぉ": "o",
    "ゃ": "ya", "ゅ": "yu", "ょ": "yo",
    "ゎ": "wa",
}

VOWELS = {"a", "i", "u", "e", "o"}

def _last_vowel(roman: str) -> str:
    for ch in reversed(roman):
        if ch in VOWELS:
            return ch
    return "a"

def _peek_next_roman(hira: str, i: int) -> str:
    if i >= len(hira):
        return ""
    if i + 1 < len(hira):
        pair = hira[i] + hira[i + 1]
        if pair in DIGRAPHS:
            return DIGRAPHS[pair]
    return SINGLE.get(hira[i], "")

def to_romaji(input_str: str) -> str:
    if not input_str:
        return ""
    hira = _katakana_to_hiragana(input_str)
    out: list[str] = []
    last_roman = ""
    i = 0
    while i < len(hira):
        ch = hira[i]
        cp = ord(ch)

        # small tsu — double next consonant
        if ch == "っ":
            next_roman = _peek_next_roman(hira, i + 1)
            if next_roman and next_roman[0] not in VOWELS and next_roman[0] != "n":
                out.append(next_roman[0])
                last_roman = next_roman[0]
            else:
                out.append("tsu")
                last_roman = "tsu"
            i += 1
            continue

        # prolonged sound mark ー
        if ch == "ー" or cp == 0x30FC:
            vowel = _last_vowel(last_roman or "".join(out))
            out.append(vowel)
            i += 1
            continue

        # digraph
        if i + 1 < len(hira):
            pair = hira[i] + hira[i + 1]
            if pair in DIGRAPHS:
                roman = DIGRAPHS[pair]
                out.append(roman)
                last_roman = roman
                i += 2
                continue

        # single kana
        if ch in SINGLE:
            roman = SINGLE[ch]
            # ん before vowel or y → n'
            if ch == "ん" and i + 1 < len(hira):
                nxt = hira[i + 1]
                nxt_r = SINGLE.get(nxt, "")
                if nxt_r and (nxt_r[0] in VOWELS or nxt_r[0] == "y"):
                    out.append("n'")
                    last_roman = "n"
                    i += 1
                    continue
            out.append(roman)
            last_roman = roman
            i += 1
            continue

        # non-kana: pass through using original (pre-hiragana-conversion) char
        out.append(input_str[i])
        last_roman = ""
        i += 1

    return "".join(out)


# ---------------------------------------------------------------------------
# Main: rewrite TSV
# ---------------------------------------------------------------------------

def main() -> None:
    with open(TSV_PATH, encoding="utf-8", newline="") as f:
        lines = f.readlines()

    header = lines[0]
    data_lines = lines[1:]

    out_lines = [header]
    for line in data_lines:
        stripped = line.rstrip("\n")
        parts = stripped.split("\t")
        if len(parts) < 5:
            out_lines.append(line)
            continue
        headword, pos, kana_reading, glosses, forms = parts[0], parts[1], parts[2], parts[3], parts[4]
        romaji = to_romaji(kana_reading)
        out_lines.append(f"{headword}\t{pos}\t{romaji}\t{glosses}\t{forms}\n")

    with open(TSV_PATH, "w", encoding="utf-8", newline="") as f:
        f.writelines(out_lines)

    print(f"Done. Processed {len(data_lines)} rows.")
    # Spot-check a few
    import random
    sample_indices = random.sample(range(len(data_lines)), min(10, len(data_lines)))
    print("\nSpot-check (kana → romaji):")
    for idx in sorted(sample_indices):
        parts = data_lines[idx].rstrip("\n").split("\t")
        if len(parts) >= 3:
            print(f"  {parts[2]!r:30} → {to_romaji(parts[2])!r}")

if __name__ == "__main__":
    main()
