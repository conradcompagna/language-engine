from __future__ import annotations

import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "cedict_ts.u8"
OUTPUT_PATH = (
    REPO_ROOT
    / "wiktionary general pipeline"
    / "converted_tsv"
    / "dict-chinese-cc-cedict.tsv"
)

CEDICT_LINE_RE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$")
TRADITIONAL_ALT_TAG = "Traditional-Chinese;alternative"


def _normalize_pinyin(raw: str) -> str:
    return " ".join(str(raw or "").strip().lower().split())


def _clean_text(value: str) -> str:
    return (
        str(value or "")
        .replace("\t", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _sense_key(sense: Dict[str, object]) -> str:
    return json.dumps(sense, ensure_ascii=False, sort_keys=True)


def _form_key(form: List[str]) -> str:
    return json.dumps(form, ensure_ascii=False, sort_keys=False)


def _parse_senses(defs_raw: str) -> List[Dict[str, object]]:
    senses: List[Dict[str, object]] = []
    for chunk in str(defs_raw or "").split("/"):
        gloss = _clean_text(chunk)
        if not gloss:
            continue
        senses.append({"glosses": [gloss]})
    return senses


def _build_traditional_form(
    simplified: str,
    traditional: str,
    romanization: str,
) -> List[List[str]]:
    simp = _clean_text(simplified)
    trad = _clean_text(traditional)
    if not simp or not trad or trad == simp:
        return []
    return [[trad, TRADITIONAL_ALT_TAG, romanization]]


def convert() -> None:
    entries: "OrderedDict[Tuple[str, str], Dict[str, object]]" = OrderedDict()
    headword_group_keys: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    raw_entry_count = 0
    kept_entry_count = 0

    with INPUT_PATH.open("r", encoding="utf-8") as infile:
        for line in infile:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue

            match = CEDICT_LINE_RE.match(line)
            if not match:
                continue

            raw_entry_count += 1
            traditional = _clean_text(match.group(1))
            simplified = _clean_text(match.group(2))
            romanization = _normalize_pinyin(match.group(3))
            senses = _parse_senses(match.group(4))

            if not simplified or not senses:
                continue

            group_key = (simplified, romanization)
            entry = entries.get(group_key)
            if entry is None:
                forms = _build_traditional_form(simplified, traditional, romanization)
                entry = {
                    "headword": simplified,
                    "pos": "",
                    "romanization": romanization,
                    "glosses": [],
                    "forms": list(forms),
                    "etymology_number": "",
                    "_sense_seen": set(),
                    "_form_seen": {_form_key(form) for form in forms},
                }
                entries[group_key] = entry
                headword_group_keys[simplified].append(group_key)

            for form in _build_traditional_form(simplified, traditional, romanization):
                form_id = _form_key(form)
                if form_id in entry["_form_seen"]:
                    continue
                entry["_form_seen"].add(form_id)
                entry["forms"].append(form)

            for sense in senses:
                sense_id = _sense_key(sense)
                if sense_id in entry["_sense_seen"]:
                    continue
                entry["_sense_seen"].add(sense_id)
                entry["glosses"].append(sense)

            kept_entry_count += 1

    for headword, group_keys in headword_group_keys.items():
        if len(group_keys) <= 1:
            continue
        for idx, key in enumerate(group_keys, start=1):
            entries[key]["etymology_number"] = str(idx)

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
                _clean_text(entry["headword"]),
                _clean_text(entry["pos"]),
                _clean_text(entry["romanization"]),
                json.dumps(entry["glosses"], ensure_ascii=False),
                json.dumps(entry["forms"], ensure_ascii=False),
                _clean_text(entry["etymology_number"]),
            ]
            outfile.write("\t".join(row) + "\n")

    print(
        "Converted "
        f"{kept_entry_count:,} parsed CEDICT rows from {raw_entry_count:,} source lines "
        f"into {len(entries):,} TSV rows at {OUTPUT_PATH}"
    )
    print("Structured POS scan: CC-CEDICT source lines do not include a dedicated POS field.")


if __name__ == "__main__":
    convert()
