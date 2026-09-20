"""Detailed analysis of CAMeL vs Trankit Arabic tokenization (drift-corrected alignment)."""
import json, sys, io, re
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

with open("arabic_tokenization_comparison.json", encoding="utf-8") as f:
    data = json.load(f)

camel = data["camel_tools_morph_segmentation"]["tokens"]
trankit = data["trankit_native"]["tokens"]

L = []
def p(s=""):
    L.append(s)


def strip_diacritics(s):
    return re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)


# ── Drift-corrected alignment ──
# Both tokenizers may produce different token counts if they segment
# whitespace-delimited tokens differently. Align by matching surface forms.
def align_tokens(camel_toks, trankit_toks):
    """Align camel and trankit tokens using surface-form matching.
    Returns list of (camel_idx_or_None, trankit_idx_or_None) pairs.
    """
    ci, ti = 0, 0
    pairs = []
    while ci < len(camel_toks) or ti < len(trankit_toks):
        if ci >= len(camel_toks):
            pairs.append((None, ti))
            ti += 1
            continue
        if ti >= len(trankit_toks):
            pairs.append((ci, None))
            ci += 1
            continue

        c_word = strip_diacritics(camel_toks[ci]["word"])
        t_word = strip_diacritics(trankit_toks[ti]["text"])

        if c_word == t_word:
            pairs.append((ci, ti))
            ci += 1
            ti += 1
        else:
            # Try lookahead to find match
            # Check if camel word matches a nearby trankit word
            found = False
            for lookahead in range(1, 4):
                if ti + lookahead < len(trankit_toks):
                    if c_word == strip_diacritics(trankit_toks[ti + lookahead]["text"]):
                        # Trankit has extra tokens before the match
                        for x in range(lookahead):
                            pairs.append((None, ti + x))
                        pairs.append((ci, ti + lookahead))
                        ti += lookahead + 1
                        ci += 1
                        found = True
                        break
                if ci + lookahead < len(camel_toks):
                    if strip_diacritics(camel_toks[ci + lookahead]["word"]) == t_word:
                        # CAMeL has extra tokens
                        for x in range(lookahead):
                            pairs.append((ci + x, None))
                        pairs.append((ci + lookahead, ti))
                        ci += lookahead + 1
                        ti += 1
                        found = True
                        break
            if not found:
                # Force pair them and move on
                pairs.append((ci, ti))
                ci += 1
                ti += 1
    return pairs


aligned = align_tokens(camel, trankit)

p("ARABIC TOKENIZATION COMPARISON — DIACRITICS STRIPPED (drift-corrected)")
p("=" * 90)
p(f"CAMeL tokens: {len(camel)}  |  Trankit tokens: {len(trankit)}  |  Aligned pairs: {len(aligned)}")
p()

# ── Token-by-token (split tokens only) ──
p("TOKEN-BY-TOKEN (tokens where at least one system splits)")
p("-" * 90)
p(f"{'#':<6}{'Surface':<26} {'CAMeL':<30} {'Trankit MWT':<30} {'Match'}")
p("-" * 90)

diffs = []
agreements = 0
both_unsplit = 0
camel_only_extra = 0
trankit_only_extra = 0

for pair_idx, (ci, ti) in enumerate(aligned):
    if ci is None:
        trankit_only_extra += 1
        continue
    if ti is None:
        camel_only_extra += 1
        continue

    c = camel[ci]
    t = trankit[ti]
    word = c["word"]

    c_split = len(c["morph_segments"]) > 1
    t_split = "expanded" in t

    c_seg = "+".join(c["morph_segments"]) if c_split else "—"
    if t_split:
        t_seg = "+".join(tok["text"] for tok in t["expanded"])
    else:
        t_seg = "—"

    if not c_split and not t_split:
        both_unsplit += 1
        continue

    if c_seg == t_seg:
        match = "SAME"
        agreements += 1
    else:
        match = "** DIFF"
        diffs.append((pair_idx, ci, ti))

    p(f"{pair_idx:<6}{word:<26} {c_seg:<30} {t_seg:<30} {match}")

p("-" * 90)
p(f"Both unsplit (agree): {both_unsplit}  |  Both split & agree: {agreements}  |  Differences: {len(diffs)}")
if camel_only_extra or trankit_only_extra:
    p(f"Alignment drift: CAMeL-only tokens: {camel_only_extra}, Trankit-only tokens: {trankit_only_extra}")
p()

# ── Categorize differences ──
p("CATEGORIZED DIFFERENCES")
p("=" * 90)

cat_tanwin = []
cat_baa_split = []
cat_camel_wrong = []
cat_boundary = []
cat_segcount = []
cat_camel_only = []
cat_trankit_only = []

