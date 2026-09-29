from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[1]
SOURCE_FILES = BASE_DIR / "finerweb_source_files.tsv"
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
OUT_TSV = OUT_DIR / "finerweb_coarse_tag_percent_by_language.tsv"
TOTALS_TSV = OUT_DIR / "finerweb_language_coarse_tag_totals.tsv"


def coarse_from_label(label: str) -> str:
    return (label or "").split("/", 1)[0].strip()


def load_sources() -> list[dict[str, str]]:
    with SOURCE_FILES.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        row["abs_file"] = str((ROOT_DIR / row["file"]).resolve())
    return rows


def count_language(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    parquet_file = pq.ParquetFile(path)
    for batch in parquet_file.iter_batches(batch_size=4096, columns=["char_spans"]):
        for row in batch.to_pylist():
            for span in row.get("char_spans") or []:
                coarse = coarse_from_label(span.get("label") or "")
                if coarse:
                    counts[coarse] += 1
    return counts


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    all_counts: dict[str, Counter[str]] = {}

    for source in sources:
        lang = source["lang"]
        all_counts[lang] = count_language(Path(source["abs_file"]))

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "lang",
                "coarse_tag",
                "count",
                "language_total",
                "percent_of_language",
                "cumulative_percent_of_language",
            ]
        )
        for lang in sorted(all_counts):
            counts = all_counts[lang]
            total = sum(counts.values())
            cumulative = 0
            for coarse, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
                cumulative += count
                writer.writerow(
                    [
                        lang,
                        coarse,
                        count,
                        total,
                        f"{count / total * 100:.6f}",
                        f"{cumulative / total * 100:.6f}",
                    ]
                )

    with TOTALS_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["lang", "language_total", "unique_coarse_tags"])
        for lang in sorted(all_counts):
            counts = all_counts[lang]
            writer.writerow([lang, sum(counts.values()), len(counts)])

    print(f"languages={len(all_counts)}")
    print(f"rows={sum(len(counts) for counts in all_counts.values())}")
    print(f"spans={sum(sum(counts.values()) for counts in all_counts.values())}")
    print(f"wrote={OUT_TSV}")
    print(f"totals={TOTALS_TSV}")
    for lang in sorted(all_counts):
        counts = all_counts[lang]
        total = sum(counts.values())
        top = "; ".join(
            f"{tag}={count / total * 100:.2f}%"
            for tag, count in counts.most_common(5)
        )
        print(f"{lang}\t{total}\t{len(counts)}\t{top}")


if __name__ == "__main__":
    main()
