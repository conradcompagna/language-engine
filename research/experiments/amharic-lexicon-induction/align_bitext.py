"""
Word alignment using simalign (multilingual BERT) on Amharic-English parallel corpus.
Extracts top-5 English translations per Amharic word scored by dice coefficient.
Output: am_en_bitext_dictionary.tsv
"""

from simalign import SentenceAligner
from collections import defaultdict
import sys

AM_FILE  = "train.am"
EN_FILE  = "train.en"
OUT_TSV  = "am_en_bitext_dictionary.tsv"
MIN_COUNT = 3
TOP_K    = 5

print("Loading aligner...")
aligner = SentenceAligner(model="bert", token_type="bpe", matching_methods="mai")
print("Aligner ready.\n")

# co-occurrence counts
pair_count  = defaultdict(int)   # (am_word, en_word) -> count
am_count    = defaultdict(int)   # am_word -> total aligned count
en_count    = defaultdict(int)   # en_word -> total aligned count

with open(AM_FILE, encoding="utf-8") as fa, \
     open(EN_FILE, encoding="utf-8") as fe:
    lines_am = fa.readlines()
    lines_en = fe.readlines()

total = len(lines_am)
print(f"Aligning {total} sentence pairs...\n")

for i, (am_line, en_line) in enumerate(zip(lines_am, lines_en)):
    am_line = am_line.strip()
    en_line = en_line.strip()
    if not am_line or not en_line:
        continue

    am_tokens = am_line.split()
    en_tokens = en_line.split()

    if len(am_tokens) == 0 or len(en_tokens) == 0:
        continue

    try:
        alignments = aligner.get_word_aligns(en_tokens, am_tokens)
        # use 'mwmf' (itermax) alignment
        links = alignments.get("mwmf", alignments.get("inter", []))
        for en_idx, am_idx in links:
            if en_idx < len(en_tokens) and am_idx < len(am_tokens):
                am_word = am_tokens[am_idx].lower().strip("።፡፣፤,.!?\"'")
                en_word = en_tokens[en_idx].lower().strip(".,!?\"'")
                if am_word and en_word:
                    pair_count[(am_word, en_word)] += 1
                    am_count[am_word] += 1
                    en_count[en_word] += 1
    except Exception:
        continue

    if (i + 1) % 5000 == 0:
        print(f"  {i+1}/{total} ({100*(i+1)//total}%) | unique am words: {len(am_count)}")

print(f"\nAlignment done. Computing scores...")

# group by am_word
from collections import defaultdict
am_to_en = defaultdict(list)
for (am_word, en_word), count in pair_count.items():
    if count < MIN_COUNT:
        continue
    dice = (2 * count) / (am_count[am_word] + en_count[en_word])
    am_to_en[am_word].append((en_word, round(dice, 4), count))

# sort each am_word's candidates by dice descending
for am_word in am_to_en:
    am_to_en[am_word].sort(key=lambda x: x[1], reverse=True)

# sort all am_words by their top-1 dice score descending
sorted_am = sorted(am_to_en.keys(), key=lambda w: am_to_en[w][0][1], reverse=True)

print(f"Writing {len(sorted_am)} Amharic entries to {OUT_TSV}...")

with open(OUT_TSV, "w", encoding="utf-8") as out:
    out.write("am_word\tscore\ten_1\ten_2\ten_3\ten_4\ten_5\n")
    for am_word in sorted_am:
        candidates = am_to_en[am_word][:TOP_K]
        # pad to 5
        while len(candidates) < TOP_K:
            candidates.append(("", "", ""))
        score = candidates[0][1]
        en_words = "\t".join(c[0] for c in candidates)
        out.write(f"{am_word}\t{score}\t{en_words}\n")

print(f"Done! Saved to {OUT_TSV}")
print(f"Total unique Amharic words: {len(sorted_am)}")
