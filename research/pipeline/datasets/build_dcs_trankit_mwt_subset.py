import json
import random
from pathlib import Path

from build_dcs_trankit_full_dataset import (
    FILES_DIR,
    CHAPTER_INFO_PATH,
    chapter_surface_text_lines,
    ordered_chapter_paths,
    write_conllu_export,
    write_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "training" / "dcs_sanskrit_trankit_mwt_subset_10pct"

SUBSET_FRACTION = 0.10
DEV_FRACTION = 0.10
RANDOM_SEED = 1337


def has_mwt_rows(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if "\t" not in line:
                continue
            tok_id = line.split("\t", 1)[0]
            if "-" in tok_id and tok_id[0].isdigit():
                return True
    return False


def write_surface_text_export(paths, out_path: Path) -> int:
    chapter_count = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for rel in paths:
            lines = chapter_surface_text_lines(FILES_DIR / rel)
            if not lines:
                continue
            handle.write("\n".join(lines))
            handle.write("\n\n")
            chapter_count += 1
    return chapter_count


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ordered = ordered_chapter_paths()
    mwt_paths = [rel for rel in ordered if has_mwt_rows(FILES_DIR / rel)]

    rng = random.Random(RANDOM_SEED)
    shuffled = list(mwt_paths)
    rng.shuffle(shuffled)

    subset_size = max(1, round(len(mwt_paths) * SUBSET_FRACTION))
    selected_set = set(shuffled[:subset_size])
    selected_paths = [rel for rel in ordered if rel in selected_set]

    dev_size = max(1, round(len(selected_paths) * DEV_FRACTION))
    dev_set = set(rng.sample(selected_paths, dev_size))
    train_paths = [rel for rel in selected_paths if rel not in dev_set]
    dev_paths = [rel for rel in selected_paths if rel in dev_set]

    write_manifest(ordered, OUTPUT_DIR / "all_chapters_corpus_order.txt")
    write_manifest(mwt_paths, OUTPUT_DIR / "all_mwt_chapters.txt")
    write_manifest(selected_paths, OUTPUT_DIR / "subset_chapters.txt")
    write_manifest(train_paths, OUTPUT_DIR / "train_chapters.txt")
    write_manifest(dev_paths, OUTPUT_DIR / "dev_chapters.txt")

    train_text_chapters = write_surface_text_export(train_paths, OUTPUT_DIR / "train.txt")
    dev_text_chapters = write_surface_text_export(dev_paths, OUTPUT_DIR / "dev.txt")
    train_stats = write_conllu_export(train_paths, OUTPUT_DIR / "train.conllu")
    dev_stats = write_conllu_export(dev_paths, OUTPUT_DIR / "dev.conllu")

    stats = {
        "source_dir": str(FILES_DIR),
        "chapter_info": str(CHAPTER_INFO_PATH),
        "total_chapters": len(ordered),
        "mwt_chapters": len(mwt_paths),
        "subset_fraction": SUBSET_FRACTION,
        "selected_chapters": len(selected_paths),
        "train_chapters": len(train_paths),
        "dev_chapters": len(dev_paths),
        "train_text_chapters_written": train_text_chapters,
        "dev_text_chapters_written": dev_text_chapters,
        "split_rule": {
            "type": "random_chapter_subset",
            "random_seed": RANDOM_SEED,
            "subset_fraction": SUBSET_FRACTION,
            "dev_fraction_within_subset": DEV_FRACTION,
        },
        "train_stats": train_stats.__dict__,
        "dev_stats": dev_stats.__dict__,
    }
    (OUTPUT_DIR / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
