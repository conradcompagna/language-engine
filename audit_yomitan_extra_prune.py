#!/usr/bin/env python3
"""
One-off audit for proposed Yomitan-inspired SQLite form cuts and gloss redirects.

Outputs:
- per-dictionary rule counts
- max-100 deterministic sample rows per dictionary/rule
- per-dictionary TSVs for "gloss ends in of <existing headword>" collapses
- zip archive of the generated output folder
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable

from sqlite_prune_policy import parse_glosses


APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
REPORTS_DIR = APP_ROOT / "reports"

RULES = [
    "auxiliary_tag",
    "used_in_the_form_tag",
    "exact_headword",
    "edge_hyphen_form_only",
    "cross_script_non_romanization",
]

MAX_SAMPLES_PER_RULE = 100
CHUNK_SIZE = 10000

TAG_SPLIT_RE = re.compile(r"[;|,]")
SPACE_RE = re.compile(r"\s+")
OF_TARGET_RE = re.compile(r"(?i)\bof\s+(.+?)\s*$")
OF_OCCURRENCE_RE = re.compile(r"(?i)(?<![A-Za-z])of\s+")
EDGE_HYPHENS = ("-", "\u2010", "\u2011")
TRAILING_GLOSS_PUNCT = ".;:!?。！？؛؟"
TARGET_QUOTES = "\"'`“”‘’«»‹›"

EAST_ASIAN_DBS = {
    "ja",
    "ja-jmdict",
    "ko",
    "ko-krdict",
    "zh",
    "zh-cc-cedict",
    "zh-hant",
    "zh-hant-cc-cedict",
    "lzh",
    "lzh-wiktionary",
    "vi",
}

ROMANIZATION_TAGS = {
    "reading",
    "romanization",
    "romanisation",
    "transliteration",
    "romaji",
    "pinyin",
    "bopomofo",
    "jyutping",
    "kana",
    "hiragana",
    "katakana",
}

ROMANIZATION_TAG_NEEDLES = (
    "romanization",
    "romanisation",
    "transliteration",
    "reading",
    "romaji",
    "pinyin",
    "bopomofo",
    "jyutping",
)


def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _iter_rows(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    cur = conn.execute(sql, params)
    while True:
        rows = cur.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        for row in rows:
            yield row


def _write_tsv(path: Path, headers: list[str], rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _safe_cell(text: object) -> str:
    return SPACE_RE.sub(" ", str(text or "").replace("\t", " ").strip())


def _split_tags(raw_tags: object) -> set[str]:
    out: set[str] = set()
    for part in TAG_SPLIT_RE.split(str(raw_tags or "")):
        tag = unicodedata.normalize("NFKC", part.strip()).casefold()
        if tag:
            out.add(tag)
    return out


def _has_romanization_tag(tags: set[str]) -> bool:
    for tag in tags:
        if tag in ROMANIZATION_TAGS:
            return True
        if any(needle in tag for needle in ROMANIZATION_TAG_NEEDLES):
            return True
    return False


def _has_edge_hyphen(text: str) -> bool:
    s = str(text or "")
    return bool(s) and (s.startswith(EDGE_HYPHENS) or s.endswith(EDGE_HYPHENS))


def _char_script(ch: str) -> str:
    code = ord(ch)
    if 0x0041 <= code <= 0x024F or 0x1E00 <= code <= 0x1EFF or 0x2C60 <= code <= 0x2C7F or 0xA720 <= code <= 0xA7FF:
        return "Latin"
    if 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF:
        return "Greek"
    if 0x0400 <= code <= 0x052F or 0x2DE0 <= code <= 0x2DFF or 0xA640 <= code <= 0xA69F or 0x1C80 <= code <= 0x1C8F:
        return "Cyrillic"
    if 0x0590 <= code <= 0x05FF or 0xFB1D <= code <= 0xFB4F:
        return "Hebrew"
    if 0x0530 <= code <= 0x058F or 0xFB13 <= code <= 0xFB17:
        return "Armenian"
    if (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0x0870 <= code <= 0x089F
        or 0x08A0 <= code <= 0x08FF
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    ):
        return "Arabic"
    if 0x0900 <= code <= 0x097F:
        return "Devanagari"
    if 0x0980 <= code <= 0x09FF:
        return "Bengali"
    if 0x0A00 <= code <= 0x0A7F:
        return "Gurmukhi"
    if 0x0B80 <= code <= 0x0BFF:
        return "Tamil"
    if 0x0E00 <= code <= 0x0E7F:
        return "Thai"
    if 0x3040 <= code <= 0x309F:
        return "Hiragana"
    if 0x30A0 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF:
        return "Katakana"
    if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
        return "Hangul"
    if (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2CEB0 <= code <= 0x2EBEF
        or 0x30000 <= code <= 0x3134F
    ):
        return "Han"
    return "Other"


def _scripts(text: str) -> set[str]:
    out: set[str] = set()
    for ch in str(text or ""):
        if unicodedata.category(ch).startswith("L"):
            script = _char_script(ch)
            if script != "Other":
                out.add(script)
    return out


def _is_cross_script(db_name: str, headword: str, form_text: str, tags: set[str]) -> bool:
    if db_name.casefold() in EAST_ASIAN_DBS:
        return False
    if _has_romanization_tag(tags):
        return False
    head_scripts = _scripts(headword)
    form_scripts = _scripts(form_text)
    return bool(head_scripts and form_scripts and head_scripts.isdisjoint(form_scripts))


def _matching_rules(db_name: str, headword: str, form_text: str, raw_tags: str) -> list[str]:
    tags = _split_tags(raw_tags)
    rules: list[str] = []
    if "auxiliary" in tags or "auxilliary" in tags:
        rules.append("auxiliary_tag")
    if "used-in-the-form" in tags or "used in the form" in tags:
        rules.append("used_in_the_form_tag")
    if form_text == headword:
        rules.append("exact_headword")
    if _has_edge_hyphen(form_text) and not _has_edge_hyphen(headword):
        rules.append("edge_hyphen_form_only")
    if _is_cross_script(db_name, headword, form_text, tags):
        rules.append("cross_script_non_romanization")
    return rules


def _add_sample(samples: dict[str, list[dict[str, object]]], counts: dict[str, int], rule: str, sample: dict[str, object], rng: random.Random) -> None:
    count = counts[rule]
    bucket = samples[rule]
    if len(bucket) < MAX_SAMPLES_PER_RULE:
        bucket.append(sample)
        return
    idx = rng.randrange(count)
    if idx < MAX_SAMPLES_PER_RULE:
        bucket[idx] = sample


def _clean_target_candidate(text: str) -> str:
    return (
        str(text or "")
        .strip()
        .strip(TARGET_QUOTES)
        .strip()
        .rstrip(TRAILING_GLOSS_PUNCT)
        .strip()
        .strip(TARGET_QUOTES)
        .strip()
    )


def _is_target_boundary(ch: str) -> bool:
    if not ch:
        return True
    if ch.isspace():
        return True
    cat = unicodedata.category(ch)
    if cat[0] in {"P", "S", "Z"}:
        return True
    return False


def _extract_of_suffix_target(gloss: str, headwords: set[str]) -> list[str]:
    text = SPACE_RE.sub(" ", str(gloss or "").strip())
    if not text:
        return []
    text = text.rstrip(TRAILING_GLOSS_PUNCT).strip()
    match = OF_TARGET_RE.search(text)
    if not match:
        return []
    target = _clean_target_candidate(match.group(1))
    if target in headwords:
        return [target]
    return []


def _extract_of_contains_targets(gloss: str, headwords: set[str], *, max_scan_chars: int = 180) -> list[str]:
    text = SPACE_RE.sub(" ", str(gloss or "").strip())
    if not text:
        return []
    targets: list[str] = []
    seen: set[str] = set()
    for match in OF_OCCURRENCE_RE.finditer(text):
        tail = text[match.end():].lstrip()
        while tail[:1] in TARGET_QUOTES:
            tail = tail[1:].lstrip()
        if not tail:
            continue
        limit = min(len(tail), max_scan_chars)
        for end in range(1, limit + 1):
            next_ch = tail[end:end + 1]
            if next_ch and not _is_target_boundary(next_ch):
                continue
            candidate = _clean_target_candidate(tail[:end])
            if not candidate or candidate in seen:
                continue
            if candidate in headwords:
                seen.add(candidate)
                targets.append(candidate)
    return targets


def _load_headwords(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row["headword"] or "")
        for row in _iter_rows(conn, "SELECT headword FROM entries WHERE headword IS NOT NULL AND headword != ''")
    }


def audit_forms(db_path: Path, out_dir: Path) -> dict[str, int | str]:
    db_name = db_path.stem
    conn = _open_db(db_path)
    rng = random.Random(f"form-samples:{db_name}")
    counts = {rule: 0 for rule in RULES}
    samples = {rule: [] for rule in RULES}
    union_cut = 0
    total_forms = 0

    sql = """
        SELECT f.id AS form_id,
               f.entry_id AS entry_id,
               e.headword AS headword,
               f.form_text AS form_text,
               f.morph_tags AS morph_tags
        FROM forms f
        JOIN entries e ON e.id = f.entry_id
        ORDER BY f.id
    """
    for row in _iter_rows(conn, sql):
        total_forms += 1
        headword = str(row["headword"] or "")
        form_text = str(row["form_text"] or "")
        morph_tags = str(row["morph_tags"] or "")
        matched = _matching_rules(db_name, headword, form_text, morph_tags)
        if not matched:
            continue
        union_cut += 1
        sample = {
            "entry_id": int(row["entry_id"] or 0),
            "form_id": int(row["form_id"] or 0),
            "headword": _safe_cell(headword),
            "form_text": _safe_cell(form_text),
            "form_tags": _safe_cell(morph_tags),
        }
        for rule in matched:
            counts[rule] += 1
            _add_sample(samples, counts, rule, sample, rng)

    sample_dir = out_dir / "form_cut_samples" / db_name
    for rule in RULES:
        if not samples[rule]:
            continue
        _write_tsv(
            sample_dir / f"{rule}.tsv",
            ["entry_id", "form_id", "headword", "form_text", "form_tags"],
            samples[rule],
        )

    row_out: dict[str, int | str] = {
        "dictionary": db_name,
        "total_form_rows": total_forms,
        "union_cut_rows": union_cut,
    }
    row_out.update(counts)
    return row_out


def audit_collapses(db_path: Path, out_dir: Path, *, mode: str = "suffix") -> dict[str, int | str]:
    db_name = db_path.stem
    conn = _open_db(db_path)
    headwords = _load_headwords(conn)
    collapse_dir_name = "gloss_of_collapses" if mode == "suffix" else "gloss_of_contains_collapses"
    collapse_path = out_dir / collapse_dir_name / f"{db_name}.tsv"
    collapse_path.parent.mkdir(parents=True, exist_ok=True)
    collapse_count = 0
    total_entries = 0

    sql = """
        SELECT id, headword, glosses
        FROM entries
        WHERE headword IS NOT NULL AND headword != ''
        ORDER BY id
    """
    with collapse_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["original_headword", "gloss", "redirected_headword"],
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in _iter_rows(conn, sql):
            total_entries += 1
            original = str(row["headword"] or "")
            glosses, _parse_error = parse_glosses(str(row["glosses"] or ""))
            for gloss in glosses:
                if mode == "contains":
                    targets = _extract_of_contains_targets(gloss, headwords)
                else:
                    targets = _extract_of_suffix_target(gloss, headwords)
                for target in targets:
                    if not target or target == original:
                        continue
                    writer.writerow(
                        {
                            "original_headword": _safe_cell(original),
                            "gloss": _safe_cell(gloss),
                            "redirected_headword": _safe_cell(target),
                        }
                    )
                    collapse_count += 1

    return {
        "dictionary": db_name,
        "total_entries": total_entries,
        "collapse_rows": collapse_count,
    }


def write_readme(out_dir: Path, db_count: int, *, collapse_mode: str = "suffix", collapse_only: bool = False) -> None:
    collapse_dir_name = "gloss_of_collapses" if collapse_mode == "suffix" else "gloss_of_contains_collapses"
    collapse_rule = (
        "gloss ends with `of <headword>`"
        if collapse_mode == "suffix"
        else "gloss contains any occurrence of `of <headword>`"
    )
    readme = f"""# Yomitan Extra Prune Audit

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

