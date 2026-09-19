import os

SRC = r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_sampled_10000\splits_txt"
DST = r"C:\Users\conra\Desktop\universal - js hybrid\training\perseus\grc_trankit_sampled_10000\splits_txt_para4"
N = 4

pairs = [
    ("train (2).txt", "train.para4.txt"),
    ("dev (2).txt",   "dev.para4.txt"),
    ("test (2).txt",  "test.para4.txt"),
]

for src_name, dst_name in pairs:
    src_path = os.path.join(SRC, src_name)
    dst_path = os.path.join(DST, dst_name)
    with open(src_path, "r", encoding="utf-8") as f:
        sentences = [ln.rstrip("\r\n") for ln in f if ln.strip() != ""]
    paragraphs = []
    for i in range(0, len(sentences), N):
        paragraphs.append("\n".join(sentences[i:i+N]))
    out = "\n\n".join(paragraphs) + "\n"
    with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print(f"{dst_name}: {len(sentences)} sents -> {len(paragraphs)} paragraphs")
