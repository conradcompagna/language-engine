# grc_pausanias_ethnic_civic_misc

Source: `training\nerdump\anc\tlg0525_pausanias_ner_recreated\pausanias_grc2_ner_all*.conll`

Remap rule:

```text
MISC + proposed_label ETHNIC_CIVIC_GROUP -> ETHNIC_CIVIC_GROUP
all other MISC -> MISC
PER / LOC / O unchanged
```

Files:

```text
train.bio
dev.bio
test.bio
all.bio
label_token_counts.tsv
dataset_report.json
```

Entity-token counts in `all.bio`:

```text
ETHNIC_CIVIC_GROUP  5,923
LOC                 6,394
MISC                1,287
PER                12,041
O                 217,896
```

Use with:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py
```
