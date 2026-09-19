"""
Convert official KRDICT XML (LMF format) to JSON term banks.

Reads all *_*.xml files from korean/off/, extracts every field,
keeps ONLY English (영어) equivalents, and writes term_bank_*.json
files into korean/dict/.

Usage:
    python korean/convert_krdict_xml.py
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SRC_DIR = Path(__file__).parent / "off"
DST_DIR = Path(__file__).parent / "dict"
ENTRIES_PER_BANK = 5000


def _feat(el, att):
    """Get the val of a <feat att="X" val="Y"/> child, or ''."""
    for f in el.findall("feat"):
        if f.get("att") == att:
            return f.get("val", "")
    return ""


def _all_feats(el, att):
    """Get all vals for a given att (some elements have multiple)."""
    return [f.get("val", "") for f in el.findall("feat") if f.get("att") == att]


def parse_entry(lex_entry):
    """Parse a single <LexicalEntry> into a dict with all fields."""
    entry_id = lex_entry.get("val", "")
    homonym_number = _feat(lex_entry, "homonym_number")
    lexical_unit = _feat(lex_entry, "lexicalUnit")
    part_of_speech = _feat(lex_entry, "partOfSpeech")
    origin = _feat(lex_entry, "origin")
    vocabulary_level = _feat(lex_entry, "vocabularyLevel")

    # Lemma
    lemma_el = lex_entry.find("Lemma")
    headword = _feat(lemma_el, "writtenForm") if lemma_el is not None else ""

    # WordForms — split into pronunciation vs conjugations
    pronunciation = ""
    pronunciation_url = ""
    conjugations = []
    for wf in lex_entry.findall("WordForm"):
        wf_type = _feat(wf, "type")
        if wf_type == "발음":
            pronunciation = _feat(wf, "pronunciation")
            pronunciation_url = _feat(wf, "sound")
        elif wf_type == "활용":
            conjugations.append(
                {
                    "written": _feat(wf, "writtenForm"),
                    "pronunciation": _feat(wf, "pronunciation"),
                    "sound_url": _feat(wf, "sound"),
                }
            )

    # Related forms
    related_forms = []
    for rf in lex_entry.findall("RelatedForm"):
        related_forms.append(
            {
                "type": _feat(rf, "type"),
                "id": _feat(rf, "id"),
                "written": _feat(rf, "writtenForm"),
            }
        )

    # Senses
    senses = []
    for sense_el in lex_entry.findall("Sense"):
        sense_id = sense_el.get("val", "")
        definition_ko = _feat(sense_el, "definition")
        syntactic_pattern = _feat(sense_el, "syntacticPattern")
        semantic_category = _feat(sense_el, "semanticCategory")

        # Examples
        examples = []
        for ex_el in sense_el.findall("SenseExample"):
            ex_type = _feat(ex_el, "type")
            ex_texts = _all_feats(ex_el, "example")
            examples.append({"type": ex_type, "texts": ex_texts})

        # English equivalent only
        en_lemma = ""
        en_definition = ""
        for eq_el in sense_el.findall("Equivalent"):
            if _feat(eq_el, "language") == "영어":
                en_lemma = _feat(eq_el, "lemma").strip()
                en_definition = _feat(eq_el, "definition").strip()
                break

        senses.append(
            {
                "id": sense_id,
                "definition_ko": definition_ko,
                "syntactic_pattern": syntactic_pattern,
                "semantic_category": semantic_category,
                "examples": examples,
                "en_lemma": en_lemma,
                "en_definition": en_definition,
            }
        )

    return {
        "entry_id": entry_id,
        "headword": headword,
        "homonym_number": homonym_number,
        "lexical_unit": lexical_unit,
        "part_of_speech": part_of_speech,
        "origin": origin,
        "pronunciation": pronunciation,
        "pronunciation_url": pronunciation_url,
        "conjugations": conjugations,
        "related_forms": related_forms,
        "vocabulary_level": vocabulary_level,
        "senses": senses,
    }


def natural_sort_key(p):
    """Sort filenames like 1_5000, 2_5000, ... 10_5000, 11_1961."""
    nums = re.findall(r"\d+", p.stem)
    return [int(n) for n in nums]


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(SRC_DIR.glob("*_*_*.xml"), key=natural_sort_key)
    if not xml_files:
        print(f"[ERROR] No XML files found in {SRC_DIR}")
        return

    print(f"[INFO] Found {len(xml_files)} XML files in {SRC_DIR}")

    all_entries = []
    for xml_path in xml_files:
        print(f"  Parsing {xml_path.name} ...", end=" ", flush=True)
        tree = ET.parse(xml_path)
        root = tree.getroot()
        lexicon = root.find("Lexicon")
        count = 0
        for lex_entry in lexicon.findall("LexicalEntry"):
            entry = parse_entry(lex_entry)
            all_entries.append(entry)
            count += 1
        print(f"{count:,} entries")

    print(f"\n[INFO] Total entries parsed: {len(all_entries):,}")

    # Write term banks
    bank_num = 1
    for i in range(0, len(all_entries), ENTRIES_PER_BANK):
        chunk = all_entries[i : i + ENTRIES_PER_BANK]
        out_path = DST_DIR / f"term_bank_{bank_num}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  Wrote {out_path.name}: {len(chunk):,} entries")
        bank_num += 1

    # Write index
    index = {
        "title": "KRDICT-Official",
        "format": 4,
        "revision": "krdict_official_20260219",
        "description": "Korean-English from NIKL KRDICT (official XML export)",
        "entry_count": len(all_entries),
    }
    index_path = DST_DIR / "index.json"
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  Wrote {index_path.name}")

    print(f"\n[DONE] {len(all_entries):,} entries -> {bank_num - 1} term banks in {DST_DIR}")


if __name__ == "__main__":
    main()
