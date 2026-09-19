"""
Split MWT and lemmatizer CoNLL-U files 95/5 train/dev, then train both components.
Output: trankit_save_ar_camelmorph_v1/ (new directory, does not touch existing Arabic model)
"""

import math
import io
import sys
import trankit
from pathlib import Path

# Force UTF-8 stdout/stderr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SAVE = ROOT / "trankit_save_ar_camelmorph_v1"


def fix_head(sentence: str) -> str:
    """Fix HEAD column so the UD scorer sees exactly one root per sentence.
    Range rows (e.g. 1-2) keep HEAD=0. Regular token rows chain: each points
    to the next, and the last points to 0 (root)."""
    lines = sentence.splitlines()
    # Collect indices of regular token lines (not comments, not range rows)
    token_indices = []
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) == 10 and "-" not in cols[0]:
            token_indices.append(i)

    for rank, i in enumerate(token_indices):
        cols = lines[i].split("\t")
        if rank < len(token_indices) - 1:
            cols[6] = str(int(cols[0]) + 1)  # point to next token
            cols[7] = "dep"
        else:
            cols[6] = "0"  # last token is root
            cols[7] = "root"
        lines[i] = "\t".join(cols)

    # Range rows: set HEAD=0 deprel=_ (they are ignored by scorer but must be valid)
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) == 10 and "-" in cols[0]:
            cols[6] = "_"  # range rows don't need valid HEAD
            lines[i] = "\t".join(cols)

    return "\n".join(lines)


def split_conllu(src: Path, train_dst: Path, dev_dst: Path, dev_ratio: float = 0.05):
    import random
    text = src.read_text(encoding="utf-8")
    sentences = [fix_head(s.strip()) for s in text.strip().split("\n\n") if s.strip()]
    random.seed(42)
    random.shuffle(sentences)
    n_dev = max(1, math.ceil(len(sentences) * dev_ratio))
    dev_sents = sentences[:n_dev]
    train_sents = sentences[n_dev:]
    train_dst.write_text("\n\n".join(train_sents) + "\n", encoding="utf-8")
    dev_dst.write_text("\n\n".join(dev_sents) + "\n", encoding="utf-8")
    print(f"{src.name}: {len(train_sents)} train / {len(dev_sents)} dev")
    return str(train_dst), str(dev_dst)


def main():
    SAVE.mkdir(exist_ok=True)

    print("=== Splitting files ===")
    mwt_train, mwt_dev = split_conllu(
        HERE / "camelmorph_mwt_final.conllu",
        HERE / "camelmorph_mwt_train.conllu",
        HERE / "camelmorph_mwt_dev.conllu",
    )
    lem_train, lem_dev = split_conllu(
        HERE / "camelmorph_lemmatizer_final.conllu",
        HERE / "camelmorph_lemmatizer_train.conllu",
        HERE / "camelmorph_lemmatizer_dev.conllu",
    )

    SAVE_DIR = str(SAVE)
    CATEGORY = "customized-mwt"

    # Pre-create preds directory that trankit fails to create itself
    (SAVE / "xlm-roberta-base" / "customized-mwt" / "preds").mkdir(parents=True, exist_ok=True)

    print("\n=== Training MWT ===")
    trankit.TPipeline(training_config={
        "category": CATEGORY,
        "task": "mwt",
        "save_dir": SAVE_DIR,
        "train_conllu_fpath": mwt_train,
        "dev_conllu_fpath": mwt_dev,
    }).train()

    print("\n=== Training Lemmatizer ===")
    trankit.TPipeline(training_config={
        "category": CATEGORY,
        "task": "lemmatize",
        "save_dir": SAVE_DIR,
        "train_conllu_fpath": lem_train,
        "dev_conllu_fpath": lem_dev,
    }).train()

    print("\nDone. Model saved to:", SAVE_DIR)


if __name__ == "__main__":
    main()
