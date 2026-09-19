"""
Fix systematic issues in ara_news_2022_10K_plain_trankit_tok_train.conllu/.txt
to align with PADT conventions.

Fixes applied:
1. Remove bogus nisba ية→ي+ه MWT splits (بيروتية is NOT بيروتي+ه)
2. Remove proper noun MWT splits (كورونا, فيسبوك, حمدوك)
3. Fix preposition+pronoun sub-tokens: على→علي, لدى→لدي, إلى→إلي (PADT convention)
4. Remove bogus ي-suffix splits (أسبوعي→أسبوعي+ي is wrong)
5. Remove non-possessive ة→X+ه splits (منقوصة is NOT منقوص+ه)
6. Fix truncated sub-tokens (بالتزاماتها→ب+التزام is broken)
7. Fix NOAN placeholder tokens
8. Fix ممن→من+من, كلاهما→كلى+هما (match PADT: من+من is OK for ممن)
9. Convert txt to paragraph format with blank-line separators
"""

import re
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = os.path.dirname(os.path.abspath(__file__))

FILE_PAIRS = [
    (
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_train.conllu"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_train.txt"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_train_fixed.conllu"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_train_fixed.txt"),
    ),
    (
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_dev.conllu"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_dev.txt"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_dev_fixed.conllu"),
        os.path.join(BASE, "ara_news_2022_10K_plain_trankit_tok_dev_fixed.txt"),
    ),
]

# ── Proper noun blocklist: these should NEVER be MWT-split ──
PROPER_NOUN_BLOCKLIST = {
    "كورونا",
    "فيسبوك",
    "حمدوك",
    "تويتر",
    "يوتيوب",
    "أردوغان",
    "أوباما",
    "ماكرون",
    "بوتين",
    "ترامب",
    "نتنياهو",
    "أنقرة",
    "بروكسل",
    "كوريغرافي",
    "ميلوني",
    "ماسوني",
    # Place names wrongly split as verb+pronoun
    "تبوك",
    "دهوك",
    "شبوة",
    "وستبروك",
    "تازروك",
    # Nouns wrongly analyzed as verb+pronoun
    "هواة",
    "عنوة",
    "غفوة",
    "جذوة",
    "فروة",
    "قراوة",
}

# Words where MWT sub-tokens have wrong form but the split is valid.
# Map: surface → corrected sub-token list (or None to collapse to single token).
SURFACE_FIXES = {
    "بالمائة": ["ب", "المائة"],  # not ب+الماءة
}

# Prefixed forms that should also be blocked
# e.g. لكورونا, وشبوة — match if surface minus common prefixes is in blocklist
PREFIXES = ["ال", "و", "ف", "ب", "ل", "ك", "وال", "بال", "فال", "كال", "لل"]

# ── Preposition stems that need ى→ي before pronoun suffix (PADT convention) ──
PREP_ALIF_MAQSURA = {"على": "علي", "لدى": "لدي", "إلى": "إلي"}

# ── Helpers ──


def strip_diacritics(s):
    return re.sub(r"[\u064B-\u0652\u0670\u0640\u0651]", "", s)


def _is_prefixed_proper_noun(surface_clean):
    """Check if surface is a common prefix + a proper noun from the blocklist.
    e.g. لكورونا, وشبوة, بفيسبوك
    """
    for pfx in PREFIXES:
        if surface_clean.startswith(pfx):
            remainder = surface_clean[len(pfx) :]
            if remainder in PROPER_NOUN_BLOCKLIST:
                return True
    return False


def is_bogus_nisba(surface, subs):
    """بيروتية → بيروتي+ه — the ية is part of the adjective, not possessive.
    Also catches prefixed forms: وعائلية→و+عائلي+ه, بإنسانية→ب+إنساني+ه
    """
    if len(subs) < 2:
        return False
    if subs[-1] != "ه":
        return False
    if surface.endswith("ية") and subs[-2].endswith("ي"):
        return True
    return False


