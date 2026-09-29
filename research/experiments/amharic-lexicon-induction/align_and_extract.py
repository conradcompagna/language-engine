"""
GPU-accelerated unsupervised cross-lingual alignment + dictionary extraction.
Uses PyTorch (no CuPy dependency) for all GPU operations.

Pipeline:
1. Load EN and AM vectors
2. Unsupervised alignment via iterative Procrustes (VecMap-style)
3. Extract top-5 nearest English neighbors for every Amharic word
4. Save to am_en_dictionary.tsv

Reference: Artetxe et al. 2018 (ACL) - unsupervised self-learning alignment
"""

import torch
import numpy as np
import sys
import time

# ── Config ──────────────────────────────────────────────────────────────────
EN_VEC       = "cc.en.300.vec"
AM_VEC       = "cc.am.300.vec"
SEED_DICT    = "seed_dict.txt"   # tab-separated am_word\ten_word
OUT_TSV      = "am_en_dictionary.tsv"
TOP_K        = 5
VOCAB_CUTOFF = 200_000
BATCH_SIZE   = 4096
N_ITER       = 10
CSLS_K       = 10
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# ─────────────────────────────────────────────────────────────────────────────

print(f"Device: {device}")
if device.type == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")


# ── 1. Load vectors ──────────────────────────────────────────────────────────
def load_vectors(path, cutoff=None):
    words, vecs = [], []
    print(f"  Loading {path} ...")
    with open(path, "r", encoding="utf-8") as f:
        n, d = map(int, f.readline().split())
        limit = min(n, cutoff) if cutoff else n
        for i, line in enumerate(f):
            if i >= limit:
                break
            parts = line.rstrip().split(" ")
            words.append(parts[0])
            vecs.append(parts[1:d+1])
            if (i + 1) % 100_000 == 0:
                print(f"    {i+1}/{limit}")
    mat = np.array(vecs, dtype=np.float32)
    print(f"  Loaded {len(words)} words")
    return words, mat


print("\n[1/4] Loading vectors...")
en_words, en_mat = load_vectors(EN_VEC, cutoff=200_000)    # top 200k EN
am_words, am_mat = load_vectors(AM_VEC, cutoff=200_000)    # top 200k AM


# ── 2. Normalise ─────────────────────────────────────────────────────────────
def normalise(mat):
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-9, None)
    return mat / norms

en_mat = normalise(en_mat)
am_mat = normalise(am_mat)

# Subsets for alignment (faster, still good)
en_align = torch.tensor(en_mat[:VOCAB_CUTOFF], device=device)
am_align = torch.tensor(am_mat[:VOCAB_CUTOFF], device=device)


# ── 3. Unsupervised Procrustes alignment (iterative self-learning) ───────────
print(f"\n[2/4] Running unsupervised Procrustes alignment ({N_ITER} iterations)...")

def procrustes(A, B):
    """Find rotation W that minimises ||AW - B||  via SVD."""
    M = B.T @ A          # (300, 300)
    U, S, Vt = torch.linalg.svd(M)
    W = Vt.T @ U.T
    return W

def get_candidates_csls(src, tgt, k=CSLS_K, batch=2048):
    """
    CSLS-based nearest neighbour induction.
    Returns for each src row the index of its nearest tgt neighbour.
    """
    # mean similarity of each tgt word to its k nearest src words
    tgt_avg = torch.zeros(tgt.shape[0], device=device)
    for i in range(0, tgt.shape[0], batch):
        sims = tgt[i:i+batch] @ src.T          # (B, N_src)
        topk_sims = torch.topk(sims, k, dim=1).values
        tgt_avg[i:i+batch] = topk_sims.mean(dim=1)

    nn = torch.zeros(src.shape[0], dtype=torch.long, device=device)
    for i in range(0, src.shape[0], batch):
        sims = src[i:i+batch] @ tgt.T          # (B, N_tgt)
        # src_avg for this batch
        src_avg = torch.topk(sims, k, dim=1).values.mean(dim=1, keepdim=True)
        csls = 2 * sims - src_avg - tgt_avg.unsqueeze(0)
        nn[i:i+batch] = csls.argmax(dim=1)
    return nn

