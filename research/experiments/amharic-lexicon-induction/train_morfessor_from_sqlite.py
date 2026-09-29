"""
Train a Morfessor model from a dictionary SQLite database.

The primary use case is exporting Ancient Greek forms from ``dict_sqlite/grc.sqlite``
into a counted wordlist and training a local Morfessor model that can be loaded by
the experiment Flask app.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import math
import random
import sqlite3
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import morfessor
from morfessor import baseline as morfessor_baseline


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = REPO_ROOT / "dict_sqlite" / "grc.sqlite"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "models" / "morfessor_grc"
TOKEN_STRIP_CHARS = "\u00B7.,;:!?()[]{}<>\"'"
EDGE_APOSTROPHES = "\u1FBD'\u2019`"
ALLOWED_INNER_PUNCT = {
    "-",
    "\u2010",
    "\u2011",
    "\u2012",
    "\u2013",
    "\u2014",
    "\u1FBD",
    "'",
}
PROGRESS_EVERY = 100_000


def is_combining_mark(char: str) -> bool:
    return unicodedata.category(char).startswith("M")


def is_greek_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x0370 <= codepoint <= 0x03FF
        or 0x1F00 <= codepoint <= 0x1FFF
        or codepoint == 0x0342
        or codepoint == 0x0345
    )


def normalize_token(token: str) -> str:
    token = unicodedata.normalize("NFC", (token or "").strip())
    token = token.strip(TOKEN_STRIP_CHARS)
    token = token.strip(EDGE_APOSTROPHES)
    token = unicodedata.normalize("NFC", token)
    return token


def is_valid_greek_token(token: str) -> bool:
    if not token:
        return False
    if any(char.isspace() for char in token):
        return False
    has_greek = False
    for char in token:
        if is_greek_char(char):
            has_greek = True
            continue
        if is_combining_mark(char):
            continue
        if char in ALLOWED_INNER_PUNCT:
            continue
        return False
    return has_greek


def iter_dictionary_tokens(conn: sqlite3.Connection):
    cur = conn.cursor()
    for (headword,) in cur.execute("SELECT headword FROM entries"):
        yield "entry", headword
    for form_text, morph_tags in cur.execute("SELECT form_text, morph_tags FROM forms"):
        yield "form", form_text


def build_counter(sqlite_path: Path) -> tuple[Counter[str], dict]:
    counter: Counter[str] = Counter()
    stats = {
        "entries_seen": 0,
        "forms_seen": 0,
        "kept_tokens": 0,
        "rejected_tokens": 0,
    }

    started_at = time.time()
    processed = 0

    conn = sqlite3.connect(str(sqlite_path))
    try:
        for source, raw_token in iter_dictionary_tokens(conn):
            processed += 1
            if source == "entry":
                stats["entries_seen"] += 1
            else:
                stats["forms_seen"] += 1

            token = normalize_token(raw_token)
            if not is_valid_greek_token(token):
                stats["rejected_tokens"] += 1
                continue

            counter[token] += 1
            stats["kept_tokens"] += 1

            if processed % PROGRESS_EVERY == 0:
                elapsed = time.time() - started_at
                print(
                    f"[export] processed={processed:,} kept={stats['kept_tokens']:,} "
                    f"rejected={stats['rejected_tokens']:,} unique={len(counter):,} "
                    f"elapsed={elapsed:.1f}s",
                    flush=True,
                )
    finally:
        conn.close()

    stats["unique_tokens"] = len(counter)
    return counter, stats


def write_wordlist(counter: Counter[str], wordlist_path: Path) -> None:
    wordlist_path.parent.mkdir(parents=True, exist_ok=True)
    with wordlist_path.open("w", encoding="utf-8", newline="\n") as handle:
        for token, count in counter.most_common():
            handle.write(f"{count} {token}\n")


def get_count_modifier(mode: str):
    if mode == "none":
        return None
    if mode == "ones":
        return lambda _: 1
    if mode == "log":
        return lambda count: int(round(math.log(count + 1, 2)))
    raise ValueError(f"Unsupported dampening mode: {mode}")


def train_model(
    wordlist_path: Path,
    full_model_path: Path,
    reduced_model_path: Path,
    manifest_path: Path,
    manifest_base: dict,
    dampening: str,
    finish_threshold: float,
    max_epochs: int | None,
) -> dict:
    io = morfessor.MorfessorIO()
    model = morfessor.BaselineModel()
    count_modifier = get_count_modifier(dampening)

    print(f"[train] loading wordlist: {wordlist_path}", flush=True)
    train_data = io.read_corpus_list_file(str(wordlist_path))
    model.load_data(train_data, count_modifier=count_modifier)
    print(
        "[train] starting Morfessor batch training "
        f"(dampening={dampening}, finish_threshold={finish_threshold}, max_epochs={max_epochs})",
        flush=True,
    )
    checkpoints = []

    def save_checkpoint(
        *,
        epochs_completed: int,
        current_cost: float,
        interrupted: bool,
        interrupted_during_epoch: int | None = None,
    ) -> None:
        io.write_binary_model_file(str(full_model_path), model)
        reduced_model = copy.deepcopy(model)
        reduced_model.make_segment_only()
        io.write_binary_model_file(str(reduced_model_path), reduced_model)

        checkpoint_payload = {
            **manifest_base,
            "training": {
                "epochs": epochs_completed,
                "final_cost": current_cost,
                "interrupted": interrupted,
                "interrupted_during_epoch": interrupted_during_epoch,
                "history": checkpoints,
            },
        }
        manifest_path.write_text(
            json.dumps(checkpoint_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    epochs = 0
    forced_epochs = max(1, model._epoch_update(epochs))
    current_cost = model.get_cost()
    compounds = list(model.get_compounds())
    morfessor_baseline._logger.info(
        "Compounds in training data: %s types / %s tokens",
        len(compounds),
        model._corpus_coding.boundaries,
    )
    morfessor_baseline._logger.info("Starting batch training")
    morfessor_baseline._logger.info("Epochs: %s\tCost: %s", epochs, current_cost)
    checkpoints.append({"epoch": epochs, "cost": current_cost})
    save_checkpoint(
        epochs_completed=epochs,
        current_cost=current_cost,
        interrupted=False,
    )
    print(f"[checkpoint] saved initial model state at epoch {epochs}", flush=True)

    interrupted = False
    interrupted_during_epoch = None

    while True:
        random.shuffle(compounds)
        try:
            for word in morfessor_baseline._progress(compounds):
                model._recursive_optimize(word)
        except KeyboardInterrupt:
            interrupted = True
            interrupted_during_epoch = epochs + 1
            current_cost = model.get_cost()
            print(
                f"\n[train] interrupted during epoch {interrupted_during_epoch}; "
                "saving current model state...",
                flush=True,
            )
            save_checkpoint(
                epochs_completed=epochs,
                current_cost=current_cost,
                interrupted=True,
                interrupted_during_epoch=interrupted_during_epoch,
            )
            print("[checkpoint] saved interrupted model state", flush=True)
            break

        epochs += 1
        forced_epochs = max(forced_epochs, model._epoch_update(epochs))
        old_cost = current_cost
        current_cost = model.get_cost()
        checkpoints.append({"epoch": epochs, "cost": current_cost})
        morfessor_baseline._logger.info("Epochs: %s\tCost: %s", epochs, current_cost)
        save_checkpoint(
            epochs_completed=epochs,
            current_cost=current_cost,
            interrupted=False,
        )
        print(f"[checkpoint] saved epoch {epochs}", flush=True)

        if (
            forced_epochs == 0
            and current_cost >= old_cost - finish_threshold * model._corpus_coding.boundaries
        ):
            break
        if forced_epochs > 0:
            forced_epochs -= 1
        if max_epochs is not None and epochs >= max_epochs:
            morfessor_baseline._logger.info("Max number of epochs reached, stop training")
            break

    morfessor_baseline._logger.info("Done.")
    print(
        f"[train] finished training: epochs={epochs} final_cost={current_cost} "
        f"interrupted={interrupted}",
        flush=True,
    )
    return {
        "epochs": epochs,
        "final_cost": current_cost,
        "interrupted": interrupted,
        "interrupted_during_epoch": interrupted_during_epoch,
        "history": checkpoints,
    }


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )


def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--dampening",
        choices=["none", "log", "ones"],
        default="ones",
        help="Count handling for dictionary-derived training data.",
    )
    parser.add_argument("--finish-threshold", type=float, default=0.005)
    parser.add_argument("--max-epochs", type=int, default=None)
    args = parser.parse_args()

    sqlite_path = args.sqlite.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    wordlist_path = out_dir / "grc_wordlist.txt"
    full_model_path = out_dir / "grc_model.bin"
    reduced_model_path = out_dir / "grc_model.reduced.bin"
    manifest_path = out_dir / "grc_manifest.json"

    started_at = time.time()
    print(f"[main] sqlite={sqlite_path}", flush=True)
    print(f"[main] out_dir={out_dir}", flush=True)
    print("[main] building counted Ancient Greek wordlist from SQLite...", flush=True)
    counter, stats = build_counter(sqlite_path)
    print(
        "[main] finished wordlist export: "
        f"entries={stats['entries_seen']:,} forms={stats['forms_seen']:,} "
        f"kept={stats['kept_tokens']:,} rejected={stats['rejected_tokens']:,} "
        f"unique={stats['unique_tokens']:,}",
        flush=True,
    )
    print(f"[main] writing wordlist: {wordlist_path}", flush=True)
    write_wordlist(counter, wordlist_path)
    manifest_base = {
        "sqlite_path": str(sqlite_path),
        "wordlist_path": str(wordlist_path),
        "full_model_path": str(full_model_path),
        "reduced_model_path": str(reduced_model_path),
        "dampening": args.dampening,
        "finish_threshold": args.finish_threshold,
        "max_epochs": args.max_epochs,
        "stats": stats,
    }
    training_stats = train_model(
        wordlist_path=wordlist_path,
        full_model_path=full_model_path,
        reduced_model_path=reduced_model_path,
        manifest_path=manifest_path,
        manifest_base=manifest_base,
        dampening=args.dampening,
        finish_threshold=args.finish_threshold,
        max_epochs=args.max_epochs,
    )
    duration_seconds = round(time.time() - started_at, 3)

    manifest = {
        **manifest_base,
        "duration_seconds": duration_seconds,
        "training": training_stats,
    }
    print(f"[main] writing manifest: {manifest_path}", flush=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