Scanned SQLite dictionaries: {db_count}

Collapse mode: `{collapse_mode}` ({collapse_rule})

## Form Cut Rules

- `auxiliary_tag`: form tag set contains `auxiliary` or misspelled `auxilliary`.
- `used_in_the_form_tag`: form tag set contains `used-in-the-form` or `used in the form`.
- `exact_headword`: `forms.form_text` is literally identical to `entries.headword`; no normalization is applied.
- `edge_hyphen_form_only`: form text starts or ends with `-`, U+2010, or U+2011, while the headword does not.
- `cross_script_non_romanization`: form and headword have disjoint writing-script sets, excluding romanization/reading/transliteration-tagged rows and East Asian DBs.

East Asian DBs excluded from cross-script cuts: {', '.join(sorted(EAST_ASIAN_DBS))}

## Files

- `form_cut_counts_by_dictionary.tsv`: per-dictionary raw rule counts plus deduped union count.
- `form_cut_counts_overall.tsv`: overall raw rule counts plus deduped union count.
- `form_cut_samples/<dictionary>/<rule>.tsv`: deterministic reservoir samples, max 100 rows per dictionary/rule.
- `gloss_of_collapse_counts_by_dictionary.tsv`: count of gloss-ending redirects per dictionary.
- `{collapse_dir_name}/<dictionary>.tsv`: exactly three columns: original headword, gloss, redirected headword.

