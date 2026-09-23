"""Trankit benchmark: worker handle."""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from . import settings, worker


@dataclass
class WorkerHandle:
    device: str
    use_gpu: bool
    ctx: Any
    optimized_cpu: bool = False
    optimized_gpu: bool = False
    onnx_cpu: bool = False
    cpu_opt_profile: str = "runtime_patches"
    cpu_opt_thread_count: Optional[int] = None
    cpu_opt_tok_batch_size: Optional[int] = None
    cpu_opt_tag_batch_size: Optional[int] = None
    cpu_opt_skip_startup_tuning: bool = False
    command_queue: mp.Queue = field(init=False)
    result_queue: mp.Queue = field(init=False)
    process: mp.Process = field(init=False)
    status: Dict[str, Any] = field(default_factory=lambda: {"state": "not_started"})
    pending: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self.command_queue = self.ctx.Queue()
        self.result_queue = self.ctx.Queue()
        self.process = self.ctx.Process(
            target=worker._worker_main,
            args=(
                self.device,
                self.use_gpu,
                self.command_queue,
                self.result_queue,
                self.optimized_cpu,
                self.optimized_gpu,
                self.onnx_cpu,
                self.cpu_opt_profile,
                self.cpu_opt_thread_count,
                self.cpu_opt_tok_batch_size,
                self.cpu_opt_tag_batch_size,
                self.cpu_opt_skip_startup_tuning,
            ),
            daemon=False,
        )
        self.process.start()
        self.status = {
            "state": "starting",
            "pid": self.process.pid,
            "device": self.device,
        }

    def drain(self) -> None:
        while True:
            try:
                msg = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "status":
                self.status = msg
            elif msg.get("type") == "result":
                self.pending[str(msg.get("request_id") or "")] = msg
        try:
            state = str(self.status.get("state") or "")
            if (
                state in {"starting", "loading"}
                and hasattr(self, "process")
                and not self.process.is_alive()
            ):
                self.status = {
                    "type": "status",
                    "device": self.device,
                    "state": "error",
                    "pid": getattr(self.process, "pid", None),
                    "time": time.time(),
                    "error": f"worker process exited before ready; exitcode={self.process.exitcode}",
                }
        except Exception:
            pass

    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            self.drain()
            request_id = str(payload["request_id"])
            self.command_queue.put(dict(payload))
            deadline = time.time() + settings.WORKER_RESPONSE_TIMEOUT_SECONDS
            while time.time() < deadline:
                self.drain()
                if request_id in self.pending:
                    return self.pending.pop(request_id)
                if not self.process.is_alive():
                    return {
                        "type": "result",
                        "device": self.device,
                        "request_id": request_id,
                        "ok": False,
                        "error": "worker process exited",
                        "status": self.status,
                    }
                time.sleep(0.05)
            return {
                "type": "result",
                "device": self.device,
                "request_id": request_id,
                "ok": False,
                "error": "worker response timed out",
                "status": self.status,
            }

    def shutdown(self) -> None:
        try:
            self.command_queue.put({"type": "shutdown"})
        except Exception:
            pass
        try:
            self.process.join(timeout=5)
        except Exception:
            pass
        if self.process.is_alive():
            self.process.terminate()
