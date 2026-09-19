#!/usr/bin/env python3
"""For each trigger word in SYNTHETIC_COLLAPSE_TRIGGERS, sample up to N collapse
rows whose gloss contains that word. Writes one section per tag into
reports/synthetic_collapses/_samples_by_tag.txt for review.
"""

from __future__ import annotations

import csv
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sqlite_prune_policy import SYNTHETIC_COLLAPSE_TRIGGERS  # noqa: E402

REPORT_DIR = ROOT / "reports" / "synthetic_collapses"
SAMPLES_PER_TAG = 100
random.seed(0)

WORD_RE_CACHE: dict[str, re.Pattern] = {}


def gloss_has_tag(gloss: str, tag: str) -> bool:
    pat = WORD_RE_CACHE.get(tag)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(tag)}\b", re.IGNORECASE)
        WORD_RE_CACHE[tag] = pat
    return bool(pat.search(gloss))


def main() -> int:
    by_tag: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    csv.field_size_limit(2**31 - 1)
    for csv_path in sorted(REPORT_DIR.glob("*_collapses.csv")):
        db_name = csv_path.stem.replace("_collapses", "")
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                gloss = row.get("gloss") or ""
                if not gloss:
                    continue
                donor = row.get("collapsed_headword") or ""
                target = row.get("destination_headword") or ""
                for tag in SYNTHETIC_COLLAPSE_TRIGGERS:
                    if gloss_has_tag(gloss, tag):
                        by_tag[tag].append((db_name, donor, target, gloss))

    out_path = REPORT_DIR / "_samples_by_tag.txt"
    with out_path.open("w", encoding="utf-8") as fh:
        for tag in sorted(SYNTHETIC_COLLAPSE_TRIGGERS):
            samples = by_tag.get(tag) or []
            total = len(samples)
            if total > SAMPLES_PER_TAG:
                picked = random.sample(samples, SAMPLES_PER_TAG)
            else:
                picked = samples
            fh.write(f"\n========== TAG: {tag}  (total hits: {total})  ==========\n")
            for db, donor, target, gloss in picked:
                fh.write(f"[{db}] {donor!r} -> {target!r}: {gloss}\n")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
