from __future__ import annotations

import random
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ZIP_PATH = Path(__file__).resolve().parent / "ara-master (1).zip"
OUT_DIR = ZIP_PATH.parent
TAG = "ziplex_20260405a"
TRAIN_OUT = OUT_DIR / f"ara_zip_lemmatizer_{TAG}_train.conllu"
DEV_OUT = OUT_DIR / f"ara_zip_lemmatizer_{TAG}_dev.conllu"
REPORT_OUT = OUT_DIR / f"ara_zip_lemmatizer_{TAG}_report.txt"

DIAC_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
POS_MAP = {"N": "NOUN", "ADJ": "ADJ", "V": "VERB"}
SOURCE_WEIGHT = {"ara-master/ara_atb": 3, "ara-master/ara_new": 2, "ara-master/ara": 1}
RNG = random.Random(42)


def dediac(text: str) -> str:
    return DIAC_RE.sub("", text)


def to_conllu_sentence(sent_id: str, form: str, lemma: str, upos: str, source: str) -> str:
    return "\n".join(
        [
            f"# sent_id = {sent_id}",
            f"# text = {form}",
            f"# source = {source}",
            f"1\t{form}\t{lemma}\t{upos}\t{upos.lower()}\t_\t0\troot\t_\t_",
        ]
    )


def load_candidates() -> tuple[
    dict[tuple[str, str], Counter], dict[tuple[str, str, str], set[str]]
]:
    counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
    provenance: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        for member, weight in SOURCE_WEIGHT.items():
            lines = zf.read(member).decode("utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                lemma, form, feats = line.split("\t")
                upos = POS_MAP.get(feats.split(";", 1)[0])
                if not upos:
                    continue
                surface = dediac(form).strip()
                if not surface:
                    continue
                key = (surface, upos)
                counts[key][lemma] += weight
                provenance[(surface, upos, lemma)].add(member)
    return counts, provenance


def choose_canonical_entries(
    counts: dict[tuple[str, str], Counter],
    provenance: dict[tuple[str, str, str], set[str]],
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for (surface, upos), lemmas in counts.items():
        best_lemma, _ = sorted(
            lemmas.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
        prov = sorted(provenance[(surface, upos, best_lemma)])
        rows.append((surface, upos, best_lemma, ",".join(prov)))
    rows.sort()
    return rows


def write_split(rows: list[tuple[str, str, str, str]]) -> None:
    shuffled = rows[:]
    RNG.shuffle(shuffled)
    dev_size = max(1, round(len(shuffled) * 0.05))
    dev_rows = shuffled[:dev_size]
    train_rows = shuffled[dev_size:]

    train_sentences = [
        to_conllu_sentence(f"ziplem_train_{i:08d}", form, lemma, upos, source)
        for i, (form, upos, lemma, source) in enumerate(train_rows, 1)
    ]
    dev_sentences = [
        to_conllu_sentence(f"ziplem_dev_{i:08d}", form, lemma, upos, source)
        for i, (form, upos, lemma, source) in enumerate(dev_rows, 1)
    ]

    TRAIN_OUT.write_text("\n\n".join(train_sentences) + "\n\n", encoding="utf-8")
    DEV_OUT.write_text("\n\n".join(dev_sentences) + "\n\n", encoding="utf-8")

    report = [
        f"zip={ZIP_PATH.name}",
        f"train={TRAIN_OUT.name}",
        f"dev={DEV_OUT.name}",
        f"rows_total={len(rows)}",
        f"rows_train={len(train_rows)}",
        f"rows_dev={len(dev_rows)}",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    counts, provenance = load_candidates()
    rows = choose_canonical_entries(counts, provenance)
    write_split(rows)
    print(TRAIN_OUT.name)
    print(DEV_OUT.name)
    print(len(rows))


if __name__ == "__main__":
    main()
