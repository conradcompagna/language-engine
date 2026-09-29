"""Evaluate the selected Japanese Trankit NER checkpoint on retained BIO development data."""
import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import time


def identity(path):
    return {"file": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def bio_to_bioes(tags):
    converted = []
    for index, tag in enumerate(tags):
        if tag == "O":
            converted.append(tag)
            continue
        prefix, entity = tag.split("-", 1)
        following = tags[index + 1] if index + 1 < len(tags) else "O"
        continues = following == "I-" + entity
        converted.append((("B-" if continues else "S-") if prefix == "B"
                          else ("I-" if continues else "E-")) + entity)
    return converted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-store", required=True, type=Path,
                        help="Trankit cache root containing xlm-roberta-base and customized-ner.")
    parser.add_argument("--dev-bio", required=True, type=Path)
    parser.add_argument("--training-command", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", type=Path,
                        help="Optional scratch cache; use a short path on Windows.")
    args = parser.parse_args()
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache = args.cache_dir or args.output_dir / "cache"
    base = cache / "xlm-roberta-base"
    model_dir = base / "customized-ner"
    model_dir.mkdir(parents=True, exist_ok=True)
    for source in (args.model_store / "xlm-roberta-base").iterdir():
        if source.is_file() and not source.name.endswith(".lock"):
            shutil.copy2(source, base / source.name)
    for source in (args.model_store / "xlm-roberta-base/customized-ner").glob("customized-ner*"):
        if source.is_file():
            shutil.copy2(source, model_dir / source.name)

    words, golds, sentence, tags = [], [], [], []
    for line in args.dev_bio.read_text(encoding="utf-8-sig").splitlines() + [""]:
        if not line.strip():
            if sentence:
                words.append(sentence)
                golds.append(bio_to_bioes(tags))
                sentence, tags = [], []
        else:
            token, tag = line.rsplit("\t", 1)
            sentence.append(token)
            tags.append(tag)
    vocab = json.loads((model_dir / "customized-ner.ner-vocab.json").read_text(encoding="utf-8"))
    assert {tag for sent in golds for tag in sent} <= vocab.keys()

    import torch
    torch.set_num_threads(4)
    original_load = torch.load

    def legacy_load(*positional, **keywords):
        keywords.setdefault("weights_only", False)
        return original_load(*positional, **keywords)

    torch.load = legacy_load  # Trankit 1.1.1 uses legacy native checkpoint loading.
    import trankit
    from trankit.utils.scorers.ner_scorer import score_by_entity, decode_from_bioes
    started = time.monotonic()
    pipeline = trankit.Pipeline("customized-ner", cache_dir=str(cache), gpu=False)
    with torch.inference_mode():
        result = pipeline.ner(words)
    predicted = [[token["ner"] for token in sent["tokens"]] for sent in result["sentences"]]
    assert len(predicted) == len(golds)
    assert all(len(pred) == len(gold) for pred, gold in zip(predicted, golds))
    checkpoint = args.model_store / "xlm-roberta-base/customized-ner/customized-ner.ner.mdl"
    record = {
        "record_type": "Fresh selected-checkpoint development reevaluation",
        "evaluated_on": date.today().isoformat(), "checkpoint": identity(checkpoint),
        "selected_epoch": original_load(checkpoint, map_location="cpu", weights_only=False)["epoch"],
        "dataset": {**identity(args.dev_bio), "split": "development", "sentences": len(words),
                    "tokens": sum(map(len, words)), "gold_entities": sum(len(decode_from_bioes(s)) for s in golds)},
        "training_command": identity(args.training_command),
        "metrics": score_by_entity(predicted, golds, None),
        "metric_scope": "Entity micro precision/recall/F1, percent; pretokenized development sentences, BIO gold converted to BIOES.",
        "runtime": {"torch": torch.__version__, "trankit": trankit.__version__,
                    "device": "CPU", "threads": 4, "elapsed_seconds": time.monotonic() - started},
    }
    (args.output_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record["metrics"]), flush=True)


if __name__ == "__main__":
    main()
