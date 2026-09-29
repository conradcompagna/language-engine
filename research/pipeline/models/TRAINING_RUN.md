# Trankit NER training workflow

The [training wrapper](train_ner.py) connects prepared BIO corpora, Trankit's
training pipeline, epoch evaluation and named output directories. The
[model-run index](../../models/README.md) records 29 completed NER runs with their
label vocabularies and retained configurations.

## From corpus to model artifact

| Stage | Implementation and record |
|---|---|
| Corpus preparation | Dataset directories supply training and development BIO files; [dataset cards](../../datasets/README.md) record source, labels and split construction. |
| Input validation | The wrapper checks UTF-8 token/tag rows, nonempty splits and exact token-sequence overlap, with hashes and counts for the input files. |
| Training configuration | The run selects the base encoder, corpus, epoch limit, working cache and named output directory. |
| Epoch evaluation | Logs record entity-level micro scores and per-label precision, recall and F1. |
| Artifact capture | Completed or interrupted runs copy newly saved model artifacts into the reserved run directory and record their hashes. |

The trainer separates the active Trankit cache from finished runs. Run identifiers
are reserved before training to protect previous outputs, and cache paths are
configurable to accommodate Windows path-length constraints. A separate snapshot
operation preserves an existing active cache.

## Reading the training evidence

Historical configurations and log excerpts record the original runs. The current
wrapper also writes `run_evidence.json` with corpus identities, installed package
versions and the actual `TPipeline` source hash. These are distinct records: a
snapshot identifies model files, while a training record connects files to the
inputs and execution that produced them.

The bundled [Trankit pipeline patch](upstream_patches/trankit/tpipeline.py) sets
seed 1234. The wrapper records the installed pipeline implementation so the seed
policy remains attributable to the code used for that run.

The [selected results](../../models/README.md#selected-training-results) report
best-development scores with their dataset and epoch-selection context. The
[application selection map](../../STATUS.md) connects completed training runs to
the components loaded by Language Engine.