# ── Seed dictionary initialisation ───────────────────────────────────────────
print("\nLoading seed dictionary...")
en_word2idx = {w: i for i, w in enumerate(en_words)}
am_word2idx = {w: i for i, w in enumerate(am_words)}

seed_am, seed_en = [], []
with open(SEED_DICT, encoding="utf-8") as f:
    for line in f:
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        aw, ew = parts[0].strip(), parts[1].strip().lower()
        if aw in am_word2idx and ew in en_word2idx:
            seed_am.append(am_word2idx[aw])
            seed_en.append(en_word2idx[ew])

print(f"  {len(seed_am)} seed pairs matched in vocab")

# Initialise W from seed pairs via Procrustes
A_seed = am_align[seed_am]
B_seed = en_align[seed_en]
W = procrustes(A_seed, B_seed)
print("  Seed-based W initialised.")

for iteration in range(N_ITER):
    t0 = time.time()

    # Map AM into EN space
    am_mapped = am_align @ W.T          # (N, 300)

    # Build synthetic dictionary via CSLS nearest neighbours
    nn_am_to_en = get_candidates_csls(am_mapped, en_align)
    nn_en_to_am = get_candidates_csls(en_align, am_mapped)

    # Mutual nearest neighbours (intersection)
    fwd = torch.zeros(am_align.shape[0], dtype=torch.bool, device=device)
    for i, j in enumerate(nn_am_to_en.tolist()):
        if nn_en_to_am[j] == i:
            fwd[i] = True

    idx_am = torch.where(fwd)[0]
    idx_en = nn_am_to_en[idx_am]

    # Procrustes on matched pairs
    if idx_am.shape[0] < 10:
        print(f"  iter {iteration+1}: too few mutual pairs ({idx_am.shape[0]}), stopping early")
        break

    A = am_align[idx_am]
    B = en_align[idx_en]
    W = procrustes(A, B)

    elapsed = time.time() - t0
    print(f"  iter {iteration+1}/{N_ITER} | pairs: {idx_am.shape[0]} | time: {elapsed:.1f}s")

print("Alignment complete.")


# ── 4. Apply final W to ALL Amharic vectors ──────────────────────────────────
print(f"\n[3/4] Applying alignment to all {len(am_words)} Amharic vectors...")
am_tensor_full = torch.tensor(am_mat, device=device)
am_mapped_full = am_tensor_full @ W.T
am_mapped_full = am_mapped_full / am_mapped_full.norm(dim=1, keepdim=True).clamp(min=1e-9)
del am_tensor_full


# ── 5. Extract top-5 English neighbours ──────────────────────────────────────
print(f"\n[4/4] Extracting top-{TOP_K} English neighbours for {len(am_words)} Amharic words...")
en_tensor_full = torch.tensor(en_mat, device=device)
# already normalised
en_words_arr = np.array(en_words)

rows = []
total = len(am_words)
for batch_start in range(0, total, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total)
    am_batch = am_mapped_full[batch_start:batch_end]
    sims = torch.mm(am_batch, en_tensor_full.T)
    topk = torch.topk(sims, TOP_K, dim=1)
    topk_idx = topk.indices.cpu().numpy()
    topk_scores = topk.values.cpu().numpy()
    for i, (idx_row, score_row) in enumerate(zip(topk_idx, topk_scores)):
        am_word = am_words[batch_start + i]
        top1_score = round(float(score_row[0]), 4)
        neighbors = list(en_words_arr[idx_row])
        rows.append([am_word, top1_score] + neighbors)
    if batch_end % 50_000 < BATCH_SIZE or batch_end == total:
        print(f"  {batch_end}/{total} ({100*batch_end//total}%)")

rows.sort(key=lambda r: r[1], reverse=True)

with open(OUT_TSV, "w", encoding="utf-8") as out:
    out.write("am_word\tscore\ten_1\ten_2\ten_3\ten_4\ten_5\n")
    for r in rows:
        out.write("\t".join(str(x) for x in r) + "\n")

print(f"\nDone! Dictionary saved to: {OUT_TSV}")
print(f"Rows: {len(am_words)}")
