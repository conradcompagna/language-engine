#!/usr/bin/env python3
"""
Analyze words and template phrases in generated "of <headword>" collapse TSVs.

Input defaults to the broad contains-collapse audit:
reports/yomitan_contains_of_collapse_audit_20260424/gloss_of_contains_collapses

The script builds one concatenated corpus across all DBs, masks the original
and redirected headwords, strips parenthetical tails for template-word counts,
then marks tokens that exactly match the observed SQLite Wiktionary form-tag
inventory.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import zipfile
from collections import Counter
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = APP_ROOT / "reports"
DEFAULT_COLLAPSE_DIR = REPORTS_DIR / "yomitan_contains_of_collapse_audit_20260424" / "gloss_of_contains_collapses"
DEFAULT_TAGS_TSV = REPORTS_DIR / "sqlite_form_tags_flat_20260423" / "MASTER_FORM_TAGS.tsv"

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*")
OF_RE = re.compile(r"\bof\b", re.IGNORECASE)
PAREN_RE = re.compile(r"\([^()]*\)")
BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
SPACE_RE = re.compile(r"\s+")

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _read_tag_inventory(path: Path) -> tuple[set[str], dict[str, int]]:
    tag_set: set[str] = set()
    counts: dict[str, int] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            tag = str(row.get("form_tag") or "").strip().casefold()
            if not tag:
                continue
            tag_set.add(tag)
            try:
                counts[tag] = int(row.get("total_occurrence_count") or 0)
            except Exception:
                counts[tag] = 0
    return tag_set, counts


def _iter_collapse_rows(collapse_dir: Path):
    for path in sorted(collapse_dir.glob("*.tsv")):
        db_name = path.stem
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                yield db_name, row


def _mask_literal(text: str, literal: str) -> str:
    literal = str(literal or "").strip()
    if not literal:
        return text
    return re.sub(re.escape(literal), " ", text, flags=re.IGNORECASE)


def _clean_template_text(gloss: str, original: str, target: str) -> str:
    text = str(gloss or "")
    text = _mask_literal(text, original)
    text = _mask_literal(text, target)
    text = PAREN_RE.sub(" ", text)
    text = BRACKET_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def _tokens(text: str) -> list[str]:
    return [m.group(0).casefold().strip("'") for m in TOKEN_RE.finditer(text) if m.group(0).strip("'")]


def _prefix_tokens_before_of(gloss: str, target: str) -> list[str]:
    text = str(gloss or "")
    target = str(target or "").strip()
    match = None
    if target:
        match = re.search(r"\bof\s+" + re.escape(target) + r"(?=\s|$|[^\w])", text, flags=re.IGNORECASE)
    if match is None:
        match = OF_RE.search(text)
    if match is None:
        return []
    left = text[: match.start()]
    left = PAREN_RE.sub(" ", left)
    left = BRACKET_RE.sub(" ", left)
    toks = _tokens(left)
    return toks[-8:]


def _tag_words(tokens: list[str], tag_set: set[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in tag_set and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _counter_rows(counter: Counter[str], tag_set: set[str], tag_counts: dict[str, int], *, limit: int = 0) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    items = counter.most_common(limit or None)
    for text, count in items:
        key = text.casefold()
        toks = key.split()
        tag_words = _tag_words(toks, tag_set)
        rows.append(
            {
                "text": text,
                "count": count,
                "is_exact_form_tag": "yes" if key in tag_set else "",
                "form_tag_occurrence_count": tag_counts.get(key, ""),
                "contains_form_tag_words": ";".join(tag_words),
            }
        )
    return rows


def _zip_dir(out_dir: Path) -> Path:
    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collapse-dir", default=str(DEFAULT_COLLAPSE_DIR))
    parser.add_argument("--tags-tsv", default=str(DEFAULT_TAGS_TSV))
    parser.add_argument("--out", default="")
    parser.add_argument("--max-ngram", type=int, default=4)
    args = parser.parse_args()

    collapse_dir = Path(args.collapse_dir)
    tags_tsv = Path(args.tags_tsv)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out else REPORTS_DIR / f"yomitan_contains_of_gloss_word_audit_{stamp}"
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    tag_set, tag_counts = _read_tag_inventory(tags_tsv)
    word_counts: Counter[str] = Counter()
    content_word_counts: Counter[str] = Counter()
    tag_word_counts: Counter[str] = Counter()
    prefix_phrase_counts: Counter[str] = Counter()
    ngram_counts: dict[int, Counter[str]] = {n: Counter() for n in range(2, max(2, args.max_ngram) + 1)}
    db_row_counts: Counter[str] = Counter()
    total_rows = 0

    for db_name, row in _iter_collapse_rows(collapse_dir):
        total_rows += 1
        db_row_counts[db_name] += 1
        gloss = str(row.get("gloss") or "")
        original = str(row.get("original_headword") or "")
        target = str(row.get("redirected_headword") or "")
        clean = _clean_template_text(gloss, original, target)
        toks = _tokens(clean)
        word_counts.update(toks)
        content_word_counts.update(tok for tok in toks if tok not in STOPWORDS)
        for tok in toks:
            if tok in tag_set:
                tag_word_counts[tok] += 1
        for n, counter in ngram_counts.items():
            if len(toks) >= n:
                counter.update(" ".join(toks[i:i + n]) for i in range(0, len(toks) - n + 1))
        prefix = _prefix_tokens_before_of(gloss, target)
        if prefix:
            prefix_phrase_counts[" ".join(prefix)] += 1

    word_rows = _counter_rows(word_counts, tag_set, tag_counts)
    # Rename first column for the principal file.
    for row in word_rows:
        row["word"] = row.pop("text")
    _write_tsv(
        out_dir / "word_frequencies.tsv",
        ["word", "count", "is_exact_form_tag", "form_tag_occurrence_count", "contains_form_tag_words"],
        word_rows,
    )

    content_rows = _counter_rows(content_word_counts, tag_set, tag_counts)
    for row in content_rows:
        row["word"] = row.pop("text")
    _write_tsv(
        out_dir / "content_word_frequencies.tsv",
        ["word", "count", "is_exact_form_tag", "form_tag_occurrence_count", "contains_form_tag_words"],
        content_rows,
    )

    tag_rows = _counter_rows(tag_word_counts, tag_set, tag_counts)
    for row in tag_rows:
        row["word"] = row.pop("text")
    _write_tsv(
        out_dir / "form_tag_word_frequencies.tsv",
        ["word", "count", "is_exact_form_tag", "form_tag_occurrence_count", "contains_form_tag_words"],
        tag_rows,
    )

    _write_tsv(
        out_dir / "prefix_phrase_before_of_frequencies.tsv",
        ["text", "count", "is_exact_form_tag", "form_tag_occurrence_count", "contains_form_tag_words"],
        _counter_rows(prefix_phrase_counts, tag_set, tag_counts),
    )

    for n, counter in ngram_counts.items():
        _write_tsv(
            out_dir / f"{n}gram_frequencies.tsv",
            ["text", "count", "is_exact_form_tag", "form_tag_occurrence_count", "contains_form_tag_words"],
            _counter_rows(counter, tag_set, tag_counts),
        )

    db_rows = [{"dictionary": db, "collapse_rows": count} for db, count in sorted(db_row_counts.items())]
    _write_tsv(out_dir / "input_rows_by_dictionary.tsv", ["dictionary", "collapse_rows"], db_rows)

    top_words = word_rows[:50]
    top_content = content_rows[:50]
    top_tags = tag_rows[:50]
    top_prefixes = _counter_rows(prefix_phrase_counts, tag_set, tag_counts, limit=50)
    summary = {
        "input_collapse_dir": str(collapse_dir),
        "tag_inventory": str(tags_tsv),
        "total_collapse_rows": total_rows,
        "distinct_words": len(word_counts),
        "distinct_form_tag_words_seen": len(tag_word_counts),
        "top_words": top_words[:25],
        "top_content_words": top_content[:25],
        "top_form_tag_words": top_tags[:25],
        "top_prefix_phrases_before_of": top_prefixes[:25],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Gloss Word/Tag Audit",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input collapse rows: {total_rows:,}",
        f"Distinct words after masking targets/parentheticals: {len(word_counts):,}",
        f"Distinct exact form-tag words seen: {len(tag_word_counts):,}",
        "",
        "## Files",
        "",
        "- `word_frequencies.tsv`: all words in the cleaned concatenated gloss corpus.",
        "- `content_word_frequencies.tsv`: same, with small English stopwords removed.",
        "- `form_tag_word_frequencies.tsv`: only words that exactly match an observed form tag.",
        "- `prefix_phrase_before_of_frequencies.tsv`: up to eight tokens before the matched `of <headword>` phrase.",
        "- `2gram_frequencies.tsv` through `4gram_frequencies.tsv`: phrase frequencies in cleaned gloss text.",
        "- `summary.json`: top slices for quick inspection.",
        "",
        "## Top Content Words",
        "",
    ]
    for row in top_content[:40]:
        marker = " [FORM_TAG]" if row["is_exact_form_tag"] else ""
        lines.append(f"- {row['word']}: {row['count']}{marker}")
    lines.extend(["", "## Top Form-Tag Words In Glosses", ""])
    for row in top_tags[:40]:
        lines.append(f"- {row['word']}: {row['count']} (tag rows: {row['form_tag_occurrence_count']})")
    lines.extend(["", "## Top Prefix Phrases Before `of`", ""])
    for row in top_prefixes[:40]:
        tag_words = f" [tags: {row['contains_form_tag_words']}]" if row["contains_form_tag_words"] else ""
        lines.append(f"- {row['text']}: {row['count']}{tag_words}")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = _zip_dir(out_dir)
    print(json.dumps({"out_dir": str(out_dir), "zip_path": str(zip_path), "total_rows": total_rows}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
