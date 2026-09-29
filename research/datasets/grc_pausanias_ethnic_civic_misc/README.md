# Ancient Greek Pausanias: ethnic and civic groups

The Pausanias Ancient Greek NER corpus with ethnic and civic groups separated from the
MISC label. Person and location labels are unchanged.

```text
MISC spans proposed as ETHNIC_CIVIC_GROUP -> ETHNIC_CIVIC_GROUP
all other MISC                            -> MISC
PER / LOC / O                             unchanged
```

Entity-token counts across all splits:

```text
ETHNIC_CIVIC_GROUP  5,923
LOC                 6,394
MISC                1,287
PER                12,041
O                 217,896
```

Split sizes are in [`dataset_report.json`](dataset_report.json). The training run is
[`../../models/grc_pausanias_ethnic_civic_misc/`](../../models/grc_pausanias_ethnic_civic_misc/).
