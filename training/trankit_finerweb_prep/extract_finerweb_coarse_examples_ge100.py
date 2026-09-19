from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[1]
COARSE_INVENTORY = BASE_DIR / "finerweb_label_inventory_coarse.tsv"
SOURCE_FILES = BASE_DIR / "finerweb_source_files.tsv"
OUTPUT_DIR = BASE_DIR / "derived_fasttext_categories"
OUTPUT_TSV = OUTPUT_DIR / "finerweb_coarse_ge100_examples.tsv"

MIN_COUNT = 101
MODEL_NAME = "facebook/nllb-200-distilled-600M"
TARGET_LANG = "eng_Latn"

LANG_TO_NLLB = {
    "ell": "ell_Grek",
    "fas": "pes_Arab",
    "fil": "tgl_Latn",
    "heb": "heb_Hebr",
    "hin": "hin_Deva",
    "hye": "hye_Armn",
    "ind": "ind_Latn",
    "ita": "ita_Latn",
    "por": "por_Latn",
    "san": "san_Deva",
    "swh": "swh_Latn",
    "tha": "tha_Thai",
    "tur": "tur_Latn",
    "vie": "vie_Latn",
}

LANG_PREFERENCE = [
    "ind",
    "ita",
    "por",
    "tur",
    "swh",
    "vie",
    "fil",
    "hin",
    "heb",
    "hye",
    "fas",
    "tha",
    "ell",
    "san",
    "lat",
]

LATINISH_RE = re.compile(
    r"^[\w\s\-\.,'’\"“”:/@#%&+(){}\[\]<>!?;·|=~`^*$€£¥₹]+$",
    re.UNICODE,
)
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def load_target_coarse_labels() -> list[str]:
    csv.field_size_limit(2**31 - 1)
    labels: list[str] = []
    with COARSE_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            if int(row["total_count"]) >= MIN_COUNT:
                labels.append(row["coarse_label"])
    return labels


def load_source_files() -> list[dict[str, str]]:
    with SOURCE_FILES.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    by_lang = {row["lang"]: row for row in rows}
    ordered = [by_lang[lang] for lang in LANG_PREFERENCE if lang in by_lang]
    ordered.extend(row for row in rows if row["lang"] not in {item["lang"] for item in ordered})
    for row in ordered:
        row["abs_file"] = str((ROOT_DIR / row["file"]).resolve())
    return ordered


def coarse_from_label(label: str) -> str:
    return (label or "").split("/", 1)[0].strip()


def extract_examples(targets: list[str], source_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    target_set = set(targets)
    examples: dict[str, dict[str, str]] = {}

    for source in source_rows:
        path = Path(source["abs_file"])
        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(batch_size=2048, columns=["text", "char_spans"]):
            for row in batch.to_pylist():
                text = row.get("text") or ""
                for span in row.get("char_spans") or []:
                    coarse = coarse_from_label(span.get("label") or "")
                    if coarse not in target_set or coarse in examples:
                        continue

                    start = span.get("start")
                    end = span.get("end")
                    if start is None or end is None:
                        continue

                    example = normalize_text(text[int(start) : int(end)])
                    if not example:
                        continue

                    examples[coarse] = {
                        "example": example,
                        "lang": source["lang"],
                    }
                    if len(examples) == len(targets):
                        return examples
    return examples


def is_latinish(text: str) -> bool:
    return bool(text) and bool(LATINISH_RE.match(text))


def is_likely_latin_name_or_code(text: str) -> bool:
    if not is_latinish(text):
        return False
    words = WORD_RE.findall(text)
    if not words:
        return True
    if len(words) > 4:
        return False
    name_like = 0
    for word in words:
        if word.isupper() or word[0].isupper():
            name_like += 1
    return name_like == len(words)


class NllbTranslator:
    def __init__(self) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, local_files_only=True)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME, local_files_only=True)
        self.model.eval()
        self.target_token_id = self.tokenizer.convert_tokens_to_ids(TARGET_LANG)
        torch.set_num_threads(max(1, min(4, torch.get_num_threads())))

    def translate_batch(self, source_lang: str, texts: list[str]) -> list[str]:
        source_code = LANG_TO_NLLB.get(source_lang)
        if not source_code:
            return texts

        translations: list[str] = []
        for start in range(0, len(texts), 16):
            chunk = texts[start : start + 16]
            self.tokenizer.src_lang = source_code
            inputs = self.tokenizer(
                chunk,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=96,
            )
            with torch.no_grad():
                generated = self.model.generate(
                    **inputs,
                    forced_bos_token_id=self.target_token_id,
                    max_new_tokens=64,
                    num_beams=4,
                )
            translations.extend(
                normalize_text(text)
                for text in self.tokenizer.batch_decode(generated, skip_special_tokens=True)
            )
        return translations


def translate_examples(examples: dict[str, dict[str, str]]) -> None:
    translator = NllbTranslator()
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for coarse, item in examples.items():
        example = item["example"]
        if is_likely_latin_name_or_code(example):
            item["translation"] = example
        else:
            grouped[item["lang"]].append((coarse, example))

    for lang, rows in grouped.items():
        translated = translator.translate_batch(lang, [example for _, example in rows])
        for (coarse, _), translation in zip(rows, translated):
            examples[coarse]["translation"] = translation

    for item in examples.values():
        item["translation"] = item.get("translation") or item["example"]


def write_tsv(targets: list[str], examples: dict[str, dict[str, str]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["example", "translation", "coarse_tag"])
        for coarse in targets:
            item = examples.get(coarse)
            if not item:
                continue
            writer.writerow([item["example"], item["translation"], coarse])


def main() -> None:
    targets = load_target_coarse_labels()
    sources = load_source_files()
    examples = extract_examples(targets, sources)
    missing = [label for label in targets if label not in examples]
    if missing:
        raise RuntimeError(f"Missing examples for {len(missing)} coarse labels: {missing[:20]}")

    translate_examples(examples)
    write_tsv(targets, examples)
    print(f"Wrote {len(examples)} rows to {OUTPUT_TSV}")


if __name__ == "__main__":
    main()
