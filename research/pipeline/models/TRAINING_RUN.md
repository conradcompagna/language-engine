# Trankit NER Training Run

This folder is the reusable training work area.

Use `training\t` as Trankit's `save_dir`. The path is intentionally short because Trankit's old transformer cache uses very long hash filenames on Windows. The training script keeps the active Trankit category fixed as `customized-ner` by default, so repeated NER runs reuse the same downloaded XLM-R / Trankit work cache instead of creating a fresh category cache for every dataset.

Finished model artifacts are copied after each run into:

```text
finished_models/<run-id>/
```

Default first run:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py
```

Short smoke run:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --max-epoch 1
```

Low-memory run:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --batch-size 4
```

If you manually stop a run with `Ctrl+C`, the wrapper snapshots the latest saved active model into `finished_models/<run-id>` before exiting.

For a run that was started before this behavior was added, snapshot the active cache manually:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --run-id <dataset-name> --snapshot-only
```

For another dataset, put `train.bio` and `dev.bio` in a dataset folder under `training\trankit_finerweb_prep\datasets`, then run:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --dataset-dir training\trankit_finerweb_prep\datasets\<dataset-name> --run-id <dataset-name>
```

The active model during training lives at:

```text
training/t/xlm-roberta-base/customized-ner/
```

That directory is reused and overwritten by each training job. The preserved outputs are the copied subfolders under `finished_models`.

This local Trankit NER training path expects CUDA.

By default the script seeds the local XLM-R cache from:

```text
training/trankit_save_ja_ner_v2/
```
