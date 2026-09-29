# Training and evaluation procedure

The training record connects source corpora and task-specific labels to selected
model components, CPU inference artifacts and saved measurements.

## Corpus preparation and validation

[Dataset cards](datasets/README.md) identify the supervision sources and label
inventories. The [Sanskrit builders](pipeline/datasets/sanskrit/) preserve the
relationship between surface tokens, underlying words, corpus annotations and
corrected BIO output. Chapter-level sampling and recorded seeds make the selected
DCS preparation traceable.

The [NER trainer](pipeline/models/train_ner.py) checks BIO structure, rejects
empty/malformed corpora and detects exact cross-split duplicates before training.
Its [training contract](pipeline/models/TRAINING_RUN.md) documents configuration,
inputs and output artifacts. Historical run configurations and label vocabularies
are indexed in the [model guide](models/README.md).

## Selection and artifact records

The [active model map](STATUS.md) records component-level choices rather than
assuming each language uses a single training run. Selected development scores
retain their epochs, label schemes and source-log identities in
[selected_ner_training.json](evaluation/results/selected_ner_training.json).

The published trainer's run-evidence writer records input hashes/counts,
Python/package versions, wrapper and TPipeline source hashes, and output hashes.
The [deployment inventory](models/deployed_artifacts.json) separately identifies
selected resources and retained checkpoint matches.

## CPU inference experiments

The [ONNX exporter](pipeline/models/build_trankit_xlmr_onnx_cpu.py),
[bundle builder](pipeline/models/build_trankit_compressed_runtime_artifacts.py)
and [benchmark](evaluation/benchmarks/trankit_benchmark/README.md) connect the
checkpoint store to shared-encoder INT8 inference. Their cache and dependency
settings make the worker environments explicit.

[Session-tuning results](evaluation/README.md#onnx-session-tuning) record the
measured machine, input text, settings and samples. The
[evidence index](EVIDENCE.md) distinguishes those runtime measurements from
linguistic development scores and corpus-construction statistics.
