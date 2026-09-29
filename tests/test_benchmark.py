"""Benchmark composition and comparison contracts without hardware/model imports."""
import json
import multiprocessing
import pickle
from pathlib import Path

import pytest

from research.evaluation.benchmarks.trankit_benchmark import comparison, worker
from research.evaluation.benchmarks.trankit_benchmark.routes import app

ROWS = json.loads((Path(__file__).parent / "fixtures/benchmark-comparison.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", ROWS)
def test_original_discrepancy_metrics(row):
    assert comparison._annotation_discrepancy_report(row["left"], row["right"]) == row["expected"]


def test_import_and_web_interface_do_not_start_workers():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"/static/benchmark.js" in response.data
    assert client.get("/static/benchmark.js").status_code == 200
    assert client.get("/static/benchmark.css").status_code == 200
    assert all(s["state"] == "not_started" for s in client.get("/api/status").json.values())
    assert client.post("/api/analyze", json={"text": "fixture"}).status_code == 503


def test_worker_target_is_picklable_and_modules_import_under_spawn():
    assert pickle.loads(pickle.dumps(worker._worker_main)) is worker._worker_main
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        actual = pool.apply(comparison._annotation_counts, (ROWS[1]["left"],))
    assert actual == comparison._annotation_counts(ROWS[1]["left"])
