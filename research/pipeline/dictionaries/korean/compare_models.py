"""
Compare Trankit korean (GSD) vs korean-kaist tokenizer+lemmatizer output.
Processes debug.txt in batches and writes results to two files.
"""

import os
import sys

# Run from project root
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trankit import Pipeline

INPUT = "korean/debug.txt"
OUT_GSD = "korean/result_gsd.txt"
OUT_KAIST = "korean/result_kaist.txt"
BATCH_SIZE = 2000  # characters per batch


def read_batches(path, size):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # Split on newlines to avoid cutting mid-sentence, then group
    lines = text.split("\n")
    batches = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > size and current:
            batches.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current.strip():
        batches.append(current)
    return batches


def run_model(model_name, batches, output_path):
    print(f"\n{'='*60}")
    print(f"Loading {model_name}...")
    print(f"{'='*60}")
    p = Pipeline(model_name, gpu=True)

    results = []
    for i, batch in enumerate(batches):
        if not batch.strip():
            continue
        print(f"  [{model_name}] batch {i+1}/{len(batches)} ({len(batch)} chars)")
        doc = p(batch)
        for sent in doc.get("sentences", []):
            for tok in sent.get("tokens", []):
                # Handle MWT (multi-word tokens)
                if "expanded" in tok:
                    for exp in tok["expanded"]:
                        surface = exp.get("text", "")
                        lemma = exp.get("lemma", surface)
                        upos = exp.get("upos", "")
                        xpos = exp.get("xpos", "")
                        results.append(f"{surface}\t{lemma}\t{upos}\t{xpos}")
                else:
                    surface = tok.get("text", "")
                    lemma = tok.get("lemma", surface)
                    upos = tok.get("upos", "")
                    xpos = tok.get("xpos", "")
                    results.append(f"{surface}\t{lemma}\t{upos}\t{xpos}")
            results.append("")  # blank line between sentences

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Model: {model_name}\n")
        f.write(f"# Format: surface\\tlemma\\tupos\\txpos\n\n")
        f.write("\n".join(results))

    print(f"  -> Wrote {len(results)} lines to {output_path}")


if __name__ == "__main__":
    batches = read_batches(INPUT, BATCH_SIZE)
    print(f"Input: {INPUT} -> {len(batches)} batches")

    run_model("korean", batches, OUT_GSD)
    run_model("korean-kaist", batches, OUT_KAIST)

    print(f"\nDone! Compare:\n  {OUT_GSD}\n  {OUT_KAIST}")
