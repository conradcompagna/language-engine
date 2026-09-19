from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
PERSEUS_DIR = APP_ROOT / "training" / "perseus"
DEFAULT_SOURCE = PERSEUS_DIR / "grc_trankit_minimal" / "grc_perseus_minimal_all.conllu"
DEFAULT_OUTPUT = PERSEUS_DIR / "grc_trankit_sampled_10000"


@dataclass(frozen=True)
class SentenceRecord:
    document: str
    sent_key: str
    order_key: tuple[int, int]
    block_lines: tuple[str, ...]
    text: str


def parse_conllu_records(path: Path) -> list[SentenceRecord]:
    text = path.read_text(encoding="utf-8")
    blocks = [block for block in text.split("\n\n") if block.strip()]
    records: list[SentenceRecord] = []
    current_doc = ""
    doc_order_map: dict[str, int] = {}
    doc_sent_index: Counter[str] = Counter()

    for block in blocks:
        lines = [line for line in block.splitlines() if line]
        local_lines: list[str] = []
        sent_key = ""
        sent_text = ""
        for line in lines:
            if line.startswith("# newdoc id = "):
                current_doc = line.split("=", 1)[1].strip()
                if current_doc not in doc_order_map:
                    doc_order_map[current_doc] = len(doc_order_map)
                continue
            if line.startswith("# sent_id = "):
                sent_key = line.split("=", 1)[1].strip()
            elif line.startswith("# text = "):
                sent_text = line.split("=", 1)[1].strip()
            local_lines.append(line)
        if not current_doc:
            raise ValueError("Encountered sentence block before any # newdoc id comment.")
        doc_sent_index[current_doc] += 1
        records.append(
            SentenceRecord(
                document=current_doc,
                sent_key=sent_key,
                order_key=(doc_order_map[current_doc], doc_sent_index[current_doc]),
                block_lines=tuple(local_lines),
                text=sent_text,
            )
        )
    return records


def allocate_doc_sample_sizes(counts: dict[str, int], sample_size: int) -> dict[str, int]:
    docs = list(counts)
    total = sum(counts.values())
    if sample_size <= 0 or sample_size > total:
        raise ValueError(f"sample_size must be between 1 and {total}")

    if sample_size < len(docs):
        raise ValueError("sample_size is smaller than the number of documents; cannot sample from all files.")

    allocations = {doc: 1 for doc in docs}
    remaining = sample_size - len(docs)
    weights = {doc: counts[doc] - 1 for doc in docs}
    weight_total = sum(weights.values())
    fractional: list[tuple[float, str]] = []

    if weight_total > 0:
        for doc in docs:
            exact = remaining * (weights[doc] / weight_total)
            extra = int(exact)
            allocations[doc] += extra
            fractional.append((exact - extra, doc))
        assigned = sum(allocations.values())
        leftover = sample_size - assigned
        for _, doc in sorted(fractional, reverse=True)[:leftover]:
            allocations[doc] += 1

    diff = sample_size - sum(allocations.values())
    if diff != 0:
        ordered = sorted(docs, key=lambda doc: counts[doc], reverse=True)
        step = 1 if diff > 0 else -1
        while diff != 0:
            for doc in ordered:
                next_value = allocations[doc] + step
                if next_value < 1 or next_value > counts[doc]:
                    continue
                allocations[doc] = next_value
                diff -= step
                if diff == 0:
                    break

    for doc, amount in allocations.items():
        if amount < 1 or amount > counts[doc]:
            raise ValueError(f"Invalid allocation for {doc}: {amount} / {counts[doc]}")
    return allocations


def render_records_to_conllu(records: list[SentenceRecord]) -> str:
    blocks: list[str] = []
    last_doc = None
    for record in records:
        lines = list(record.block_lines)
        if record.document != last_doc:
            lines.insert(0, f"# newdoc id = {record.document}")
            last_doc = record.document
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks).rstrip() + "\n\n"


def render_records_to_txt(records: list[SentenceRecord]) -> str:
    return "\n".join(record.text for record in records).rstrip() + "\n"


def split_records(records: list[SentenceRecord], seed: int) -> dict[str, list[SentenceRecord]]:
    shuffled = list(records)
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    total = len(shuffled)
    dev_count = total // 10
    test_count = total // 10
    train_count = total - dev_count - test_count

    buckets = {
        "train": shuffled[:train_count],
        "dev": shuffled[train_count:train_count + dev_count],
        "test": shuffled[train_count + dev_count:],
    }
    for key in buckets:
        buckets[key] = sorted(buckets[key], key=lambda record: record.order_key)
    return buckets


def write_subset(output_dir: Path, records: list[SentenceRecord], seed: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    splits_dir = output_dir / "splits"
    splits_txt_dir = output_dir / "splits_txt"
    splits_dir.mkdir(parents=True, exist_ok=True)
    splits_txt_dir.mkdir(parents=True, exist_ok=True)

    ordered_records = sorted(records, key=lambda record: record.order_key)
    (output_dir / "all.conllu").write_text(render_records_to_conllu(ordered_records), encoding="utf-8")
    (output_dir / "all.txt").write_text(render_records_to_txt(ordered_records), encoding="utf-8")

    split_map = split_records(ordered_records, seed + 1)
    split_summary = {}
    for split_name, split_records_list in split_map.items():
        (splits_dir / f"{split_name}.conllu").write_text(
            render_records_to_conllu(split_records_list),
            encoding="utf-8",
        )
        (splits_txt_dir / f"{split_name}.txt").write_text(
            render_records_to_txt(split_records_list),
            encoding="utf-8",
        )
        doc_counts = Counter(record.document for record in split_records_list)
        split_summary[split_name] = {
            "sentence_count": len(split_records_list),
            "document_count": len(doc_counts),
            "documents": dict(sorted(doc_counts.items())),
        }

    full_doc_counts = Counter(record.document for record in ordered_records)
    summary = {
        "sample_sentence_count": len(ordered_records),
        "document_count": len(full_doc_counts),
        "seed": seed,
        "documents": dict(sorted(full_doc_counts.items())),
        "splits": split_summary,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a deterministic sampled subset from the generated Perseus CoNLL-U export.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1729)
    args = parser.parse_args()

    records = parse_conllu_records(args.source)
    by_doc: dict[str, list[SentenceRecord]] = defaultdict(list)
    for record in records:
        by_doc[record.document].append(record)

    allocations = allocate_doc_sample_sizes(
        {doc: len(doc_records) for doc, doc_records in by_doc.items()},
        args.sample_size,
    )
    rng = random.Random(args.seed)
    sampled: list[SentenceRecord] = []
    for doc, doc_records in by_doc.items():
        chosen = rng.sample(doc_records, allocations[doc])
        sampled.extend(chosen)

    summary = write_subset(args.output_dir, sampled, args.seed)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
