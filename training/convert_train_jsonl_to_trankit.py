from __future__ import annotations

import argparse
import json
import re
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "train.jsonl"
DEFAULT_PREFIX = "sa_lattice_trankit"
DEFAULT_PARAGRAPH_SIZE = 20
DEFAULT_DEV_MOD = 10
DEFAULT_DEV_REMAINDER = 0
MAX_OPTIONS_PER_SLOT = 12
BEAM_SIZE = 128


IAST_TO_LATTICE = {
    "\u006d\u0310": "~",
    "\u006b\u0068": "K",
    "\u0067\u0068": "G",
    "\u0063\u0068": "C",
    "\u006a\u0068": "J",
    "\u1e6d\u0068": "W",
    "\u1e0d\u0068": "Q",
    "\u0074\u0068": "T",
    "\u0064\u0068": "D",
    "\u0070\u0068": "P",
    "\u0062\u0068": "B",
    "\u0061\u0069": "E",
    "\u0061\u0075": "O",
    "\u0061": "a",
    "\u0101": "A",
    "\u0069": "i",
    "\u012b": "I",
    "\u0075": "u",
    "\u016b": "U",
    "\u1e5b": "f",
    "\u1e5d": "F",
    "\u1e37": "x",
    "\u1e39": "X",
    "\u0065": "e",
    "\u006f": "o",
    "\u006b": "k",
    "\u0067": "g",
    "\u1e45": "N",
    "\u0063": "c",
    "\u006a": "j",
    "\u00f1": "Y",
    "\u1e6d": "w",
    "\u1e0d": "q",
    "\u1e47": "R",
    "\u0074": "t",
    "\u0064": "d",
    "\u006e": "n",
    "\u0070": "p",
    "\u0062": "b",
    "\u006d": "m",
    "\u0079": "y",
    "\u0072": "r",
    "\u006c": "l",
    "\u0076": "v",
    "\u015b": "S",
    "\u1e63": "z",
    "\u0073": "s",
    "\u0068": "h",
    "\u1e43": "M",
    "\u1e41": "M",
    "\u1e25": "H",
    "\u2019": "'",
    "\u0027": "'",
    "\u002d": "-",
    "\u0020": " ",
}


@dataclass(frozen=True)
class Candidate:
    cid: str
    word: str
    lemma: str
    morph: str
    cng: str
    position: int
    length: int


@dataclass
class ChunkSelection:
    forms: list[str]
    lemmas: list[str]
    upos: list[str]
    strong_matches: int
    token_count: int


@dataclass
class SentenceExample:
    sent_id: str
    synthetic_text: str
    original_text: str
    forms: list[str]
    lemmas: list[str]
    upos: list[str]


@dataclass(frozen=True)
class BeamState:
    score: float
    exact_lemma_count: int
    exact_tag_count: int
    strong_count: int
    positive_count: int
    last_positive_position: int
    used_ids: frozenset[str]
    chosen: tuple[Candidate, ...]