for pair_idx, ci, ti in diffs:
    c = camel[ci]
    t = trankit[ti]
    c_segs = c["morph_segments"] if len(c["morph_segments"]) > 1 else [c["word"]]
    t_segs = [tok["text"] for tok in t["expanded"]] if "expanded" in t else [t["text"]]
    c_split = len(c["morph_segments"]) > 1
    t_split = "expanded" in t
    word = c["word"]

    if not c_split and t_split:
        # Check if this is a tanwin spurious split
        if t_segs[-1] in ("نا", "ا", "ما") and word.endswith("ا"):
            cat_tanwin.append((pair_idx, ci, ti))
        else:
            cat_trankit_only.append((pair_idx, ci, ti))
    elif c_split and not t_split:
        cat_camel_only.append((pair_idx, ci, ti))
    elif len(c_segs) != len(t_segs):
        cat_segcount.append((pair_idx, ci, ti))
    else:
        # Same segment count — check specific patterns
        if c["word"] == "بعض" or "بعض" in "+".join(c_segs):
            cat_baa_split.append((pair_idx, ci, ti))
        else:
            cat_boundary.append((pair_idx, ci, ti))


def print_category(name, items):
    if not items:
        return
    p()
    p(f"── {name} ({len(items)} cases) ──")
    for pair_idx, ci, ti in items:
        c = camel[ci]
        t = trankit[ti]
        c_seg = "+".join(c["morph_segments"]) if len(c["morph_segments"]) > 1 else "(not split) " + c["word"]
        if "expanded" in t:
            t_parts = t["expanded"]
            t_seg = "+".join(tok["text"] for tok in t_parts)
            t_detail = ", ".join(f'{tok["text"]}({tok.get("upos","?")})' for tok in t_parts)
        else:
            t_seg = "(not split) " + t["text"]
            t_detail = f'{t["text"]}({t.get("upos","?")})'
        p(f"  [{pair_idx}] {c['word']}")
        p(f"    CAMeL:   {c_seg}")
        p(f"    Trankit: {t_seg}")


print_category("Trankit spuriously splits tanwin/diacritics as pronoun", cat_tanwin)
print_category("بعض mis-split (ب+عض)", cat_baa_split)
print_category("CAMeL wrong (Trankit correct)", cat_camel_wrong)
print_category("Same segment count, different boundary", cat_boundary)
print_category("Different segment count", cat_segcount)
print_category("CAMeL splits, Trankit does not", cat_camel_only)
print_category("Trankit splits, CAMeL does not", cat_trankit_only)

# ── Reconstruction quality ──
p()
p("TRANKIT MWT RECONSTRUCTION QUALITY")
p("=" * 90)
mwt_errors = []
for i, t in enumerate(trankit):
    if "expanded" not in t:
        continue
    surface = t["text"]
    pieces = "".join(tok["text"] for tok in t["expanded"])
    if pieces != surface:
        mwt_errors.append((i, surface, pieces, t["expanded"]))

if not mwt_errors:
    p("  (none — all reconstruct correctly)")
else:
    for i, surface, pieces, expanded in mwt_errors:
        p(f'  [{i}] surface="{surface}" → reconstructed="{pieces}"')
        for tok in expanded:
            p(f'       {tok["text"]:>12}  {tok.get("upos","")}  lemma={tok.get("lemma","")}')

p()
p("CAMEL MORPH RECONSTRUCTION QUALITY")
p("=" * 90)
camel_errors = []
for i, c in enumerate(camel):
    if len(c["morph_segments"]) <= 1:
        continue
    joined = "".join(c["morph_segments"])
    if joined != c["word"]:
        camel_errors.append((i, c["word"], joined, c["morph_segments"]))

if not camel_errors:
    p("  (none)")
else:
    for i, word, joined, segs in camel_errors:
        p(f'  [{i}] surface="{word}" → reconstructed="{joined}" segments={segs}')

# ── Summary ──
p()
p("SUMMARY")
p("=" * 90)
total_aligned = both_unsplit + agreements + len(diffs)
p(f"Total aligned pairs:       {total_aligned}")
p(f"Both unsplit (agree):      {both_unsplit}")
p(f"Both split, agree:         {agreements}")
p(f"Differences:               {len(diffs)}")
if agreements + len(diffs) > 0:
    p(f"Agreement rate (split):    {agreements}/{agreements+len(diffs)} = {agreements/(agreements+len(diffs))*100:.1f}%")
p(f"Overall agreement rate:    {(both_unsplit+agreements)}/{total_aligned} = {(both_unsplit+agreements)/total_aligned*100:.1f}%")
p()
p(f"Diff breakdown:")
p(f"  Trankit spuriously splits tanwin/diacritics as pronoun: {len(cat_tanwin)}")
p(f"  بعض mis-split (ب+عض): {len(cat_baa_split)}")
p(f"  CAMeL wrong (Trankit correct): {len(cat_camel_wrong)}")
p(f"  Same segment count, different boundary: {len(cat_boundary)}")
p(f"  Different segment count: {len(cat_segcount)}")
p(f"  CAMeL splits, Trankit does not: {len(cat_camel_only)}")
p(f"  Trankit splits, CAMeL does not: {len(cat_trankit_only)}")

out = "\n".join(L)
with open("crusades_tokenization_comparison.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(out)
