"""Rebuild the retained Sanskrit MWT development reference from its source chapter IDs."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--chapter-info", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--exporter", required=True, type=Path,
                        help="Original build_dcs_trankit_full_dataset.py.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    chapter_ids = []
    for line in args.input.open(encoding="utf-8"):
        match = re.match(r"## chapter_id: (\d+)", line)
        if match:
            chapter_ids.append(match.group(1))
    assert len(chapter_ids) == len(set(chapter_ids))
    lookup = {entry.findtext("chapterId"): entry.findtext("path")
              for entry in ET.parse(args.chapter_info).getroot().findall(".//chapter")}
    paths = [lookup[chapter_id] for chapter_id in chapter_ids]
    spec = importlib.util.spec_from_file_location("dcs_exporter", args.exporter)
    exporter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = exporter
    spec.loader.exec_module(exporter)
    corpus_root = args.corpus_root.resolve()
    exporter.FILES_DIR = Path("\\\\?\\" + str(corpus_root)) if os.name == "nt" else corpus_root
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = args.output_dir / "reference.conllu"
    stats = exporter.write_conllu_export(paths, reference)
    fingerprint = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "method": "Chapter IDs from retained MWT input, mapped through original chapter metadata and exported from authentic corpus chapters.",
        "chapter_count": len(chapter_ids), "chapter_ids": chapter_ids, "stats": stats.__dict__,
        "input_sha256": fingerprint(args.input), "metadata_sha256": fingerprint(args.chapter_info),
        "exporter_sha256": fingerprint(args.exporter), "reference_sha256": fingerprint(reference),
    }
    (args.output_dir / "recovery.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Recovered {len(chapter_ids)} chapters to {reference}")


if __name__ == "__main__":
    main()
