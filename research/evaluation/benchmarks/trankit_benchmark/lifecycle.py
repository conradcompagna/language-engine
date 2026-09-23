"""Trankit benchmark: lifecycle."""

from __future__ import annotations

import json
import multiprocessing as mp
import time
from typing import Any, Dict, Optional

from . import settings, state, worker_handle


def _start_worker_if_missing(
    name: str,
    device: str,
    use_gpu: bool,
    ctx: Any,
    *,
    optimized_cpu: bool = False,
    optimized_gpu: bool = False,
    onnx_cpu: bool = False,
    cpu_opt_profile: str = "runtime_patches",
    cpu_opt_thread_count: Optional[int] = None,
    cpu_opt_tok_batch_size: Optional[int] = None,
    cpu_opt_tag_batch_size: Optional[int] = None,
    cpu_opt_skip_startup_tuning: bool = False,
) -> None:
    existing = state.workers.get(name)
    if existing is not None:
        try:
            existing.drain()
            if existing.process.is_alive():
                return
        except Exception:
            pass
    state.workers[name] = worker_handle.WorkerHandle(
        device,
        use_gpu,
        ctx,
        optimized_cpu=optimized_cpu,
        optimized_gpu=optimized_gpu,
        onnx_cpu=onnx_cpu,
        cpu_opt_profile=cpu_opt_profile,
        cpu_opt_thread_count=cpu_opt_thread_count,
        cpu_opt_tok_batch_size=cpu_opt_tok_batch_size,
        cpu_opt_tag_batch_size=cpu_opt_tag_batch_size,
        cpu_opt_skip_startup_tuning=cpu_opt_skip_startup_tuning,
    )
    state.workers[name].start()


def _startup_status_line(name: str, status: Dict[str, Any]) -> str:
    state = str(status.get("state") or "unknown")
    pid = status.get("pid")
    error = status.get("error")
    pieces = [f"{name}={state}"]
    if pid:
        pieces.append(f"pid={pid}")
    if error:
        pieces.append(f"error={error}")
    return " ".join(pieces)


def wait_for_required_workers(required_names: list[str]) -> None:
    deadline = time.time() + settings.STARTUP_WORKER_TIMEOUT_SECONDS
    last_line = ""
    print(
        "Waiting for benchmark workers to fully load before serving: "
        + ", ".join(required_names),
        flush=True,
    )
    while time.time() < deadline:
        for worker in state.workers.values():
            worker.drain()

        statuses = {
            name: state.workers[name].status
            for name in required_names
            if name in state.workers
        }
        line = " | ".join(
            _startup_status_line(name, statuses.get(name, {}))
            for name in required_names
        )
        if line != last_line:
            print(line, flush=True)
            last_line = line

        for name, status in statuses.items():
            if status.get("state") == "error":
                raise RuntimeError(
                    f"Benchmark worker '{name}' failed during startup before lookup. "
                    f"Status: {json.dumps(status, ensure_ascii=False, default=str)}"
                )

        if all(status.get("state") == "ready" for status in statuses.values()) and len(
            statuses
        ) == len(required_names):
            print("Benchmark workers are ready; starting Flask server.", flush=True)
            return

        time.sleep(1.0)

    timed_out = {
        name: state.workers[name].status
        for name in required_names
        if name in state.workers
    }
    raise RuntimeError(
        "Benchmark workers did not finish startup before timeout. "
        f"Status: {json.dumps(timed_out, ensure_ascii=False, default=str)}"
    )


def start_workers() -> None:

    ctx = mp.get_context("spawn")
    _start_worker_if_missing("gpu", "gpu", True, ctx)
    _start_worker_if_missing(
        "onnx_cpu",
        "onnx_cpu",
        False,
        ctx,
        onnx_cpu=True,
    )
    wait_for_required_workers(["onnx_cpu", "gpu"])
    state.workers_started = True


def ensure_workers_started() -> None:
    if state.workers_started:
        return
    raise RuntimeError(
        "workers are not started; start_workers() must run before serving requests"
    )


def ensure_cpu_opt_gpu_started(command: Dict[str, Any]) -> Dict[str, Any]:
    if state.cpu_opt_selection is None:
        raise RuntimeError(
            "optimized CPU worker is not started; start_workers() must run before serving requests"
        )
    return state.cpu_opt_selection


def stop_workers() -> None:
    for worker in state.workers.values():
        worker.shutdown()
