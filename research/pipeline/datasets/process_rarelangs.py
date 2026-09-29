#!/usr/bin/env python3
"""
Process UD treebank zips for trankit training.
"""

import os
import sys
import re
import zipfile
import shutil
import tempfile
from pathlib import Path
from collections import defaultdict

PYTHON = r"C:/Users/conra/AppData/Local/Programs/Python/Python312/python.exe"

ZIPS_DIR = Path(r"C:/Users/conra/Desktop/universal/training/rarelangs")
OUTPUT_DIR = Path(r"C:/Users/conra/Desktop/universal/training/rarelangs_prepped")

TARGETS = [
    ("UD_Assamese-AiW-dev.zip",      "assamese",   "as"),
    ("UD_Bengali-Sabdakosh-dev.zip",  "bengali",    "bn"),
    ("UD_Old_Japanese-LMJ-dev.zip",   "old_japanese","ojp"),
    ("UD_Marathi-CMUPAN-dev.zip",     "marathi",    "mr"),
    ("UD_Prakrit-DIPI-dev.zip",       "prakrit",    "pkt"),
    ("UD_Punjabi-PunTB-dev.zip",      "punjabi",    "pa"),
]

# ─────────────────────────────────────────────
# CoNLL-U helpers
# ─────────────────────────────────────────────

def read_sentences(path):
    """Return list of sentences; each sentence is a list of raw lines (str, no newline)."""
    sentences = []
    current = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if line == "":
                if current:
                    sentences.append(current)
                    current = []
            else:
                current.append(line)
    if current:
        sentences.append(current)
    return sentences


