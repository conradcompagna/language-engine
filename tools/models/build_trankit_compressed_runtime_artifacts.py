"""
Build sandbox artifacts for the compressed Trankit runtime.

This creates:
  .trankit_compressed_runtime/xlmr_dynamic_adapters_dynamic_int8.onnx
  .trankit_compressed_runtime/adapter_packs/<language>__<task>.npz
  .trankit_compressed_runtime/manifest.json

It does not edit production runtime files or installed Trankit files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from trankit_compressed_runtime import (
    ARTIFACT_DIR,
    MANIFEST_PATH,
    build_artifacts,
    force_utf8,
    prepend_deps,
    set_sandbox_env,
)


def _force_trankit_pipeline_cpu() -> None:
    import trankit  # type: ignore

    real_init = trankit.Pipeline.__init__
    if getattr(real_init, "_sandbox_forced_cpu", False):
        return

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["gpu"] = False
        return real_init(self, *args, **kwargs)

    setattr(patched_init, "_sandbox_forced_cpu", True)
    trankit.Pipeline.__init__ = patched_init


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence-length", type=int, default=128)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    set_sandbox_env()
    prepend_deps()
    if MANIFEST_PATH.exists() and not args.force:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        print(
            json.dumps(
                {
                    "ok": True,
                    "reused_existing_manifest": True,
                    "manifest_path": str(MANIFEST_PATH),
                    "artifact_dir": str(ARTIFACT_DIR),
                    "manifest": {
                        "profile": manifest.get("profile"),
                        "task_count": manifest.get("task_count"),
                        "language_count": len(manifest.get("languages") or []),
                        "onnx": manifest.get("onnx"),
                    },
                },
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        )
        return 0

    import torch  # type: ignore

    _force_trankit_pipeline_cpu()
    import language_registry as lr

    started = time.perf_counter()
    print("loading full Trankit pipeline through language_registry.init_trankit()", flush=True)
    lr.init_trankit()
    pipeline = getattr(lr, "_trankit_pipeline", None)
    if pipeline is None:
        raise RuntimeError("language_registry did not create _trankit_pipeline")
    pipeline._embedding_layers.eval()
    pipeline._embedding_layers.xlmr.eval()
    if hasattr(pipeline._embedding_layers.xlmr, "config"):
        pipeline._embedding_layers.xlmr.config.output_hidden_states = False

    manifest = build_artifacts(pipeline, torch, sequence_length=int(args.sequence_length))
    manifest["builder_elapsed_seconds"] = time.perf_counter() - started
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "ok": True,
                "manifest_path": str(MANIFEST_PATH),
                "artifact_dir": str(ARTIFACT_DIR),
                "task_count": manifest.get("task_count"),
                "language_count": len(manifest.get("languages") or []),
                "onnx": manifest.get("onnx"),
                "timing": manifest.get("timing"),
                "builder_elapsed_seconds": manifest.get("builder_elapsed_seconds"),
            },
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