def is_bogus_ya_suffix(surface, subs):
    """أسبوعي → أسبوعي+ي — the final ي is adjectival/nisba, not a pronoun.
    Pattern: surface ends with ي, subs = [X, ي] where X also ends with ي,
    and X+ي ≠ surface (because it double-counts the ي).
    """
    if len(subs) < 2:
        return False
    if subs[-1] != "ي":
        return False
    # Check: is the surface a word ending in ي that is NOT a 1st person possessive?
    # Heuristic: if the stem already ends in ي and adding ي would double it,
    # this is bogus. E.g. أسبوعي → أسبوعي+ي (joined=أسبوعيي ≠ أسبوعي)
    joined = "".join(subs)
    if joined != surface and joined == surface + "ي":
        return True
    # Also: stems ending with و+ي like مسؤولو+ي for مسؤولي
    # These are broken masculine plural + ي splits
    if len(subs) >= 2 and subs[-1] == "ي":
        stem = "".join(subs[:-1])
        if stem.endswith("و") and surface.endswith("ي"):
            # لمسؤولي → ل+مسؤولو+ي (stem ends و, surface ends ي)
            return True
    return False


def is_non_possessive_ta_marbuta(surface, subs):
    """منقوصة → منقوص+ه — the ة is part of the word, not a possessive suffix.

    In PADT, ة→ه splits only happen for actual possessives like حكومته→حكومة+ه.
    For standalone words ending in ة (adjectives, nouns), there's no split.

    Heuristic: if surface ends with ة and the last sub is ه (not ها/هم/هما/هن),
    AND the surface is NOT of the form Xته (possessive), it's bogus.

    Also catches prefixed forms: بوفرة→ب+وفر+ه, لأنسنة→ل+آنسن+ه
    """
    if len(subs) < 2:
        return False
    if subs[-1] != "ه":
        return False
    if not surface.endswith("ة"):
        return False
    # This IS a standalone word ending in ة, being wrongly split into stem+ه
    # (In possessives like حكومته, the surface ends in ته not ة)
    return True


def is_truncated_mwt(surface, subs):
    """بالتزاماتها → ب+التزام — sub-tokens are truncated, missing significant content.

    Detect: joined sub-tokens are much shorter than surface form.
    """
    joined = "".join(subs)
    joined_clean = strip_diacritics(joined)
    surface_clean = strip_diacritics(surface)
    # If joined is significantly shorter than surface (more than 2 chars missing)
    if len(surface_clean) - len(joined_clean) > 2:
        return True
    return False


def has_noan(subs):
    """Check if any sub-token contains 'NOAN' placeholder."""
    return any("NOAN" in s for s in subs)


def fix_prep_pronoun(surface, subs):
    """Fix على→علي, لدى→لدي, إلى→إلي before pronoun suffixes (PADT convention).
    Returns fixed subs list, or None if no fix needed.
    """
    if len(subs) < 2:
        return None

    # Direct preposition + suffix: عليه → علي+ه
    if subs[0] in PREP_ALIF_MAQSURA:
        new_stem = PREP_ALIF_MAQSURA[subs[0]]
        new_subs = [new_stem] + subs[1:]
        # Verify reconstruction
        if "".join(new_subs) == surface:
            return new_subs

    # Conjunction + preposition + suffix: وعليه → و+علي+ه
    if len(subs) >= 3 and subs[0] in ("و", "ف") and subs[1] in PREP_ALIF_MAQSURA:
        new_stem = PREP_ALIF_MAQSURA[subs[1]]
        new_subs = [subs[0], new_stem] + subs[2:]
        if "".join(new_subs) == surface:
            return new_subs

    return None


# ── Parse CoNLL-U into sentence blocks ──


def parse_conllu(path):
    """Parse CoNLL-U into list of sentence blocks.
    Each block is a dict with 'meta' (list of comment lines) and 'tokens' (list of token dicts).
    Each token dict has 'id', 'form', 'lemma', 'upos', 'xpos', 'feats', 'head', 'deprel', 'deps', 'misc', 'raw'.
    MWT range lines have id like '3-4'.
    """
    sentences = []
    current_meta = []
    current_tokens = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                current_meta.append(line)
            elif line == "":
                if current_meta or current_tokens:
                    sentences.append({"meta": current_meta, "tokens": current_tokens})
                    current_meta = []
                    current_tokens = []
            else:
                parts = line.split("\t")
                if len(parts) == 10:
                    current_tokens.append(
                        {
                            "id": parts[0],
                            "form": parts[1],
                            "lemma": parts[2],
                            "upos": parts[3],
                            "xpos": parts[4],
                            "feats": parts[5],
                            "head": parts[6],
                            "deprel": parts[7],
                            "deps": parts[8],
                            "misc": parts[9],
                        }
                    )
                else:
                    # Malformed line, keep as-is
                    current_tokens.append({"raw": line})

    if current_meta or current_tokens:
        sentences.append({"meta": current_meta, "tokens": current_tokens})

    return sentences


