"""
Regroup Thai UD CoNLL-U files so sentences from the same document
are contiguous. Generate .txt files where:
  - sentences within a document are separated by single newline
  - documents are separated by double newline (blank line)
This teaches Trankit to learn sentence segmentation.

Also rewrites CoNLL-U with sentences grouped by document, so the
sentence order in .txt aligns with the CoNLL-U.
"""
from pathlib import Path
from collections import OrderedDict

base = Path(r"C:\Users\conra\Desktop\universal\training")

def parse_sentences(conllu_path):
    """Parse CoNLL-U into list of (filename, sent_id, text, raw_block)."""
    sentences = []
    current_lines = []
    filename = None
    sent_id = None
    text = None

    for line in conllu_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "" and current_lines:
            sentences.append((filename, sent_id, text, "\n".join(current_lines)))
            current_lines = []
            filename = sent_id = text = None
        else:
            current_lines.append(line)
            if line.startswith("# filename = "):
                filename = line[len("# filename = "):]
            elif line.startswith("# sent_id = "):
                sent_id = int(line[len("# sent_id = "):])
            elif line.startswith("# text = "):
                text = line[len("# text = "):]

    if current_lines:
        sentences.append((filename, sent_id, text, "\n".join(current_lines)))

    return sentences

def group_by_doc(sentences):
    """Group sentences by filename, preserving sent_id order within each doc."""
    docs = OrderedDict()
    for fname, sid, text, block in sentences:
        key = fname or f"_unknown_{sid}"
        if key not in docs:
            docs[key] = []
        docs[key].append((sid, text, block))

    # Sort sentences within each doc by sent_id
    for key in docs:
        docs[key].sort(key=lambda x: x[0] if x[0] is not None else 0)

    return docs

def process(conllu_in, conllu_out, txt_out):
    sentences = parse_sentences(conllu_in)
    docs = group_by_doc(sentences)

    # Write regrouped CoNLL-U
    conllu_blocks = []
    for doc_sents in docs.values():
        for _, _, block in doc_sents:
            conllu_blocks.append(block)

    conllu_out.write_text("\n\n".join(conllu_blocks) + "\n\n", encoding="utf-8")

    # Write .txt: sentences within doc joined by \n, docs separated by \n\n
    doc_texts = []
    for doc_sents in docs.values():
        texts = [t for _, t, _ in doc_sents if t]
        if texts:
            doc_texts.append("\n".join(texts))

    txt_out.write_text("\n\n".join(doc_texts) + "\n", encoding="utf-8")

    print(f"{conllu_in.name}: {len(sentences)} sentences, {len(docs)} documents")
    print(f"  -> {conllu_out.name}, {txt_out.name}")

# Back up originals
for name in ["th_tud-ud-train.conllu", "th_tud-ud-dev.conllu"]:
    src = base / name
    bak = base / (name + ".bak")
    if not bak.exists():
        import shutil
        shutil.copy2(src, bak)
        print(f"Backed up {name} -> {name}.bak")

process(
    base / "th_tud-ud-train.conllu",
    base / "th_tud-ud-train.grouped.conllu",
    base / "th_tud-ud-train.txt",
)
process(
    base / "th_tud-ud-dev.conllu",
    base / "th_tud-ud-dev.grouped.conllu",
    base / "th_tud-ud-dev.txt",
)
