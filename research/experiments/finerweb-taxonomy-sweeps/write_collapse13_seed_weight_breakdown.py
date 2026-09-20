from __future__ import annotations

import csv
import re
from pathlib import Path

from expand_collapse13_seed_taxonomy_coherence_gate import RAW_SEEDS


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "collapse13_seed_coherence_expansion"
TSV_OUT = OUT_DIR / "collapse13_seed_bucket_weight_breakdown.tsv"
MD_OUT = OUT_DIR / "collapse13_seed_bucket_weight_breakdown.md"

ITEM_RE = re.compile(r"^\s*(.+?)\s*\((\d+)\)\s*$")


def parse_items(raw: str) -> list[tuple[str, int]]:
    items = []
    for piece in raw.replace("\n", " ").split(";"):
        value = piece.strip()
        if not value:
            continue
        match = ITEM_RE.match(value)
        if not match:
            raise ValueError(f"Could not parse seed item: {value!r}")
        items.append((match.group(1).strip(), int(match.group(2))))
    return items


def cumulative_cutoff(items: list[tuple[str, int]], threshold: float) -> int:
    total = sum(count for _tag, count in items)
    running = 0
    for idx, (_tag, count) in enumerate(items, start=1):
        running += count
        if running / total >= threshold:
            return idx
    return len(items)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    parsed = {}
    for bucket, raw in RAW_SEEDS.items():
        items = sorted(parse_items(raw), key=lambda item: (-item[1], item[0]))
        parsed[bucket] = items
        total = sum(count for _tag, count in items)
        running = 0
        for rank, (tag, count) in enumerate(items, start=1):
            running += count
            rows.append(
                {
                    "bucket": bucket,
                    "bucket_total": total,
                    "rank": rank,
                    "tag": tag,
                    "count": count,
                    "pct_of_bucket": count / total * 100.0,
                    "cumulative_pct": running / total * 100.0,
                }
            )

    with TSV_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "bucket",
                "bucket_total",
                "rank",
                "tag",
                "count",
                "pct_of_bucket",
                "cumulative_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "pct_of_bucket": f"{row['pct_of_bucket']:.6f}",
                    "cumulative_pct": f"{row['cumulative_pct']:.6f}",
                }
            )

    with MD_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Collapse-13 Seed Bucket Weight Breakdown\n\n")
        handle.write("Percentages are each tag's share of its own seed bucket frequency mass.\n\n")
        for bucket, items in sorted(parsed.items()):
            total = sum(count for _tag, count in items)
            top5 = sum(count for _tag, count in items[:5])
            top10 = sum(count for _tag, count in items[:10])
            handle.write(f"## {bucket}\n\n")
            handle.write(f"- Bucket total: {total}\n")
            handle.write(f"- Top 1 share: {items[0][1] / total * 100.0:.2f}%\n")
            handle.write(f"- Top 5 share: {top5 / total * 100.0:.2f}%\n")
            handle.write(f"- Top 10 share: {top10 / total * 100.0:.2f}%\n")
            handle.write(f"- Tags needed for 80%: {cumulative_cutoff(items, 0.80)}\n")
            handle.write(f"- Tags needed for 90%: {cumulative_cutoff(items, 0.90)}\n\n")
            for rank, (tag, count) in enumerate(items[:15], start=1):
                handle.write(f"{rank}. `{tag}` ({count}) - {count / total * 100.0:.2f}%\n")
            handle.write("\n")

    print(f"tsv={TSV_OUT}")
    print(f"md={MD_OUT}")


if __name__ == "__main__":
    main()
