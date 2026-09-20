from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd


BASE = Path(__file__).resolve().parent
NERDUMP = BASE.parent / "nerdump" / "fiNERweb_app_languages"
INVENTORY = BASE / "finerweb_label_inventory.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_TEXT = OUT_DIR / "finerweb_ge100_tag_span_examples.txt"
OUT_TSV = OUT_DIR / "finerweb_ge100_tag_span_examples.tsv"
OUT_LANG_TSV = OUT_DIR / "finerweb_ge100_tag_span_examples_with_lang.tsv"
RANDOM_SEED = 20260505
EXAMPLES_PER_TAG = 10


def load_target_labels() -> list[str]:
    labels = []
    with INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["count"]) >= 100:
                labels.append(row["original_label"])
    return labels


def clean_span(text: str) -> str:
    return " ".join((text or "").split())


def collect_examples(targets: set[str]) -> dict[str, dict[str, list[tuple[str, str]]]]:
    by_label_lang: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    seen: dict[str, set[str]] = defaultdict(set)

    for path in sorted(NERDUMP.glob("*.parquet")):
        lang = path.name.split("-", 1)[0]
        df = pd.read_parquet(path, columns=["text", "char_spans"])
        for row in df.itertuples(index=False):
            text = row.text or ""
            for span in row.char_spans:
                label = span.get("label")
                if label not in targets:
                    continue
                start = int(span.get("start", -1))
                end = int(span.get("end", -1))
                if start < 0 or end <= start or end > len(text):
                    continue
                value = clean_span(text[start:end])
                if not value or value in seen[label]:
                    continue
                seen[label].add(value)
                by_label_lang[label][lang].append((lang, value))

    return by_label_lang


def choose_examples(by_lang: dict[str, list[tuple[str, str]]], rng: random.Random) -> list[tuple[str, str]]:
    langs = list(by_lang)
    rng.shuffle(langs)
    chosen: list[tuple[str, str]] = []
    used = set()

    for lang in langs:
        values = list(by_lang[lang])
        rng.shuffle(values)
        for lang_value, value in values:
            if value in used:
                continue
            chosen.append((lang_value, value))
            used.add(value)
            break
        if len(chosen) >= EXAMPLES_PER_TAG:
            return chosen

    leftovers = []
    for values in by_lang.values():
        leftovers.extend(values)
    rng.shuffle(leftovers)
    for lang_value, value in leftovers:
        if value in used:
            continue
        chosen.append((lang_value, value))
        used.add(value)
        if len(chosen) >= EXAMPLES_PER_TAG:
            break

    return chosen


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels = load_target_labels()
    by_label_lang = collect_examples(set(labels))
    rng = random.Random(RANDOM_SEED)

    selected = {label: choose_examples(by_label_lang.get(label, {}), rng) for label in labels}

    with OUT_TEXT.open("w", encoding="utf-8", newline="\n") as handle:
        for label in labels:
            handle.write(f"{label}\n")
            for _lang, example in selected[label]:
                handle.write(f"{example}\n")
            handle.write("\n")

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["tag", *[f"example_{idx}" for idx in range(1, EXAMPLES_PER_TAG + 1)]])
        for label in labels:
            examples = [example for _lang, example in selected[label]]
            writer.writerow([label, *examples, *([""] * (EXAMPLES_PER_TAG - len(examples)))])

    with OUT_LANG_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["tag", "rank", "lang", "example"])
        for label in labels:
            for rank, (lang, example) in enumerate(selected[label], start=1):
                writer.writerow([label, rank, lang, example])

    missing = sum(1 for examples in selected.values() if not examples)
    short = sum(1 for examples in selected.values() if 0 < len(examples) < EXAMPLES_PER_TAG)
    print(f"tags\t{len(labels)}")
    print(f"missing\t{missing}")
    print(f"short\t{short}")
    print(f"text\t{OUT_TEXT}")
    print(f"tsv\t{OUT_TSV}")
    print(f"lang_tsv\t{OUT_LANG_TSV}")


if __name__ == "__main__":
    main()
