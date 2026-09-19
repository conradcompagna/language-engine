import os

os.environ["PYTHONIOENCODING"] = "utf-8"

import trankit

trainer = trankit.TPipeline(
    training_config={
        "category": "customized-mwt-ner",
        "task": "posdep",
        "save_dir": r"C:/Users/conra/Desktop/universal - js hybrid/training/newsanskritdict/data/conllu/files/newparser/posdep_model",
        "train_conllu_fpath": r"C:/Users/conra/Desktop/universal - js hybrid/training/newsanskritdict/data/conllu/files/newparser/train.conllu",
        "dev_conllu_fpath": r"C:/Users/conra/Desktop/universal - js hybrid/training/newsanskritdict/data/conllu/files/newparser/dev.conllu",
    }
)

trainer.train()
