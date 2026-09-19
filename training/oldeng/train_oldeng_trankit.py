from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_oldeng_trankit_dataset import build_all


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
DEFAULT_SAVE_DIR = ROOT_DIR / "training" / "trankit_save_oldeng_v1"
DEFAULT_TASKS = ("tokenize", "posdep", "lemmatize")
TASK_ORDER = ("tokenize", "posdep", "lemmatize")
CATEGORY = "customized"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and train a customized Trankit pipeline for Old English."
    )
    parser.add_argument(
        "--save-dir",
        default=str(DEFAULT_SAVE_DIR),
        help="Directory that will hold the Trankit customized pipeline.",
    )
    parser.add_argument(
        "--embedding",
        default="xlm-roberta-base",
        help="Trankit embedding name.",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=TASK_ORDER,
        default=list(DEFAULT_TASKS),
        help="Subset of supported tasks to run, in any order.",
    )
    parser.add_argument(
        "--max-epoch",
        type=int,
        default=100,
        help="Epoch count passed to each Trankit training stage.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional global batch size override.",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Disable GPU usage and force CPU mode.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse existing generated Old English training assets.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip Trankit verify_customized_pipeline after training.",
    )
    return parser.parse_args()


def ordered_tasks(tasks: list[str]) -> list[str]:
    requested = set(tasks)
    return [task for task in TASK_ORDER if task in requested]


def training_config(task: str, args: argparse.Namespace) -> dict[str, object]:
    train_conllu = BASE_DIR / "ang_oedt-ud-train.grouped.conllu"
    dev_conllu = BASE_DIR / "ang_oedt-ud-dev.grouped.conllu"
    if task == "lemmatize":
        train_conllu = BASE_DIR / "ang_oedt-ud-train.lemmafill.conllu"
        dev_conllu = BASE_DIR / "ang_oedt-ud-dev.lemmafill.conllu"

    config: dict[str, object] = {
        "category": CATEGORY,
        "task": task,
        "save_dir": str(Path(args.save_dir)),
        "embedding": args.embedding,
        "gpu": not args.cpu,
        "max_epoch": args.max_epoch,
        "train_conllu_fpath": str(train_conllu),
        "dev_conllu_fpath": str(dev_conllu),
    }
    if args.batch_size is not None:
        config["batch_size"] = args.batch_size
    if task == "tokenize":
        config["train_txt_fpath"] = str(BASE_DIR / "ang_oedt-ud-train.txt")
        config["dev_txt_fpath"] = str(BASE_DIR / "ang_oedt-ud-dev.txt")
    return config


def ensure_assets(skip_build: bool) -> dict[str, object]:
    if skip_build:
        stats_path = BASE_DIR / "ang_oedt-ud-trankit-stats.json"
        if stats_path.exists():
            return json.loads(stats_path.read_text(encoding="utf-8"))
    return build_all()


def main() -> None:
    args = parse_args()
    ensure_assets(skip_build=args.skip_build)

    import trankit

    for task in ordered_tasks(args.tasks):
        config = training_config(task, args)
        print(f"Starting Trankit task: {task}")
        print(json.dumps(config, ensure_ascii=False, indent=2))
        trainer = trankit.TPipeline(training_config=config)
        trainer.train()

    if not args.skip_verify:
        trankit.verify_customized_pipeline(
            category=CATEGORY,
            save_dir=str(Path(args.save_dir)),
            embedding_name=args.embedding,
        )


if __name__ == "__main__":
    main()
