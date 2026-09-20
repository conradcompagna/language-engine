"""
Parse parquet parallel corpus and write plain text files.
Filters: empty pairs, extreme length ratios (>1:9), pairs >80 tokens.
"""
import pandas as pd
import sys

RATIO_MAX = 9
MAX_TOKENS = 80
OUT_AM = "train.am"
OUT_EN = "train.en"

dfs = []
for split in ["train", "validation", "test"]:
    try:
        df = pd.read_parquet(f"parallel/{split}-00000-of-00001 (1).parquet")
        dfs.append(df)
        print(f"Loaded {split}: {len(df)} rows")
    except Exception as e:
        print(f"Skipped {split}: {e}")

df = pd.concat(dfs, ignore_index=True)
print(f"Total rows: {len(df)}")

pairs = [(r["am"], r["en"]) for r in df["translation"]]

kept, dropped = [], 0
seen = set()
for am, en in pairs:
    am, en = am.strip(), en.strip()
    if not am or not en:
        dropped += 1; continue
    key = (am, en)
    if key in seen:
        dropped += 1; continue
    seen.add(key)
    am_tok = len(am.split())
    en_tok = len(en.split())
    if am_tok == 0 or en_tok == 0:
        dropped += 1; continue
    ratio = max(am_tok, en_tok) / min(am_tok, en_tok)
    if ratio > RATIO_MAX or am_tok > MAX_TOKENS or en_tok > MAX_TOKENS:
        dropped += 1; continue
    kept.append((am, en))

print(f"Kept: {len(kept)} | Dropped: {dropped}")

with open(OUT_AM, "w", encoding="utf-8") as fa, \
     open(OUT_EN, "w", encoding="utf-8") as fe:
    for am, en in kept:
        fa.write(am + "\n")
        fe.write(en + "\n")

print(f"Written: {OUT_AM}, {OUT_EN}")
