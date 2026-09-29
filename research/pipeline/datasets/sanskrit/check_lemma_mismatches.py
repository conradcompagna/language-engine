#!/usr/bin/env python3
"""Scan DCS conllu corpus and report tokens where the conllu lemma column
does NOT match the dictionary.csv headword referenced by LemmaId.

Output: /tmp/sa_lemma_mismatches.log
  - summary counts
  - aggregated (lemma_id, dict_headword, conllu_lemma, count)
"""
import csv
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_DIR = Path(__file__).resolve().parent
CSV_PATH = THIS_DIR / "data" / "conllu" / "lookup" / "dictionary.csv"
CONLLU_ROOT = THIS_DIR / "data" / "conllu" / "files"

LEMMA_RE = re.compile(r"(?:^|\|)LemmaId=(\d+)")


def nfc(s):
    return unicodedata.normalize("NFC", (s or "").strip())


def open_long(p):
    sp = str(p)
    if os.name == "nt" and not sp.startswith("\\\\?\\"):
        sp = "\\\\?\\" + os.path.abspath(sp)
    return open(sp, encoding="utf-8")


def load_headwords():
    hw = {}
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter="\t")
        next(r)
        for row in r:
            if not row:
                continue
            try:
                lid = int(row[0])
            except ValueError:
                continue
            hw[lid] = nfc(row[1])
    return hw


def main():
    print("loading dictionary.csv...", flush=True)
    hw = load_headwords()
    print(f"  {len(hw):,} headwords", flush=True)

    files = []
    for sub in sorted(os.listdir(CONLLU_ROOT)):
        d = CONLLU_ROOT / sub
        if not d.is_dir():
            continue
        for fn in os.listdir(d):
            if fn.endswith(".conllu"):
                files.append(d / fn)
    print(f"scanning {len(files)} conllu files...", flush=True)

    total_tokens = 0
    match = 0
    mismatch = 0
    missing_lemma_id = 0       # LemmaId not in CSV
    empty_conllu_lemma = 0     # conllu lemma col is '_' or ''
    mismatches = Counter()     # (lemma_id, dict_hw, conllu_lemma) -> count

    import time
    t0 = time.time()

    for idx, fp in enumerate(files):
        try:
            with open_long(fp) as f:
                for line in f:
                    if not line or line[0] == "#" or line[0] == "\n":
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 10:
                        continue
                    tok_id = parts[0]
                    if "-" in tok_id or "." in tok_id:
                        continue
                    conllu_lemma = parts[2]
                    misc = parts[9]
                    m = LEMMA_RE.search(misc)
                    if not m:
                        continue
                    lid = int(m.group(1))
                    total_tokens += 1
                    dict_hw = hw.get(lid)
                    if dict_hw is None:
                        missing_lemma_id += 1
                        continue
                    cl_n = nfc(conllu_lemma)
                    if not cl_n or cl_n == "_":
                        empty_conllu_lemma += 1
                        continue
                    if cl_n == dict_hw:
                        match += 1
                    else:
                        mismatch += 1
                        mismatches[(lid, dict_hw, cl_n)] += 1
        except Exception as e:
            print(f"  err in {fp}: {e}", flush=True)

        if (idx + 1) % 2000 == 0:
            print(f"  {idx+1}/{len(files)}  elapsed={time.time()-t0:.0f}s", flush=True)

    print()
    print("=" * 80)
    print(f"total tokens with LemmaId:      {total_tokens:,}")
    print(f"  match:                        {match:,}")
    print(f"  mismatch:                     {mismatch:,}")
    print(f"  LemmaId not in CSV:           {missing_lemma_id:,}")
    print(f"  conllu lemma empty/'_':       {empty_conllu_lemma:,}")
    print(f"distinct mismatch triples:      {len(mismatches):,}")
    print("=" * 80)
    print()
    print("TOP 50 MISMATCHES BY COUNT")
    print("-" * 80)
    print(f"{'lemma_id':>8}  {'dict_headword':<30}  {'conllu_lemma':<30}  count")
    print("-" * 80)
    for (lid, dh, cl), cnt in mismatches.most_common(50):
        print(f"{lid:>8}  {dh:<30}  {cl:<30}  {cnt}")
    print()
    print("FULL MISMATCH LIST")
    print("-" * 80)
    for (lid, dh, cl), cnt in sorted(mismatches.items(), key=lambda x: (-x[1], x[0])):
        print(f"{lid}\t{dh}\t{cl}\t{cnt}")


if __name__ == "__main__":
    main()
