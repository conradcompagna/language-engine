"""
Build a new Ancient Greek training split from grc_trankit_minimal/by_document/*.conllu
with natural paragraph structure (no arbitrary paragraphization, no random sampling).

Writes to training/perseus/grc_trankit_naturalpara_10k/ -- a brand new folder.
Source data is not modified.

Rules:
- Per-document order preserved (sentences remain in original sequence).
- Sentences with # text longer than MAX_SENT_CHARS are dropped (overlap pathology source).
- Within each document, consecutive sentences are packed into paragraphs up to MAX_PARA_CHARS.
  Paragraphs never cross document boundaries. No synthetic N-per-paragraph chunking.
- txt: sentences within paragraph joined by '\n', paragraphs separated by '\n\n'.
- conllu: sentences emitted in the exact same order as the txt file's paragraphs,
  with standard blank line between sentences. Paragraph structure is implicit in the
  txt (conllu has no extra blank lines between paragraphs -- Trankit uses the txt for
  paragraph segmentation and the conllu only for labels).

Train composition: all non-Homer train docs from summary.json (16 docs, prose).
Dev/test: all docs from the existing dev/test partitions.
"""

import os
import json

BASE = r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_minimal"
BY_DOC = os.path.join(BASE, "by_document")
SUMMARY = os.path.join(BASE, "summary.json")

OUT_DIR = (
    r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_naturalpara_10k"
)
OUT_CONLLU = os.path.join(OUT_DIR, "splits")
OUT_TXT = os.path.join(OUT_DIR, "splits_txt")

MAX_SENT_CHARS = 300  # drop sentences whose # text exceeds this
MAX_PARA_CHARS = 450  # cap paragraph size (safe margin under Trankit max_input_length=512)

# Homer is hexameter poetry; exclude from prose-focused train. Keeping 16 prose docs.
HOMER_DOCS = {
    "tlg0012.tlg001.perseus-grc1.tb.xml",  # Iliad
    "tlg0012.tlg002.perseus-grc1.tb.xml",  # Odyssey
}


def doc_stem(xml_name):
    # e.g. "tlg0003.tlg001.perseus-grc1.1.tb.xml" -> "tlg0003.tlg001.perseus-grc1.1.tb"
    if xml_name.endswith(".xml"):
        return xml_name[:-4]
    return xml_name


def parse_conllu(path):
    """Yield sentence dicts: {text, comments, token_lines, raw_block_str}."""
    with open(path, "r", encoding="utf-8") as f:
        buf = []
        for ln in f:
            if ln.strip() == "":
                if buf:
                    yield _sentence_from_buf(buf)
                    buf = []
            else:
                buf.append(ln.rstrip("\n"))
        if buf:
            yield _sentence_from_buf(buf)


def _sentence_from_buf(buf):
    comments = [l for l in buf if l.startswith("#")]
    tokens = [l for l in buf if not l.startswith("#")]
    text = None
    for c in comments:
        if c.startswith("# text = "):
            text = c[len("# text = ") :]
            break
    return {
        "comments": comments,
        "tokens": tokens,
        "text": text or "",
    }


def pack_paragraphs(sentences, max_para_chars):
    """Group consecutive sentences into paragraphs bounded by max_para_chars.
    Returns list of lists of sentence dicts."""
    paragraphs = []
    cur = []
    cur_len = 0
    for s in sentences:
        tlen = len(s["text"])
        sep = 1 if cur else 0  # the '\n' joining sentences
        if cur and cur_len + sep + tlen > max_para_chars:
            paragraphs.append(cur)
            cur = [s]
            cur_len = tlen
        else:
            cur.append(s)
            cur_len += sep + tlen
    if cur:
        paragraphs.append(cur)
    return paragraphs


