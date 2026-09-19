import argparse
import builtins
import json
import os
import shutil
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path


RUN_DIR = Path(__file__).resolve().parent
PREP_DIR = Path("training") / "trankit_finerweb_prep"
DEFAULT_DATASET = PREP_DIR / "datasets" / "grc_pausanias_ethnic_civic_misc"
DEFAULT_WORK_CACHE = Path("training") / "t"
DEFAULT_FINISHED_MODELS = PREP_DIR / "finished_models"
DEFAULT_SEED_CACHE = Path("training") / "trankit_save_ja_ner_v2"
_OPEN = builtins.open


def force_utf8_open(
    file,
    mode="r",
    buffering=-1,
    encoding=None,
    errors=None,
    newline=None,
    closefd=True,
    opener=None,
):
    if "b" not in mode and encoding is None:
        encoding = "utf-8"
    return _OPEN(file, mode, buffering, encoding, errors, newline, closefd, opener)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a Trankit NER model from BIO files.")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-id", default="grc_pausanias_ethnic_civic_misc")
    parser.add_argument("--train-file", default="train.bio")
    parser.add_argument("--dev-file", default="dev.bio")
    parser.add_argument("--work-cache", type=Path, default=DEFAULT_WORK_CACHE)
    parser.add_argument("--finished-models", type=Path, default=DEFAULT_FINISHED_MODELS)
    parser.add_argument("--seed-cache", type=Path, default=DEFAULT_SEED_CACHE)
    parser.add_argument("--category", default="customized-ner")
    parser.add_argument("--embedding", default="xlm-roberta-base")
    parser.add_argument("--max-epoch", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--snapshot-only", action="store_true")
    return parser.parse_args()


def seed_xlmr_cache(args: argparse.Namespace) -> None:
    source_root = args.seed_cache / args.embedding
    source_category = source_root / args.category
    target_category = args.work_cache / args.embedding / args.category
    target_model_cache = target_category / args.embedding

    if not source_root.exists():
        print(f"Seed cache not found, skipping: {source_root}")
        return

    target_category.mkdir(parents=True, exist_ok=True)
    target_model_cache.mkdir(parents=True, exist_ok=True)

    if source_category.exists():
        for path in source_category.iterdir():
            if path.is_file():
                if path.name.endswith(".ner.mdl") or path.name.endswith(".ner-vocab.json"):
                    continue
                target = target_category / path.name
                if not target.exists():
                    shutil.copy2(path, target)

    for path in source_root.iterdir():
        if path.is_file():
            target = target_model_cache / path.name
            if not target.exists():
                shutil.copy2(path, target)


def artifact_signature(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def copy_active_artifacts(args: argparse.Namespace, config: dict | None = None) -> Path:
    model_dir = args.work_cache / args.embedding / args.category
    out_dir = args.finished_models / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if config is not None:
        (out_dir / "training_config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    for name in [
        f"{args.category}.ner.mdl",
        f"{args.category}.ner-vocab.json",
    ]:
        src = model_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    log_dir = model_dir / "logs"
    if log_dir.exists():
        out_log_dir = out_dir / "logs"
        out_log_dir.mkdir(exist_ok=True)
        for path in log_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, out_log_dir / path.name)

    return out_dir


def reserve_run_id(args: argparse.Namespace) -> Path:
    base_run_id = args.run_id
    out_dir = args.finished_models / base_run_id
    if not out_dir.exists():
        out_dir.mkdir(parents=True)
        return out_dir

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i in range(1000):
        suffix = timestamp if i == 0 else f"{timestamp}_{i:03d}"
        candidate_run_id = f"{base_run_id}_{suffix}"
        out_dir = args.finished_models / candidate_run_id
        if not out_dir.exists():
            out_dir.mkdir(parents=True)
            print(f"Run id already exists; saving this run as: {candidate_run_id}")
            args.run_id = candidate_run_id
            return out_dir
    raise RuntimeError(f"Could not reserve a unique finished model directory for {base_run_id}")


def write_run_config(args: argparse.Namespace, config: dict) -> Path:
    out_dir = args.finished_models / args.run_id
    (out_dir / "training_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_dir


def watch_active_model(
    args: argparse.Namespace, initial_signature: tuple[int, int] | None, stop: threading.Event
) -> None:
    model_path = args.work_cache / args.embedding / args.category / f"{args.category}.ner.mdl"
    last_signature = initial_signature
    while not stop.wait(10):
        current_signature = artifact_signature(model_path)
        if current_signature is not None and current_signature != last_signature:
            copy_active_artifacts(args)
            last_signature = current_signature


def _decode_bioes_entities(tag_sequences: list[list[str]]) -> list[tuple[int, int, int, str]]:
    entities: list[tuple[int, int, int, str]] = []
    for sent_id, tags in enumerate(tag_sequences):
        cur_type = None
        ent_idxs: list[int] = []

        def flush() -> None:
            if ent_idxs:
                entities.append((sent_id, ent_idxs[0], ent_idxs[-1], str(cur_type or "")))

        for idx, raw_tag in enumerate(tags):
            tag = raw_tag or "O"
            if tag == "O":
                flush()
                ent_idxs = []
                cur_type = None
            elif tag.startswith("B-"):
                flush()
                ent_idxs = [idx]
                cur_type = tag[2:]
            elif tag.startswith("I-"):
                ent_idxs.append(idx)
                cur_type = tag[2:]
            elif tag.startswith("E-"):
                ent_idxs.append(idx)
                cur_type = tag[2:]
                flush()
                ent_idxs = []
                cur_type = None
            elif tag.startswith("S-"):
                flush()
                ent_idxs = [idx]
                cur_type = tag[2:]
                flush()
                ent_idxs = []
                cur_type = None
            else:
                flush()
                ent_idxs = []
                cur_type = None
        flush()
    return entities


def _per_label_ner_metrics(
    predictions: list[list[str]],
    golds: list[list[str]],
) -> list[dict[str, float | int | str]]:
    pred_entities = _decode_bioes_entities(predictions)
    gold_entities = _decode_bioes_entities(golds)
    gold_set = set(gold_entities)

    pred_by_label = Counter(ent[3] for ent in pred_entities)
    gold_by_label = Counter(ent[3] for ent in gold_entities)
    correct_by_label = Counter(ent[3] for ent in pred_entities if ent in gold_set)

    rows: list[dict[str, float | int | str]] = []
    for label in sorted(set(pred_by_label) | set(gold_by_label)):
        pred = int(pred_by_label.get(label, 0))
        gold = int(gold_by_label.get(label, 0))
        correct = int(correct_by_label.get(label, 0))
        precision = (correct / pred * 100.0) if pred else 0.0
        recall = (correct / gold * 100.0) if gold else 0.0
        f1 = (2.0 * precision * recall / (precision + recall)) if precision + recall else 0.0
        rows.append(
            {
                "label": label,
                "gold": gold,
                "pred": pred,
                "correct": correct,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    rows.sort(key=lambda row: (-int(row["gold"]), str(row["label"])))
    return rows


def patch_trankit_ner_eval_logging() -> None:
    from torch.utils.data import DataLoader
    from tqdm import tqdm
    from trankit.tpipeline import TPipeline
    from trankit.utils.scorers.ner_scorer import score_by_entity

    if getattr(TPipeline, "_language_engine_per_label_ner_eval", False):
        return

    def _eval_ner(self, data_set, batch_num, name, epoch):
        self._ner_model.eval()
        progress = tqdm(total=batch_num, ncols=75, desc="{} {}".format(name, epoch))
        predictions = []
        golds = []
        for batch in DataLoader(
            data_set,
            batch_size=self._config.batch_size,
            shuffle=False,
            collate_fn=data_set.collate_fn,
        ):
            progress.update(1)
            word_reprs, cls_reprs = self._embedding_layers.get_tagger_inputs(batch)
            pred_entity_labels = self._ner_model.predict(batch, word_reprs)
            predictions += pred_entity_labels
            batch_entity_labels = batch.entity_label_idxs.data.cpu().numpy().tolist()
            golds += [
                [self.tag_itos[label_id] for label_id in seq[: batch.word_num[i]]]
                for i, seq in enumerate(batch_entity_labels)
            ]
        progress.close()

        score = score_by_entity(predictions, golds, self.logger)
        rows = _per_label_ner_metrics(predictions, golds)
        if rows:
            self._printlog("NER per-label {} metrics:".format(name))
            self._printlog("label\tgold\tpred\tcorrect\tP\tR\tF1")
            for row in rows:
                self._printlog(
                    "{label}\t{gold}\t{pred}\t{correct}\t{precision:.2f}\t{recall:.2f}\t{f1:.2f}".format(
                        **row
                    )
                )
        return score

    TPipeline._eval_ner = _eval_ner
    TPipeline._language_engine_per_label_ner_eval = True


def main() -> None:
    args = parse_args()
    args.finished_models.mkdir(parents=True, exist_ok=True)
    reserve_run_id(args)
    args.work_cache.mkdir(parents=True, exist_ok=True)

    if args.snapshot_only:
        out_dir = copy_active_artifacts(args)
        print(f"Active model snapshot copied to: {out_dir}")
        return

    train_bio = args.dataset_dir / args.train_file
    dev_bio = args.dataset_dir / args.dev_file
    if not train_bio.exists():
        raise FileNotFoundError(train_bio)
    if not dev_bio.exists():
        raise FileNotFoundError(dev_bio)

    seed_xlmr_cache(args)

    config = {
        "category": args.category,
        "task": "ner",
        "save_dir": str(args.work_cache),
        "train_bio_fpath": str(train_bio),
        "dev_bio_fpath": str(dev_bio),
        "embedding": args.embedding,
        "max_epoch": args.max_epoch,
        "batch_size": args.batch_size,
        "gpu": True,
    }

    print(json.dumps(config, ensure_ascii=False, indent=2))

    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    builtins.open = force_utf8_open

    import trankit

    patch_trankit_ner_eval_logging()

    if args.max_epoch <= 0:
        trainer = trankit.TPipeline(training_config=config)
        trainer.train()
        print("No finished model copied because --max-epoch is 0.")
        return

    model_path = args.work_cache / args.embedding / args.category / f"{args.category}.ner.mdl"
    initial_signature = artifact_signature(model_path)
    write_run_config(args, config)

    stop_watcher = threading.Event()
    watcher = threading.Thread(
        target=watch_active_model,
        args=(args, initial_signature, stop_watcher),
        daemon=True,
    )
    watcher.start()

    interrupted = False
    try:
        trainer = trankit.TPipeline(training_config=config)
        trainer.train()
    except KeyboardInterrupt:
        interrupted = True
        print("Training interrupted; snapshotting latest saved active model.")
    finally:
        stop_watcher.set()
        watcher.join(timeout=15)
        current_signature = artifact_signature(model_path)
        if current_signature is not None and current_signature != initial_signature:
            out_dir = copy_active_artifacts(args, config=config)
            print(f"Latest saved model copied to: {out_dir}")
        else:
            print("No new active NER model was saved during this run.")

    if interrupted:
        return


if __name__ == "__main__":
    main()
