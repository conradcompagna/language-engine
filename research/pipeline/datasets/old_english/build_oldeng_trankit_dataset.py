from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
SOURCE_SPLITS = ("train", "dev", "test")
OUTPUT_SPLITS = ("train", "dev")
PREFIX = "ang_oedt-ud"
DEV_RATIO = 0.10


@dataclass
class SentenceBlock:
    sent_id: str
    text: str
    raw_block: str
    group_key: str
    source_split: str


def input_path(split: str) -> Path:
    return BASE_DIR / f"{PREFIX}-{split}.conllu"


def grouped_conllu_path(split: str) -> Path:
    return BASE_DIR / f"{PREFIX}-{split}.grouped.conllu"


def raw_text_path(split: str) -> Path:
    return BASE_DIR / f"{PREFIX}-{split}.txt"


def lemmafill_conllu_path(split: str) -> Path:
    return BASE_DIR / f"{PREFIX}-{split}.lemmafill.conllu"


def derive_group_key(sent_id: str, fallback_index: int) -> str:
    cleaned = sent_id.strip().strip(".")
    if not cleaned:
        return f"_unknown_{fallback_index:06d}"

    parts = cleaned.split(".")
    if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit():
        return ".".join(parts[:-2])
    if len(parts) > 1:
        return ".".join(parts[:-1])
    return cleaned


def reconstruct_surface_text(block_lines: Iterable[str]) -> str:
    pieces: list[str] = []
    mwt_start = None
    mwt_end = None

    for line in block_lines:
        if not line or line.startswith("#"):
            continue

        cols = line.split("\t")
        if len(cols) != 10:
            continue

        tok_id = cols[0]
        form = cols[1]
        misc = cols[9]

        if "." in tok_id:
            continue
        if "-" in tok_id:
            pieces.append(form)
            start, end = tok_id.split("-", 1)
            mwt_start = int(start)
            mwt_end = int(end)
            continue

        numeric_id = int(tok_id)
        if mwt_start is not None and mwt_end is not None and mwt_start <= numeric_id <= mwt_end:
            if numeric_id == mwt_end:
                mwt_start = None
                mwt_end = None
            continue

        pieces.append(form)
        if misc == "SpaceAfter=No":
            continue
        if misc == r"SpacesAfter=\n":
            pieces.append("\n")
            continue
        pieces.append(" ")

    return "".join(pieces).rstrip(" \n")


def parse_sentences(conllu_path: Path, source_split: str) -> list[SentenceBlock]:
    sentences: list[SentenceBlock] = []
    block_lines: list[str] = []
    sent_id = ""

    def flush_block() -> None:
        nonlocal block_lines, sent_id
        if not block_lines:
            return
        block_index = len(sentences) + 1
        resolved_text = reconstruct_surface_text(block_lines)
        group_key = derive_group_key(sent_id, block_index)
        sentences.append(
            SentenceBlock(
                sent_id=sent_id,
                text=resolved_text,
                raw_block="\n".join(block_lines),
                group_key=group_key,
                source_split=source_split,
            )
        )
        block_lines = []
        sent_id = ""

    for raw_line in conllu_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            flush_block()
            continue

        block_lines.append(line)
        if line.startswith("# sent_id = "):
            sent_id = line[len("# sent_id = ") :]

    flush_block()
    return sentences


def group_sentences(sentences: Iterable[SentenceBlock]) -> dict[str, list[SentenceBlock]]:
    grouped: dict[str, list[SentenceBlock]] = {}
    for sentence in sentences:
        unique_group_key = f"{sentence.source_split}:{sentence.group_key}"
        grouped.setdefault(unique_group_key, []).append(sentence)
    return grouped


def count_annotations(conllu_path: Path) -> dict[str, int]:
    stats = {
        "sentences": 0,
        "tokens": 0,
        "mwt_rows": 0,
        "empty_nodes": 0,
        "lemmas": 0,
        "upos": 0,
        "xpos": 0,
        "feats": 0,
        "head": 0,
        "deprel": 0,
        "deps": 0,
        "misc": 0,
    }

    for raw_line in conllu_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("# sent_id = "):
            stats["sentences"] += 1
            continue
        if not raw_line or raw_line.startswith("#"):
            continue

        cols = raw_line.split("\t")
        if len(cols) != 10:
            continue

        tok_id = cols[0]
        if "-" in tok_id:
            stats["mwt_rows"] += 1
            continue
        if "." in tok_id:
            stats["empty_nodes"] += 1
            continue

        stats["tokens"] += 1
        if cols[2] != "_":
            stats["lemmas"] += 1
        if cols[3] != "_":
            stats["upos"] += 1
        if cols[4] != "_":
            stats["xpos"] += 1
        if cols[5] != "_":
            stats["feats"] += 1
        if cols[6] != "_":
            stats["head"] += 1
        if cols[7] != "_":
            stats["deprel"] += 1
        if cols[8] != "_":
            stats["deps"] += 1
        if cols[9] != "_":
            stats["misc"] += 1

    return stats


