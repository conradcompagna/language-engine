"""
Train all Trankit components for Ancient Hebrew (hbo_ptnk).
Run after build_ancient_hebrew_dataset.py has generated ./ancient_hebrew/*.

Pipeline category: customized-mwt (no NER).
Tasks trained in order: tokenize -> mwt -> posdep -> lemmatize
"""

import trankit
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "ancient_hebrew"
SAVE = HERE / "trankit_save_hbo_ptnk_v1"

CATEGORY = "customized-mwt"

TRAIN_CONLLU = str(DATA / "hbo-train.conllu")
DEV_CONLLU   = str(DATA / "hbo-dev.conllu")
TRAIN_TXT    = str(DATA / "hbo-train.txt")
DEV_TXT      = str(DATA / "hbo-dev.txt")
SAVE_DIR     = str(SAVE)

COMMON = {
    "category": CATEGORY,
    "save_dir": SAVE_DIR,
    "train_conllu_fpath": TRAIN_CONLLU,
    "dev_conllu_fpath":   DEV_CONLLU,
}

TASKS = [
    {
        **COMMON,
        "task": "tokenize",
        "train_txt_fpath": TRAIN_TXT,
        "dev_txt_fpath":   DEV_TXT,
    },
    {**COMMON, "task": "mwt"},
    {**COMMON, "task": "posdep"},
    {**COMMON, "task": "lemmatize"},
]


def main():
    for cfg in TASKS:
        print(f"\n{'='*60}")
        print(f"Training task: {cfg['task']}")
        print(f"{'='*60}")
        trainer = trankit.TPipeline(training_config=cfg)
        trainer.train()

    print("\nVerifying pipeline...")
    trankit.verify_customized_pipeline(
        category=CATEGORY,
        save_dir=SAVE_DIR,
        embedding_name="xlm-roberta-base",
    )


if __name__ == "__main__":
    main()
