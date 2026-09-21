# Research evidence index

Counts below are published historical records, not newly reproduced training results.
No private model store or deployed server was consulted for this cleanup.

| Work | Trainer/configuration | Data, split and seed | Evaluation/artifacts and limits |
|---|---|---|---|
| Sanskrit sandhi/MWT | [reported run history](STATUS.md) and [subset builder](pipeline/datasets/build_dcs_trankit_mwt_subset.py); exact DCS trainer configuration is not published | [DCS aggregate](pipeline/datasets/sanskrit/stats.json): seed 1337, chapter sample and split, 1,309 train / 146 dev chapters | 70,355 train / 9,349 dev sentences are data counts; [MWT evaluation builder](pipeline/datasets/build_trankit_mwt_eval_input.py); published weights, hashes and held-out score are absent |
| Sanskrit synthetic NER | [trainer](pipeline/models/train_ner.py), [dataset builder](pipeline/datasets/sanskrit/build_final_sanskrit_gemini_ner_dataset.py) | [final dataset summary](pipeline/datasets/sanskrit/gemini_ner/final/dataset_summary.json) and builder define the split; installed Trankit controls training seed | [run aggregate](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json): 1,852 jobs, 1,680 validated BIO artifacts, estimated USD 0.6023; these do not measure NER generalization |
| Multilingual NER datasets | [dataset cards](datasets/README.md), [trainer and commands](pipeline/models/TRAINING_RUN.md) | Read each card's source and split; bundled TPipeline patch sets seed 1234, while historical configs do not record the installed trainer hash | 29 [run configuration/vocabulary directories](models/README.md); no new accuracy or training-reproduction claim |
| CPU/GPU inference comparison | [benchmark modules and commands](evaluation/benchmarks/trankit_benchmark/README.md), [ONNX exporter](pipeline/models/build_trankit_xlmr_onnx_cpu.py) | Same input text across worker profiles; hardware and local model artifacts required | Public tests check comparison math, routes and process lifecycle; they are not throughput measurements |

The [Vietnamese WikiANN card](datasets/wikiann_vi/README.md) combines the upstream
train and test sets for training and uses validation as dev: its retained `test.bio`
is an audit copy, **not a held-out test set**. Do not report a test score on it as
unseen-data performance.

Future NER runs write `run_evidence.json` with input hashes/counts, Python/package
versions, wrapper and installed TPipeline source hashes, and hashes of copied output
artifacts. This cannot retroactively authenticate earlier runs. Historical configs
and logs retain their original paths and contents as evidence; do not publish newly
generated private paths, corpora or weights without reviewing them.

Losslessly split rules, reports and logs carry ordered SHA-256 manifests; run
`python -m pytest tests/test_research_artifacts.py` to validate the published reconstruction.