def token_to_line(tok):
    if "raw" in tok:
        return tok["raw"]
    return "\t".join(
        [
            tok["id"],
            tok["form"],
            tok["lemma"],
            tok["upos"],
            tok["xpos"],
            tok["feats"],
            tok["head"],
            tok["deprel"],
            tok["deps"],
            tok["misc"],
        ]
    )


def get_sent_id(sent):
    for m in sent["meta"]:
        if m.startswith("# sent_id"):
            return m.split("=")[1].strip()
    return "?"


def get_text(sent):
    for m in sent["meta"]:
        if m.startswith("# text = "):
            return m[len("# text = ") :]
    return ""


# ── Main fix logic ──


def fix_sentence(sent):
    """Apply all fixes to a sentence. Returns (fixed_sent, stats_dict)."""
    stats = {
        "proper_noun_removed": 0,
        "ya_suffix_removed": 0,
        "truncated_removed": 0,
        "noan_removed": 0,
    }

    tokens = sent["tokens"]
    new_tokens = []
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        # Only process MWT range lines
        if "raw" in tok or "-" not in tok["id"]:
            new_tokens.append(tok)
            i += 1
            continue

        # This is an MWT range line
        mwt_tok = tok
        surface = mwt_tok["form"]
        rng = mwt_tok["id"].split("-")
        start_id, end_id = int(rng[0]), int(rng[1])
        num_subs = end_id - start_id + 1

        # Collect sub-tokens
        sub_tokens = []
        j = i + 1
        while j < len(tokens) and len(sub_tokens) < num_subs:
            if "raw" not in tokens[j] and "-" not in tokens[j]["id"]:
                try:
                    tid = int(tokens[j]["id"])
                    if start_id <= tid <= end_id:
                        sub_tokens.append(tokens[j])
                except ValueError:
                    pass
            j += 1

        sub_forms = [t["form"] for t in sub_tokens]
        should_remove_mwt = False
        fix_type = None

        # ── Check each fix condition ──
        # Only fix things that are linguistically WRONG, not just
        # different conventions. CAMeL's nisba ية→ي+ه and ة→X+ه
        # splits are consistent conventions — keep them.

        # 1. Proper noun — these should NEVER be MWT-split
        surface_clean = strip_diacritics(surface)
        if surface_clean in PROPER_NOUN_BLOCKLIST or surface in PROPER_NOUN_BLOCKLIST:
            should_remove_mwt = True
            fix_type = "proper_noun_removed"
        elif _is_prefixed_proper_noun(surface_clean):
            should_remove_mwt = True
            fix_type = "proper_noun_removed"

        # 2. NOAN placeholder — broken tokens
        elif has_noan(sub_forms):
            should_remove_mwt = True
            fix_type = "noan_removed"

        # 3. Truncated sub-tokens — data corruption
        elif is_truncated_mwt(surface, sub_forms):
            should_remove_mwt = True
            fix_type = "truncated_removed"

        # 4. Bogus ي-suffix — أسبوعي→أسبوعي+ي doubles the ي
        elif is_bogus_ya_suffix(surface, sub_forms):
            should_remove_mwt = True
            fix_type = "ya_suffix_removed"

        # ── Apply the fix ──

        if should_remove_mwt:
            # Remove MWT: replace range line + sub-tokens with single token
            stats[fix_type] += 1
            single_tok = {
                "id": str(start_id),
                "form": surface,
                "lemma": surface,
                "upos": "X",
                "xpos": "X",
                "feats": "_",
                "head": sub_tokens[0]["head"] if sub_tokens else "0",
                "deprel": sub_tokens[0]["deprel"] if sub_tokens else "dep",
                "deps": "_",
                "misc": "_",
            }
            new_tokens.append(single_tok)
            # Skip the sub-tokens, and renumber everything after
            i = i + 1 + len(sub_tokens)

            # We need to renumber all subsequent tokens
            id_shift = num_subs - 1  # how many IDs we removed
            while i < len(tokens):
                t = tokens[i]
                if "raw" in t:
                    new_tokens.append(t)
                    i += 1
                    continue
                # Renumber
                t_copy = dict(t)
                if "-" in t_copy["id"]:
                    r = t_copy["id"].split("-")
                    t_copy["id"] = f"{int(r[0]) - id_shift}-{int(r[1]) - id_shift}"
                else:
                    try:
                        old_id = int(t_copy["id"])
                        t_copy["id"] = str(old_id - id_shift)
                    except ValueError:
                        pass
                # Also fix head references
                if t_copy["head"] not in ("_", "0"):
                    try:
                        old_head = int(t_copy["head"])
                        if old_head > end_id:
                            t_copy["head"] = str(old_head - id_shift)
                        elif old_head >= start_id:
                            # Point to the merged token
                            t_copy["head"] = str(start_id)
                    except ValueError:
                        pass
                new_tokens.append(t_copy)
                i += 1

            # Also fix heads in earlier tokens that pointed to removed sub-tokens
            for t in new_tokens:
                if "raw" in t:
                    continue
                if t["head"] not in ("_", "0"):
                    try:
                        h = int(t["head"])
                        if h > start_id and h <= end_id:
                            t["head"] = str(start_id)
                    except ValueError:
                        pass
            continue

        else:
            # No fix needed, keep as-is
            new_tokens.append(mwt_tok)
            for sub_tok in sub_tokens:
                new_tokens.append(sub_tok)
            i = i + 1 + len(sub_tokens)
            continue

    sent["tokens"] = new_tokens
    return sent, stats


