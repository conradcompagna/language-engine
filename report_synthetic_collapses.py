#!/usr/bin/env python3
"""Dump synthetic-collapse decisions per kaikki DB into reports/synthetic_collapses/.

For each DB, writes a CSV row per donor entry: donor headword, gloss used,
target headword, target entry id, synthetic tags. Then zips the folder.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sqlite_prune_policy import compute_synthetic_collapses, is_kaikki_db  # noqa: E402

DICT_DIR = ROOT / "dict_sqlite"
REPORT_DIR = ROOT / "reports" / "synthetic_collapses"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_rows: list[tuple[str, int]] = []
    written_files: list[Path] = []

    for db_path in sorted(DICT_DIR.glob("*.sqlite")):
        db_name = db_path.stem
        if not is_kaikki_db(db_name):
            continue
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            try:
                conn.execute("ATTACH DATABASE ? AS d", (str(db_path),))
                alias = "d"
            except sqlite3.OperationalError:
                alias = "main"
            try:
                info = compute_synthetic_collapses(conn, alias, db_name)
            except Exception as exc:
                print(f"[skip] {db_name}: {exc}", file=sys.stderr)
                continue
        finally:
            conn.close()

        donors = info.get("donor_to_target") or {}
        if not donors:
            summary_rows.append((db_name, 0))
            continue

        out_path = REPORT_DIR / f"{db_name}_collapses.csv"
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["collapsed_headword", "destination_headword", "gloss", "trigger_tags"])
            for donor_id, target_id in sorted(donors.items()):
                writer.writerow([
                    info["donor_surface_by_donor"].get(donor_id, ""),
                    info["target_headword_by_donor"].get(donor_id, ""),
                    info["donor_gloss_by_donor"].get(donor_id, ""),
                    ";".join(info["synthetic_tags_by_donor"].get(donor_id, [])),
                ])
        written_files.append(out_path)
        summary_rows.append((db_name, len(donors)))
        print(f"[ok] {db_name}: {len(donors)} collapses -> {out_path.name}")

    summary_path = REPORT_DIR / "_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["db_name", "collapse_count"])
        for name, count in summary_rows:
            writer.writerow([name, count])
    written_files.append(summary_path)

    zip_path = REPORT_DIR.parent / f"synthetic_collapses_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in written_files:
            zf.write(fp, arcname=f"synthetic_collapses/{fp.name}")
    print(f"\nZip: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
