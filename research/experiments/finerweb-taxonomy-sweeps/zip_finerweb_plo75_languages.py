from __future__ import annotations

import os
import zipfile
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE / "datasets" / "finerweb_plo75_by_language"
OUT = BASE / "datasets" / "finerweb_plo75_language_zips"


def zip_dir(src: Path, dest: Path) -> None:
    tmp = dest.with_suffix(".zip.tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src.parent).as_posix())
    os.replace(tmp, dest)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang_dir in sorted(path for path in ROOT.iterdir() if path.is_dir()):
        zip_dir(lang_dir, OUT / f"{lang_dir.name}.zip")
    for path in sorted(OUT.glob("*.zip")):
        print(f"{path.name}\t{path.stat().st_size}")


if __name__ == "__main__":
    main()
