#!/usr/bin/env python3
"""For each trigger tag, sample 100 collapse rows whose trigger_tags column
includes that tag, balanced across as many DBs as possible (round-robin from a
shuffled per-DB queue)."""
from __future__ import annotations
import csv, random, sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sqlite_prune_policy import SYNTHETIC_COLLAPSE_TRIGGERS  # noqa

REPORT_DIR = ROOT / "reports" / "synthetic_collapses"
SAMPLES = 100
random.seed(0)

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
                    if tag in SYNTHETIC_COLLAPSE_TRIGGERS:
                        by_tag_db[tag][db].append((donor, target, gloss, tags_field))

    out_path = REPORT_DIR / "_balanced_samples_by_tag.txt"
    with out_path.open("w", encoding="utf-8") as fh:
        for tag in sorted(by_tag_db.keys()):
            db_buckets = by_tag_db[tag]
            total = sum(len(v) for v in db_buckets.values())
            queues: dict[str, deque] = {}
            for db, rows in db_buckets.items():
                shuffled = rows[:]
                random.shuffle(shuffled)
                queues[db] = deque(shuffled)
            db_order = sorted(queues.keys())
            random.shuffle(db_order)
            picked: list[tuple[str, tuple]] = []
            while len(picked) < SAMPLES and any(queues[d] for d in db_order):
                for db in db_order:
                    if not queues[db]:
                        continue
                    picked.append((db, queues[db].popleft()))
                    if len(picked) >= SAMPLES:
                        break
            n_dbs = len({db for db, _ in picked})
            fh.write(f"\n========== TAG: {tag}  (total: {total}, sampled: {len(picked)}, dbs: {n_dbs})  ==========\n")
            for db, (donor, target, gloss, tags_field) in picked:
                gloss_short = gloss if len(gloss) <= 200 else gloss[:197] + "…"
                fh.write(f"[{db}] {donor!r} -> {target!r} | tags={tags_field} | {gloss_short}\n")
    print(f"Wrote {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
