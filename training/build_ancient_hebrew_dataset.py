"""
Build Trankit training datasets for Ancient Hebrew (hbo_ptnk UD treebank).

Produces in ./ancient_hebrew/:
  - hbo-train.conllu / hbo-dev.conllu   (posdep, mwt, lemmatize — full CoNLL-U)
  - hbo-train.txt    / hbo-dev.txt       (tokenize — surface text, one sentence per line)

The surface .txt files reconstruct the pre-tokenization surface form from MWT
rows (X-Y spans), falling back to regular token forms where no MWT is present.
"""

from pathlib import Path

RARELANGS = Path(__file__).resolve().parent / "rarelangs"
OUT = Path(__file__).resolve().parent / "ancient_hebrew"
OUT.mkdir(exist_ok=True)

SPLITS = {
    "train": RARELANGS / "hbo_ptnk-ud-train.conllu",
    "dev":   RARELANGS / "hbo_ptnk-ud-dev.conllu",
}


def sentence_blocks(path: Path):
    """Yield (comment_lines, token_lines) for each sentence in a CoNLL-U file."""
    comments = []
    tokens = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith("#"):
                comments.append(line)
            elif line == "":
                if tokens:
                    yield comments, tokens
                comments, tokens = [], []
            else:
                tokens.append(line)
    if tokens:
        yield comments, tokens


def surface_text_from_block(token_lines):
    """
    Reconstruct the surface (pre-tokenization) text for one sentence.
    MWT rows (id like '1-2') give the surface form; their component rows are skipped
    from the surface reconstruction. Maqqef-joined tokens (SpaceAfter=No on the
    preceding token) are joined without a space.
    """
    surface = []
    mwt_end = -1

    for line in token_lines:
        cols = line.split("\t")
        if len(cols) != 10:
            continue
        tok_id, form = cols[0], cols[1]
        misc = cols[9]

        # Skip empty nodes
        if "." in tok_id:
            continue

        if "-" in tok_id:
            # MWT row — use this as the surface token
            start, end = tok_id.split("-")
            mwt_end = int(end)
            no_space = "SpaceAfter=No" in misc
            surface.append((form, no_space))
        else:
            idx = int(tok_id)
            if idx <= mwt_end:
                # Sub-token covered by MWT — skip
                continue
            no_space = "SpaceAfter=No" in misc
            surface.append((form, no_space))

    # Join respecting SpaceAfter
    result = []
    for i, (form, no_space) in enumerate(surface):
        result.append(form)
        if i < len(surface) - 1 and not no_space:
            result.append(" ")
    return "".join(result)


def write_split(split_name: str, src: Path):
    out_conllu = OUT / f"hbo-{split_name}.conllu"
    out_txt    = OUT / f"hbo-{split_name}.txt"

    sentences_written = 0
    with out_conllu.open("w", encoding="utf-8") as fc, \
         out_txt.open("w", encoding="utf-8") as ft:

        for comments, tokens in sentence_blocks(src):
            # Write full CoNLL-U block (unchanged)
            for c in comments:
                fc.write(c + "\n")
            for t in tokens:
                fc.write(t + "\n")
            fc.write("\n")

            # Write surface text line
            surface = surface_text_from_block(tokens)
            ft.write(surface + "\n")
            sentences_written += 1

    print(f"[{split_name}] {sentences_written} sentences -> {out_conllu.name}, {out_txt.name}")


def main():
    for split_name, src in SPLITS.items():
        if not src.exists():
            print(f"WARNING: {src} not found, skipping.")
            continue
        write_split(split_name, src)

    print("\nDone. Files written to:", OUT)
    print("\nAll four tasks (tokenize, mwt, posdep, lemmatize) can use these files:")
    print("  train_conllu_fpath  -> ancient_hebrew/hbo-train.conllu")
    print("  dev_conllu_fpath    -> ancient_hebrew/hbo-dev.conllu")
    print("  train_txt_fpath     -> ancient_hebrew/hbo-train.txt   (tokenize only)")
    print("  dev_txt_fpath       -> ancient_hebrew/hbo-dev.txt     (tokenize only)")


if __name__ == "__main__":
    main()