def build_split(doc_xml_names, out_txt_path, out_conllu_path):
    stats = {
        "input_docs": len(doc_xml_names),
        "input_sents_total": 0,
        "dropped_long_sents": 0,
        "kept_sents": 0,
        "paragraphs": 0,
        "chars_written": 0,
        "max_para_chars_seen": 0,
        "paras_over_512": 0,
    }

    all_paragraphs = []  # list of lists of sentence dicts, in emission order

    for xml_name in doc_xml_names:
        conllu_path = os.path.join(BY_DOC, doc_stem(xml_name) + ".conllu")
        if not os.path.exists(conllu_path):
            raise FileNotFoundError(conllu_path)
        doc_sents = list(parse_conllu(conllu_path))
        stats["input_sents_total"] += len(doc_sents)
        kept = [s for s in doc_sents if 0 < len(s["text"]) <= MAX_SENT_CHARS]
        stats["dropped_long_sents"] += len(doc_sents) - len(kept)
        if not kept:
            continue
        doc_paras = pack_paragraphs(kept, MAX_PARA_CHARS)
        all_paragraphs.extend(doc_paras)

    # Write txt
    os.makedirs(os.path.dirname(out_txt_path), exist_ok=True)
    with open(out_txt_path, "w", encoding="utf-8", newline="\n") as f:
        chunks = []
        for para in all_paragraphs:
            block = "\n".join(s["text"] for s in para)
            chunks.append(block)
            plen = len(block)
            stats["paragraphs"] += 1
            stats["kept_sents"] += len(para)
            if plen > stats["max_para_chars_seen"]:
                stats["max_para_chars_seen"] = plen
            if plen > 512:
                stats["paras_over_512"] += 1
        out = "\n\n".join(chunks) + "\n"
        f.write(out)
        stats["chars_written"] = len(out)

    # Write conllu (sentences in same order as txt, blank line between sentences only)
    os.makedirs(os.path.dirname(out_conllu_path), exist_ok=True)
    with open(out_conllu_path, "w", encoding="utf-8", newline="\n") as f:
        first = True
        for para in all_paragraphs:
            for s in para:
                if not first:
                    f.write("\n")
                first = False
                for c in s["comments"]:
                    f.write(c + "\n")
                for t in s["tokens"]:
                    f.write(t + "\n")

    return stats


def main():
    with open(SUMMARY, "r", encoding="utf-8") as f:
        summary = json.load(f)

    train_docs_all = summary["splits"]["train"]["documents"]
    dev_docs = summary["splits"]["dev"]["documents"]
    test_docs = summary["splits"]["test"]["documents"]

    train_docs = [d for d in train_docs_all if d not in HOMER_DOCS]
    excluded = [d for d in train_docs_all if d in HOMER_DOCS]

    print("=== TRAIN ===")
    print(f"docs used: {len(train_docs)}, excluded (Homer): {excluded}")
    s_train = build_split(
        train_docs,
        os.path.join(OUT_TXT, "train.txt"),
        os.path.join(OUT_CONLLU, "train.conllu"),
    )
    print(s_train)

    print("\n=== DEV ===")
    print(f"docs used: {len(dev_docs)}")
    s_dev = build_split(
        dev_docs,
        os.path.join(OUT_TXT, "dev.txt"),
        os.path.join(OUT_CONLLU, "dev.conllu"),
    )
    print(s_dev)

    print("\n=== TEST ===")
    print(f"docs used: {len(test_docs)}")
    s_test = build_split(
        test_docs,
        os.path.join(OUT_TXT, "test.txt"),
        os.path.join(OUT_CONLLU, "test.conllu"),
    )
    print(s_test)

    manifest = {
        "output_dir": OUT_DIR,
        "max_sent_chars": MAX_SENT_CHARS,
        "max_para_chars": MAX_PARA_CHARS,
        "homer_excluded": sorted(excluded),
        "train_docs": train_docs,
        "dev_docs": dev_docs,
        "test_docs": test_docs,
        "train_stats": s_train,
        "dev_stats": s_dev,
        "test_stats": s_test,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest: {os.path.join(OUT_DIR, 'manifest.json')}")


if __name__ == "__main__":
    main()
