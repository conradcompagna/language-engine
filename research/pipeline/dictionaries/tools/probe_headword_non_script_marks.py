#!/usr/bin/env python3
"""Inventory non-script marks in dictionary headwords and forms."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, DefaultDict, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from language_registry import APP_ROOT, LANGUAGE_REGISTRY


def _set_csv_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _in_ranges(cp: int, ranges: Iterable[Tuple[int, int]]) -> bool:
    return any(start <= cp <= end for start, end in ranges)


COMMON_COMBINING_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0300, 0x036F),   # Combining Diacritical Marks
    (0x1AB0, 0x1AFF),   # Combining Diacritical Marks Extended
    (0x1DC0, 0x1DFF),   # Combining Diacritical Marks Supplement
    (0x20D0, 0x20FF),   # Combining Diacritical Marks for Symbols
    (0xFE20, 0xFE2F),   # Combining Half Marks
)

LATIN_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0041, 0x005A),
    (0x0061, 0x007A),
    (0x00C0, 0x00FF),
    (0x0100, 0x017F),
    (0x0180, 0x024F),
    (0x1E00, 0x1EFF),
    (0x2C60, 0x2C7F),
    (0xA720, 0xA7FF),
    (0xAB30, 0xAB6F),
    (0xFB00, 0xFB06),
)

CYRILLIC_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0400, 0x04FF),
    (0x0500, 0x052F),
    (0x1C80, 0x1C8F),
    (0x2DE0, 0x2DFF),
    (0xA640, 0xA69F),
    (0x1E030, 0x1E08F),
)

GREEK_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0370, 0x03FF),
    (0x1F00, 0x1FFF),
)

ARMENIAN_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0530, 0x058F),
    (0xFB13, 0xFB17),
)

HEBREW_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0590, 0x05FF),
    (0xFB1D, 0xFB4F),
)

ARABIC_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x0870, 0x089F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
    (0x1EE00, 0x1EEFF),
)

DEVANAGARI_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0900, 0x097F),
    (0xA8E0, 0xA8FF),
    (0x1CD0, 0x1CFF),
)

TAMIL_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0B80, 0x0BFF),
    (0x11FC0, 0x11FFF),
)

THAI_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x0E00, 0x0E7F),
)

HIRAGANA_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x3040, 0x309F),
)

KATAKANA_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x30A0, 0x30FF),
    (0x31F0, 0x31FF),
    (0xFF65, 0xFF9F),
)

HANGUL_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x1100, 0x11FF),
    (0x3130, 0x318F),
    (0xA960, 0xA97F),
    (0xAC00, 0xD7A3),
    (0xD7B0, 0xD7FF),
    (0xFFA0, 0xFFDC),
)

HAN_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x2E80, 0x2EFF),   # CJK Radicals Supplement
    (0x2FF0, 0x2FFF),   # Ideographic Description Characters
    (0x31C0, 0x31EF),   # CJK Strokes
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF), # Extension B
    (0x2A700, 0x2B73F), # Extension C
    (0x2B740, 0x2B81F), # Extension D
    (0x2B820, 0x2CEAF), # Extension E
    (0x2CEB0, 0x2EBEF), # Extension F
    (0x2EBF0, 0x2EE5F), # Extension I
    (0x2F800, 0x2FA1F), # Compatibility Supplement
    (0x30000, 0x3134F), # Extension G
    (0x31350, 0x323AF), # Extension H
)

HAN_SINGLETONS = {0x3005, 0x3006, 0x3007, 0x3031, 0x3032, 0x3033, 0x3034, 0x3035, 0x303B}


def _is_common_combining_mark(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, COMMON_COMBINING_RANGES)


def _is_han_family(ch: str) -> bool:
    cp = ord(ch)
    return cp in HAN_SINGLETONS or _in_ranges(cp, HAN_RANGES)


def _is_japanese_family(ch: str) -> bool:
    cp = ord(ch)
    return (
        _is_han_family(ch)
        or _in_ranges(cp, HIRAGANA_RANGES)
        or _in_ranges(cp, KATAKANA_RANGES)
    )


def _is_korean_family(ch: str) -> bool:
    cp = ord(ch)
    return _is_han_family(ch) or _in_ranges(cp, HANGUL_RANGES)


def _is_latin_family(ch: str) -> bool:
    cp = ord(ch)
    if _in_ranges(cp, LATIN_RANGES):
        return True
    return _is_common_combining_mark(ch)


def _is_cyrillic_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, CYRILLIC_RANGES) or _is_common_combining_mark(ch)


def _is_greek_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, GREEK_RANGES) or _is_common_combining_mark(ch)


def _is_armenian_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, ARMENIAN_RANGES) or _is_common_combining_mark(ch)


def _is_hebrew_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, HEBREW_RANGES) or _is_common_combining_mark(ch)


def _is_arabic_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, ARABIC_RANGES) or _is_common_combining_mark(ch)


def _is_devanagari_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, DEVANAGARI_RANGES) or _is_common_combining_mark(ch)


def _is_tamil_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, TAMIL_RANGES) or _is_common_combining_mark(ch)


def _is_thai_family(ch: str) -> bool:
    cp = ord(ch)
    return _in_ranges(cp, THAI_RANGES) or _is_common_combining_mark(ch)


@dataclass(frozen=True)
class ScriptFamily:
    key: str
    description: str
    checker: Callable[[str], bool]


SCRIPT_FAMILIES: Dict[str, ScriptFamily] = {
    "latin": ScriptFamily(
        key="latin",
        description="Latin script family plus common combining diacritics",
        checker=_is_latin_family,
    ),
    "cyrillic": ScriptFamily(
        key="cyrillic",
        description="Cyrillic script family plus common combining diacritics",
        checker=_is_cyrillic_family,
    ),
    "greek": ScriptFamily(
        key="greek",
        description="Greek script family plus common combining diacritics",
        checker=_is_greek_family,
    ),
    "armenian": ScriptFamily(
        key="armenian",
        description="Armenian script family plus common combining diacritics",
        checker=_is_armenian_family,
    ),
    "hebrew": ScriptFamily(
        key="hebrew",
        description="Hebrew script family plus common combining diacritics",
        checker=_is_hebrew_family,
    ),
    "arabic": ScriptFamily(
        key="arabic",
        description="Arabic script family plus common combining diacritics",
        checker=_is_arabic_family,
    ),
    "devanagari": ScriptFamily(
        key="devanagari",
        description="Devanagari script family plus common combining diacritics",
        checker=_is_devanagari_family,
    ),
    "tamil": ScriptFamily(
        key="tamil",
        description="Tamil script family plus common combining diacritics",
        checker=_is_tamil_family,
    ),
    "thai": ScriptFamily(
        key="thai",
        description="Thai script family plus common combining diacritics",
        checker=_is_thai_family,
    ),
    "han": ScriptFamily(
        key="han",
        description="Han family (CJK ideographs, extensions, radicals, strokes, IDCs)",
        checker=_is_han_family,
    ),
    "japanese": ScriptFamily(
        key="japanese",
        description="Japanese family (Han + Hiragana + Katakana + related kana marks)",
        checker=_is_japanese_family,
    ),
    "korean": ScriptFamily(
        key="korean",
        description="Korean family (Hangul + Han/Hanja)",
        checker=_is_korean_family,
    ),
}


DICT_FAMILY_BY_STEM: Dict[str, str] = {
    "dict-ancientgreek": "greek",
    "dict-arabic": "arabic",
    "dict-armenian": "armenian",
    "dict-chinese": "han",
    "dict-dutch": "latin",
    "dict-french": "latin",
    "dict-german": "latin",
    "dict-greek": "greek",
    "dict-hebrew": "hebrew",
    "dict-hindi": "devanagari",
    "dict-indonesian": "latin",
    "dict-italian": "latin",
    "dict-japanese": "japanese",
    "dict-korean": "korean",
    "dict-latin": "latin",
    "dict-persian": "arabic",
    "dict-portuguese": "latin",
    "dict-russian": "cyrillic",
    "dict-spanish": "latin",
    "dict-tamil": "tamil",
    "dict-thai": "thai",
    "dict-turkish": "latin",
    "dict-urdu": "arabic",
    "dict-vietnamese": "latin",
}


LANG_FAMILY_BY_KEY: Dict[str, str] = {
    "ar": "arabic",
    "fa": "arabic",
    "grc": "greek",
    "el": "greek",
    "he": "hebrew",
    "hi": "devanagari",
    "hy": "armenian",
    "ja": "japanese",
    "ko": "korean",
    "lzh": "han",
    "mr": "devanagari",
    "nl": "latin",
    "de": "latin",
    "es": "latin",
    "fr": "latin",
    "id": "latin",
    "it": "latin",
    "la": "latin",
    "pt": "latin",
    "tr": "latin",
    "vi": "latin",
    "ru": "cyrillic",
    "ta": "tamil",
    "th": "thai",
    "ur": "arabic",
    "zh": "han",
    "zh-Hant": "han",
}


@dataclass
class DictSpec:
    label: str
    path: Path
    script_family: ScriptFamily
    report_path: Path


@dataclass
class ReportData:
    label: str
    path: Path
    script_family: ScriptFamily
    row_count: int
    headword_surface_count: int
    form_surface_count: int
    total_counts: Counter[str]
    headword_counts: Counter[str]
    form_counts: Counter[str]
    examples: Dict[str, List[str]]


def _resolve_lang_key(lang: str) -> str:
    candidate = str(lang or "").strip()
    if candidate in LANGUAGE_REGISTRY:
        return candidate
    lowered = candidate.lower()
    for key, cfg in LANGUAGE_REGISTRY.items():
        aliases = [str(a).lower() for a in cfg.get("aliases", [])]
        if lowered == key.lower() or lowered in aliases:
            return key
    raise KeyError(f"Unsupported language key or alias: {lang}")


def _resolve_family_for_lang(lang_key: str) -> ScriptFamily:
    family_key = LANG_FAMILY_BY_KEY.get(lang_key)
    if not family_key:
        raise KeyError(f"No script-family mapping defined for language {lang_key}")
    return SCRIPT_FAMILIES[family_key]


def _resolve_dict_path_for_lang(lang_key: str) -> Path:
    cfg = LANGUAGE_REGISTRY[lang_key]
    dict_file = cfg.get("dict_file")
    if not dict_file:
        raise KeyError(f"No dict_file configured for language {lang_key}")
    return (APP_ROOT / dict_file).resolve()


def _iter_surfaces(row: Dict[str, str]) -> Iterable[Tuple[str, str]]:
    headword = str(row.get("headword", "") or "").strip()
    if headword:
        yield "headword", headword

    forms_raw = str(row.get("forms", "") or "").strip()
    if not forms_raw:
        return

    try:
        forms = json.loads(forms_raw)
    except (json.JSONDecodeError, TypeError):
        return

    if not isinstance(forms, list):
        return

    for form_row in forms:
        if not isinstance(form_row, list) or not form_row:
            continue
        form_text = str(form_row[0] or "").strip()
        if not form_text:
            continue
        yield "form", form_text


def _should_count_char(ch: str, in_family: Callable[[str], bool]) -> bool:
    if in_family(ch):
        return False
    category = unicodedata.category(ch)
    if not category:
        return False
    return category[0] in {"P", "S", "Z", "M", "C"}


def _codepoint_label(ch: str) -> str:
    return f"U+{ord(ch):04X}"


def _display_char(ch: str) -> str:
    named = {
        " ": "[space]",
        "\t": "[tab]",
        "\n": "[newline]",
        "\r": "[carriage return]",
    }
    if ch in named:
        return named[ch]
    if unicodedata.category(ch).startswith("C"):
        return "[control/format]"
    return ch


def _md_escape(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n")


def _write_report(report: ReportData, output_path: Path) -> None:
    rows = sorted(
        report.total_counts,
        key=lambda ch: (-report.total_counts[ch], _codepoint_label(ch)),
    )
    total_occurrences = sum(report.total_counts.values())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"# Non-script Marks Inventory for `{report.label}`\n\n")
        out.write(f"- Dictionary: `{report.path.relative_to(APP_ROOT)}`\n")
        out.write(f"- TSV rows scanned: {report.row_count:,}\n")
        out.write(f"- Headword surfaces scanned: {report.headword_surface_count:,}\n")
        out.write(f"- Form surfaces scanned: {report.form_surface_count:,}\n")
        out.write(f"- Script family treated as in-family: {report.script_family.description}\n")
        out.write("- Counted as junk: codepoints outside that family whose Unicode category starts with `P`, `S`, `Z`, `M`, or `C`\n")
        out.write("- Explicitly excluded from this pass: letters and decimal digits\n")
        out.write(f"- Distinct junk codepoints found: {len(rows):,}\n")
        out.write(f"- Total junk-codepoint occurrences: {total_occurrences:,}\n\n")
        out.write("| Glyph | Codepoint | Total | Headword | Forms | Category | Unicode name | Sample surfaces |\n")
        out.write("| --- | --- | ---: | ---: | ---: | --- | --- | --- |\n")

        for ch in rows:
            name = unicodedata.name(ch, "<unnamed>")
            samples = "; ".join(_md_escape(s) for s in report.examples.get(ch, []))
            out.write(
                f"| {_md_escape(_display_char(ch))} | `{_codepoint_label(ch)}` | "
                f"{report.total_counts[ch]:,} | {report.headword_counts[ch]:,} | {report.form_counts[ch]:,} | "
                f"`{unicodedata.category(ch)}` | {_md_escape(name)} | {samples} |\n"
            )


def _scan_dictionary(spec: DictSpec) -> ReportData:
    total_counts: Counter[str] = Counter()
    headword_counts: Counter[str] = Counter()
    form_counts: Counter[str] = Counter()
    examples: DefaultDict[str, List[str]] = defaultdict(list)

    row_count = 0
    headword_surface_count = 0
    form_surface_count = 0

    with spec.path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            row_count += 1
            for source, surface in _iter_surfaces(row):
                if source == "headword":
                    headword_surface_count += 1
                else:
                    form_surface_count += 1
                for ch in surface:
                    if not _should_count_char(ch, spec.script_family.checker):
                        continue
                    total_counts[ch] += 1
                    if source == "headword":
                        headword_counts[ch] += 1
                    else:
                        form_counts[ch] += 1
                    if surface not in examples[ch] and len(examples[ch]) < 5:
                        examples[ch].append(surface)

    return ReportData(
        label=spec.label,
        path=spec.path,
        script_family=spec.script_family,
        row_count=row_count,
        headword_surface_count=headword_surface_count,
        form_surface_count=form_surface_count,
        total_counts=total_counts,
        headword_counts=headword_counts,
        form_counts=form_counts,
        examples=dict(examples),
    )


def _build_batch_specs(reports_dir: Path) -> List[DictSpec]:
    folder = ROOT / "wiktionary general pipeline" / "converted_tsv"
    specs: List[DictSpec] = []
    for path in sorted(folder.glob("dict-*.tsv")):
        stem = path.stem
        if " - Copy" in stem:
            continue
        family_key = DICT_FAMILY_BY_STEM.get(stem)
        if not family_key:
            raise KeyError(f"No script-family mapping defined for {stem}")
        report_path = reports_dir / f"{stem}.md"
        specs.append(
            DictSpec(
                label=stem,
                path=path.resolve(),
                script_family=SCRIPT_FAMILIES[family_key],
                report_path=report_path.resolve(),
            )
        )
    return specs


def _build_single_spec(lang_key: str, out_path: Path) -> DictSpec:
    path = _resolve_dict_path_for_lang(lang_key)
    family = _resolve_family_for_lang(lang_key)
    return DictSpec(
        label=lang_key,
        path=path,
        script_family=family,
        report_path=out_path.resolve(),
    )


def _write_master_report(
    reports: List[ReportData],
    output_path: Path,
    min_total: int,
) -> None:
    total_counts: Counter[str] = Counter()
    headword_counts: Counter[str] = Counter()
    form_counts: Counter[str] = Counter()
    dict_presence: DefaultDict[str, set[str]] = defaultdict(set)
    per_dict_counts: DefaultDict[str, Dict[str, int]] = defaultdict(dict)
    examples: DefaultDict[str, List[str]] = defaultdict(list)

    total_rows = 0
    total_head_surfaces = 0
    total_form_surfaces = 0

    for report in reports:
        total_rows += report.row_count
        total_head_surfaces += report.headword_surface_count
        total_form_surfaces += report.form_surface_count
        for ch, count in report.total_counts.items():
            total_counts[ch] += count
            headword_counts[ch] += report.headword_counts.get(ch, 0)
            form_counts[ch] += report.form_counts.get(ch, 0)
            dict_presence[ch].add(report.label)
            per_dict_counts[ch][report.label] = count
            for sample in report.examples.get(ch, []):
                tagged = f"{report.label}: {sample}"
                if tagged not in examples[ch] and len(examples[ch]) < 8:
                    examples[ch].append(tagged)

    rows = [
        ch for ch in total_counts
        if total_counts[ch] >= min_total
    ]
    rows.sort(key=lambda ch: (-total_counts[ch], _codepoint_label(ch)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# Combined Non-script Marks Inventory\n\n")
        out.write("- Source folder: `wiktionary general pipeline/converted_tsv`\n")
        out.write(f"- Dictionaries merged: {len(reports):,}\n")
        out.write("- Excluded from the batch: `dict-russian - Copy.tsv` (duplicate backup)\n")
        out.write(f"- Total TSV rows scanned: {total_rows:,}\n")
        out.write(f"- Total headword surfaces scanned: {total_head_surfaces:,}\n")
        out.write(f"- Total form surfaces scanned: {total_form_surfaces:,}\n")
        out.write("- Counted as junk: codepoints outside each dictionary's script family whose Unicode category starts with `P`, `S`, `Z`, `M`, or `C`\n")
        out.write("- Explicitly excluded from this pass: letters and decimal digits\n")
        out.write(f"- Included below only when global total >= {min_total}\n")
        out.write(f"- Distinct junk codepoints meeting threshold: {len(rows):,}\n")
        out.write(
            f"- Total junk-codepoint occurrences meeting threshold: "
            f"{sum(total_counts[ch] for ch in rows):,}\n\n"
        )
        out.write(
            "| Glyph | Codepoint | Total | Headword | Forms | Dicts | "
            "Category | Unicode name | Per-dictionary totals | Sample surfaces |\n"
        )
        out.write("| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |\n")

        for ch in rows:
            per_dict = "; ".join(
                f"{label}: {count:,}"
                for label, count in sorted(
                    per_dict_counts[ch].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            )
            sample_text = "; ".join(_md_escape(s) for s in examples[ch])
            out.write(
                f"| {_md_escape(_display_char(ch))} | `{_codepoint_label(ch)}` | "
                f"{total_counts[ch]:,} | {headword_counts[ch]:,} | {form_counts[ch]:,} | "
                f"{len(dict_presence[ch]):,} | `{unicodedata.category(ch)}` | "
                f"{_md_escape(unicodedata.name(ch, '<unnamed>'))} | {_md_escape(per_dict)} | {sample_text} |\n"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory out-of-script marks in headwords and forms.",
    )
    parser.add_argument(
        "--lang",
        help="Single registry language key or alias to scan.",
    )
    parser.add_argument(
        "--out",
        default="reports/headword_non_script_marks_ja.md",
        help="Single-report output path when --lang is used.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Scan every converted Wiktionary TSV and emit per-dictionary reports plus a master report.",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports/headword_non_script_marks",
        help="Per-dictionary output directory for --batch.",
    )
    parser.add_argument(
        "--master-out",
        default="reports/headword_non_script_marks_master.md",
        help="Master merged markdown output path for --batch.",
    )
    parser.add_argument(
        "--master-min-total",
        type=int,
        default=10,
        help="Only include master-report rows whose global total is at least this value.",
    )
    args = parser.parse_args()

    _set_csv_limit()

    if args.batch:
        reports_dir = (ROOT / args.reports_dir).resolve()
        specs = _build_batch_specs(reports_dir)
        reports: List[ReportData] = []
        for spec in specs:
            report = _scan_dictionary(spec)
            _write_report(report, spec.report_path)
            reports.append(report)
        _write_master_report(
            reports=reports,
            output_path=(ROOT / args.master_out).resolve(),
            min_total=max(1, int(args.master_min_total)),
        )
        return 0

    lang_key = _resolve_lang_key(args.lang or "ja")
    spec = _build_single_spec(lang_key, ROOT / args.out)
    report = _scan_dictionary(spec)
    _write_report(report, spec.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
