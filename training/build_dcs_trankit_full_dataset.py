import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


ROOT = Path(__file__).resolve().parents[1]
FILES_DIR = ROOT / "files"
CHAPTER_INFO_PATH = FILES_DIR / "chapter-info.xml"
OUTPUT_DIR = ROOT / "training" / "dcs_sanskrit_trankit_full"

DEV_MODULUS = 10
DEV_REMAINDER = 0


@dataclass
class SentenceStats:
    sentences: int = 0
    token_rows: int = 0
    mwt_rows: int = 0
    empty_nodes: int = 0
    blank_head_rows_filled: int = 0
    blank_deprel_rows_filled: int = 0


def ordered_chapter_paths() -> List[str]:
    xml_paths: List[str] = []
    if CHAPTER_INFO_PATH.exists():
        root = ET.parse(CHAPTER_INFO_PATH).getroot()
        for chapter in root.findall(".//chapter"):
            rel = (chapter.findtext("path") or "").strip().replace("\\", "/")
            if rel:
                xml_paths.append(rel)
    existing = {
        str(path.relative_to(FILES_DIR)).replace("\\", "/") for path in FILES_DIR.rglob("*.conllu")
    }
    ordered = [rel for rel in xml_paths if rel in existing]
    missing = sorted(existing - set(ordered))
    ordered.extend(missing)
    return ordered


def chapter_text_lines(path: Path) -> List[str]:
    out: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("# text = "):
                out.append(line[len("# text = ") :].rstrip("\n"))
    return out


def chapter_surface_text_lines(path: Path) -> List[str]:
    sentences: List[str] = []
    surface_tokens: List[str] = []
    mwtbegin = None
    mwtend = None

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line:
                if surface_tokens:
                    sentences.append(" ".join(surface_tokens))
                    surface_tokens = []
                mwtbegin = None
                mwtend = None
                continue
            if line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 10:
                continue
            tok_id = cols[0]
            form = cols[1]
            if "." in tok_id:
                continue
            if "-" in tok_id:
                surface_tokens.append(form)
                start, end = tok_id.split("-", 1)
                mwtbegin = int(start)
                mwtend = int(end)
                continue
            if mwtbegin is not None and mwtend is not None and mwtbegin <= int(tok_id) <= mwtend:
                if int(tok_id) == mwtend:
                    mwtbegin = None
                    mwtend = None
                continue
            surface_tokens.append(form)

    if surface_tokens:
        sentences.append(" ".join(surface_tokens))

    return sentences


def finalize_sentence(block_lines: List[str], stats: SentenceStats) -> List[str]:
    if not block_lines:
        return []

    stats.sentences += 1
    token_records = []
    root_id = None
    has_blank_head = False
    has_blank_deprel = False

    for idx, line in enumerate(block_lines):
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            continue
        tok_id = cols[0]
        if "-" in tok_id:
            stats.mwt_rows += 1
            continue
        if "." in tok_id:
            stats.empty_nodes += 1
            continue
        stats.token_rows += 1
        token_records.append((idx, cols))
        if cols[6] == "0":
            root_id = tok_id
        if cols[6] in {"", "_"}:
            has_blank_head = True
        if cols[7] in {"", "_"}:
            has_blank_deprel = True

    if not token_records:
        return block_lines

    if root_id is None:
        root_id = token_records[0][1][0]

    if has_blank_head or has_blank_deprel:
        for idx, cols in token_records:
            tok_id = cols[0]
            if cols[6] in {"", "_"}:
                if tok_id == root_id:
                    cols[6] = "0"
                else:
                    cols[6] = str(root_id)
                stats.blank_head_rows_filled += 1
            if cols[7] in {"", "_"}:
                cols[7] = "root" if cols[6] == "0" else "dep"
                stats.blank_deprel_rows_filled += 1
            block_lines[idx] = "\t".join(cols)

    return block_lines


def chapter_conllu_lines(path: Path, stats: SentenceStats) -> List[str]:
    output: List[str] = []
    sentence_block: List[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line == "":
                if sentence_block:
                    output.extend(finalize_sentence(sentence_block, stats))
                    output.append("")
                    sentence_block = []
                else:
                    output.append("")
                continue
            sentence_block.append(line)

    if sentence_block:
        output.extend(finalize_sentence(sentence_block, stats))
        output.append("")

    return output


def write_text_export(paths: Iterable[str], out_path: Path) -> int:
    chapter_count = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for rel in paths:
            lines = chapter_surface_text_lines(FILES_DIR / rel)
            if not lines:
                continue
            handle.write("\n".join(lines))
            handle.write("\n\n")
            chapter_count += 1
    return chapter_count


def write_conllu_export(paths: Iterable[str], out_path: Path) -> SentenceStats:
    stats = SentenceStats()
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for rel in paths:
            lines = chapter_conllu_lines(FILES_DIR / rel, stats)
            if not lines:
                continue
            handle.write("\n".join(lines))
            if not lines[-1].endswith("\n"):
                handle.write("\n")
    return stats


def write_manifest(paths: Iterable[str], out_path: Path) -> None:
    data = "\n".join(paths)
    if data:
        data += "\n"
    out_path.write_text(data, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ordered = ordered_chapter_paths()
    train_paths: List[str] = []
    dev_paths: List[str] = []
    for idx, rel in enumerate(ordered):
        if idx % DEV_MODULUS == DEV_REMAINDER:
            dev_paths.append(rel)
        else:
            train_paths.append(rel)

    write_manifest(ordered, OUTPUT_DIR / "all_chapters.txt")
    write_manifest(train_paths, OUTPUT_DIR / "train_chapters.txt")
    write_manifest(dev_paths, OUTPUT_DIR / "dev_chapters.txt")

    train_text_chapters = write_text_export(train_paths, OUTPUT_DIR / "train.txt")
    dev_text_chapters = write_text_export(dev_paths, OUTPUT_DIR / "dev.txt")
    train_stats = write_conllu_export(train_paths, OUTPUT_DIR / "train.conllu")
    dev_stats = write_conllu_export(dev_paths, OUTPUT_DIR / "dev.conllu")

    stats = {
        "source_dir": str(FILES_DIR),
        "chapter_info": str(CHAPTER_INFO_PATH),
        "total_chapters": len(ordered),
        "train_chapters": len(train_paths),
        "dev_chapters": len(dev_paths),
        "train_text_chapters_written": train_text_chapters,
        "dev_text_chapters_written": dev_text_chapters,
        "split_rule": {
            "type": "chapter_level_modulus",
            "dev_modulus": DEV_MODULUS,
            "dev_remainder": DEV_REMAINDER,
        },
        "train_stats": train_stats.__dict__,
        "dev_stats": dev_stats.__dict__,
    }
    (OUTPUT_DIR / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
