import os

base_src = r"c:/Users/conra/Desktop/universal/training/commercialviable"
base_dst = r"c:/Users/conra/Desktop/universal/training/commercialviable_prepped"

languages = [
    dict(
        src_dir="UD_Ancient_Greek-PTNK",
        train="grc_ptnk-ud-train.conllu",
        dev="grc_ptnk-ud-dev.conllu",
        prefix="grc",
        out="ancient_greek",
    ),
    dict(
        src_dir="UD_Arabic-NYUAD",
        train="ar_nyuad-ud-train.conllu",
        dev="ar_nyuad-ud-dev.conllu",
        prefix="ar",
        out="arabic_nyuad",
    ),
    dict(
        src_dir="UD_Hebrew-IAHLTwiki",
        train="he_iahltwiki-ud-train.conllu",
        dev="he_iahltwiki-ud-dev.conllu",
        prefix="he",
        out="hebrew_iahltwiki",
    ),
    dict(
        src_dir="UD_Latin-LLCT",
        train="la_llct-ud-train.conllu",
        dev="la_llct-ud-dev.conllu",
        prefix="la",
        out="latin_llct",
    ),
    dict(
        src_dir="UD_Turkish-BOUN",
        train="tr_boun-ud-train.conllu",
        dev="tr_boun-ud-dev.conllu",
        prefix="tr",
        out="turkish_boun",
    ),
    dict(
        src_dir="UD_Greek-GUD",
        train="el_gud-ud-train.conllu",
        dev=None,
        prefix="el",
        out="modern_greek",
        split=True,
    ),
]


def parse_conllu(path):
    sentences = []
    current = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.strip() == "":
                if current:
                    sentences.append(current)
                    current = []
            else:
                current.append(line)
    if current:
        sentences.append(current)
    return sentences


def sentences_to_txt(sentences):
    lines = []
    for sent in sentences:
        tokens = []
        for line in sent:
            if line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            tok_id = cols[0]
            if "-" in tok_id:
                continue
            tokens.append(cols[1])
        lines.append(" ".join(tokens))
    return "\n".join(lines) + "\n"


def write_conllu(sentences, path):
    with open(path, "w", encoding="utf-8") as f:
        for sent in sentences:
            for line in sent:
                f.write(line + "\n")
            f.write("\n")


summary = {}

for lang in languages:
    src_dir = os.path.join(base_src, lang["src_dir"])
    dst_dir = os.path.join(base_dst, lang["out"])
    os.makedirs(dst_dir, exist_ok=True)
    prefix = lang["prefix"]

    train_src = os.path.join(src_dir, lang["train"])
    train_sentences = parse_conllu(train_src)

    if lang.get("split"):
        split_idx = int(len(train_sentences) * 0.9)
        dev_sentences = train_sentences[split_idx:]
        train_sentences = train_sentences[:split_idx]
    else:
        dev_src = os.path.join(src_dir, lang["dev"])
        dev_sentences = parse_conllu(dev_src)

    write_conllu(train_sentences, os.path.join(dst_dir, f"{prefix}-train.conllu"))
    write_conllu(dev_sentences, os.path.join(dst_dir, f"{prefix}-dev.conllu"))

    with open(os.path.join(dst_dir, f"{prefix}-train.txt"), "w", encoding="utf-8") as f:
        f.write(sentences_to_txt(train_sentences))
    with open(os.path.join(dst_dir, f"{prefix}-dev.txt"), "w", encoding="utf-8") as f:
        f.write(sentences_to_txt(dev_sentences))

    summary[lang["out"]] = {"train": len(train_sentences), "dev": len(dev_sentences)}

print("=== Summary: sentence counts ===")
for lang_out, counts in summary.items():
    print(f"  {lang_out}: train={counts['train']}, dev={counts['dev']}")
