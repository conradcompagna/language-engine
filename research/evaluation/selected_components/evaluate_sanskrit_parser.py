"""Re-evaluate the selected Sanskrit tagger/parser on retained gold-segmented dev.

Tested with Python 3.10.20, pristine Trankit 1.1.1, and torch 2.6.0+cpu.
The default SHA-256 values identify the exact checkpoint, vocabulary, and dev
file used for the 2026-09-24 result. The corpus and checkpoint are separate inputs.
"""
import argparse
from datetime import date
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import sys
import time


SELECTED = {
    "model": "93532d76a28c787467898d5cbf43d1a555f492cbd865084160b3acb9e8795b78",
    "vocab": "4902589a4e4b2cd2f592b1cf5e9275d3c044a49fa0783d5b23eb73d595c547de",
    "dev": "cacf6991faf32b50f5de541a2f58c3b1030e6976c5b161e9ca1427043b8eb398",
}
ALIAS = "sanskrit-vedic"
TREEBANK = "UD_Vedic_Sanskrit-Vedic"


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
        return value.hexdigest()


def hub_url(model_id, filename, **_):
    return f"https://huggingface.co/{model_id}/resolve/main/{filename}"


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in SELECTED:
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--expected-{name}-sha256", default=SELECTED[name])
    parser.add_argument("--cache", type=Path, required=True,
                        help="XLM-R download cache; prefer a short path on Windows")
    parser.add_argument("--output", type=Path, required=True, help="Metric JSON path")
    parser.add_argument("--expected-epoch", type=int, default=74)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--verify-only", action="store_true",
                        help="Check input hashes and stored epoch without inference")
    return parser.parse_args()


def main():
    args = arguments()
    started = time.monotonic()
    artifacts = {}
    for name in SELECTED:
        path = getattr(args, name).resolve(strict=True)
        actual = digest(path)
        expected = getattr(args, f"expected_{name}_sha256").lower()
        if actual != expected:
            raise ValueError(f"{name} SHA-256 mismatch: {actual} != {expected}")
        artifacts[name] = {"file": path.name, "bytes": path.stat().st_size,
                           "sha256": actual}
    import torch
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=True)
    epoch = checkpoint["epoch"]
    if epoch != args.expected_epoch:
        raise ValueError(f"Stored epoch {epoch} != expected {args.expected_epoch}")
    del checkpoint
    if args.verify_only:
        print(json.dumps({"verified": artifacts, "epoch": epoch}, indent=2))
        return

    from trankit import TPipeline
    from trankit.adapter_transformers import (
        XLMRobertaTokenizer, configuration_utils, modeling_utils,
    )
    from trankit.config import Config
    from trankit.iterators.tagger_iterators import TaggerDataset
    from trankit.models.base_models import Multilingual_Embedding
    from trankit.models.classifiers import PosDepClassifier
    from trankit.utils.tbinfo import lang2treebank, treebank2lang

    torch.set_num_threads(args.threads)
    torch.manual_seed(1234)
    configuration_utils.hf_bucket_url = modeling_utils.hf_bucket_url = hub_url
    XLMRobertaTokenizer.pretrained_vocab_files_map["vocab_file"]["xlm-roberta-base"] = (
        hub_url("FacebookAI/xlm-roberta-base", "sentencepiece.bpe.model")
    )
    lang2treebank[ALIAS], treebank2lang[TREEBANK] = TREEBANK, ALIAS
    cache = args.cache.resolve()
    output = args.output.resolve()
    run = output.parent / f"{output.stem}.run"
    (run / "preds").mkdir(parents=True, exist_ok=True)
    model_dir = cache / "xlm-roberta-base" / ALIAS
    model_dir.mkdir(parents=True, exist_ok=True)
    for original, target in [
        (args.model, model_dir / f"{ALIAS}.tagger.mdl"),
        (args.vocab, model_dir / f"{ALIAS}.vocabs.json"),
        (args.vocab, run / f"{ALIAS}.vocabs.json"),
    ]:
        if original.resolve() != target.resolve():
            shutil.copy2(original, target)
        if digest(original) != digest(target):
            raise ValueError("Input copy failed SHA-256 verification")
    vocabs = json.loads(args.vocab.read_text(encoding="utf-8"))
    config = Config()
    config.training = False
    config.device = torch.device("cpu")
    config._cache_dir, config._save_dir = str(cache), str(run)
    config.lang = config.active_lang = ALIAS
    config.treebank_name = TREEBANK
    config.max_input_length = 512
    config.batch_size = args.batch_size
    config.vocabs = {TREEBANK: vocabs}
    config.itos = {key: {v: k for k, v in values.items()}
                   for key, values in vocabs.items()}
    config.wordpiece_splitter = XLMRobertaTokenizer.from_pretrained(
        "xlm-roberta-base", cache_dir=str(cache / "xlm-roberta-base")
    )
    data = TaggerDataset(config, str(args.dev), str(args.dev), evaluate=True)
    sentence_count = len(data.conllu_doc)
    if len(data) != sentence_count:
        raise ValueError("Length-filtered sentences require a separate evaluation scope")
    data.numberize()
    embedding = Multilingual_Embedding(config, model_name="tagger").cpu().eval()
    classifier = PosDepClassifier(config, TREEBANK).cpu().eval()
    weights = classifier.pretrained_tagger_weights
    state = embedding.state_dict()
    unknown = set(weights) - set(state) - set(classifier.state_dict())
    if unknown:
        raise ValueError(f"Unrecognized checkpoint keys: {sorted(unknown)}")
    state.update({key: value for key, value in weights.items() if key in state})
    embedding.load_state_dict(state)
    trainer = TPipeline.__new__(TPipeline)
    trainer._config, trainer._embedding_layers, trainer._tagger = config, embedding, classifier
    with torch.inference_mode():
        scores, prediction = trainer._eval_posdep(
            data, math.ceil(len(data) / config.batch_size), "retained-dev", epoch
        )
    metrics = {
        name: {key: getattr(scores[name], key) for key in
               ["precision", "recall", "f1", "aligned_accuracy"]}
        for name in ["UPOS", "XPOS", "UFeats", "AllTags", "UAS", "LAS", "CLAS", "MLAS"]
    }
    record = {
        "evaluated_on": date.today().isoformat(),
        "record_type": "Component-stage evaluation on retained development corpus",
        "checkpoint_epoch": epoch, "input_artifacts": artifacts,
        "input_stage": "Gold sentences and expanded words; predicted POS, features, heads and relations; no tokenizer, MWT or lemmatizer inference.",
        "sentences": sentence_count, "evaluated_sentences": len(data),
        "words": sum(item.word_num for item in data), "max_wordpieces": 512,
        "batch_size": args.batch_size, "cpu_threads": args.threads, "seed": 1234,
        "metrics_scale": "fractions 0-1", "metrics": metrics,
        "method": "Native Trankit TaggerDataset / TPipeline._eval_posdep and bundled CoNLL 2018 UD scorer.",
        "prediction_sha256": digest(Path(prediction)),
        "evaluator_sha256": digest(Path(__file__)), "python": sys.version.split()[0],
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ["trankit", "torch", "numpy", "sentencepiece", "tokenizers"]},
        "elapsed_seconds": time.monotonic() - started,
        "note": "Development re-evaluation, not an independent test set or recovered historical console score. XPOS has only the '_' label and is not a substantive tagging benchmark.",
    }
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