Counts are raw SQLite form-row matches for these proposed rules, not incremental-over-current-prune counts.
"""
    if collapse_only:
        readme += "\nThis run was collapse-only, so form-cut count/sample files are intentionally absent.\n"
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def zip_dir(out_dir: Path) -> Path:
    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))
    return zip_path


def discover_db_paths(selected: list[str]) -> list[Path]:
    dbs = sorted(path for path in SQLITE_DIR.glob("*.sqlite") if path.stat().st_size > 0)
    if not selected:
        return dbs
    wanted = {item.strip().casefold() for item in selected if item.strip()}
    return [path for path in dbs if path.stem.casefold() in wanted or path.name.casefold() in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="Output directory. Default: reports/yomitan_extra_prune_audit_<timestamp>")
    parser.add_argument("--db", action="append", default=[], help="Limit to a dictionary stem or sqlite filename. Repeatable.")
    parser.add_argument("--collapse-mode", choices=["suffix", "contains"], default="suffix", help="Gloss collapse rule to audit.")
    parser.add_argument("--collapse-only", action="store_true", help="Only run the gloss collapse audit, not form cut counts/samples.")
    args = parser.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else REPORTS_DIR / f"yomitan_extra_prune_audit_{stamp}"
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    db_paths = discover_db_paths(args.db)
    form_rows: list[dict[str, int | str]] = []
    collapse_rows: list[dict[str, int | str]] = []

    for idx, db_path in enumerate(db_paths, start=1):
        if not args.collapse_only:
            print(f"[{idx}/{len(db_paths)}] {db_path.name}: form cuts", flush=True)
            form_rows.append(audit_forms(db_path, out_dir))
        print(f"[{idx}/{len(db_paths)}] {db_path.name}: gloss collapses ({args.collapse_mode})", flush=True)
        collapse_rows.append(audit_collapses(db_path, out_dir, mode=args.collapse_mode))

    if not args.collapse_only:
        _write_tsv(
            out_dir / "form_cut_counts_by_dictionary.tsv",
            ["dictionary", "total_form_rows", "union_cut_rows", *RULES],
            form_rows,
        )
        overall = {"dictionary": "OVERALL"}
        for key in ["total_form_rows", "union_cut_rows", *RULES]:
            overall[key] = sum(int(row.get(key, 0) or 0) for row in form_rows)
        _write_tsv(
            out_dir / "form_cut_counts_overall.tsv",
            ["dictionary", "total_form_rows", "union_cut_rows", *RULES],
            [overall],
        )

    _write_tsv(
        out_dir / "gloss_of_collapse_counts_by_dictionary.tsv",
        ["dictionary", "total_entries", "collapse_rows"],
        collapse_rows,
    )
    collapse_overall = {
        "dictionary": "OVERALL",
        "total_entries": sum(int(row.get("total_entries", 0) or 0) for row in collapse_rows),
        "collapse_rows": sum(int(row.get("collapse_rows", 0) or 0) for row in collapse_rows),
    }
    _write_tsv(
        out_dir / "gloss_of_collapse_counts_overall.tsv",
        ["dictionary", "total_entries", "collapse_rows"],
        [collapse_overall],
    )

    write_readme(out_dir, len(db_paths), collapse_mode=args.collapse_mode, collapse_only=args.collapse_only)
    zip_path = zip_dir(out_dir)
    print(json.dumps({"out_dir": str(out_dir), "zip_path": str(zip_path)}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
