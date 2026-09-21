# Research and build infrastructure

This directory records offline model training, dictionary construction and evaluation.
Start with the [evidence index](EVIDENCE.md), then follow the [build chains](pipeline/README.md).
The current application is documented in the root [README](../README.md).

| Directory | Contents |
|---|---|
| [pipeline/](pipeline/) | Dataset builders, trainers, model conversion and dictionary tooling |
| [evaluation/](evaluation/) | Regression harnesses, hardware benchmarks and historical reports |
| [experiments/](experiments/) | Earlier approaches, with recorded outcomes |
| [notes/](notes/) | Design records written during development |
| [datasets/](datasets/) | Dataset cards, aggregate counts and provenance; full corpora excluded |
| [models/](models/) | Configuration and vocabulary records for 29 runs; weights excluded |

[STATUS.md](STATUS.md) preserves the historically reported run-to-deployment mapping.
It is not a verified inventory of a live server. Equal file sizes establish only
candidates; [check_provenance.py](tools/check_provenance.py) requires `--hash` to
report a SHA-256 match. A missing match does not establish that a run was abandoned,
and a matching artifact alone does not prove which training data produced it.

The [reproduction guide](REPRODUCIBILITY.md) distinguishes maintained commands with
public synthetic checks from archival scripts with unavailable dependencies or old
workstation paths. Models, full corpora, account data and annotation-job outputs are
excluded; the [Sanskrit run aggregate](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json)
records the published job totals without redistributing those outputs.