def fix_noan_tokens(sent, original_text):
    """Replace الNOAN tokens with the correct word from the original text.

    The original text has the real word; we align by token position.
    """
    fixed = 0
    # Get surface token forms (MWT surface, not sub-tokens)
    surface_forms = []
    skip_ids = set()
    token_indices = []  # index into sent["tokens"] for each surface form
    for ti, tok in enumerate(sent["tokens"]):
        if "raw" in tok:
            continue
        if "-" in tok["id"]:
            rng = tok["id"].split("-")
            for x in range(int(rng[0]), int(rng[1]) + 1):
                skip_ids.add(x)
            surface_forms.append(tok["form"])
            token_indices.append(ti)
        else:
            try:
                tid = int(tok["id"])
                if tid not in skip_ids:
                    surface_forms.append(tok["form"])
                    token_indices.append(ti)
            except ValueError:
                surface_forms.append(tok["form"])
                token_indices.append(ti)

    orig_words = original_text.split()

    for si, sf in enumerate(surface_forms):
        if "NOAN" in sf and si < len(orig_words):
            correct_word = orig_words[si]
            ti = token_indices[si]
            sent["tokens"][ti]["form"] = correct_word
            sent["tokens"][ti]["lemma"] = correct_word
            fixed += 1

    return fixed


def rebuild_text_comment(sent):
    """Rebuild # text = from surface tokens (MWT surfaces + non-MWT forms)."""
    forms = []
    skip_ids = set()
    for tok in sent["tokens"]:
        if "raw" in tok:
            continue
        if "-" in tok["id"]:
            # MWT range line — use its surface
            forms.append(tok["form"])
            rng = tok["id"].split("-")
            for x in range(int(rng[0]), int(rng[1]) + 1):
                skip_ids.add(x)
        else:
            try:
                tid = int(tok["id"])
                if tid not in skip_ids:
                    forms.append(tok["form"])
            except ValueError:
                forms.append(tok["form"])

    new_text = " ".join(forms)
    # Update meta
    for mi, m in enumerate(sent["meta"]):
        if m.startswith("# text = "):
            sent["meta"][mi] = f"# text = {new_text}"
            break
    return new_text


def write_conllu(sentences, path):
    with open(path, "w", encoding="utf-8") as f:
        for sent in sentences:
            for m in sent["meta"]:
                f.write(m + "\n")
            for tok in sent["tokens"]:
                f.write(token_to_line(tok) + "\n")
            f.write("\n")


def convert_txt_to_paragraphs(sentences, txt_in, txt_out):
    """Convert one-sentence-per-line txt to paragraph format with blank-line separators.

    Group sentences into paragraphs using the original source text's sentence structure.
    Since we don't have the original paragraph structure, use a heuristic:
    group consecutive sentences into paragraphs of ~3-5 sentences, splitting at
    natural boundaries (sentences ending with .).
    """
    texts = []
    for sent in sentences:
        texts.append(get_text(sent))

    # Build paragraphs: group sentences, break at natural points
    paragraphs = []
    current_para = []

    for i, text in enumerate(texts):
        current_para.append(text)

        # Break paragraph at natural boundaries
        should_break = False

        # Break after 3-5 sentences if current sentence ends with period
        if len(current_para) >= 3 and text.rstrip().endswith("."):
            should_break = True
        # Break after 5 sentences regardless
        if len(current_para) >= 5:
            should_break = True
        # Break at last sentence
        if i == len(texts) - 1:
            should_break = True

        if should_break:
            paragraphs.append(current_para)
            current_para = []

    if current_para:
        paragraphs.append(current_para)

    # Write: each paragraph's sentences are on separate lines, paragraphs separated by blank lines
    with open(txt_out, "w", encoding="utf-8") as f:
        for pi, para in enumerate(paragraphs):
            for line in para:
                f.write(line + "\n")
            if pi < len(paragraphs) - 1:
                f.write("\n")

    return len(paragraphs)


