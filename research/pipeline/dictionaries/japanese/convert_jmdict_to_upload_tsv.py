from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = REPO_ROOT / "JMdict_e"
OUTPUT_PATH = REPO_ROOT / "japanese" / "jmdict_upload.tsv"

_ENTITY_RE = re.compile(r'<!ENTITY\s+(\S+)\s+"([^"]*)">')
_ENTITY_REF_RE = re.compile(r'&([a-zA-Z0-9_.-]+);')


def _extract_entities(path: Path) -> Dict[str, str]:
    entities: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip() == "]>":
                break
            match = _ENTITY_RE.search(line)
            if match:
                entities[match.group(1)] = match.group(2)
    return entities


def _read_and_resolve_entities(path: Path, entity_map: Dict[str, str]) -> str:
    lines: List[str] = []
    past_dtd = False
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not past_dtd:
                if line.strip() == "]>":
                    past_dtd = True
                continue
            lines.append(line)
    text = "".join(lines)

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in {"amp", "lt", "gt", "quot", "apos"}:
            return match.group(0)
        return entity_map.get(name, match.group(0))

    text = _ENTITY_REF_RE.sub(_replace, text)
    if not text.lstrip().startswith("<?xml"):
        text = '<?xml version="1.0" encoding="UTF-8"?>\n' + text
    return text


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _map_pos(raw_pos_list: Sequence[str]) -> str:
    tags = [_norm(p) for p in raw_pos_list if str(p or "").strip()]
    if not tags:
        return "[]"

    def has(substr: str) -> bool:
        return any(substr in tag for tag in tags)

    if has("proper noun"):
        return "name"
    if has("pronoun"):
        return "pron"
    if has("interjection"):
        return "intj"
    if has("conjunction"):
        return "conj"
    if any(tag.startswith("particle") for tag in tags):
        return "particle"
    if has("prefix"):
        return "prefix"
    if has("suffix"):
        return "suffix"
    if has("counter"):
        return "counter"
    if has("numeric"):
        return "num"
    if has("symbol"):
        return "symbol"
    if has("expression") or has("phrases") or has("clauses") or has("unclassified"):
        return "phrase"
    if has("adverb"):
        return "adv"
    if has("pre-noun") or has("prenominally") or has("rentaishi"):
        return "adnominal"
    if (
        has("adjective")
        or has("adjectival")
        or has("keiyoushi")
        or has("keiyodoshi")
        or has("'taru'")
        or has("'shiku'")
        or has("'ku' adjective")
    ):
        return "adj"
    if (
        has("verb")
        or has("auxiliary verb")
        or has("auxiliary adjective")
        or has("copula")
        or any(tag.startswith("v1") or tag.startswith("v5") or tag.startswith("vk") or tag.startswith("vs") for tag in tags)
    ):
        return "verb"
    if has("noun"):
        return "noun"
    if has("affix"):
        return "affix"
    return "[]"


def _clean_cell(text: str) -> str:
    return str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _dedupe_forms(forms: Iterable[Tuple[str, str, str]]) -> List[List[str]]:
    out: List[List[str]] = []
    seen = set()
    for form, tag, reading in forms:
        form_txt = _clean_cell(form)
        if not form_txt or form_txt == "-":
            continue
        tag_txt = _clean_cell(tag)
        reading_txt = _clean_cell(reading)
        key = (form_txt, tag_txt, reading_txt)
        if key in seen:
            continue
        seen.add(key)
        out.append([form_txt, tag_txt, reading_txt])
    return out


def _reading_allowed_for_kanji(reading_restr: Dict[str, List[str]], reading: str, kanji: str) -> bool:
    allowed = reading_restr.get(reading) or []
    return not allowed or kanji in allowed


def _sense_allows_kanji(sense: Dict[str, object], kanji: str) -> bool:
    stagk = [str(v or "").strip() for v in (sense.get("stagk") or []) if str(v or "").strip()]
    return (not stagk) or (kanji in stagk)


def _sense_allows_reading(sense: Dict[str, object], reading: str) -> bool:
    stagr = [str(v or "").strip() for v in (sense.get("stagr") or []) if str(v or "").strip()]
    return (not stagr) or (reading in stagr)


def _sense_applies_to_pair(
    sense: Dict[str, object],
    reading_restr: Dict[str, List[str]],
    kanji: str,
    reading: str,
) -> bool:
    if not _sense_allows_kanji(sense, kanji):
        return False
    if not _sense_allows_reading(sense, reading):
        return False
    return _reading_allowed_for_kanji(reading_restr, reading, kanji)


