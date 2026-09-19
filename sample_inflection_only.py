#!/usr/bin/env python3
"""Resample 100 fresh balanced rows for the pure inflectional-morphology tags
and report bad-target rates."""
from __future__ import annotations
import csv, random, re, sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports" / "synthetic_collapses"

INFLECTIONAL = [
    # number
    "singular", "plural", "dual",
    # case
    "nominative", "accusative", "dative", "genitive", "vocative", "ablative",
    "locative", "instrumental", "prepositional", "partitive", "oblique",
    # gender
    "masculine", "feminine", "neuter",
    # person
    "first-person", "second-person", "third-person",
    # tense
    "present", "past", "future", "imperfect", "perfect", "pluperfect",
    "preterite", "aorist",
    # aspect
    "perfective", "imperfective", "progressive", "continuative", "habitual",
    "contemplative", "prospective",
    # mood
    "indicative", "subjunctive", "conditional", "imperative",
    # non-finite
    "infinitive", "gerund", "participle", "supine", "optative",
    # voice
    "active", "passive", "mediopassive", "reflexive", "causative", "agentive",
    # other inflectional
    "definite", "indefinite", "possessive", "comparative", "superlative",
    "augmentative", "diminutive", "inflection", "inflected",
]

ARTICLE_BLACKLIST = {
    "a","an","the","of","in","at","on","by","to","with","for","and","or","is",
    "as","be","was","were","been","this","that","these","those","his","her",
    "its","their","de","da","du","del","el","la","le","les","los","las","das",
    "der","den","dem","du","uw","an","ar","of"
}

SAMPLES = 100
random.seed(42)  # fresh seed for new sample

def main() -> int:
    by_tag_db: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    csv.field_size_limit(2**31 - 1)
    for csv_path in sorted(REPORT_DIR.glob("*_collapses.csv")):
        db = csv_path.stem.replace("_collapses", "")
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                tags_field = row.get("trigger_tags") or ""
                tags = {t.strip().lower() for t in tags_field.split(";") if t.strip()}
                donor = row.get("collapsed_headword") or ""
                target = row.get("destination_headword") or ""
                gloss = row.get("gloss") or ""
                for tag in tags:
                    if tag in INFLECTIONAL:
                        by_tag_db[tag][db].append((donor, target, gloss, tags_field))

    out_path = REPORT_DIR / "_inflection_samples.txt"
    summary_path = REPORT_DIR / "_inflection_badrate.txt"
    sum_lines = []
    with out_path.open("w", encoding="utf-8") as fh:
        for tag in INFLECTIONAL:
            db_buckets = by_tag_db.get(tag, {})
            if not db_buckets:
                continue
            total = sum(len(v) for v in db_buckets.values())
            queues = {db: deque(random.sample(rows, len(rows))) for db, rows in db_buckets.items()}
            db_order = sorted(queues.keys()); random.shuffle(db_order)
            picked = []
            while len(picked) < SAMPLES and any(queues[d] for d in db_order):
                for db in db_order:
                    if queues[db]:
                        picked.append((db, queues[db].popleft()))
                        if len(picked) >= SAMPLES: break
            n_dbs = len({d for d, _ in picked})
            bad = sum(1 for _, (_, target, _, _) in picked if target.lower() in ARTICLE_BLACKLIST)
            fh.write(f"\n========== TAG: {tag}  (total: {total}, sampled: {len(picked)}, dbs: {n_dbs}, article-bad: {bad}/{len(picked)})  ==========\n")
            for db, (donor, target, gloss, tags_field) in picked:
                gloss_short = gloss if len(gloss) <= 200 else gloss[:197] + "…"
                fh.write(f"[{db}] {donor!r} -> {target!r} | tags={tags_field} | {gloss_short}\n")
            sum_lines.append((tag, len(picked), bad, total))
    with summary_path.open("w", encoding="utf-8") as fh:
        fh.write("tag                  sampled  article-bad  bad%   total\n")
        for tag, sampled, bad, total in sorted(sum_lines, key=lambda r: -r[2]):
            pct = 100*bad/sampled if sampled else 0
            fh.write(f"{tag:20s} {sampled:7d}  {bad:11d}  {pct:4.1f}%  {total:6d}\n")
    print(f"Wrote {out_path}")
    print(f"Wrote {summary_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