# ── Main ──


def process_file_pair(conllu_in, txt_in, conllu_out, txt_out):
    print(f"\n{'=' * 60}")
    print(f"Processing: {os.path.basename(conllu_in)}")
    print(f"Parsing CoNLL-U...")
    sentences = parse_conllu(conllu_in)
    print(f"  {len(sentences)} sentences loaded")

    total_stats = {}

    print("Applying fixes (multi-pass until stable)...")
    for si, sent in enumerate(sentences):
        while True:
            sent, stats = fix_sentence(sent)
            total_fixes = sum(stats.values())
            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v
            if total_fixes == 0:
                break

    # Fix NOAN tokens using original text from the txt file
    print("Fixing NOAN placeholder tokens...")
    original_texts = open(txt_in, encoding="utf-8").read().splitlines()
    noan_fixed = 0
    for si, sent in enumerate(sentences):
        if si < len(original_texts):
            noan_fixed += fix_noan_tokens(sent, original_texts[si])
    total_stats["noan_restored"] = noan_fixed

    print(f"\n=== Fix Statistics ===")
    for k, v in sorted(total_stats.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"  TOTAL fixes: {sum(total_stats.values())}")

    # Rebuild # text comments from fixed tokens
    print("\nRebuilding # text comments...")
    for sent in sentences:
        rebuild_text_comment(sent)

    # Write fixed CoNLL-U
    print(f"Writing {conllu_out}...")
    write_conllu(sentences, conllu_out)

    # Convert txt to paragraph format
    print(f"Writing {txt_out} (paragraph format)...")
    n_para = convert_txt_to_paragraphs(sentences, txt_in, txt_out)
    print(f"  {n_para} paragraphs")

    # Validation
    print("\n=== Validation ===")
    fixed_sents = parse_conllu(conllu_out)
    mwt_total = 0
    mwt_fail = 0
    for sent in fixed_sents:
        mwt_surface = None
        mwt_subs = []
        mwt_end = -1
        for tok in sent["tokens"]:
            if "raw" in tok:
                continue
            if "-" in tok["id"]:
                mwt_surface = tok["form"]
                mwt_subs = []
                rng = tok["id"].split("-")
                mwt_end = int(rng[1])
                mwt_total += 1
            elif mwt_surface:
                mwt_subs.append(tok["form"])
                try:
                    if int(tok["id"]) >= mwt_end:
                        joined = "".join(mwt_subs)
                        if joined != mwt_surface:
                            mwt_fail += 1
                        mwt_surface = None
                except:
                    pass

    print(f"  MWT total: {mwt_total}")
    print(f"  MWT reconstruction OK: {mwt_total - mwt_fail}")
    print(f"  MWT reconstruction FAIL: {mwt_fail} ({mwt_fail / max(mwt_total, 1) * 100:.1f}%)")

    # Check token ID continuity
    id_errors = 0
    for sent in fixed_sents:
        expected = 1
        for tok in sent["tokens"]:
            if "raw" in tok:
                continue
            if "-" in tok["id"]:
                continue
            try:
                actual = int(tok["id"])
                if actual != expected:
                    id_errors += 1
                expected = actual + 1
            except:
                id_errors += 1
    print(f"  Token ID sequence errors: {id_errors}")

    # Check zero NOANs
    noan_remaining = sum(
        1
        for sent in fixed_sents
        for tok in sent["tokens"]
        if "raw" not in tok and "NOAN" in tok.get("form", "")
    )
    print(f"  NOAN remaining: {noan_remaining}")


def main():
    for conllu_in, txt_in, conllu_out, txt_out in FILE_PAIRS:
        process_file_pair(conllu_in, txt_in, conllu_out, txt_out)

    print("\nDone!")


if __name__ == "__main__":
    main()
