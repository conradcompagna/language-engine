"""
Extract top-5 nearest English neighbors for every Amharic word.
Uses GPU (CUDA) via PyTorch for fast cosine similarity in batches.
Output: am_en_dictionary.tsv
"""

import torch
import numpy as np
import sys

BATCH_SIZE = 2048  # Amharic words processed per GPU batch
TOP_K = 5
EN_VEC = "cc.en.300.vec"
AM_VEC = "cc.am.mapped.vec"
OUT_TSV = "am_en_dictionary.tsv"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")


def load_vectors(path, verbose=True):
    words = []
    vecs = []
    with open(path, "r", encoding="utf-8") as f:
        n, d = map(int, f.readline().split())
        if verbose:
            print(f"  Loading {n} words x {d} dims from {path}")
        for i, line in enumerate(f):
            parts = line.rstrip().split(" ")
            words.append(parts[0])
            vecs.append(parts[1:])
            if verbose and (i + 1) % 200000 == 0:
                print(f"  ... {i+1}/{n}")
    mat = np.array(vecs, dtype=np.float32)
    return words, mat


print("Loading English vectors...")
en_words, en_mat = load_vectors(EN_VEC)
print(f"English loaded: {len(en_words)} words")

# Normalise English matrix and move to GPU
en_tensor = torch.tensor(en_mat, device=device)
en_tensor = en_tensor / en_tensor.norm(dim=1, keepdim=True).clamp(min=1e-9)
del en_mat

print("Loading mapped Amharic vectors...")
am_words, am_mat = load_vectors(AM_VEC)
print(f"Amharic loaded: {len(am_words)} words")

am_tensor = torch.tensor(am_mat, device=device)
am_tensor = am_tensor / am_tensor.norm(dim=1, keepdim=True).clamp(min=1e-9)
del am_mat

print(f"\nExtracting top-{TOP_K} English neighbors for {len(am_words)} Amharic words...")
print(f"Writing to {OUT_TSV}\n")

en_words_arr = np.array(en_words)

with open(OUT_TSV, "w", encoding="utf-8") as out:
    out.write("am_word\ten_1\ten_2\ten_3\ten_4\ten_5\n")
    total = len(am_words)
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        am_batch = am_tensor[batch_start:batch_end]  # (B, 300)

        # cosine similarity: (B, N_en)
        sims = torch.mm(am_batch, en_tensor.T)

        # top-k indices
        topk = torch.topk(sims, TOP_K, dim=1).indices.cpu().numpy()

        for i, idx_row in enumerate(topk):
            am_word = am_words[batch_start + i]
            en_neighbors = "\t".join(en_words_arr[idx_row])
            out.write(f"{am_word}\t{en_neighbors}\n")

        if (batch_end) % 50000 < BATCH_SIZE or batch_end == total:
            print(f"  Progress: {batch_end}/{total} ({100*batch_end//total}%)")

print(f"\nDone! Dictionary saved to {OUT_TSV}")