def _sense_to_tsv_object(sense: Dict[str, object]) -> Dict[str, object] | None:
    glosses = [_clean_cell(g) for g in (sense.get("glosses") or []) if _clean_cell(g)]
    if not glosses:
        return None
    out: Dict[str, object] = {"glosses": glosses}
    misc = [_clean_cell(v) for v in (sense.get("misc") or []) if _clean_cell(v)]
    field = [_clean_cell(v) for v in (sense.get("field") or []) if _clean_cell(v)]
    s_inf = _clean_cell(sense.get("s_inf") or "")
    xref = [_clean_cell(v) for v in (sense.get("xref") or []) if _clean_cell(v)]
    ant = [_clean_cell(v) for v in (sense.get("ant") or []) if _clean_cell(v)]
    dial = [_clean_cell(v) for v in (sense.get("dial") or []) if _clean_cell(v)]
    if misc:
        out["misc"] = misc
    if field:
        out["field"] = field
    if s_inf:
        out["s_inf"] = s_inf
    if xref:
        out["xref"] = xref
    if ant:
        out["ant"] = ant
    if dial:
        out["dial"] = dial
    return out


def _parse_entries(xml_text: str) -> Iterable[Dict[str, object]]:
    root = ET.fromstring(xml_text)
    for entry_el in root.iter("entry"):
        kanji_forms: List[str] = []
        kanji_info: Dict[str, List[str]] = {}
        for k_ele in entry_el.iter("k_ele"):
            keb = k_ele.find("keb")
            if keb is not None and keb.text:
                kanji_forms.append(keb.text)
                infos = [ki.text for ki in k_ele.iter("ke_inf") if ki.text]
                if infos:
                    kanji_info[keb.text] = infos

        readings: List[str] = []
        reading_restr: Dict[str, List[str]] = {}
        reading_info: Dict[str, List[str]] = {}
        for r_ele in entry_el.iter("r_ele"):
            reb = r_ele.find("reb")
            if reb is None or not reb.text:
                continue
            reading = reb.text
            readings.append(reading)
            infos = [ri.text for ri in r_ele.iter("re_inf") if ri.text]
            if infos:
                reading_info[reading] = infos
            restr = [rr.text for rr in r_ele.iter("re_restr") if rr.text]
            if restr:
                reading_restr[reading] = restr
        if not readings:
            continue

        senses: List[Dict[str, object]] = []
        inherited_pos: List[str] = []
        for sense_el in entry_el.iter("sense"):
            glosses = [g.text for g in sense_el.iter("gloss") if g.text]
            if not glosses:
                continue
            sense_pos = [p.text for p in sense_el.iter("pos") if p.text]
            if sense_pos:
                inherited_pos = list(sense_pos)
            senses.append({
                "glosses": glosses,
                "pos": list(inherited_pos),
                "misc": [m.text for m in sense_el.iter("misc") if m.text],
                "s_inf": "; ".join(si.text for si in sense_el.iter("s_inf") if si.text),
                "field": [f.text for f in sense_el.iter("field") if f.text],
                "stagk": [sk.text for sk in sense_el.iter("stagk") if sk.text],
                "stagr": [sr.text for sr in sense_el.iter("stagr") if sr.text],
                "xref": [x.text for x in sense_el.iter("xref") if x.text],
                "ant": [a.text for a in sense_el.iter("ant") if a.text],
                "dial": [d.text for d in sense_el.iter("dial") if d.text],
            })
        if not senses:
            continue

        yield {
            "kanji_forms": kanji_forms,
            "kanji_info": kanji_info,
            "readings": readings,
            "reading_info": reading_info,
            "reading_restr": reading_restr,
            "senses": senses,
        }


def _sense_mapped_pos(sense: Dict[str, object]) -> str:
    return _map_pos([str(v or "") for v in (sense.get("pos") or []) if str(v or "").strip()])


