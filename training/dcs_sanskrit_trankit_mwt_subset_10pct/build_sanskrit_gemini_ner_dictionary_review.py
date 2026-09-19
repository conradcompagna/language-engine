from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TRAIN_CONLLU = ROOT / "training" / "dcs_sanskrit_trankit_mwt_subset_10pct" / "train.conllu"
PARENT_CHUNK_DIR = (
    ROOT
    / "training"
    / "dcs_sanskrit_trankit_mwt_subset_10pct"
    / "train_10k_parent_tokens_unannotated_bio_chunks"
)
GEMINI_FINAL_DIR = (
    ROOT
    / "training"
    / "dcs_sanskrit_trankit_mwt_subset_10pct"
    / "gemini_ner_test_10_sentences"
    / "final"
)
FINAL_ATOMIC = GEMINI_FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_atomic.txt"
FINAL_MANIFEST = (
    GEMINI_FINAL_DIR / "sanskrit_gemini_ner_chunks_0001_1800_nonempty_fixed_manifest.tsv"
)
DICTIONARY_CSV = Path(
    "C:/Users/conra/Desktop/sanskrit-master/dcs/data/conllu/lookup/dictionary.csv"
)


def parse_misc(misc: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not misc or misc == "_":
        return out
    for part in misc.split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def parse_train_units() -> dict[str, list[tuple[dict[str, str], list[dict[str, str]]]]]:
    by_text_id: dict[str, list[tuple[dict[str, str], list[dict[str, str]]]]] = defaultdict(list)
    current_text_id = ""
    current_meta: dict[str, str] = {}
    sent_rows: list[list[str]] = []

    def flush_sentence() -> None:
        nonlocal sent_rows
        if not sent_rows:
            return
        units: list[dict[str, Any]] = []
        index = 0
        while index < len(sent_rows):
            cols = sent_rows[index]
            row_id = cols[0]
            if "-" in row_id:
                start, end = [int(part) for part in row_id.split("-", 1)]
                parent_form = cols[1]
                child_rows: list[list[str]] = []
                index += 1
                while index < len(sent_rows):
                    child_id = sent_rows[index][0]
                    if "-" in child_id or "." in child_id:
                        break
                    try:
                        child_int = int(child_id)
                    except ValueError:
                        break
                    if start <= child_int <= end:
                        child_rows.append(sent_rows[index])
                        index += 1
                    else:
                        break
                units.append(
                    {
                        "parent_form": parent_form,
                        "children": [
                            row_info(row, current_meta, parent_form) for row in child_rows
                        ],
                    }
                )
            elif "." in row_id:
                index += 1
            else:
                units.append(
                    {
                        "parent_form": cols[1],
                        "children": [row_info(cols, current_meta, cols[1])],
                    }
                )
                index += 1
        by_text_id[current_text_id].append((current_meta.copy(), units))
        sent_rows = []

    for line in TRAIN_CONLLU.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            flush_sentence()
            continue
        if line.startswith("## text_id:"):
            current_text_id = line.split(":", 1)[1].strip()
            current_meta = {"text_id": current_text_id}
        elif line.startswith("## text:"):
            current_meta["text_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("## chapter:"):
            current_meta["chapter"] = line.split(":", 1)[1].strip()
        elif line.startswith("## chapter_id:"):
            current_meta["chapter_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("# sent_id"):
            current_meta["sent_id"] = line.split("=", 1)[1].strip()
        elif line.startswith("# sent_counter"):
            current_meta["sent_counter"] = line.split("=", 1)[1].strip()
        elif line.startswith("# text ="):
            current_meta["sentence_text"] = line.split("=", 1)[1].strip()
        elif line.startswith("#"):
            continue
        else:
            sent_rows.append(line.split("\t"))
    flush_sentence()
    return dict(by_text_id)


def row_info(cols: list[str], meta: dict[str, str], parent_form: str) -> dict[str, str]:
    misc = parse_misc(cols[9] if len(cols) > 9 else "")
    return {
        "token_id": cols[0],
        "original_token": cols[1],
        "lemma": cols[2] if len(cols) > 2 else "",
        "upos": cols[3] if len(cols) > 3 else "",
        "feats": cols[5] if len(cols) > 5 else "",
        "misc": cols[9] if len(cols) > 9 else "",
        "lemma_id": misc.get("LemmaId", ""),
        "occ_id": misc.get("OccId", ""),
        "wordsem": misc.get("WordSem", ""),
        "parent_form": parent_form,
        "text_id": meta.get("text_id", ""),
        "text_name": meta.get("text_name", ""),
        "chapter": meta.get("chapter", ""),
        "chapter_id": meta.get("chapter_id", ""),
        "sent_id": meta.get("sent_id", ""),
        "sent_counter": meta.get("sent_counter", ""),
        "sentence_text": meta.get("sentence_text", ""),
    }


def read_parent_sentences(path: Path) -> list[list[str]]:
    sentences: list[list[str]] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                sentences.append(current)
                current = []
            continue
        current.append(stripped.rsplit(maxsplit=1)[0])
    if current:
        sentences.append(current)
    return sentences


def load_source_defs() -> dict[int, dict[str, Any]]:
    defs: dict[int, dict[str, Any]] = {
        1: {
            "text_id": "5",
            "selection": ("range", 1, 1000),
            "parent_file": "train_10k_parent_tokens_unannotated_chunk_01.bio",
        }
    }
    with (PARENT_CHUNK_DIR / "manifest_diverse_chunks_02_10.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            chunk = int(row["chunk"])
            defs[chunk] = {
                "text_id": row["text_id"],
                "selection": ("sample", 1000),
                "parent_file": row["file"],
            }
    with (PARENT_CHUNK_DIR / "manifest_chunks_11_20.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            chunk = int(row["chunk"])
            if chunk > 18:
                continue
            defs[chunk] = {
                "text_id": row["text_id"],
                "selection": (
                    "range",
                    int(row["source_sentence_start"]),
                    int(row["source_sentence_end"]),
                ),
                "parent_file": row["file"],
            }
    return defs


def select_source_sentences(
    text_sentences: list[tuple[dict[str, str], list[dict[str, Any]]]],
    selection: tuple[Any, ...],
) -> list[tuple[dict[str, str], list[dict[str, Any]]]]:
    if selection[0] == "range":
        start, end = int(selection[1]), int(selection[2])
        return text_sentences[start - 1 : end]
    if selection[0] == "sample":
        count = int(selection[1])
        total = len(text_sentences)
        return [text_sentences[round(i * (total - 1) / (count - 1))] for i in range(count)]
    raise ValueError(f"unknown selection: {selection}")


def map_parent_sentence(
    parent_tokens: list[str], units: list[dict[str, Any]], source_chunk: int, source_sentence: int
) -> list[dict[str, str]]:
    used = [False] * len(units)
    mapped: list[dict[str, str]] = []
    for parent_token in parent_tokens:
        found = None
        for index, unit in enumerate(units):
            if not used[index] and unit["parent_form"] == parent_token:
                found = index
                break
        if found is None:
            raise RuntimeError(
                f"could not map parent token {parent_token!r} in source chunk {source_chunk} sentence {source_sentence}"
            )
        used[found] = True
        for child in units[found]["children"]:
            item = dict(child)
            item["source_chunk"] = str(source_chunk)
            item["source_sentence"] = str(source_sentence)
            mapped.append(item)
    return mapped


def build_source_child_rows() -> dict[int, list[list[dict[str, str]]]]:
    train_by_text = parse_train_units()
    source_defs = load_source_defs()
    out: dict[int, list[list[dict[str, str]]]] = {}
    for source_chunk in range(1, 19):
        spec = source_defs[source_chunk]
        selected = select_source_sentences(train_by_text[spec["text_id"]], spec["selection"])
        parent_sentences = read_parent_sentences(PARENT_CHUNK_DIR / spec["parent_file"])
        if len(selected) != len(parent_sentences):
            raise RuntimeError(
                f"source chunk {source_chunk} sentence count mismatch: {len(selected)} source vs {len(parent_sentences)} parent"
            )
        mapped_sentences: list[list[dict[str, str]]] = []
        for index, (parent_tokens, (_meta, units)) in enumerate(
            zip(parent_sentences, selected), start=1
        ):
            mapped_sentences.append(map_parent_sentence(parent_tokens, units, source_chunk, index))
        out[source_chunk] = mapped_sentences
    return out


def load_dictionary() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with DICTIONARY_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            out[row["id"]] = row
    return out


def load_final_manifest() -> list[dict[str, str]]:
    with FINAL_MANIFEST.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_final_atomic_groups() -> list[list[tuple[str, str]]]:
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for line in FINAL_ATOMIC.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                groups.append(current)
                current = []
            continue
        token, tag = stripped.rsplit(" ", 1)
        current.append((token, tag))
    if current:
        groups.append(current)
    return groups


def source_rows_for_job(
    job_chunk: int, source_child_rows: dict[int, list[list[dict[str, str]]]]
) -> list[dict[str, str]]:
    source_chunk = (job_chunk - 1) // 100 + 1
    sentence_start = ((job_chunk - 1) % 100) * 10
    rows: list[dict[str, str]] = []
    for sentence in source_child_rows[source_chunk][sentence_start : sentence_start + 10]:
        rows.extend(sentence)
    return rows


def main() -> None:
    source_child_rows = build_source_child_rows()
    dictionary = load_dictionary()
    manifest_rows = [row for row in load_final_manifest() if row["status"] == "included"]
    atomic_groups = load_final_atomic_groups()
    if len(manifest_rows) != len(atomic_groups):
        raise RuntimeError(
            f"manifest/group mismatch: {len(manifest_rows)} included chunks vs {len(atomic_groups)} atomic groups"
        )

    occurrence_rows: list[list[str]] = [
        [
            "chunk",
            "selected_prefix",
            "source_chunk",
            "source_sentence",
            "text_id",
            "text_name",
            "chapter",
            "sent_id",
            "token_id",
            "original_token",
            "gemini_tag",
            "lemma_id",
            "lemma",
            "upos",
            "dictionary_word",
            "dictionary_grammar",
            "dictionary_meanings",
        ]
    ]
    aggregate: dict[tuple[str, str, str], dict[str, Any]] = {}
    mismatches: list[str] = []

    for manifest, atomic_group in zip(manifest_rows, atomic_groups):
        chunk = int(manifest["chunk"])
        selected_prefix = manifest["selected_prefix"]
        original_rows = source_rows_for_job(chunk, source_child_rows)
        if len(original_rows) != len(atomic_group):
            mismatches.append(
                f"chunk {chunk}: original rows {len(original_rows)} != atomic rows {len(atomic_group)}"
            )
            continue
        for row_index, (original, (token, tag)) in enumerate(
            zip(original_rows, atomic_group), start=1
        ):
            if original["original_token"] != token:
                mismatches.append(
                    f"chunk {chunk} row {row_index}: original {original['original_token']!r} != final {token!r}"
                )
                continue
            if tag == "O":
                continue
            lemma_id = original["lemma_id"]
            dictionary_row = dictionary.get(lemma_id, {})
            key = (original["original_token"], tag, lemma_id)
            rec = aggregate.setdefault(
                key,
                {
                    "count": 0,
                    "chunks": Counter(),
                    "upos": Counter(),
                    "lemma": original["lemma"],
                    "dictionary_word": dictionary_row.get("word", ""),
                    "dictionary_grammar": dictionary_row.get("grammar", ""),
                    "dictionary_meanings": dictionary_row.get("meanings", ""),
                    "missing_dictionary": "no" if dictionary_row else "yes",
                },
            )
            rec["count"] += 1
            rec["chunks"][str(chunk)] += 1
            rec["upos"][original["upos"]] += 1
            occurrence_rows.append(
                [
                    str(chunk),
                    selected_prefix,
                    original["source_chunk"],
                    original["source_sentence"],
                    original["text_id"],
                    original["text_name"],
                    original["chapter"],
                    original["sent_id"],
                    original["token_id"],
                    original["original_token"],
                    tag,
                    lemma_id,
                    original["lemma"],
                    original["upos"],
                    dictionary_row.get("word", ""),
                    dictionary_row.get("grammar", ""),
                    dictionary_row.get("meanings", ""),
                ]
            )

    if mismatches:
        mismatch_path = GEMINI_FINAL_DIR / "sanskrit_gemini_ner_dictionary_review_mismatches.txt"
        mismatch_path.write_text("\n".join(mismatches) + "\n", encoding="utf-8")
        raise RuntimeError(f"token mapping mismatches found: {len(mismatches)}")

    review_rows: list[list[str]] = [
        [
            "original_token",
            "gemini_tag",
            "occurrence_count",
            "lemma_id",
            "lemma",
            "upos_counts",
            "dictionary_word",
            "dictionary_grammar",
            "dictionary_meanings",
            "missing_dictionary",
            "example_chunks",
        ]
    ]
    for (token, tag, lemma_id), rec in sorted(
        aggregate.items(),
        key=lambda item: (item[0][1], -int(item[1]["count"]), item[0][0], item[0][2]),
    ):
        review_rows.append(
            [
                token,
                tag,
                str(rec["count"]),
                lemma_id,
                rec["lemma"],
                ", ".join(f"{key}:{value}" for key, value in rec["upos"].most_common()),
                rec["dictionary_word"],
                rec["dictionary_grammar"],
                rec["dictionary_meanings"],
                rec["missing_dictionary"],
                ", ".join(key for key, _value in rec["chunks"].most_common(12)),
            ]
        )

    review_path = GEMINI_FINAL_DIR / "sanskrit_gemini_ner_non_o_token_dictionary_review.tsv"
    occurrences_path = (
        GEMINI_FINAL_DIR / "sanskrit_gemini_ner_non_o_token_dictionary_occurrences.tsv"
    )
    summary_path = GEMINI_FINAL_DIR / "sanskrit_gemini_ner_non_o_token_dictionary_summary.json"
    review_path.write_text(
        "\n".join("\t".join(row) for row in review_rows) + "\n", encoding="utf-8"
    )
    occurrences_path.write_text(
        "\n".join("\t".join(row) for row in occurrence_rows) + "\n", encoding="utf-8"
    )
    summary = {
        "unique_token_tag_lemma_rows": len(review_rows) - 1,
        "non_o_occurrences": len(occurrence_rows) - 1,
        "missing_dictionary_rows": sum(1 for row in review_rows[1:] if row[9] == "yes"),
        "review_file": str(review_path),
        "occurrences_file": str(occurrences_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