def iast_to_lattice(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    i = 0
    while i < len(text):
        pair = text[i : i + 2]
        if pair in IAST_TO_LATTICE:
            out.append(IAST_TO_LATTICE[pair])
            i += 2
            continue
        ch = text[i]
        out.append(IAST_TO_LATTICE.get(ch, ch))
        i += 1
    return "".join(out)


def normalize_candidate(raw: dict) -> Candidate:
    return Candidate(
        cid=str(raw["id"]),
        word=str(raw["word"]),
        lemma=str(raw["lemma"]),
        morph=str(raw.get("morph", "")),
        cng=str(raw["cng"]),
        position=int(raw["position"]),
        length=int(raw["length"]),
    )


CASE_PREFIXES = ("nom.", "acc.", "ins.", "dat.", "abl.", "gen.", "loc.", "voc.")
VERB_PREFIXES = (
    "pr.",
    "ipf.",
    "impf.",
    "fut.",
    "pf.",
    "perf.",
    "aor.",
    "opt.",
    "impv.",
    "ben.",
    "cond.",
    "inj.",
    "subj.",
    "pft.",
    "ppf.",
    "caus.",
    "desid.",
    "intens.",
    "pfp.",
    "ger.",
    "inf.",
    "abs.",
)


def infer_upos(candidate: Candidate) -> str:
    morph = candidate.morph.strip().lower()
    if not morph:
        return "X"

    if "conj." in morph:
        return "CCONJ"
    if "adv." in morph:
        return "ADV"
    if "prep." in morph or "postp." in morph:
        return "ADP"
    if "interj." in morph:
        return "INTJ"
    if "part." in morph:
        return "PART"
    if "pron." in morph:
        return "PRON"
    if "num." in morph or "card." in morph or "ord." in morph:
        return "NUM"
    if morph.startswith(VERB_PREFIXES) or "[" in morph or re.search(r"\b[123]\b", morph):
        return "VERB"
    if morph.startswith(CASE_PREFIXES) or "iic." in morph:
        return "NOUN"
    return "X"


def slot_score(
    candidate: Candidate, gold_lemma: str, gold_tag: str, slot_index: int
) -> tuple[float, bool, bool]:
    lemma_exact = candidate.lemma == gold_lemma
    tag_exact = candidate.cng == gold_tag
    lemma_soft = gold_lemma in candidate.lemma or candidate.lemma in gold_lemma

    score = 0.0
    if lemma_exact:
        score += 14.0
    if tag_exact:
        score += 10.0
    if lemma_soft:
        score += 3.0
    if candidate.position >= 0:
        score += 2.0
    else:
        score -= 2.0
    if slot_index == 0 and candidate.position == 0:
        score += 2.5
    score += candidate.length / 1000.0
    score += len(candidate.word) / 1000.0
    return score, lemma_exact, tag_exact


def beam_key(state: BeamState) -> tuple[float, int, int, int, int, int]:
    return (
        state.score,
        state.strong_count,
        state.exact_lemma_count,
        state.exact_tag_count,
        state.positive_count,
        -state.last_positive_position,
    )


def choose_chunk_candidates(
    candidates: list[Candidate], gold_lemmas: list[str], gold_tags: list[str]
) -> ChunkSelection | None:
    if not gold_lemmas:
        return None

    gold_lemmas_lattice = [iast_to_lattice(item) for item in gold_lemmas]
    gold_tags = [str(item) for item in gold_tags]

    slot_options: list[list[tuple[Candidate, float, bool, bool]]] = []
    for slot_index, (gold_lemma, gold_tag) in enumerate(zip(gold_lemmas_lattice, gold_tags)):
        scored = []
        for candidate in candidates:
            token_score, lemma_exact, tag_exact = slot_score(
                candidate, gold_lemma, gold_tag, slot_index
            )
            scored.append((candidate, token_score, lemma_exact, tag_exact))
        scored.sort(
            key=lambda item: (item[1], item[2], item[3], item[0].position >= 0, item[0].length),
            reverse=True,
        )
        slot_options.append(scored[:MAX_OPTIONS_PER_SLOT])

    beams = [
        BeamState(
            score=0.0,
            exact_lemma_count=0,
            exact_tag_count=0,
            strong_count=0,
            positive_count=0,
            last_positive_position=-1,
            used_ids=frozenset(),
            chosen=(),
        )
    ]

    for slot_index, options in enumerate(slot_options):
        next_beams: list[BeamState] = []
        for state in beams:
            for candidate, token_score, lemma_exact, tag_exact in options:
                if candidate.cid in state.used_ids:
                    continue
                if candidate.position >= 0 and candidate.position <= state.last_positive_position:
                    continue
                next_beams.append(
                    BeamState(
                        score=state.score + token_score,
                        exact_lemma_count=state.exact_lemma_count + int(lemma_exact),
                        exact_tag_count=state.exact_tag_count + int(tag_exact),
                        strong_count=state.strong_count + int(lemma_exact or tag_exact),
                        positive_count=state.positive_count + int(candidate.position >= 0),
                        last_positive_position=(
                            candidate.position
                            if candidate.position >= 0
                            else state.last_positive_position
                        ),
                        used_ids=state.used_ids | {candidate.cid},
                        chosen=state.chosen + (candidate,),
                    )
                )
        if not next_beams:
            return None
        next_beams.sort(key=beam_key, reverse=True)
        beams = next_beams[:BEAM_SIZE]

    best = max(beams, key=beam_key)
    if best.strong_count < len(gold_lemmas):
        return None

    forms = [candidate.word for candidate in best.chosen]
    lemmas = [candidate.lemma for candidate in best.chosen]
    upos = [infer_upos(candidate) for candidate in best.chosen]
    return ChunkSelection(
        forms=forms,
        lemmas=lemmas,
        upos=upos,
        strong_matches=best.strong_count,
        token_count=len(forms),
    )


def build_example(record: dict) -> SentenceExample | None:
    grouped_candidates: dict[int, list[Candidate]] = {}
    for raw_candidate in record["candidates"]:
        candidate = normalize_candidate(raw_candidate)
        chunk_no = int(raw_candidate["chunk_no"])
        grouped_candidates.setdefault(chunk_no, []).append(candidate)

    forms: list[str] = []
    lemmas: list[str] = []
    upos: list[str] = []
    chunk_texts: list[str] = []

    for chunk_index, (gold_lemmas, gold_tags) in enumerate(
        zip(record["lemmas"], record["morph_tags"]), start=1
    ):
        candidates = grouped_candidates.get(chunk_index)
        if not candidates:
            return None
        selection = choose_chunk_candidates(candidates, list(gold_lemmas), list(gold_tags))
        if selection is None:
            return None
        forms.extend(selection.forms)
        lemmas.extend(selection.lemmas)
        upos.extend(selection.upos)
        chunk_texts.append("".join(selection.forms))

    if not forms:
        return None

    synthetic_text = " ".join(chunk_texts)
    return SentenceExample(
        sent_id=str(record["id"]),
        synthetic_text=synthetic_text,
        original_text=str(record["sentence"]),
        forms=forms,
        lemmas=lemmas,
        upos=upos,
    )


def iter_jsonl(path: Path, limit: int | None = None) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if limit is not None and index >= limit:
                break
            yield json.loads(line)


def split_name(sent_id: str, dev_mod: int, dev_remainder: int) -> str:
    try:
        numeric = int(sent_id)
    except ValueError:
        numeric = zlib.crc32(sent_id.encode("utf-8")) & 0xFFFFFFFF
    return "dev" if numeric % dev_mod == dev_remainder else "train"


def format_conllu_block(example: SentenceExample) -> str:
    lines = [
        f"# sent_id = {example.sent_id}",
        f"# text = {example.synthetic_text}",
        f"# orig_text = {example.original_text}",
    ]
    for index, (form, lemma, upos) in enumerate(
        zip(example.forms, example.lemmas, example.upos), start=1
    ):
        head = "0" if index == 1 else "1"
        deprel = "root" if index == 1 else "dep"
        lines.append(f"{index}\t{form}\t{lemma}\t{upos}\t_\t_\t{head}\t{deprel}\t_\t_")
    return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    prefix: str,
    split_name_value: str,
    examples: list[SentenceExample],
    paragraph_size: int,
) -> tuple[Path, Path]:
    txt_path = out_dir / f"{prefix}-{split_name_value}.txt"
    conllu_path = out_dir / f"{prefix}-{split_name_value}.conllu"

    paragraphs: list[str] = []
    for start in range(0, len(examples), paragraph_size):
        batch = examples[start : start + paragraph_size]
        paragraphs.append("\n".join(example.synthetic_text for example in batch))

    txt_path.write_text("\n\n".join(paragraphs) + ("\n" if paragraphs else ""), encoding="utf-8")
    conllu_blocks = [format_conllu_block(example) for example in examples]
    conllu_path.write_text(
        "\n\n".join(conllu_blocks) + ("\n\n" if conllu_blocks else ""), encoding="utf-8"
    )
    return txt_path, conllu_path


