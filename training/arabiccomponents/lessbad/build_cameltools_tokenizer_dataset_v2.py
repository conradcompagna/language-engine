"""
Regenerate Arabic Trankit tokenizer training data (v2 — cleaned).

Reads ara_news_2022_10K_plain.txt, runs CAMeL Tools morph tokenizer per-word,
applies cleanup rules, writes proper CoNLL-U with correct MWT notation.

Fixes vs original converter:
1. Article ال preserved in MWT subtokens (ل+الحدود not ل+لحدود)
2. Taamarbuta ة not split as standalone subtoken
3. بعض not mis-split as ب+عض
"""

from __future__ import annotations
import os, math, sys
from pathlib import Path
from typing import List, Sequence, Tuple

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


def _iter_lines(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                yield line


def _get_morphemes(word: str, tokenizer: MorphologicalTokenizer) -> List[str]:
    """Get cleaned morphemes for a single word."""
    try:
        raw = list(tokenizer.tokenize([word]) or [])
    except Exception:
        return [word]
    cleaned = []
    for tok in raw:
        if not tok:
            continue
        tok = str(tok).replace("+", "").replace("_", "").strip()
        if tok:
            cleaned.append(tok)
    return cleaned if cleaned else [word]


def _apply_cleanup(morphemes: List[str]) -> List[str]:
    """Merge non-clitic splits back together."""
    if len(morphemes) <= 1:
        return morphemes
    result = list(morphemes)

    # Rule 1: trailing standalone ة → merge onto previous morpheme
    if len(result) >= 2 and result[-1] == "\u0629":  # ة
        result[-2] = result[-2] + "\u0629"
        result.pop()

    # Rule 2: ب + عض → بعض (anywhere in the list)
    i = 0
    while i < len(result) - 1:
        if result[i] == "\u0628" and result[i + 1] == "\u0639\u0636":  # ب + عض
            result[i] = "\u0628\u0639\u0636"  # بعض
            result.pop(i + 1)
        else:
            i += 1

    return result


def _sentence_to_conllu(
    sent_id: int,
    text: str,
    token_groups: Sequence[Tuple[str, List[str]]],
) -> str:
    lines = [f"# sent_id = {sent_id}", f"# text = {text}"]
    tid = 1
    for surface, morphemes in token_groups:
        if len(morphemes) == 1:
            head = "0" if tid == 1 else "1"
            deprel = "root" if tid == 1 else "dep"
            form = morphemes[0]
            lines.append(
                "\t".join(
                    [
                        str(tid),
                        form,
                        form,
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
            tid += 1
        else:
            end = tid + len(morphemes) - 1
            lines.append(
                "\t".join(
                    [
                        f"{tid}-{end}",
                        surface,
                        "_",
                        "_",
                        "_",
                        "_",
                        "_",
                        "_",
                        "_",
                        "_",
                    ]
                )
            )
            for morph in morphemes:
                head = "0" if tid == 1 else "1"
                deprel = "root" if tid == 1 else "dep"
                lines.append(
                    "\t".join(
                        [
                            str(tid),
                            morph,
                            morph,
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
                tid += 1
    return "\n".join(lines)


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(SRC)

    print("Loading CAMeL Tools MLE disambiguator …")
    mle = MLEDisambiguator.pretrained(MODEL_NAME)
    tokenizer = MorphologicalTokenizer(
        disambiguator=mle,
        scheme=SCHEME,
        split=True,
        diac=False,
    )

    all_rows: List[Tuple[str, List[Tuple[str, List[str]]]]] = []
    for line_no, orig_line in enumerate(_iter_lines(SRC), 1):
        words = simple_word_tokenize(orig_line)
        if not words:
            continue
        text = " ".join(words)
        token_groups = []
        for word in words:
            morphemes = _get_morphemes(word, tokenizer)
            morphemes = _apply_cleanup(morphemes)
            token_groups.append((word, morphemes))
        all_rows.append((text, token_groups))
        if line_no % 1000 == 0:
            print(f"  processed {line_no} lines …")

    print(f"Total sentences: {len(all_rows)}")

    n_dev = max(1, math.ceil(len(all_rows) * DEV_RATIO))
    dev_rows = all_rows[:n_dev]
    train_rows = all_rows[n_dev:]

    for split_name, rows in [("train", train_rows), ("dev", dev_rows)]:
        stem = SRC.stem
        txt_path = OUT_DIR / f"{stem}_trankit_tok_{split_name}.conllu"
        txt_txt = OUT_DIR / f"{stem}_trankit_tok_{split_name}.txt"
        with txt_path.open("w", encoding="utf-8") as cf, txt_txt.open("w", encoding="utf-8") as tf:
            for sid, (text, groups) in enumerate(rows, 1):
                cf.write(_sentence_to_conllu(sid, text, groups) + "\n\n")
                tf.write(text + "\n")
        print(f"{split_name}: {len(rows)} sentences -> {txt_path.name}")

    print("Done.")


if __name__ == "__main__":
    main()