def _group_senses_by_pos_boundaries(senses: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: List[Dict[str, object]] = []
    current: Dict[str, object] | None = None
    for sense in senses:
        mapped_pos = _sense_mapped_pos(sense)
        if current is None or current["pos"] != mapped_pos:
            current = {
                "pos": mapped_pos,
                "senses": [],
            }
            groups.append(current)
        current["senses"].append(sense)
    return groups


def _collect_group_forms(
    group_senses: Sequence[Dict[str, object]],
    kanji_forms: Sequence[str],
    readings: Sequence[str],
    reading_restr: Dict[str, List[str]],
) -> Tuple[List[str], List[str]]:
    applicable_kanji: List[str] = []
    applicable_readings: List[str] = []

    if kanji_forms:
        for kanji in kanji_forms:
            found = False
            for reading in readings:
                if not _reading_allowed_for_kanji(reading_restr, reading, kanji):
                    continue
                if any(_sense_applies_to_pair(sense, reading_restr, kanji, reading) for sense in group_senses):
                    found = True
                    break
            if found:
                applicable_kanji.append(kanji)
        for reading in readings:
            found = False
            for kanji in kanji_forms:
                if not _reading_allowed_for_kanji(reading_restr, reading, kanji):
                    continue
                if any(_sense_applies_to_pair(sense, reading_restr, kanji, reading) for sense in group_senses):
                    found = True
                    break
            if found:
                applicable_readings.append(reading)
    else:
        for reading in readings:
            if any(_sense_allows_reading(sense, reading) for sense in group_senses):
                applicable_readings.append(reading)

    if not applicable_kanji:
        applicable_kanji = [str(v or "").strip() for v in kanji_forms if str(v or "").strip()]
    if not applicable_readings:
        applicable_readings = [str(v or "").strip() for v in readings if str(v or "").strip()]
    return applicable_kanji, applicable_readings


def _select_group_headword(
    applicable_kanji: Sequence[str],
    applicable_readings: Sequence[str],
) -> Tuple[str, str]:
    if applicable_kanji:
        headword = str(applicable_kanji[0] or "").strip()
        row_reading = str(applicable_readings[0] or "").strip() if applicable_readings else ""
        return headword, row_reading
    if applicable_readings:
        headword = str(applicable_readings[0] or "").strip()
        return headword, headword
    return "", ""


def _build_row_forms(
    headword: str,
    row_reading: str,
    applicable_kanji: Sequence[str],
    applicable_readings: Sequence[str],
    kanji_info: Dict[str, List[str]],
    reading_info: Dict[str, List[str]],
) -> List[List[str]]:
    forms: List[Tuple[str, str, str]] = []

    def has_search_only(info_values: Sequence[str]) -> bool:
        for value in info_values:
            txt = _norm(value)
            if "search-only" in txt:
                return True
        return False

    if row_reading and row_reading != headword:
        reading_tag = "search-only;reading" if has_search_only(reading_info.get(row_reading) or []) else "reading"
        forms.append((row_reading, reading_tag, ""))
    for kanji in applicable_kanji:
        if kanji != headword:
            kanji_tag = "search-only;kanji" if has_search_only(kanji_info.get(kanji) or []) else "alternative;kanji"
            forms.append((kanji, kanji_tag, ""))
    for reading in applicable_readings:
        if reading == row_reading:
            continue
        reading_tag = "search-only;reading" if has_search_only(reading_info.get(reading) or []) else "alternative;reading"
        forms.append((reading, reading_tag, ""))
    return _dedupe_forms(forms)


def convert(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> Dict[str, int]:
    entity_map = _extract_entities(input_path)
    xml_text = _read_and_resolve_entities(input_path, entity_map)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    row_count = 0
    entry_count = 0
    seen_rows = set()

    with output_path.open("w", encoding="utf-8", newline="") as out:
        out.write("headword\tpos\tromanization\tglosses\tforms\n")
        for entry in _parse_entries(xml_text):
            entry_count += 1
            kanji_forms = [str(v or "").strip() for v in entry["kanji_forms"] if str(v or "").strip()]
            kanji_info = entry["kanji_info"]
            readings = [str(v or "").strip() for v in entry["readings"] if str(v or "").strip()]
            reading_info = entry["reading_info"]
            reading_restr = entry["reading_restr"]
            senses = entry["senses"]

            pos_groups = _group_senses_by_pos_boundaries(senses)
            for group in pos_groups:
                group_senses = list(group.get("senses") or [])
                if not group_senses:
                    continue
                applicable_kanji, applicable_readings = _collect_group_forms(
                    group_senses,
                    kanji_forms,
                    readings,
                    reading_restr,
                )
                headword, row_reading = _select_group_headword(applicable_kanji, applicable_readings)
                if not headword:
                    continue

                row_senses: List[Dict[str, object]] = []
                for sense in group_senses:
                    sense_out = _sense_to_tsv_object(sense)
                    if sense_out:
                        row_senses.append(sense_out)
                if not row_senses:
                    continue

                pos = _clean_cell(group.get("pos") or "[]")
                forms = _build_row_forms(
                    headword,
                    row_reading,
                    applicable_kanji,
                    applicable_readings,
                    kanji_info,
                    reading_info,
                )
                headword_txt = _clean_cell(headword)
                reading_txt = _clean_cell(row_reading)
                glosses_json = json.dumps(row_senses, ensure_ascii=False)
                forms_json = json.dumps(forms, ensure_ascii=False)
                row_key = (headword_txt, pos, reading_txt, glosses_json, forms_json)
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                out.write(
                    f"{headword_txt}\t{_clean_cell(pos)}\t{reading_txt}\t{glosses_json}\t{forms_json}\n"
                )
                row_count += 1

    return {
        "entries": entry_count,
        "rows": row_count,
    }


if __name__ == "__main__":
    stats = convert()
    print(f"Converted {stats['entries']:,} JMdict entries -> {stats['rows']:,} TSV rows")
    print(f"Output: {OUTPUT_PATH}")
