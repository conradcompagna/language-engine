from __future__ import annotations

import random
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "ara-master (1).zip"
OUT_DIR = HERE
TAG = "zip_surface_20260405a"
TRAIN_OUT = OUT_DIR / f"ara_zip_surface_lemmatizer_{TAG}_train.conllu"
DEV_OUT = OUT_DIR / f"ara_zip_surface_lemmatizer_{TAG}_dev.conllu"
REPORT_OUT = OUT_DIR / f"ara_zip_surface_lemmatizer_{TAG}_report.txt"

POS_MAP = {"N": "NOUN", "ADJ": "ADJ", "V": "VERB"}
SOURCE_FILES = ["ara-master/ara_atb", "ara-master/ara_new", "ara-master/ara"]
RNG = random.Random(42)


def to_conllu_sentence(sent_id: str, form: str, lemma: str, upos: str, xpos: str, source: str) -> str:
    return "\n".join(
        [
            f"# sent_id = {sent_id}",
            f"# text = {form}",
            f"# source = {source}",
            f"1\t{form}\t{lemma}\t{upos}\t{xpos}\t_\t0\troot\t_\t_",
        ]
    )


def load_rows() -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for member in SOURCE_FILES:
            for line in zf.read(member).decode("utf-8").splitlines():
                if not line.strip():
                    continue
                lemma, form, feats = line.split("\t")
                xpos = feats.split(";", 1)[0]
                upos = POS_MAP.get(xpos)
                if not upos:
                    continue
                rows.append((form, lemma, upos, xpos, member))
    return rows


def write_split(rows: list[tuple[str, str, str, str, str]]) -> None:
    shuffled = rows[:]
    RNG.shuffle(shuffled)
    dev_size = max(1, round(len(shuffled) * 0.05))
    dev_rows = shuffled[:dev_size]
    train_rows = shuffled[dev_size:]

    train_sentences = [
        to_conllu_sentence(f"zipsurf_train_{i:08d}", form, lemma, upos, xpos, source)
        for i, (form, lemma, upos, xpos, source) in enumerate(train_rows, 1)
    ]
    dev_sentences = [
        to_conllu_sentence(f"zipsurf_dev_{i:08d}", form, lemma, upos, xpos, source)
        for i, (form, lemma, upos, xpos, source) in enumerate(dev_rows, 1)
    ]

    TRAIN_OUT.write_text("\n\n".join(train_sentences) + "\n\n", encoding="utf-8")
    DEV_OUT.write_text("\n\n".join(dev_sentences) + "\n\n", encoding="utf-8")

    REPORT_OUT.write_text(
        "\n".join(
            [
                f"zip={ZIP_PATH.name}",
                f"train={TRAIN_OUT.name}",
                f"dev={DEV_OUT.name}",
                f"rows_total={len(rows)}",
                f"rows_train={len(train_rows)}",
                f"rows_dev={len(dev_rows)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    rows = load_rows()
    write_split(rows)
    print(TRAIN_OUT.name)
    print(DEV_OUT.name)
    print(len(rows))


if __name__ == "__main__":
    main()
