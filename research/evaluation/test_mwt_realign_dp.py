"""Compatibility entrypoint; maintained MWT regressions live under tests/."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "tests/test_mwt_realign.py"), run_name="__main__")
