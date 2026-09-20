"""
Train the Tagalog tokenizer (sentence splitter + word tokenizer + MWT span detector).
This fixes the botched v1 run which had no MWT supervision in the CoNLL-U data.

Input files (in this directory):
  tgl-train.conllu  -- MWT-annotated training data (rebuilt from parquet with clitics)
  tgl-train.txt     -- raw sentence text (one sentence per line)
  tgl-dev.conllu    -- MWT-annotated dev data
  tgl-dev.txt       -- raw dev text

Output: trankit_save_tgl_v2/xlm-roberta-base/tagalog-v2/tagalog-v2.tokenizer.mdl
"""

import os
from pathlib import Path
from trankit import TPipeline

HERE = Path(__file__).parent.resolve()
SAVE_DIR = HERE.parent / "trankit_save_tgl_v2"

training_config = {
    "category": "tagalog-v2",
    "task": "tokenize",
    "train_txt_fpath":   str(HERE / "tgl-train.txt"),
    "train_conllu_fpath": str(HERE / "tgl-train.conllu"),
    "dev_txt_fpath":     str(HERE / "tgl-dev.txt"),
    "dev_conllu_fpath":  str(HERE / "tgl-dev.conllu"),
    "save_dir": str(SAVE_DIR),
    "embedding": "xlm-roberta-base",
    "max_epoch": 50,
    "batch_size": 4,
    "max_input_length": 512,
    "gpu": True,
}

if __name__ == "__main__":
    print("=== Tagalog tokenizer training (v2 — MWT-supervised) ===")
    print(f"Save dir: {SAVE_DIR}")
    trainer = TPipeline(training_config)
    trainer.train()
    print("Done.")