def write_lemmafilled_conllu(source_conllu_path: Path, target_conllu_path: Path) -> int:
    backfilled = 0
    out_lines: list[str] = []

    for raw_line in source_conllu_path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            out_lines.append(raw_line)
            continue

        cols = raw_line.split("\t")
        if len(cols) != 10:
            out_lines.append(raw_line)
            continue

        tok_id = cols[0]
        if "-" not in tok_id and "." not in tok_id and cols[2] == "_":
            cols[2] = cols[1]
            backfilled += 1
        out_lines.append("\t".join(cols))

    target_conllu_path.write_text(
        "\n".join(out_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return backfilled


def write_outputs(split: str, grouped_docs: list[list[SentenceBlock]]) -> dict[str, object]:
    grouped = grouped_docs

    grouped_blocks: list[str] = []
    paragraph_texts: list[str] = []
    paragraph_lengths: list[int] = []

    for group_sentences_list in grouped:
        paragraph_lengths.append(len(group_sentences_list))
        paragraph_texts.append("\n".join(sentence.text for sentence in group_sentences_list))
        grouped_blocks.extend(sentence.raw_block for sentence in group_sentences_list)

    grouped_conllu_path(split).write_text(
        "\n\n".join(grouped_blocks) + "\n\n",
        encoding="utf-8",
        newline="\n",
    )
    raw_text_path(split).write_text(
        "\n\n".join(paragraph_texts) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lemmafill_count = write_lemmafilled_conllu(
        grouped_conllu_path(split),
        lemmafill_conllu_path(split),
    )

    annotation_stats = count_annotations(grouped_conllu_path(split))
    paragraph_avg = round(sum(paragraph_lengths) / len(paragraph_lengths), 2) if paragraph_lengths else 0.0
    return {
        "grouped_conllu": str(grouped_conllu_path(split).relative_to(BASE_DIR.parent.parent)),
        "raw_text": str(raw_text_path(split).relative_to(BASE_DIR.parent.parent)),
        "lemmafill_conllu": str(lemmafill_conllu_path(split).relative_to(BASE_DIR.parent.parent)),
        "paragraphs": len(grouped),
        "min_sentences_per_paragraph": min(paragraph_lengths) if paragraph_lengths else 0,
        "max_sentences_per_paragraph": max(paragraph_lengths) if paragraph_lengths else 0,
        "avg_sentences_per_paragraph": paragraph_avg,
        "lemma_backfilled_tokens": lemmafill_count,
        "annotation_stats": annotation_stats,
    }


def collect_all_grouped_docs() -> list[tuple[str, list[SentenceBlock]]]:
    grouped_docs: list[tuple[str, list[SentenceBlock]]] = []
    for split in SOURCE_SPLITS:
        sentences = parse_sentences(input_path(split), split)
        for unique_group_key, doc_sentences in group_sentences(sentences).items():
            grouped_docs.append((unique_group_key, doc_sentences))
    return grouped_docs


def split_grouped_docs(
    grouped_docs: list[tuple[str, list[SentenceBlock]]],
) -> tuple[list[list[SentenceBlock]], list[list[SentenceBlock]]]:
    if not grouped_docs:
        return [], []

    dev_target = max(1, round(len(grouped_docs) * DEV_RATIO))
    ranked_keys = sorted(
        grouped_docs,
        key=lambda item: hashlib.sha1(item[0].encode("utf-8")).hexdigest(),
    )
    dev_keys = {key for key, _ in ranked_keys[:dev_target]}

    train_docs: list[list[SentenceBlock]] = []
    dev_docs: list[list[SentenceBlock]] = []
    for unique_key, doc_sentences in grouped_docs:
        if unique_key in dev_keys:
            dev_docs.append(doc_sentences)
        else:
            train_docs.append(doc_sentences)
    return train_docs, dev_docs


def remove_stale_test_outputs() -> None:
    for path in (
        grouped_conllu_path("test"),
        raw_text_path("test"),
        lemmafill_conllu_path("test"),
    ):
        if path.exists():
            path.unlink()


def build_all() -> dict[str, object]:
    grouped_docs = collect_all_grouped_docs()
    train_docs, dev_docs = split_grouped_docs(grouped_docs)
    remove_stale_test_outputs()

    result = {
        "dataset": PREFIX,
        "base_dir": str(BASE_DIR.relative_to(BASE_DIR.parent.parent)),
        "raw_text_source": "reconstructed_from_token_rows_and_misc_spacing",
        "source_splits": list(SOURCE_SPLITS),
        "output_splits": list(OUTPUT_SPLITS),
        "split_strategy": {
            "type": "document_hash_split",
            "dev_ratio": DEV_RATIO,
            "unit": "grouped_document",
        },
        "grouping_rule": (
            "Use sent_id prefixes as paragraph/document groups. "
            "If there are at least four dot-separated parts and the last two are numeric, "
            "drop the final two parts; otherwise drop only the final part."
        ),
        "splits": {},
    }

    result["splits"]["train"] = write_outputs("train", train_docs)
    result["splits"]["dev"] = write_outputs("dev", dev_docs)

    stats_path = BASE_DIR / "ang_oedt-ud-trankit-stats.json"
    stats_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result


def main() -> None:
    stats = build_all()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
