"""Verify the generated txt and conllu are aligned: for each split, confirm that
stripping paragraph separators from the txt yields the same byte sequence as the
conllu's # text lines joined by single \n (which is how Trankit treats intra-paragraph
whitespace)."""

import os

ROOT = r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_naturalpara_10k"

for split in ("train", "dev", "test"):
    txt_path = os.path.join(ROOT, "splits_txt", f"{split}.txt")
    conllu_path = os.path.join(ROOT, "splits", f"{split}.conllu")

    with open(txt_path, "r", encoding="utf-8") as f:
        txt = f.read()

    # Reconstruct: flatten paragraphs by replacing \n\n with \n, strip trailing \n
    txt_flat = txt.replace("\n\n", "\n").rstrip("\n")

    # Pull all # text lines from conllu
    texts = []
    with open(conllu_path, "r", encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("# text = "):
                texts.append(ln[len("# text = "):].rstrip("\n"))
    conllu_flat = "\n".join(texts)

    match = txt_flat == conllu_flat
    print(f"[{split}] txt_flat_len={len(txt_flat)}, conllu_flat_len={len(conllu_flat)}, match={match}, sents_in_conllu={len(texts)}")
    if not match:
        # Find first divergence
        for i, (a, b) in enumerate(zip(txt_flat, conllu_flat)):
            if a != b:
                print(f"  first diff at char {i}: txt={a!r}({ord(a):04x}) conllu={b!r}({ord(b):04x})")
                print(f"  txt context:    ...{txt_flat[max(0,i-30):i+30]!r}")
                print(f"  conllu context: ...{conllu_flat[max(0,i-30):i+30]!r}")
                break
        if len(txt_flat) != len(conllu_flat):
            print(f"  length diff: {len(txt_flat) - len(conllu_flat)}")
