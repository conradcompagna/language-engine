"""Evaluate a retained Trankit MWT checkpoint on a named development input."""
import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import time


def identity(path):
    return {"file": path.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def collapse_reference(source, destination):
    """Retain gold surface boundaries, replace each MWT range with MWT=Yes."""
    output, block = [], []

    def flush(lines):
        next_id, skip_until = 1, None
        for line in lines:
            if line.startswith("#"):
                output.append(line)
                continue
            cols = line.split("\t")
            if len(cols) != 10:
                output.append(line)
                continue
            token_id = cols[0]
            if "." in token_id:
                continue
            if skip_until is not None:
                if "-" in token_id:
                    continue
                current = int(token_id)
                if current <= skip_until:
                    if current == skip_until:
                        skip_until = None
                    continue
            if "-" in token_id:
                skip_until = int(token_id.split("-", 1)[1])
                misc = "MWT=Yes" if cols[9] in {"", "_"} else cols[9] + "|MWT=Yes"
            else:
                misc = cols[9] if cols[9] not in {"", "_"} else "_"
            output.append("\t".join([
                str(next_id), cols[1], "_", "_", "_", "_",
                "0" if next_id == 1 else str(next_id - 1),
                "root" if next_id == 1 else "dep", "_", misc,
            ]))
            next_id += 1
        output.append("")

    for line in source.read_text(encoding="utf-8").splitlines():
        if line:
            block.append(line)
        else:
            if block:
                flush(block)
            block = []
    if block:
        flush(block)
    destination.write_text("\n".join(output) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--language-code", required=True)
    parser.add_argument("--input-kind", required=True, choices=[
        "retained-tokenizer", "retained-gold-boundaries", "collapse-gold-reference",
    ])
    args = parser.parse_args()

    import torch
    import trankit
    from trankit.models.mwt_model import Trainer
    from trankit.iterators.mwt_iterators import MWTDataLoader
    from trankit.utils.mwt_lemma_utils.mwt_utils import get_mwt_expansions, set_mwt_expansions
    from trankit.utils.conll import CoNLL
    from trankit.utils.base_utils import get_ud_score

    torch.set_num_threads(4)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    input_path = args.input
    if args.input_kind == "collapse-gold-reference":
        input_path = args.output_dir / "reference-boundaries.conllu"
        collapse_reference(args.input, input_path)

    def score(path):
        values = get_ud_score(str(path), str(args.reference))
        return {key: {"precision": value.precision * 100, "recall": value.recall * 100,
                      "f1": value.f1 * 100}
                for key, value in values.items() if key in {"Tokens", "Words", "Sentences"}}

    input_scores = score(input_path)  # Verify reference/input character alignment before inference.
    model = Trainer(model_file=str(args.checkpoint), use_cuda=False)
    model_args = dict(model.args)
    model_args["batch_size"] = 128
    document = CoNLL.conll2dict(str(input_path))
    batches = MWTDataLoader(document, 128, model_args, vocab=model.vocab,
                           evaluation=True, training_mode=True)
    predictions = []
    started = time.monotonic()
    with torch.inference_mode():
        for index, batch in enumerate(batches):
            predictions.extend(model.predict(batch))
            if index % 100 == 0:
                print(f"{index}/{len(batches)} batches", flush=True)
    candidates = get_mwt_expansions(batches.doc, evaluation=True, training_mode=True)
    record = {
        "record_type": "Fresh native-checkpoint development reevaluation",
        "evaluated_on": date.today().isoformat(), "language_code": args.language_code,
        "checkpoint": identity(args.checkpoint), "input": identity(input_path),
        "reference": identity(args.reference), "input_kind": args.input_kind,
        "sentence_count": len(document), "mwt_candidate_count": len(candidates),
        "metric_scope": "UD Words precision/recall/F1, percent; development material, not an independent test.",
        "input_scores": input_scores, "scores": {},
        "runtime": {"torch": torch.__version__, "trankit": trankit.__version__,
                    "device": "CPU", "threads": 4, "batch_size": 128},
    }
    for name, values in [("seq2seq_only", predictions),
                         ("dictionary_ensemble", model.ensemble(candidates, predictions))]:
        path = args.output_dir / f"{name}.conllu"
        expanded = set_mwt_expansions(copy.deepcopy(batches.doc), values, training_mode=True)
        CoNLL.dict2conll(expanded, str(path))
        record["scores"][name] = {"metrics": score(path), "predictions": identity(path)}
    record["runtime"]["elapsed_seconds"] = time.monotonic() - started
    (args.output_dir / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record["scores"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
