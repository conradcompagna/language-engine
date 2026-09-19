"""
Train the Tagalog MWT expander.
This model takes a detected MWT span (e.g. "iyong") and expands it into its
component tokens (e.g. "iyo" + "-ng").  It must be trained AFTER the tokenizer
so that MWT span detection is already in place.

Requires only CoNLL-U files — no raw .txt needed.

Input files (in this directory):
  tgl-train.conllu  -- MWT-annotated training data
  tgl-dev.conllu    -- MWT-annotated dev data

Output: trankit_save_tgl_v2/xlm-roberta-base/tagalog-v2/tagalog-v2.mwt.mdl
"""

import os
from pathlib import Path
from trankit import TPipeline

HERE = Path(__file__).parent.resolve()
SAVE_DIR = HERE.parent / "trankit_save_tgl_v2"

training_config = {
    "category": "tagalog-v2",
    "task": "mwt",
    "train_conllu_fpath": str(HERE / "tgl-train.conllu"),
    "dev_conllu_fpath": str(HERE / "tgl-dev.conllu"),
    "save_dir": str(SAVE_DIR),
    "embedding": "xlm-roberta-base",
    "max_epoch": 50,
    "batch_size": 50,
    "gpu": True,
}

if __name__ == "__main__":
    print("=== Tagalog MWT expander training (v2 — MWT-supervised) ===")
    print(f"Save dir: {SAVE_DIR}")
    trainer = TPipeline(training_config)
    trainer.train()
    print("Done.")
