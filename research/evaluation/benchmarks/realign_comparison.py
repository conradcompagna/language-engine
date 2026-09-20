"""
Re-align CAMeL and Trankit token streams by matching on surface form,
then produce a clean drift-free comparison.

CAMeL outputs one entry per original surface word.
Trankit outputs one entry per token (MWT surface = original surface word,
non-MWT = same as CAMeL word). We align by matching CAMeL words to
Trankit token surfaces (MWT surface or plain text).
"""
import json, sys, io, unicodedata, re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open("crusades_comparison_data.json", encoding="utf-8") as f:
    data = json.load(f)

camel = data["camel"]   # list of {word, morph_segments}
trankit = data["trankit"]  # list of {text, upos, lemma, expanded?}


def norm(s):
    """Normalize for matching: strip diacritics, ZWNJ, shadda, tanwin."""
    s = unicodedata.normalize("NFKC", s)
    # remove Arabic diacritics (tashkeel) U+0610–U+061A, U+064B–U+065F, U+0670, U+06D6–U+06DC, U+06DF–U+06E4, U+06E7–U+06E8, U+06EA–U+06ED
    s = re.sub(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e4\u06e7\u06e8\u06ea-\u06ed]", "", s)
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]", "", s)  # ZW chars
    return s.strip()


def trankit_surface(tok):
    """The surface word a Trankit token covers (MWT line surface or plain text)."""
    return tok["text"]


# Build Trankit index: group tokens by their surface so we can look them up
# We walk both lists simultaneously, matching CAMeL word → Trankit surface.

def align(camel_toks, trankit_toks):
    """
    Align the two streams. Returns list of (camel_entry_or_None, trankit_entry_or_None).
    camel_entry: dict with word + morph_segments
    trankit_entry: dict with text + optional expanded
    """
    ci = 0
    ti = 0
    pairs = []

    while ci < len(camel_toks) and ti < len(trankit_toks):
        c = camel_toks[ci]
        t = trankit_toks[ti]
        cw = norm(c["word"])
        tw = norm(trankit_surface(t))

        if cw == tw:
            pairs.append((c, t))
            ci += 1
            ti += 1
            continue

        # Try to recover: look ahead up to 5 in each stream
        found = False
        for dc in range(0, 5):
            for dt in range(0, 5):
                if dc == 0 and dt == 0:
                    continue
                ci2 = ci + dc
                ti2 = ti + dt
                if ci2 >= len(camel_toks) or ti2 >= len(trankit_toks):
                    continue
                if norm(camel_toks[ci2]["word"]) == norm(trankit_surface(trankit_toks[ti2])):
                    # Drain the skipped tokens as unmatched
                    for x in range(dc):
                        pairs.append((camel_toks[ci + x], None))
                    for x in range(dt):
                        pairs.append((None, trankit_toks[ti + x]))
                    ci = ci2
                    ti = ti2
                    found = True
                    break
            if found:
                break

        if not found:
            # Give up on this token pair, emit both and advance
            pairs.append((c, t))
            ci += 1
            ti += 1

    while ci < len(camel_toks):
        pairs.append((camel_toks[ci], None))
        ci += 1
    while ti < len(trankit_toks):
        pairs.append((None, trankit_toks[ti]))
        ti += 1

    return pairs


pairs = align(camel, trankit)

# ── Build output ──
L = []
def p(s=""): L.append(s)

p("ARABIC TOKENIZATION COMPARISON — CRUSADES TEXT (drift-corrected)")
p("=" * 90)
p(f"CAMeL tokens: {len(camel)}  |  Trankit tokens: {len(trankit)}  |  Aligned pairs: {len(pairs)}")
p()

p("TOKEN-BY-TOKEN (tokens where at least one system splits)")
p("-" * 90)
p(f"{'#':<5} {'Surface':<26} {'CAMeL':<28} {'Trankit MWT':<28} Match")
p("-" * 90)

diffs = []
agreements = 0
both_unsplit = 0
trankit_only_diacritics = []  # tanwin issue etc.

for idx, (c, t) in enumerate(pairs):
    word = c["word"] if c else (t["text"] if t else "?")

    c_seg = "+".join(c["morph_segments"]) if (c and len(c["morph_segments"]) > 1) else "—"
    if t and "expanded" in t:
        t_seg = "+".join(sub["text"] for sub in t["expanded"])
    else:
        t_seg = "—"

    # Unmatched tokens
    if c is None:
        p(f"{idx:<5} {'[trankit only]':<26} {'—':<28} {t_seg or t['text']:<28} TRANKIT-ONLY")
        continue
    if t is None:
        p(f"{idx:<5} {word:<26} {c_seg or word:<28} {'—':<28} CAMEL-ONLY")
        continue

    if c_seg == "—" and t_seg == "—":
        both_unsplit += 1
        continue

    if c_seg == t_seg:
        match = "SAME"
        agreements += 1
    else:
        match = "** DIFF"
        diffs.append(idx)

    p(f"{idx:<5} {word:<26} {c_seg:<28} {t_seg:<28} {match}")