def write_sentences(sentences, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for sent in sentences:
            for line in sent:
                f.write(line + "\n")
            f.write("\n")


def is_token_line(line):
    """True for regular token lines (not comments, not MWT, not empty nodes)."""
    if line.startswith("#"):
        return False
    parts = line.split("\t")
    if not parts:
        return False
    idx = parts[0]
    if "-" in idx or "." in idx:
        return False
    return True


def is_mwt_line(line):
    if line.startswith("#"):
        return False
    parts = line.split("\t")
    if not parts:
        return False
    return "-" in parts[0]


def get_text_comment(sent):
    for line in sent:
        m = re.match(r"#\s*text\s*=\s*(.*)", line)
        if m:
            return m.group(1).strip()
    return None


def surface_from_tokens(sent):
    tokens = []
    for line in sent:
        if is_token_line(line):
            parts = line.split("\t")
            if len(parts) >= 2:
                tokens.append(parts[1])
    return " ".join(tokens)


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────

def validate(sentences, label=""):
    issues = []
    upos_set = set()
    mwt_count = 0
    unannotated_upos = 0
    head_errors = 0
    token_id_errors = 0
    text_mismatch = 0
    has_lemmas = False
    has_feats = False

    for si, sent in enumerate(sentences):
        token_ids = []
        token_forms = []
        for line in sent:
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 10:
                issues.append(f"  [{label}] sent {si+1}: short line ({len(parts)} cols): {line[:60]}")
                continue
            idx, form, lemma, upos, xpos, feats, head, deprel, deps, misc = parts[:10]

            if "-" in idx:
                mwt_count += 1
                continue
            if "." in idx:
                continue  # empty nodes

            try:
                iint = int(idx)
            except ValueError:
                issues.append(f"  [{label}] sent {si+1}: non-integer token id: {idx}")
                token_id_errors += 1
                continue

            token_ids.append(iint)
            token_forms.append(form)

            if upos == "_":
                unannotated_upos += 1
            else:
                upos_set.add(upos)

            if lemma != "_":
                has_lemmas = True
            if feats != "_":
                has_feats = True

            # HEAD check
            try:
                h = int(head)
                if h < 0 or h > len([l for l in sent if is_token_line(l)]):
                    head_errors += 1
                    if head_errors <= 3:
                        issues.append(f"  [{label}] sent {si+1} tok {idx}: HEAD={head} out of range")
            except ValueError:
                head_errors += 1
                if head_errors <= 3:
                    issues.append(f"  [{label}] sent {si+1} tok {idx}: HEAD not numeric: {head}")

        # Check token ID sequence
        expected = list(range(1, len(token_ids) + 1))
        if token_ids != expected:
            token_id_errors += 1
            if token_id_errors <= 3:
                issues.append(f"  [{label}] sent {si+1}: token IDs {token_ids[:5]}... expected {expected[:5]}...")

        # Check text= comment vs surface
        text_comment = get_text_comment(sent)
        surface = "".join(token_forms)  # rough check: strip spaces
        if text_comment is not None:
            tc_stripped = re.sub(r"\s+", "", text_comment)
            sf_stripped = re.sub(r"\s+", "", surface)
            if tc_stripped != sf_stripped:
                text_mismatch += 1
                if text_mismatch <= 2:
                    issues.append(f"  [{label}] sent {si+1}: text= mismatch. comment='{text_comment[:40]}' surface='{surface[:40]}'")

    if unannotated_upos > 0:
        issues.append(f"  [{label}] {unannotated_upos} lines have UPOS=_")
    if head_errors > 3:
        issues.append(f"  [{label}] ... and {head_errors-3} more HEAD errors")
    if token_id_errors > 3:
        issues.append(f"  [{label}] ... and {token_id_errors-3} more token ID errors")
    if text_mismatch > 2:
        issues.append(f"  [{label}] ... and {text_mismatch-2} more text= mismatches")

    return {
        "sent_count": len(sentences),
        "mwt_count": mwt_count,
        "upos_set": upos_set,
        "unannotated_upos": unannotated_upos,
        "head_errors": head_errors,
        "token_id_errors": token_id_errors,
        "text_mismatch": text_mismatch,
        "has_lemmas": has_lemmas,
        "has_feats": has_feats,
        "issues": issues,
    }


# ─────────────────────────────────────────────
# Main processing
# ─────────────────────────────────────────────

def process_zip(zip_path, langname, lang_code):
    print(f"\n{'='*60}")
    print(f"Processing: {zip_path.name}  ->  {langname} ({lang_code})")
    print('='*60)

    tmpdir = Path(tempfile.mkdtemp(prefix=f"ud_{langname}_"))
    try:
        # Extract
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        # Find all conllu files
        conllu_files = list(tmpdir.rglob("*.conllu"))
        print(f"Found conllu files: {[f.name for f in conllu_files]}")

        # Categorise by split
        train_files = []
        dev_files = []
        test_files = []
        for f in conllu_files:
            name = f.name.lower()
            if "-train." in name:
                train_files.append(f)
            elif "-dev." in name:
                dev_files.append(f)
            elif "-test." in name:
                test_files.append(f)
            else:
                # Try to guess from content/name
                print(f"  Unrecognized split pattern: {f.name}, treating as train")
                train_files.append(f)

        print(f"  train={[f.name for f in train_files]}")
        print(f"  dev  ={[f.name for f in dev_files]}")
        print(f"  test ={[f.name for f in test_files]}")

        # Read all train sentences
        train_sents = []
        for tf in sorted(train_files):
            s = read_sentences(tf)
            print(f"  Read {len(s)} sentences from {tf.name}")
            train_sents.extend(s)

        # Read test and merge into train
        for tf in sorted(test_files):
            s = read_sentences(tf)
            print(f"  Merging {len(s)} test sentences into train from {tf.name}")
            train_sents.extend(s)

        # Read dev if exists
        dev_sents = []
        for df in sorted(dev_files):
            s = read_sentences(df)
            print(f"  Read {len(s)} dev sentences from {df.name}")
            dev_sents.extend(s)

        # If no dev, split 10% off train (last 10%)
        if not dev_sents:
            n = len(train_sents)
            split_idx = max(1, int(n * 0.9))
            dev_sents = train_sents[split_idx:]
            train_sents = train_sents[:split_idx]
            print(f"  No dev found – split last 10%: train={len(train_sents)}, dev={len(dev_sents)}")

        # Output paths
        out_dir = OUTPUT_DIR / langname
        out_dir.mkdir(parents=True, exist_ok=True)
        train_out = out_dir / f"{lang_code}-train.conllu"
        dev_out   = out_dir / f"{lang_code}-dev.conllu"
        train_txt = out_dir / f"{lang_code}-train.txt"
        dev_txt   = out_dir / f"{lang_code}-dev.txt"

        write_sentences(train_sents, train_out)
        write_sentences(dev_sents,   dev_out)
        print(f"  Written: {train_out}")
        print(f"  Written: {dev_out}")

        # Write .txt surface text files
        with open(train_txt, "w", encoding="utf-8") as f:
            for sent in train_sents:
                text = get_text_comment(sent) or surface_from_tokens(sent)
                f.write(text + "\n")
        with open(dev_txt, "w", encoding="utf-8") as f:
            for sent in dev_sents:
                text = get_text_comment(sent) or surface_from_tokens(sent)
                f.write(text + "\n")
        print(f"  Written: {train_txt}")
        print(f"  Written: {dev_txt}")

        # Validate
        print(f"\n  --- Validation ---")
        train_val = validate(train_sents, f"{lang_code}-train")
        dev_val   = validate(dev_sents,   f"{lang_code}-dev")

        for v, split in [(train_val, "train"), (dev_val, "dev")]:
            print(f"  [{split}] sents={v['sent_count']}, mwt={v['mwt_count']}, "
                  f"upos={sorted(v['upos_set'])}, unannotated_upos={v['unannotated_upos']}, "
                  f"head_errors={v['head_errors']}, token_id_errors={v['token_id_errors']}, "
                  f"text_mismatch={v['text_mismatch']}, "
                  f"has_lemmas={v['has_lemmas']}, has_feats={v['has_feats']}")
            for issue in v["issues"]:
                print(issue)

        return {
            "langname": langname,
            "lang_code": lang_code,
            "train_sents": train_val["sent_count"],
            "dev_sents": dev_val["sent_count"],
            "mwt_tokens": train_val["mwt_count"] + dev_val["mwt_count"],
            "upos_types": sorted(train_val["upos_set"] | dev_val["upos_set"]),
            "has_lemmas": train_val["has_lemmas"] or dev_val["has_lemmas"],
            "has_feats": train_val["has_feats"] or dev_val["has_feats"],
            "train_issues": train_val["issues"],
            "dev_issues": dev_val["issues"],
            "train_unannotated_upos": train_val["unannotated_upos"],
            "dev_unannotated_upos": dev_val["unannotated_upos"],
            "train_head_errors": train_val["head_errors"],
            "dev_head_errors": dev_val["head_errors"],
            "train_token_id_errors": train_val["token_id_errors"],
            "dev_token_id_errors": dev_val["token_id_errors"],
        }

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for zip_name, langname, lang_code in TARGETS:
        zip_path = ZIPS_DIR / zip_name
        if not zip_path.exists():
            print(f"ERROR: {zip_path} not found!")
            continue
        result = process_zip(zip_path, langname, lang_code)
        results.append(result)

    # Summary table
    print("\n\n" + "="*100)
    print("SUMMARY TABLE")
    print("="*100)
    header = f"{'Language':<15} {'Code':<6} {'Train':<8} {'Dev':<6} {'MWT':<6} {'UPOS_types':<12} {'Lemmas':<8} {'Feats':<7} Issues"
    print(header)
    print("-"*100)
    for r in results:
        all_issues = r["train_issues"] + r["dev_issues"]
        unannotated = r["train_unannotated_upos"] + r["dev_unannotated_upos"]
        head_errs = r["train_head_errors"] + r["dev_head_errors"]
        tok_errs = r["train_token_id_errors"] + r["dev_token_id_errors"]

        issue_summary = []
        if unannotated: issue_summary.append(f"unannotated_upos={unannotated}")
        if head_errs:   issue_summary.append(f"head_errors={head_errs}")
        if tok_errs:    issue_summary.append(f"tok_id_errors={tok_errs}")
        if not issue_summary: issue_summary = ["none"]

        print(f"{r['langname']:<15} {r['lang_code']:<6} {r['train_sents']:<8} {r['dev_sents']:<6} "
              f"{r['mwt_tokens']:<6} {len(r['upos_types']):<12} {str(r['has_lemmas']):<8} "
              f"{str(r['has_feats']):<7} {', '.join(issue_summary)}")

    print("\nUPOS inventories:")
    for r in results:
        print(f"  {r['langname']} ({r['lang_code']}): {r['upos_types']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
