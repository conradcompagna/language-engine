import trankit

trainer = trankit.TPipeline(
    training_config={
        "category": "customized-ner",
        "task": "ner",
        "save_dir": "./save_dir",
        "train_bio_fpath": "./train.bio",
        "dev_bio_fpath": "./dev.bio",
    }
)

trainer.train()
