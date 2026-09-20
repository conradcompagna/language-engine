#!/usr/bin/env python3
"""
Postprocess per-DB flat form-tag reports into one global master list.

Reads existing `form_tags_flat.tsv` files only. It does not touch the SQLite
databases or rerun the audits.
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = APP_ROOT / "reports"
DEFAULT_INPUT_DIR = REPORTS_DIR / "sqlite_form_tags_flat_20260423"
MASTER_TSV_NAME = "MASTER_FORM_TAGS.tsv"
MASTER_MD_NAME = "MASTER_FORM_TAGS.md"
EXAMPLE_LIMIT = 10


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "").strip()).casefold()


def _safe_text(text: str) -> str:
    return str(text or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _iter_db_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir())


def _parse_examples(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [_safe_text(part) for part in text.split(" | ") if _safe_text(part)]


@dataclass
class TagAggregate:
    total_occurrence_count: int = 0
    db_counts: dict[str, int] = field(default_factory=dict)
    display_weight: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    examples_by_db: dict[str, list[str]] = field(default_factory=dict)

    def add(self, db: str, display: str, count: int, examples: list[str]) -> None:
        self.total_occurrence_count += count
        self.db_counts[db] = self.db_counts.get(db, 0) + count
        display_text = _safe_text(display)
        if display_text:
            self.display_weight[display_text] += count
        if examples:
            existing = self.examples_by_db.setdefault(db, [])
            seen = set(existing)
            for example in examples:
                if example in seen:
                    continue
                seen.add(example)
                existing.append(example)


def _choose_display(agg: TagAggregate, fallback_key: str) -> str:
    if not agg.display_weight:
        return fallback_key
    return max(
        agg.display_weight.items(),
        key=lambda item: (item[1], -len(item[0]), item[0].casefold()),
    )[0]


def _build_examples(agg: TagAggregate) -> str:
    chosen: list[str] = []
    seen: set[str] = set()
    db_order = sorted(
        agg.db_counts.items(),
        key=lambda item: (-item[1], item[0].casefold()),
    )
    for db, _count in db_order:
        for example in agg.examples_by_db.get(db, []):
            labeled = f"{db}: {example}"
            if labeled in seen:
                continue
            seen.add(labeled)
            chosen.append(labeled)
            break
        if len(chosen) >= EXAMPLE_LIMIT:
            break
    if len(chosen) < EXAMPLE_LIMIT:
        for db, _count in db_order:
            for example in agg.examples_by_db.get(db, []):
                labeled = f"{db}: {example}"
                if labeled in seen:
                    continue
                seen.add(labeled)
                chosen.append(labeled)
                if len(chosen) >= EXAMPLE_LIMIT:
                    break
            if len(chosen) >= EXAMPLE_LIMIT:
                break
    return " | ".join(chosen)


def _write_tsv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _write_md(path: Path, rows: list[dict[str, object]], source_dir: Path) -> None:
    lines = [
        "# Master Form Tags",
        "",
        f"Source folder: `{source_dir}`",
        "",
        "Aggregated from existing per-DB `form_tags_flat.tsv` files only.",
        "",
        "| Form Tag | Total Count | Sample Examples |",
        "| --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + str(row["form_tag"]).replace("|", "\\|")
            + " | "
            + f'{int(row["total_occurrence_count"]):,}'
            + " | "
            + str(row["sample_examples"]).replace("|", "\\|")
            + " |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_DIR),
        help="Existing flat tag report folder. Default: reports/sqlite_form_tags_flat_20260423",
    )
    args = parser.parse_args()

    root = Path(args.input_dir)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"input directory not found: {root}")

    aggregates: dict[str, TagAggregate] = {}

    for db_dir in _iter_db_dirs(root):
        db = db_dir.name
        tsv_path = db_dir / "form_tags_flat.tsv"
        if not tsv_path.exists():
            continue
        with tsv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                display = _safe_text(row.get("form_tag") or "")
                key = _fold(display)
                if not key:
                    continue
                count = int(str(row.get("occurrence_count") or "0").strip() or 0)
                examples = _parse_examples(row.get("sample_examples") or "")
                agg = aggregates.get(key)
                if agg is None:
                    agg = TagAggregate()
                    aggregates[key] = agg
                agg.add(db, display, count, examples)

    rows: list[dict[str, object]] = []
    for key, agg in aggregates.items():
        rows.append(
            {
                "form_tag": _choose_display(agg, key),
                "total_occurrence_count": agg.total_occurrence_count,
                "sample_examples": _build_examples(agg),
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row["total_occurrence_count"]),
            str(row["form_tag"] or "").casefold(),
        )
    )

    _write_tsv(
        root / MASTER_TSV_NAME,
        ["form_tag", "total_occurrence_count", "sample_examples"],
        rows,
    )
    _write_md(root / MASTER_MD_NAME, rows[:500], root)
    print(f"[master-form-tags] wrote {len(rows):,} aggregated tags -> {root / MASTER_TSV_NAME}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
