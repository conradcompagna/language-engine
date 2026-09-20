from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd


BASE = Path(__file__).resolve().parent
NERDUMP = BASE.parent / "nerdump" / "fiNERweb_app_languages"
COARSE_BUCKETS = BASE / "finerweb_label_inventory_coarse_buckets.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_MD = OUT_DIR / "top71_coarse_tag_actual_span_examples.md"
OUT_WIDE_TSV = OUT_DIR / "top71_coarse_tag_actual_span_examples.tsv"
OUT_LONG_TSV = OUT_DIR / "top71_coarse_tag_actual_span_examples_long.tsv"
RANDOM_SEED = 20260506
TOP_N = 71
EXAMPLES_PER_TAG = 10


def coarse_part(label: str) -> str:
    return (label or "").split("/", 1)[0].strip()


def load_top_coarse() -> list[dict[str, object]]:
    rows = []
    with COARSE_BUCKETS.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows.append({"coarse_label": row["coarse_label"], "total_count": int(row["total_count"])})
    rows.sort(key=lambda row: (-int(row["total_count"]), str(row["coarse_label"])))
    total = sum(int(row["total_count"]) for row in rows)
    for rank, row in enumerate(rows[:TOP_N], start=1):
        row["rank"] = rank
        row["pct_of_total"] = int(row["total_count"]) / total * 100
    return rows[:TOP_N]


def clean_span(text: str) -> str:
    return " ".join((text or "").split())


def collect_examples(targets: set[str]) -> dict[str, dict[str, list[dict[str, str]]]]:
    by_coarse_lang: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    seen: dict[str, set[str]] = defaultdict(set)

    for path in sorted(NERDUMP.glob("*.parquet")):
        lang = path.name.split("-", 1)[0]
        df = pd.read_parquet(path, columns=["text", "char_spans"])
        for row in df.itertuples(index=False):
            text = row.text or ""
            for span in row.char_spans:
                original_label = span.get("label") or ""
                coarse_label = coarse_part(original_label)
                if coarse_label not in targets:
                    continue
                start = int(span.get("start", -1))
                end = int(span.get("end", -1))
                if start < 0 or end <= start or end > len(text):
                    continue
                value = clean_span(text[start:end])
                if not value or value in seen[coarse_label]:
                    continue
                seen[coarse_label].add(value)
                by_coarse_lang[coarse_label][lang].append(
                    {"lang": lang, "example": value, "original_label": original_label}
                )

    return by_coarse_lang


def choose_examples(by_lang: dict[str, list[dict[str, str]]], rng: random.Random) -> list[dict[str, str]]:
    langs = list(by_lang)
    rng.shuffle(langs)
    chosen: list[dict[str, str]] = []
    used = set()

    for lang in langs:
        values = list(by_lang[lang])
        rng.shuffle(values)
        for item in values:
            if item["example"] in used:
                continue
            chosen.append(item)
            used.add(item["example"])
            break
        if len(chosen) >= EXAMPLES_PER_TAG:
            return chosen

    leftovers = []
    for values in by_lang.values():
        leftovers.extend(values)
    rng.shuffle(leftovers)
    for item in leftovers:
        if item["example"] in used:
            continue
        chosen.append(item)
        used.add(item["example"])
        if len(chosen) >= EXAMPLES_PER_TAG:
            break

    return chosen


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    top_rows = load_top_coarse()
    targets = {str(row["coarse_label"]) for row in top_rows}
    by_coarse_lang = collect_examples(targets)
    rng = random.Random(RANDOM_SEED)
    selected = {
        str(row["coarse_label"]): choose_examples(by_coarse_lang.get(str(row["coarse_label"]), {}), rng)
        for row in top_rows
    }

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top 71 Coarse FinerWeb Tags: Actual Span Examples\n\n")
        handle.write(
            "Examples are sampled from `training/nerdump/fiNERweb_app_languages/*.parquet`. "
            "Coarse label is the part before the first `/` in each original span label.\n\n"
        )
        for row in top_rows:
            coarse_label = str(row["coarse_label"])
            examples = selected[coarse_label]
            handle.write(
                f"## {int(row['rank'])}. {coarse_label} "
                f"({int(row['total_count'])}, {float(row['pct_of_total']):.6f}%)\n\n"
            )
            for idx, item in enumerate(examples, start=1):
                handle.write(
                    f"{idx}. `{item['example']}` "
                    f"[{item['lang']}; {item['original_label']}]\n"
                )
            if not examples:
                handle.write("No examples found.\n")
            handle.write("\n")

    with OUT_WIDE_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "rank",
                "coarse_label",
                "total_count",
                "pct_of_total",
                *[f"example_{idx}" for idx in range(1, EXAMPLES_PER_TAG + 1)],
            ]
        )
        for row in top_rows:
            coarse_label = str(row["coarse_label"])
            values = [
                f"{item['example']} [{item['lang']}; {item['original_label']}]"
                for item in selected[coarse_label]
            ]
            writer.writerow(
                [
                    row["rank"],
                    coarse_label,
                    row["total_count"],
                    f"{float(row['pct_of_total']):.6f}",
                    *values,
                    *([""] * (EXAMPLES_PER_TAG - len(values))),
                ]
            )

    with OUT_LONG_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["rank", "coarse_label", "total_count", "pct_of_total", "example_rank", "lang", "original_label", "example"])
        for row in top_rows:
            coarse_label = str(row["coarse_label"])
            for example_rank, item in enumerate(selected[coarse_label], start=1):
                writer.writerow(
                    [
                        row["rank"],
                        coarse_label,
                        row["total_count"],
                        f"{float(row['pct_of_total']):.6f}",
                        example_rank,
                        item["lang"],
                        item["original_label"],
                        item["example"],
                    ]
                )

    missing = [label for label, examples in selected.items() if not examples]
    short = [label for label, examples in selected.items() if 0 < len(examples) < EXAMPLES_PER_TAG]
    print(f"top_coarse_tags\t{len(top_rows)}")
    print(f"missing_examples\t{len(missing)}")
    print(f"short_examples\t{len(short)}")
    print(f"md\t{OUT_MD}")
    print(f"wide_tsv\t{OUT_WIDE_TSV}")
    print(f"long_tsv\t{OUT_LONG_TSV}")
    if missing:
        print("missing\t" + ", ".join(missing))
    if short:
        print("short\t" + ", ".join(short))


if __name__ == "__main__":
    main()