p("-" * 90)
p(f"Both unsplit (agree): {both_unsplit}  |  Both split & agree: {agreements}  |  Differences: {len(diffs)}")
p()

# ── Categorize diffs ──
p("CATEGORIZED DIFFERENCES")
p("=" * 90)

cat = {
    "tanwin_spurious_pronoun": [],   # أيضًا → أيض+ا, حاليًا → حاليا+نا
    "article_handling": [],          # ل+الحدود vs ل+لحدود
    "ba3d_misplit": [],              # بعض → ب+عض
    "camel_wrong": [],               # وسار → و+س+أر (Trankit right)
    "trankit_wrong": [],             # Trankit splits non-clitics
    "boundary_diff": [],             # Same count, different boundary
    "count_diff": [],                # Different number of pieces
    "camel_only_split": [],
    "trankit_only_split": [],
}

for idx in diffs:
    c, t = pairs[idx]
    if c is None or t is None:
        continue
    cw = c["word"]
    c_segs = c["morph_segments"] if len(c["morph_segments"]) > 1 else [cw]
    t_segs = [sub["text"] for sub in t["expanded"]] if "expanded" in t else [t["text"]]
    c_split = len(c["morph_segments"]) > 1
    t_split = "expanded" in t

    if not c_split and t_split:
        # Check for tanwin pattern: Trankit adds spurious ا/نا at end
        last = t_segs[-1]
        if last in ("ا", "نا", "ما", "ان"):
            cat["tanwin_spurious_pronoun"].append(idx)
        else:
            cat["trankit_only_split"].append(idx)
    elif c_split and not t_split:
        cat["camel_only_split"].append(idx)
    elif len(c_segs) != len(t_segs):
        # Check بعض
        if "عض" in c_segs:
            cat["ba3d_misplit"].append(idx)
        elif any(s in ("أر", "س") for s in c_segs):
            cat["camel_wrong"].append(idx)
        else:
            cat["count_diff"].append(idx)
    else:
        # Same count — check article handling
        c_j = "|".join(c_segs)
        t_j = "|".join(t_segs)
        if "ال" in c_j and "ل" + t_segs[1] == c_segs[0] + t_segs[1][:2] if len(t_segs) > 1 else False:
            cat["article_handling"].append(idx)
        else:
            cat["boundary_diff"].append(idx)

label_map = {
    "tanwin_spurious_pronoun": "Trankit spuriously splits tanwin/diacritics as pronoun",
    "article_handling": "Article ال handling differs",
    "ba3d_misplit": "بعض mis-split (ب+عض)",
    "camel_wrong": "CAMeL wrong (Trankit correct)",
    "trankit_wrong": "Trankit wrong split",
    "boundary_diff": "Same segment count, different boundary",
    "count_diff": "Different segment count",
    "camel_only_split": "CAMeL splits, Trankit does not",
    "trankit_only_split": "Trankit splits, CAMeL does not",
}

for cat_key, indices in cat.items():
    if not indices:
        continue
    p()
    p(f"── {label_map[cat_key]} ({len(indices)} cases) ──")
    for idx in indices:
        c, t = pairs[idx]
        if c is None or t is None: continue
        cw = c["word"]
        c_seg_str = " + ".join(c["morph_segments"]) if len(c["morph_segments"]) > 1 else f"(not split) {cw}"
        if "expanded" in t:
            t_seg_str = " + ".join(f'{s["text"]}({s.get("upos","")})' for s in t["expanded"])
        else:
            t_seg_str = f"(not split) {t['text']} ({t.get('upos','')})"
        p(f"  [{idx}] {cw}")
        p(f"    CAMeL:   {c_seg_str}")
        p(f"    Trankit: {t_seg_str}")

# ── Summary ──
p()
p("SUMMARY")
p("=" * 90)
total_matched = sum(1 for c, t in pairs if c and t)
p(f"Total aligned pairs:       {total_matched}")
p(f"Both unsplit (agree):      {both_unsplit}")
p(f"Both split, agree:         {agreements}")
p(f"Differences:               {len(diffs)}")
split_total = agreements + len(diffs)
if split_total:
    p(f"Agreement rate (split):    {agreements}/{split_total} = {agreements/split_total*100:.1f}%")
p(f"Overall agreement rate:    {both_unsplit+agreements}/{total_matched} = {(both_unsplit+agreements)/total_matched*100:.1f}%")
p()
p("Diff breakdown:")
for cat_key, indices in cat.items():
    if indices:
        p(f"  {label_map[cat_key]}: {len(indices)}")

out = "\n".join(L)
with open("crusades_tokenization_comparison.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(out)
print("\nWritten to crusades_tokenization_comparison.txt")
