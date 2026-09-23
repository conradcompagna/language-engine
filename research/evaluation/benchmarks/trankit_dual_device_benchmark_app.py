"""Opt-in benchmark entrypoint; see trankit_benchmark/README.md for setup."""
from pathlib import Path
import sys

# Support direct execution from any working directory and multiprocessing spawn.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.evaluation.benchmarks.trankit_benchmark.routes import app
from research.evaluation.benchmarks.trankit_benchmark.lifecycle import start_workers, stop_workers
from research.evaluation.benchmarks.trankit_benchmark.settings import HOST, PORT


if __name__ == "__main__":
    try:
        start_workers()
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)
    finally:
        stop_workers()
