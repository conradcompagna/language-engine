"""Synthetic corpus checks; these are not trained-model accuracy measurements."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from research.pipeline.models.training_evidence import inspect_split
from research.pipeline.datasets.convert_train_jsonl_to_trankit import build_datasets

ROOT = Path(__file__).resolve().parents[1]


def bio_pair(directory):
    (directory / "train.bio").write_text("Rāma B-PER\ngoes O\n\n", encoding="utf-8")
    (directory / "dev.bio").write_text("Sītā B-PER\nreads O\n\n", encoding="utf-8")
    return directory / "train.bio", directory / "dev.bio"


def test_ner_preflight_without_models_or_output_side_effects(tmp_path):
    train, dev = bio_pair(tmp_path)
    expected = inspect_split(train, dev)
    result = subprocess.run([sys.executable, str(ROOT / "research/pipeline/models/train_ner.py"),
                             "--dataset-dir", str(tmp_path), "--validate-only",
                             "--finished-models", str(tmp_path / "must-not-exist")],
                            capture_output=True, text=True, encoding="utf-8", check=True, cwd=tmp_path)
    assert json.loads(result.stdout) == expected
    assert expected["train"]["tokens"] == 2
    assert len(expected["train"]["sha256"]) == 64
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.parametrize("invalid", ["Rāma B-PER\ngoes O\n", "word INVALID\n", ""])
def test_ner_preflight_rejects_leakage_bad_labels_and_empty_data(tmp_path, invalid):
    train, dev = bio_pair(tmp_path)
    dev.write_text(invalid, encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_split(train, dev)


def test_sanskrit_conversion_stable_split_and_aligned_conllu(tmp_path):
    records = []
    for sent_id, name in [("10", "rAma"), ("11", "sItA")]:
        records.append({"id": sent_id, "sentence": name, "lemmas": [[name]], "morph_tags": [["nom"]],
                        "candidates": [{"id": sent_id, "word": name, "lemma": name, "morph": "nom.sg.",
                                        "cng": "nom", "position": 0, "length": len(name), "chunk_no": 1}]})
    source = tmp_path / "synthetic.jsonl"
    source.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")
    out = tmp_path / "new-output"
    result = build_datasets(source, out, "fixture", 20, 10, 0, None)
    assert (result["train_records"], result["dev_records"], result["skipped_records"]) == (1, 1, 0)
    first = (out / "fixture-dev.conllu").read_bytes()
    assert b"1\trAma\trAma\tNOUN\t_\t_\t0\troot\t_\t_" in first
    assert b"# sent_id = 11" in (out / "fixture-train.conllu").read_bytes()
    build_datasets(source, out, "fixture", 20, 10, 0, None)
    assert (out / "fixture-dev.conllu").read_bytes() == first


def test_onnx_exporter_uses_benchmark_paths_from_another_cwd(tmp_path):
    script = ROOT / "research/pipeline/models/build_trankit_xlmr_onnx_cpu.py"
    code = ("import runpy; m=runpy.run_path(" + repr(str(script)) + "); "
            "from research.evaluation.benchmarks.trankit_benchmark import settings; "
            "assert str(m['ONNX_CACHE_DIR']) == settings.ONNX_CACHE_DIR; "
            "assert str(m['ONNX_CACHE_DIR']).endswith('shared-export')")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path,
                   env={**os.environ, "TRANKIT_ONNX_CACHE_DIR": str(tmp_path / "shared-export")})
