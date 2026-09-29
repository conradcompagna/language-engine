# Research evidence index

The record connects four kinds of work: linguistic dataset construction, model
training, inference optimization, and application validation. Start with the selected
[complete selected-model results](models/TRAINING_RESULTS.md) and
[ONNX session measurements](evaluation/README.md#onnx-session-tuning), then follow
the inputs and implementation below.

| Work | Implementation | Data and configuration | Recorded evidence |
|---|---|---|---|
| Arabic clitic segmentation | [Teacher corpus builder and correction rules](pipeline/datasets/arabic/) | Authentic Arabic news, CAMeL MLE analyses, corrected CoNLL-U and 95/5 split | Selected tokenizer 99.86 token F1; MWT 98.09 expanded-word F1 with retained tokenizer predictions; [score records](models/TRAINING_RESULTS.md) |
| Sanskrit sandhi/MWT | [Run history](STATUS.md), [full-corpus builder](pipeline/datasets/build_dcs_trankit_full_dataset.py), and separate [subset builder](pipeline/datasets/build_dcs_trankit_mwt_subset.py) | Selected MWT development input: 1,590 DCS chapters and 97,960 expansion candidates; [subset preparation statistics](pipeline/datasets/sanskrit/stats.json) describe a separate track | Tokenizer 97.09 token F1; MWT 93.91 expanded-word F1 with reference boundaries; [stage-specific records](evaluation/results/mwt-development.json) |
| Sanskrit interpretive NER | [Trainer](pipeline/models/train_ner.py) and [dataset builder](pipeline/datasets/sanskrit/build_final_sanskrit_gemini_ner_dataset.py) | [Dataset summary](pipeline/datasets/sanskrit/gemini_ner/final/dataset_summary.json), split construction, and domain-specific labels | [Annotation aggregate](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json): 1,852 jobs, 1,680 validated BIO artifacts, estimated USD 0.6023; selected dev scores in the [model guide](models/README.md) |
| Multilingual model selection | [Component map](STATUS.md), [dataset cards](datasets/README.md), [training workflow](pipeline/models/TRAINING_RUN.md) | Source and split recorded per component; 29 retained NER configuration/vocabulary directories | [All 61 custom selections scored](models/TRAINING_RESULTS.md), alongside byte-verified [stock model identities](models/stock-models.json) |
| Inference optimization | [Benchmark modules](evaluation/benchmarks/trankit_benchmark/README.md) and [ONNX exporter](pipeline/models/build_trankit_xlmr_onnx_cpu.py) | Matched input text across worker profiles, with explicit hardware and local model resources | [Session-tuning measurements](evaluation/results/ort_session_tuning_excerpt.json) with profile settings, annotation fingerprints and runtime context |

## Reading the measurements

Dataset counts and annotation costs describe construction; development F1 describes
epoch selection on each run's own labels and split. Historical configurations and
logs retain their original context, while the run-history guide records artifact
selection. The [deployed artifact inventory](models/deployed_artifacts.json) now records
model hashes and component matches. The complete score collection separates
historical training-log results from fresh evaluations of selected checkpoints;
each fresh record identifies the reference data and the stage being evaluated.

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
