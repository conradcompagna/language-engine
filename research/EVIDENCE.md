# Research evidence index

The record connects four kinds of work: linguistic dataset construction, model
training, inference optimization, and application validation. Start with the selected
[NER training results](models/README.md#selected-training-results) and
[ONNX session measurements](evaluation/README.md#onnx-session-tuning), then follow
the inputs and implementation below.

| Work | Implementation | Data and configuration | Recorded evidence |
|---|---|---|---|
| Sanskrit sandhi/MWT | [Run history](STATUS.md) and [subset builder](pipeline/datasets/build_dcs_trankit_mwt_subset.py) | [DCS aggregate](pipeline/datasets/sanskrit/stats.json): seed 1337; 1,309 train / 146 dev chapters | 70,355 training and 9,349 development sentences; [MWT evaluation builder](pipeline/datasets/build_trankit_mwt_eval_input.py) |
| Sanskrit synthetic NER | [Trainer](pipeline/models/train_ner.py) and [dataset builder](pipeline/datasets/sanskrit/build_final_sanskrit_gemini_ner_dataset.py) | [Dataset summary](pipeline/datasets/sanskrit/gemini_ner/final/dataset_summary.json), split construction, and domain-specific labels | [Annotation aggregate](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json): 1,852 jobs, 1,680 validated BIO artifacts, estimated USD 0.6023; selected dev scores in the [model guide](models/README.md) |
| Multilingual NER | [Dataset cards](datasets/README.md), [training workflow](pipeline/models/TRAINING_RUN.md) | Source and split recorded per card; bundled TPipeline patch sets seed 1234 | 29 [configuration/vocabulary directories](models/README.md) and selected training-log excerpts |
| Inference optimization | [Benchmark modules](evaluation/benchmarks/trankit_benchmark/README.md) and [ONNX exporter](pipeline/models/build_trankit_xlmr_onnx_cpu.py) | Matched input text across worker profiles, with explicit hardware and local model resources | [Session-tuning measurements](evaluation/results/ort_session_tuning_excerpt.json) with profile settings, annotation fingerprints and runtime context |

## Reading the measurements

Dataset counts and annotation costs describe construction; development F1 describes
epoch selection on each run's own labels and split. Historical configurations and
logs retain their original context, while the run-history guide records artifact
selection. The [deployed artifact inventory](models/deployed_artifacts.json) now records
model hashes and component matches; the historical DCS trainer configuration
remains a separately retained resource. Historical configs also do not identify the installed trainer
hash or every seed setting; the installed Trankit version controls those defaults.

The [Vietnamese WikiANN card](datasets/wikiann_vi/README.md) records its use of
upstream train + test for training and validation for development. Its retained
`test.bio` is an audit copy, so the published comparison uses development scores
on that validation split. The timing record separately identifies the machine,
inputs and samples behind the inference measurements.

## Run and artifact records

NER runs write `run_evidence.json` with input hashes/counts, Python/package versions,
wrapper and installed TPipeline source hashes, and copied-output hashes. This
connects corpus inputs and training execution to the resulting artifacts,
alongside the historical logs.

Losslessly split rules, reports and logs carry ordered SHA-256 manifests, preserving
the identity and ordering of the original records.
