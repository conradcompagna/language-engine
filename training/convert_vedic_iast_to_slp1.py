from __future__ import annotations

import argparse
import unicodedata
from pathlib import Path

from convert_train_jsonl_to_trankit import IAST_TO_LATTICE


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_GLOBS = ("sa_vedic-ud-*.txt", "sa_vedic-ud-*.conllu")
TEXT_COMMENT_PREFIXES = ("# text = ", "# orig_text = ")
MISC_TEXT_KEYS = {"Unsandhied"}
MAX_KEY_LEN = max(len(key) for key in IAST_TO_LATTICE)


def iast_to_slp1(text: str) -> str:
    src = unicodedata.normalize("NFC", str(text or "")).lower()
    out: list[str] = []
    i = 0
    while i < len(src):
        matched = False
        for width in range(min(MAX_KEY_LEN, len(src) - i), 0, -1):
            chunk = src[i : i + width]
            repl = IAST_TO_LATTICE.get(chunk)
            if repl is None:
                continue
            out.append(repl)
            i += width
            matched = True
            break
        if matched:
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def transliterate_misc_field(value: str) -> str:
    if value == "_":
        return value
    items: list[str] = []
    for item in value.split("|"):
        if "=" not in item:
            items.append(item)
            continue
        key, raw_value = item.split("=", 1)
        if key in MISC_TEXT_KEYS:
            items.append(f"{key}={iast_to_slp1(raw_value)}")
        else:
            items.append(item)
    return "|".join(items)


def convert_conllu_line(line: str) -> str:
    if not line or line.startswith("#") is False:
        return line
    for prefix in TEXT_COMMENT_PREFIXES:
        if line.startswith(prefix):
            return prefix + iast_to_slp1(line[len(prefix) :])
    return line


def convert_conllu_contents(text: str) -> str:
    out_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            out_lines.append("")
            continue
        if line.startswith("#"):
            out_lines.append(convert_conllu_line(line))
            continue
        cols = line.split("\t")
        if len(cols) != 10:
            out_lines.append(line)
            continue
        cols[1] = iast_to_slp1(cols[1])
        cols[2] = iast_to_slp1(cols[2])
        cols[9] = transliterate_misc_field(cols[9])
        out_lines.append("\t".join(cols))
    return "\n".join(out_lines) + "\n"


def convert_plain_text(text: str) -> str:
    lines = text.splitlines()
    out_lines = [iast_to_slp1(line) if line else "" for line in lines]
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") or text else "")


def target_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}.slp1{path.suffix}")


def iter_sources(base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in DEFAULT_GLOBS:
        for path in sorted(base_dir.glob(pattern)):
            if ".slp1." in path.name or path.name.endswith(".bak"):
                continue
            paths.append(path)
    deduped = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def convert_file(path: Path) -> Path:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".conllu":
        converted = convert_conllu_contents(text)
    else:
        converted = convert_plain_text(text)
    out_path = target_path(path)
    out_path.write_text(converted, encoding="utf-8")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=BASE_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = [str(convert_file(path)) for path in iter_sources(args.base_dir)]
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
