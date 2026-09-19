from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "cnotes_zh_en_dict.tsv"
OUTPUT_PATH = (
    REPO_ROOT / "wiktionary general pipeline" / "converted_tsv" / "dict-classical-chinese.tsv"
)

NULL_MARKERS = {"", "\\N", "NULL"}
PROVERB_REGISTERS = {"idiom", "proverb", "common saying"}


def _clean(value: str) -> str:
    text = str(value or "").strip()
    if text in NULL_MARKERS:
        return ""
    return text


def _canonical_headword(simplified: str, traditional: str) -> Tuple[str, List[List[str]]]:
    simp = _clean(simplified)
    trad = _clean(traditional)
    if trad and trad != simp:
        return trad, [[simp, "Simplified-Chinese;alternative", ""]]
    return simp or trad, []


def _map_pos(raw_pos: str, register_en: str, headword: str) -> str:
    pos = _clean(raw_pos).lower()
    register = _clean(register_en).lower()
    if not pos:
        return "character" if len(headword) == 1 else "phrase"

    direct = {
        "noun": "noun",
        "verb": "verb",
        "proper noun": "name",
        "adjective": "adj",
        "adverb": "adv",
        "measure word": "classifier",
        "pronoun": "pron",
        "conjunction": "conj",
        "particle": "particle",
        "interjection": "intj",
        "number": "num",
        "ordinal": "num",
        "prefix": "prefix",
        "suffix": "suffix",
        "infix": "infix",
        "auxiliary verb": "verb",
        "bound form": "root",
        "preposition": "prep",
        "foreign": "character",
        "phonetic": "character",
        "radical": "character",
        "onomatopoeia": "intj",
    }
    if pos in direct:
        return direct[pos]

    if pos in {"set phrase", "phrase", "expression", "pattern"}:
        if register in PROVERB_REGISTERS:
            return "proverb"
        return "phrase"

    return pos


def _sense_from_row(row: Dict[str, str]) -> Dict[str, object]:
    english = _clean(row["english"])
    sense: Dict[str, object] = {"glosses": [english]}

    qualifier_parts = [
        _clean(row["register_en"]),
        _clean(row["topic_en"]),
        _clean(row["subtopic_en"]),
    ]
    qualifier = "; ".join(part for part in qualifier_parts if part)
    if qualifier:
        sense["qualifier"] = qualifier

    grammar_en = _clean(row["grammar_en"])
    if grammar_en:
        sense["tags"] = [grammar_en]

    notes = _clean(row["notes"])
    if notes:
        sense["notes"] = notes

    return sense


def _sense_key(sense: Dict[str, object]) -> str:
    return json.dumps(sense, ensure_ascii=False, sort_keys=True)


def _tsv_cell(value: object) -> str:
    text = str(value or "")
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def convert() -> None:
    entries: "OrderedDict[Tuple[str, str, str, str], Dict[str, object]]" = OrderedDict()
    raw_row_count = 0
    kept_row_count = 0
    mapped_pos_counts: Dict[str, int] = {}

    with INPUT_PATH.open("r", encoding="utf-8", newline="") as infile:
        import csv

        reader = csv.reader(infile, delimiter="\t")
        for cols in reader:
            raw_row_count += 1
            if len(cols) < 16:
                continue

            entry_id = _clean(cols[0])
            if not entry_id.isdigit():
                continue

            row = {
                "id": entry_id,
                "simplified": cols[1],
                "traditional": cols[2],
                "pinyin": cols[3],
                "english": cols[4],
                "pos": cols[5],
                "grammar_zh": cols[6],
                "grammar_en": cols[7],
                "register_zh": cols[8],
                "register_en": cols[9],
                "topic_zh": cols[10],
                "topic_en": cols[11],
                "subtopic_zh": cols[12],
                "subtopic_en": cols[13],
                "notes": cols[14],
                "concept_id": cols[15],
            }

            english = _clean(row["english"])
            if not english:
                continue

            headword, forms = _canonical_headword(
                row["simplified"],
                row["traditional"],
            )
            if not headword:
                continue

            pos = _map_pos(row["pos"], row["register_en"], headword)
            romanization = _clean(row["pinyin"])
            concept_id = _clean(row["concept_id"])
            group_key = (headword, pos, romanization, concept_id)

            entry = entries.get(group_key)
            if entry is None:
                entry = {
                    "headword": headword,
                    "pos": pos,
                    "romanization": romanization,
                    "glosses": [],
                    "forms": list(forms),
                    "etymology_number": concept_id if concept_id.isdigit() else "",
                    "_sense_seen": set(),
                    "_form_seen": {
                        json.dumps(form, ensure_ascii=False, sort_keys=False) for form in forms
                    },
                }
                entries[group_key] = entry

            for form in forms:
                form_key = json.dumps(form, ensure_ascii=False, sort_keys=False)
                if form_key not in entry["_form_seen"]:
                    entry["_form_seen"].add(form_key)
                    entry["forms"].append(form)

            sense = _sense_from_row(row)
            sense_key = _sense_key(sense)
            if sense_key not in entry["_sense_seen"]:
                entry["_sense_seen"].add(sense_key)
                entry["glosses"].append(sense)

            kept_row_count += 1
            mapped_pos_counts[pos] = mapped_pos_counts.get(pos, 0) + 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as outfile:
        outfile.write(
            "\t".join(
                [
                    "headword",
                    "pos",
                    "romanization",
                    "glosses",
                    "forms",
                    "etymology_number",
                ]
            )
            + "\n"
        )
        for entry in entries.values():
            row = [
                _tsv_cell(entry["headword"]),
                _tsv_cell(entry["pos"]),
                _tsv_cell(entry["romanization"]),
                json.dumps(entry["glosses"], ensure_ascii=False),
                json.dumps(entry["forms"], ensure_ascii=False),
                _tsv_cell(entry["etymology_number"]),
            ]
            outfile.write("\t".join(row) + "\n")

    unique_pos = ", ".join(sorted(mapped_pos_counts))
    print(
        "Converted "
        f"{kept_row_count:,} sense rows from {raw_row_count:,} raw rows into "
        f"{len(entries):,} compact entries at {OUTPUT_PATH}"
    )
    print(f"Mapped POS: {unique_pos}")


if __name__ == "__main__":
    convert()
