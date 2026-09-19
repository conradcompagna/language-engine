"""
Build synthetic Arabic Trankit tokenizer data from plain text using CAMeL Tools.

Input:
  ara_news_2022_10K_plain.txt

Outputs:
  ara_news_2022_10K_plain_cameltools_canonical.txt
  ara_news_2022_10K_plain_cameltools_canonical.conllu
  ara_news_2022_10K_plain_trankit_tok_train.txt
  ara_news_2022_10K_plain_trankit_tok_dev.txt
  ara_news_2022_10K_plain_trankit_tok_train.conllu
  ara_news_2022_10K_plain_trankit_tok_dev.conllu

The converter keeps the source text intact, uses CAMeL's MLE-based morphological
tokenizer with split=True and diac=False, and writes a minimal CoNLL-U file that
is suitable for Trankit tokenizer training.
"""

from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

APP_ROOT = Path(__file__).resolve().parents[3]
TRAINING_ROOT = APP_ROOT / "training"
CAMELTOOLS_DATA = TRAINING_ROOT / "camel_tools_bundle"
CAMELTOOLS_TMP = TRAINING_ROOT / "camel_tools_tmp"

os.environ["CAMELTOOLS_DATA"] = str(CAMELTOOLS_DATA)
os.environ["TEMP"] = str(CAMELTOOLS_TMP)
os.environ["TMP"] = str(CAMELTOOLS_TMP)
os.environ["HOME"] = str(TRAINING_ROOT)
os.environ["USERPROFILE"] = str(TRAINING_ROOT)

from camel_tools.tokenizers.word import simple_word_tokenize
from camel_tools.tokenizers.morphological import MorphologicalTokenizer
from camel_tools.disambig.mle import MLEDisambiguator


HERE = Path(__file__).resolve().parent
SRC = HERE / "ara_news_2022_10K_plain.txt"
OUT_DIR = HERE
DEV_RATIO = 0.05
MODEL_NAME = "calima-msa-r13"
SCHEME = "atbtok"
CANONICAL_TXT = OUT_DIR / f"{SRC.stem}_cameltools_canonical.txt"
CANONICAL_CONLLU = OUT_DIR / f"{SRC.stem}_cameltools_canonical.conllu"


def _iter_lines(path: Path) -> Iterable[str]:
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                yield line


def _tokenize_sentence(sentence: str, tokenizer: MorphologicalTokenizer) -> List[str]:
    words = simple_word_tokenize(sentence)
    if not words:
        return []
    tokens = tokenizer.tokenize(words)
    cleaned = []
    for tok in tokens:
        if not tok:
            continue
        tok = tok.replace("+", "").strip()
        if tok:
            cleaned.append(tok)
    return cleaned


def _sentence_to_conllu(sent_id: int, sentence: str, tokens: Sequence[str]) -> str:
    lines = [
        f"# sent_id = {sent_id}",
        f"# text = {sentence}",
    ]
    for i, tok in enumerate(tokens, start=1):
        head = "0" if i == 1 else "1"
        deprel = "root" if i == 1 else "dep"
        lines.append(
            "\t".join(
                [
                    str(i),
                    tok,
                    tok,
                    "X",
                    "X",
                    "_",
                    head,
                    deprel,
                    "_",
                    "_",
                ]
            )
        )
    return "\n".join(lines)


def _load_canonical_rows(path: Path) -> List[Tuple[str, List[str]]]:
    rows: List[Tuple[str, List[str]]] = []
    for sentence in _iter_lines(path):
        tokens = sentence.split()
        if tokens:
            rows.append((sentence, tokens))
    return rows


def _write_split(split_name: str, rows: Sequence[Tuple[str, List[str]]]) -> None:
    stem = SRC.stem
    txt_path = OUT_DIR / f"{stem}_trankit_tok_{split_name}.txt"
    conllu_path = OUT_DIR / f"{stem}_trankit_tok_{split_name}.conllu"

    with (
        txt_path.open("w", encoding="utf-8") as txt_fh,
        conllu_path.open("w", encoding="utf-8") as conllu_fh,
    ):
        for sent_id, (sentence, tokens) in enumerate(rows, start=1):
            txt_fh.write(sentence + "\n")
            conllu_fh.write(_sentence_to_conllu(sent_id, sentence, tokens) + "\n\n")

    print(f"{split_name}: {len(rows)} sentences -> {txt_path.name}, {conllu_path.name}")


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(SRC)

    if CANONICAL_TXT.exists():
        canonical_rows = _load_canonical_rows(CANONICAL_TXT)
    else:
        mle = MLEDisambiguator.pretrained(MODEL_NAME)
        tokenizer = MorphologicalTokenizer(
            disambiguator=mle,
            scheme=SCHEME,
            split=True,
            diac=False,
        )

        canonical_rows = []
        for line in _iter_lines(SRC):
            tokens = _tokenize_sentence(line, tokenizer)
            if tokens:
                canonical_rows.append((" ".join(tokens), tokens))

    if not canonical_rows:
        raise RuntimeError("No tokenized sentences were produced.")

    with (
        CANONICAL_TXT.open("w", encoding="utf-8") as txt_fh,
        CANONICAL_CONLLU.open("w", encoding="utf-8") as conllu_fh,
    ):
        for sent_id, (sentence, tokens) in enumerate(canonical_rows, start=1):
            txt_fh.write(sentence + "\n")
            conllu_fh.write(_sentence_to_conllu(sent_id, sentence, tokens) + "\n\n")

    print(
        f"canonical: {len(canonical_rows)} sentences -> {CANONICAL_TXT.name}, {CANONICAL_CONLLU.name}"
    )

    n_dev = max(1, math.ceil(len(canonical_rows) * DEV_RATIO))
    dev_rows = canonical_rows[:n_dev]
    train_rows = canonical_rows[n_dev:]

    _write_split("train", train_rows)
    _write_split("dev", dev_rows)

    print("Done.")


if __name__ == "__main__":
    main()
