#!/usr/bin/env python3
"""Decide which training runs produced the models a deployment actually loads.

The question this answers is not answerable from filenames. Directory names such as
`trankit_save_sa_vedic_v1` and `_final` claim a relationship to the deployed model
that may not hold. This compares artefacts instead.

Method
------
Every Trankit run writes its outputs as `.mdl` (tokenizer/tagger/NER) and `.pt`
(lemmatizer/MWT expander) files. A run produced a deployed model if one of its outputs
is byte-identical to a file in the deployed model store. Size is used as a cheap first
pass; --hash confirms survivors with SHA-256.

Sizes shared by more than `--ambiguous-threshold` deployed files are discarded. In
practice these are the XLM-R tokenizer checkpoints, which are identical across
languages and therefore carry no provenance information.

Usage
-----
    python check_provenance.py --runs <dir of trankit_save_* dirs> \
                               --deployed <deployed model store> [--hash]

Both paths are local and are not included in this repository; see research/README.md.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

MODEL_SUFFIXES = {".mdl", ".pt"}


def collect(root: Path) -> dict[int, list[Path]]:
    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in MODEL_SUFFIXES:
            by_size[p.stat().st_size].append(p)
    return by_size


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True, type=Path,
                    help="directory containing trankit_save_* run directories")
    ap.add_argument("--deployed", required=True, type=Path,
                    help="deployed model store (the xlm-roberta-base directory)")
    ap.add_argument("--hash", action="store_true",
                    help="confirm size matches with SHA-256 (slow; reads every pair)")
    ap.add_argument("--ambiguous-threshold", type=int, default=2)
    args = ap.parse_args()

    deployed = collect(args.deployed)
    ambiguous = {s for s, v in deployed.items() if len(v) > args.ambiguous_threshold}

    run_dirs = sorted(d for d in args.runs.iterdir()
                      if d.is_dir() and d.name.startswith("trankit_save_"))

    shipped: dict[str, set[str]] = defaultdict(set)
    produced_nothing: list[str] = []
    no_match: list[str] = []

    for d in run_dirs:
        outputs = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in MODEL_SUFFIXES]
        if not outputs:
            produced_nothing.append(d.name)
            continue
        matched = False
        for out in outputs:
            size = out.stat().st_size
            if size in ambiguous or size not in deployed:
                continue
            for dep in deployed[size]:
                if args.hash and sha256(out) != sha256(dep):
                    continue
                shipped[d.name].add(dep.parent.name)
                matched = True
        if not matched:
            no_match.append(d.name)

    verified = "sha256" if args.hash else "size"
    print(f"# Provenance ({verified} comparison)\n")
    print("| Run | Status | Shipped as |")
    print("|---|---|---|")
    for name in sorted(shipped):
        print(f"| {name} | Shipped | {', '.join(sorted(shipped[name]))} |")
    for name in sorted(no_match):
        print(f"| {name} | Abandoned | produced weights, none deployed |")
    for name in sorted(produced_nothing):
        print(f"| {name} | Abandoned | no weights produced |")
    print(f"\n{len(shipped)} shipped, {len(no_match)} unused, "
          f"{len(produced_nothing)} produced nothing, {len(run_dirs)} runs total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
