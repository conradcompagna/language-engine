"""
Rebuild .txt files from existing .conllu files using the official UD format:
sentences joined by spaces, hard-wrapped at ~80 chars, blank lines only between
documents (# newdoc id boundaries).
"""

import textwrap
from pathlib import Path

SAMPLED_DIR = Path(__file__).resolve().parent / "grc_trankit_sampled_10000"
WRAP_WIDTH = 80


def conllu_to_paragraph_txt(conllu_path: Path) -> str:
    """Read a .conllu file and produce hard-wrapped text grouped by document."""
    documents: list[list[str]] = []
    current_doc: list[str] = []

    for line in conllu_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# newdoc id = "):
            if current_doc:
                documents.append(current_doc)
                current_doc = []
        elif line.startswith("# text = "):
            current_doc.append(line.split("=", 1)[1].strip())

    if current_doc:
        documents.append(current_doc)

    wrapped_blocks: list[str] = []
    for doc_sents in documents:
        continuous = " ".join(doc_sents)
        wrapped = textwrap.fill(continuous, width=WRAP_WIDTH)
        wrapped_blocks.append(wrapped)

    return "\n\n".join(wrapped_blocks) + "\n"


def main():
    for subdir in ["splits", "splits_txt"]:
        d = SAMPLED_DIR / subdir
        for conllu_file in sorted(d.glob("*.conllu")):
            txt_file = d.parent / "splits_txt" / (conllu_file.stem + ".txt")
            txt_file.write_text(conllu_to_paragraph_txt(conllu_file), encoding="utf-8")
            print(f"Rebuilt {txt_file}")

    all_conllu = SAMPLED_DIR / "all.conllu"
    if all_conllu.exists():
        all_txt = SAMPLED_DIR / "all.txt"
        all_txt.write_text(conllu_to_paragraph_txt(all_conllu), encoding="utf-8")
        print(f"Rebuilt {all_txt}")


if __name__ == "__main__":
    main()