def build_datasets(
    input_path: Path,
    out_dir: Path,
    prefix: str,
    paragraph_size: int,
    dev_mod: int,
    dev_remainder: int,
    limit: int | None,
) -> dict:
    train_examples: list[SentenceExample] = []
    dev_examples: list[SentenceExample] = []
    skipped_ids: list[str] = []

    total_records = 0
    for record in iter_jsonl(input_path, limit=limit):
        total_records += 1
        example = build_example(record)
        if example is None:
            skipped_ids.append(str(record["id"]))
            continue
        split = split_name(example.sent_id, dev_mod=dev_mod, dev_remainder=dev_remainder)
        if split == "dev":
            dev_examples.append(example)
        else:
            train_examples.append(example)

    train_txt, train_conllu = write_outputs(
        out_dir, prefix, "train", train_examples, paragraph_size
    )
    dev_txt, dev_conllu = write_outputs(out_dir, prefix, "dev", dev_examples, paragraph_size)

    stats = {
        "input_path": str(input_path),
        "total_records": total_records,
        "written_records": len(train_examples) + len(dev_examples),
        "skipped_records": len(skipped_ids),
        "train_records": len(train_examples),
        "dev_records": len(dev_examples),
        "train_txt": str(train_txt),
        "train_conllu": str(train_conllu),
        "dev_txt": str(dev_txt),
        "dev_conllu": str(dev_conllu),
        "paragraph_size": paragraph_size,
        "dev_mod": dev_mod,
        "dev_remainder": dev_remainder,
        "skipped_ids_preview": skipped_ids[:100],
    }

    stats_path = out_dir / f"{prefix}-stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=BASE_DIR)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--paragraph-size", type=int, default=DEFAULT_PARAGRAPH_SIZE)
    parser.add_argument("--dev-mod", type=int, default=DEFAULT_DEV_MOD)
    parser.add_argument("--dev-remainder", type=int, default=DEFAULT_DEV_REMAINDER)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = build_datasets(
        input_path=args.input,
        out_dir=args.out_dir,
        prefix=args.prefix,
        paragraph_size=args.paragraph_size,
        dev_mod=args.dev_mod,
        dev_remainder=args.dev_remainder,
        limit=args.limit,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
