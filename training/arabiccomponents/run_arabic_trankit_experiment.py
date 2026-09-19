from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import trankit


EXPERIMENT_TAG = "trankit_exp_20260405a"
CATEGORY = "arabic_camelmorph_exp"
EMBEDDING = "xlm-roberta-base"

HERE = Path(__file__).resolve().parent
TRAINING_ROOT = HERE.parent
LAST_SAVE_DIR_FILE = HERE / "last_arabic_trankit_experiment_save_dir.txt"

MWT_TRAIN = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_train_full.conllu"
MWT_DEV_GOLD = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_dev_compat.conllu"
MWT_DEV_TOKENIZER = HERE / f"camelmorph_mwt_{EXPERIMENT_TAG}_dev_tokenizer_input.conllu"
LEMMA_TRAIN = HERE / f"camelmorph_lemmatizer_{EXPERIMENT_TAG}_train.conllu"
LEMMA_DEV = HERE / f"camelmorph_lemmatizer_{EXPERIMENT_TAG}_dev.conllu"


def build_unique_save_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = TRAINING_ROOT / f"trankit_save_ar_camelmorph_exp_{stamp}"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = TRAINING_ROOT / f"trankit_save_ar_camelmorph_exp_{stamp}_{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def read_last_save_dir() -> Path:
    if not LAST_SAVE_DIR_FILE.exists():
        raise SystemExit(
            f"No saved experiment directory found at {LAST_SAVE_DIR_FILE}. "
            "Run the MWT command first or pass --save-dir."
        )
    text = LAST_SAVE_DIR_FILE.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"{LAST_SAVE_DIR_FILE} is empty.")
    return Path(text)


def resolve_save_dir(args: argparse.Namespace) -> Path:
    if args.save_dir:
        return Path(args.save_dir).resolve()
    if args.reuse_last_save_dir:
        return read_last_save_dir().resolve()
    if args.task == "mwt":
        return build_unique_save_dir().resolve()
    raise SystemExit("For lemmatize, pass --save-dir or --reuse-last-save-dir.")


def ensure_inputs_exist(task: str) -> None:
    required = {
        "mwt": [MWT_TRAIN, MWT_DEV_GOLD, MWT_DEV_TOKENIZER],
        "lemmatize": [LEMMA_TRAIN, LEMMA_DEV],
    }[task]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required input files:\n" + "\n".join(missing))


def prepare_preds_dir(save_dir: Path, task: str) -> Path:
    preds_dir = save_dir / EMBEDDING / CATEGORY / "preds"
    if preds_dir.exists():
        shutil.rmtree(preds_dir)
    preds_dir.mkdir(parents=True, exist_ok=True)
    if task == "mwt":
        shutil.copyfile(MWT_DEV_TOKENIZER, preds_dir / "tokenizer.dev.conllu")
    return preds_dir


def record_save_dir(save_dir: Path) -> None:
    LAST_SAVE_DIR_FILE.write_text(str(save_dir), encoding="utf-8")


def build_training_config(task: str, save_dir: Path) -> dict[str, object]:
    if task == "mwt":
        return {
            "category": CATEGORY,
            "task": "mwt",
            "save_dir": str(save_dir),
            "train_conllu_fpath": str(MWT_TRAIN),
            "dev_conllu_fpath": str(MWT_DEV_GOLD),
        }
    return {
        "category": CATEGORY,
        "task": "lemmatize",
        "save_dir": str(save_dir),
        "train_conllu_fpath": str(LEMMA_TRAIN),
        "dev_conllu_fpath": str(LEMMA_DEV),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["mwt", "lemmatize"])
    parser.add_argument("--save-dir")
    parser.add_argument("--reuse-last-save-dir", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_inputs_exist(args.task)
    save_dir = resolve_save_dir(args)
    preds_dir = prepare_preds_dir(save_dir, args.task)
    record_save_dir(save_dir)

    print(f"Task: {args.task}")
    print(f"Save dir: {save_dir}")
    print(f"Preds dir: {preds_dir}")

    config = build_training_config(args.task, save_dir)
    trankit.TPipeline(training_config=config).train()

    if args.task == "mwt":
        print(
            "Reuse this save dir for lemmatize with:\n"
            "python -X utf8 training/arabiccomponents/run_arabic_trankit_experiment.py "
            "lemmatize --reuse-last-save-dir"
        )


if __name__ == "__main__":
    main()
