import pandas as pd
import os


def convert_parquet_to_conllu(parquet_path, conllu_path, txt_path):
    df = pd.read_parquet(parquet_path)

    with (
        open(conllu_path, "w", encoding="utf-8") as cf,
        open(txt_path, "w", encoding="utf-8") as tf,
    ):
        for _, row in df.iterrows():
            tokens = row["tokens"]
            lemmas = row["lemmas"]
            upos = row["upos_tags"]
            xpos = row["xpos_tags"]
            feats = row["feats"]
            heads = row["heads"]
            deprels = row["deprels"]

            # Build sentence text from tokens
            text = " ".join(str(t) for t in tokens)

            cf.write(f"# sent_id = {row['id']}\n")
            cf.write(f"# text = {text}\n")

            # Build head map and detect all tokens involved in any cycle or bad annotation
            n = len(tokens)
            raw_heads = []
            for i in range(n):
                h = heads[i]
                raw_heads.append(int(h) if h is not None and str(h) != "nan" else 0)

            # Find tokens to mask: self-refs, unannotated (head=0, no upos), and cycle participants
            mask = set()
            for i in range(n):
                tid = i + 1
                h = raw_heads[i]
                upos_tag_i = str(upos[i]) if upos[i] else "_"
                dep_i = str(deprels[i]) if deprels[i] else "_"
                if h == tid:
                    mask.add(i)
                elif h == 0 and (dep_i == "_" or dep_i == "") and upos_tag_i == "_":
                    mask.add(i)

            # Detect mutual/chain cycles among non-masked tokens
            for i in range(n):
                if i in mask:
                    continue
                visited = []
                cur = i
                while cur is not None:
                    if cur in mask:
                        break
                    if cur in visited:
                        # cycle detected — mask all tokens in the cycle
                        cycle_start = visited.index(cur)
                        for ci in visited[cycle_start:]:
                            mask.add(ci)
                        break
                    visited.append(cur)
                    next_h = raw_heads[cur]
                    cur = (next_h - 1) if next_h > 0 else None

            for i, tok in enumerate(tokens):
                token_id = i + 1
                form = str(tok)
                lemma = str(lemmas[i]) if lemmas[i] else "_"
                upos_tag = str(upos[i]) if upos[i] else "_"
                xpos_tag = str(xpos[i]) if xpos[i] else "_"
                feat = str(feats[i]) if feats[i] else "_"
                deprel = str(deprels[i]) if deprels[i] else "_"
                if i in mask:
                    head = "_"
                    deprel = "_"
                else:
                    head = raw_heads[i]

                if feat == "" or feat is None:
                    feat = "_"
                if xpos_tag == "":
                    xpos_tag = "_"

                cf.write(
                    f"{token_id}\t{form}\t{lemma}\t{upos_tag}\t{xpos_tag}\t{feat}\t{head}\t{deprel}\t_\t_\n"
                )

            cf.write("\n")
            tf.write(text + "\n")


splits = {
    "train": ("train-00000-of-00001.parquet", "tgl-train.conllu", "tgl-train.txt"),
    "dev": ("validation-00000-of-00001.parquet", "tgl-dev.conllu", "tgl-dev.txt"),
    "test": ("test-00000-of-00001.parquet", "tgl-test.conllu", "tgl-test.txt"),
}

base = os.path.dirname(os.path.abspath(__file__))
for split, (pq, conllu, txt) in splits.items():
    pq_path = os.path.join(base, pq)
    if os.path.exists(pq_path):
        print(f"Converting {split}...")
        convert_parquet_to_conllu(pq_path, os.path.join(base, conllu), os.path.join(base, txt))
        print(f"  -> {conllu}, {txt}")

print("Done.")
