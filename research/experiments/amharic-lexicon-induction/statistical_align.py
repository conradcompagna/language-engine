"""
Pure statistical word alignment using co-occurrence + dice coefficient.
No model required. Runs in under a minute.
Output: am_en_statistical_dictionary.tsv
"""

from collections import defaultdict

AM_FILE   = "train.am"
EN_FILE   = "train.en"
OUT_TSV   = "am_en_statistical_dictionary.tsv"
MIN_COUNT = 3
TOP_K     = 5

pair_count = defaultdict(int)
am_count   = defaultdict(int)
en_count   = defaultdict(int)

with open(AM_FILE, encoding="utf-8") as fa, \
     open(EN_FILE, encoding="utf-8") as fe:
    lines_am = fa.readlines()
    lines_en = fe.readlines()

total = len(lines_am)
print(f"Processing {total} sentence pairs...")

for i, (am_line, en_line) in enumerate(zip(lines_am, lines_en)):
    am_tokens = [t.strip("።፡፣፤,.!?\"'()[]") for t in am_line.strip().split()]
    en_tokens = [t.strip(".,!?\"'()[]").lower() for t in en_line.strip().split()]
    am_tokens = [t for t in am_tokens if t]
    en_tokens = [t for t in en_tokens if t]

    if not am_tokens or not en_tokens:
        continue

    for ai, am_word in enumerate(am_tokens):
        am_count[am_word] += 1
        for ei, en_word in enumerate(en_tokens):
            am_ratio = ai / max(len(am_tokens) - 1, 1)
            en_ratio = ei / max(len(en_tokens) - 1, 1)
            if abs(am_ratio - en_ratio) <= 0.3:
                pair_count[(am_word, en_word)] += 1
                en_count[en_word] += 1

    if (i + 1) % 10000 == 0:
        print(f"  {i+1}/{total} ({100*(i+1)//total}%)")

print(f"\nComputing dice scores...")

am_to_en = defaultdict(list)
for (am_word, en_word), count in pair_count.items():
    if count < MIN_COUNT:
        continue
    dice = (2 * count) / (am_count[am_word] + en_count[en_word])
    am_to_en[am_word].append((en_word, round(dice, 4)))

for am_word in am_to_en:
    am_to_en[am_word].sort(key=lambda x: x[1], reverse=True)

sorted_am = sorted(am_to_en.keys(), key=lambda w: am_to_en[w][0][1], reverse=True)

print(f"Writing {len(sorted_am)} entries to {OUT_TSV}...")

with open(OUT_TSV, "w", encoding="utf-8") as out:
    out.write("am_word\tscore\ten_1\ten_2\ten_3\ten_4\ten_5\n")
    for am_word in sorted_am:
        candidates = am_to_en[am_word][:TOP_K]
        while len(candidates) < TOP_K:
            candidates.append(("", ""))
        score = candidates[0][1]
        en_words = "\t".join(c[0] for c in candidates)
        out.write(f"{am_word}\t{score}\t{en_words}\n")

print(f"Done! Saved to {OUT_TSV}")
print(f"Total unique Amharic words: {len(sorted_am)}")
