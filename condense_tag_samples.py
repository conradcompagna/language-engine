#!/usr/bin/env python3
"""Condensed by-tag report: 10 representative samples per tag, ordered by the
user's original frequency list."""
from __future__ import annotations
import csv, random, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sqlite_prune_policy import SYNTHETIC_COLLAPSE_TRIGGERS  # noqa

REPORT_DIR = ROOT / "reports" / "synthetic_collapses"
SAMPLES = 10
random.seed(0)

# Frequency order from the user's master list (high → low). Only tags currently
# in SYNTHETIC_COLLAPSE_TRIGGERS are kept.
FREQ_ORDER = [
    "plural","inflection","singular","second-person","indicative","third-person",
    "imperfect","subjunctive","first-person","future","present","feminine",
    "conditional","past","masculine","gerund","form","genitive","preterite",
    "accusative","infinitive","historic","neuter","participle","dative",
    "alternative","nominative","compound","imperative","strong","vocative",
    "spelling","pluperfect","voseo","ablative","mixed","superlative","comparative",
    "synonym","active","diminutive","transcription","hanja","dependent","brazilian",
    "obsolete","variant","passive","abbreviation","instrumental","aorist",
    "prepositional","possessive","initialism","imperfective","noun","standard",
    "misspelling","erhua","dual","direct","mediopassive","oblique","perfective",
    "locative","optative","middle","clipping","reflexive","analytic","negative",
    "perfect","apocopic","baybayin","traditional","ellipsis","contraction",
    "indirect","archaic","partitive","defective","nonstandard","weak","agent",
    "contracted","short","adverbial","agentive","prospective","stem","conjunctive",
    "augmentative","dated","familiar","inflected","rare","causative","personal",
    "relative","pronoun","class","euphemistic","habitual","reading","informal",
    "ulster","supine","emphatic","contemplative","dialectal","epic","colloquial",
    "common","western","southern","absolute","lesbian","uncommon","cretan",
    "adverb","ionic","munster","misconstruction","pronominal","medieval",
    "adjectival","gyeongsang","formal","polite","doric","jeolla","attic",
    "katharevousa","shinjitai","suffix",
]

word_re_cache: dict[str, re.Pattern] = {}
def gloss_has(gloss: str, tag: str) -> bool:
    pat = word_re_cache.get(tag)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(tag)}\b", re.IGNORECASE)
        word_re_cache[tag] = pat
    return bool(pat.search(gloss))

def main() -> int:
    by_tag: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    csv.field_size_limit(2**31 - 1)
    for csv_path in sorted(REPORT_DIR.glob("*_collapses.csv")):
        db = csv_path.stem.replace("_collapses", "")
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                gloss = row.get("gloss") or ""
                if not gloss:
                    continue
                donor = row.get("collapsed_headword") or ""
                target = row.get("destination_headword") or ""
                for tag in SYNTHETIC_COLLAPSE_TRIGGERS:
                    if gloss_has(gloss, tag):
                        by_tag[tag].append((db, donor, target, gloss))

    out_path = REPORT_DIR / "TAG_SAMPLES_BY_FREQUENCY.md"
    seen: set[str] = set()
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("# Collapse samples by trigger tag (frequency-ordered)\n\n")
        fh.write(f"10 representative donor → target collapses per tag, drawn from `reports/synthetic_collapses/*_collapses.csv`. Ordered by the user's master frequency list.\n\n")
        for tag in FREQ_ORDER:
            if tag not in SYNTHETIC_COLLAPSE_TRIGGERS:
                continue
            seen.add(tag)
            samples = by_tag.get(tag) or []
            total = len(samples)
            picked = random.sample(samples, SAMPLES) if total > SAMPLES else samples
            fh.write(f"## `{tag}` — {total:,} hits\n\n")
            for db, donor, target, gloss in picked:
                gloss_short = gloss if len(gloss) <= 160 else gloss[:157] + "…"
                fh.write(f"- `[{db}]` **{donor}** → **{target}** — {gloss_short}\n")
            fh.write("\n")
        leftover = sorted(t for t in SYNTHETIC_COLLAPSE_TRIGGERS if t not in seen)
        if leftover:
            fh.write("## Tags not in the user's frequency list\n\n")
            for tag in leftover:
                samples = by_tag.get(tag) or []
                total = len(samples)
                picked = random.sample(samples, SAMPLES) if total > SAMPLES else samples
                fh.write(f"### `{tag}` — {total:,} hits\n\n")
                for db, donor, target, gloss in picked:
                    gloss_short = gloss if len(gloss) <= 160 else gloss[:157] + "…"
                    fh.write(f"- `[{db}]` **{donor}** → **{target}** — {gloss_short}\n")
                fh.write("\n")
    print(f"Wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
