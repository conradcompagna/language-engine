from __future__ import annotations

import math
import random
from pathlib import Path


EXPERIMENT_TAG = "trankit_exp_20260405a"
RNG = random.Random(42)


HERE = Path(__file__).resolve().parent
MWT_SRC = HERE / "camelmorph_mwt_final.conllu"
LEMMA_SRC = HERE / "camelmorph_lemmatizer_final.conllu"

MWT_TRAIN_OUT = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_train_full.conllu"
MWT_DEV_OUT = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_dev_compat.conllu"
MWT_DEV_TOKENIZER_OUT = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_dev_tokenizer_input.conllu"
LEMMA_TRAIN_OUT = HERE / f"camelmorph_lemmatizer_{EXPERIMENT_TAG}_train.conllu"
LEMMA_DEV_OUT = HERE / f"camelmorph_lemmatizer_{EXPERIMENT_TAG}_dev.conllu"


def read_sentences(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [chunk.strip() for chunk in text.strip().split("\n\n") if chunk.strip()]


def write_sentences(path: Path, sentences: list[str]) -> None:
    path.write_text("\n\n".join(sentences) + "\n\n", encoding="utf-8")


def extract_mwt_pair(sentence: str) -> tuple[str, str]:
    rows = [line for line in sentence.splitlines() if line and not line.startswith("#")]
    src = rows[0].split("\t")[1]
    dst = " ".join(row.split("\t")[1] for row in rows[1:])
    return src, dst


def patch_mwt_sentence(sentence: str) -> str:
    lines = sentence.splitlines()
    token_line_indexes: list[int] = []

    for i, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            raise ValueError(f"Expected 10 columns, got {len(cols)} in line: {line!r}")
        if "-" not in cols[0]:
            token_line_indexes.append(i)

    if len(token_line_indexes) < 2:
        raise ValueError(f"Expected an MWT with at least 2 expanded tokens:\n{sentence}")

    for rank, i in enumerate(token_line_indexes):
        cols = lines[i].split("\t")
        if rank == 0:
            cols[6] = "0"
            cols[7] = "root"
        else:
            cols[6] = "1"
            cols[7] = "dep"
        lines[i] = "\t".join(cols)

    return "\n".join(lines)


def build_mwt_tokenizer_input(sentence: str) -> str:
    output_lines: list[str] = []
    for line in sentence.splitlines():
        if not line:
            continue
        if line.startswith("#"):
            output_lines.append(line)
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            raise ValueError(f"Expected 10 columns, got {len(cols)} in line: {line!r}")
        if "-" in cols[0]:
            token_id = cols[0].split("-")[0]
            token_text = cols[1]
            output_lines.append(
                "\t".join([token_id, token_text, "_", "_", "_", "_", "_", "_", "_", "MWT=Yes"])
            )
    return "\n".join(output_lines)


def build_mwt_outputs() -> None:
    sentences = read_sentences(MWT_SRC)
    dev_size = max(1, math.ceil(len(sentences) * 0.05))

    first_mapping_for_src: dict[str, str] = {}
    compatible_sentences: list[str] = []

    for sentence in sentences:
        src, dst = extract_mwt_pair(sentence)
        if src not in first_mapping_for_src:
            first_mapping_for_src[src] = dst
        if first_mapping_for_src[src] == dst:
            compatible_sentences.append(sentence)

    if len(compatible_sentences) < dev_size:
        raise ValueError(
            f"Need {dev_size} compatible MWT dev sentences, found {len(compatible_sentences)}"
        )

    selected_dev = RNG.sample(compatible_sentences, dev_size)
    selected_dev_set = set(selected_dev)
    if len(selected_dev_set) != dev_size:
        raise ValueError("Sampled duplicate MWT dev sentences unexpectedly")

    selected_dev_in_corpus_order = [s for s in sentences if s in selected_dev_set]
    patched_train = [patch_mwt_sentence(sentence) for sentence in sentences]
    patched_dev = [patch_mwt_sentence(sentence) for sentence in selected_dev_in_corpus_order]
    tokenizer_dev = [build_mwt_tokenizer_input(sentence) for sentence in selected_dev_in_corpus_order]

    write_sentences(MWT_TRAIN_OUT, patched_train)
    write_sentences(MWT_DEV_OUT, patched_dev)
    write_sentences(MWT_DEV_TOKENIZER_OUT, tokenizer_dev)

    print(
        f"MWT full-train written: {MWT_TRAIN_OUT.name} ({len(patched_train)} sentences)"
    )
    print(
        f"MWT compat-dev written: {MWT_DEV_OUT.name} ({len(patched_dev)} sentences)"
    )
    print(
        f"MWT tokenizer-dev written: {MWT_DEV_TOKENIZER_OUT.name} ({len(tokenizer_dev)} sentences)"
    )


def build_lemma_outputs() -> None:
    sentences = read_sentences(LEMMA_SRC)
    shuffled = sentences[:]
    RNG.shuffle(shuffled)
    dev_size = max(1, math.ceil(len(shuffled) * 0.05))
    dev_sentences = shuffled[:dev_size]
    train_sentences = shuffled[dev_size:]

    write_sentences(LEMMA_TRAIN_OUT, train_sentences)
    write_sentences(LEMMA_DEV_OUT, dev_sentences)

    print(
        f"Lemma train written: {LEMMA_TRAIN_OUT.name} ({len(train_sentences)} sentences)"
    )
    print(
        f"Lemma dev written: {LEMMA_DEV_OUT.name} ({len(dev_sentences)} sentences)"
    )


def main() -> None:
    build_mwt_outputs()
    build_lemma_outputs()


if __name__ == "__main__":
    main()
