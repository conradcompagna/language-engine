# Research

Training, evaluation and data-preparation code behind the Language Engine models and
dictionaries. The application itself is described in the [root README](../README.md).

| Folder | Contents |
|---|---|
| [models/](models/) | Which components are custom or stock, development scores for every custom component, and NER run configurations |
| [releases/](releases/) | Three published models with model cards, loaders and evaluation records |
| [pipeline/](pipeline/) | Dataset builders, model training and export scripts, and dictionary conversion |
| [datasets/](datasets/) | Cards for five NER training corpora |
| [evaluation/](evaluation/) | Score records, re-evaluation scripts, benchmarks and regression tests |
| [experiments/](experiments/) | Six development experiments, including approaches that were not adopted |
| `tools/check_provenance.py` | Compares training-run output folders with a model store by file hash |

## Split files

Two large records are stored as ordered shards with a `manifest.json` that gives the
original file's SHA-256 and byte length: the Japanese morphology rules
(`pipeline/dictionaries/japanese/data/rules/`) and the Vedic Sanskrit tokenizer log
(`experiments/sanskrit-vedic-v1/run_logs/tokenize/`). `artifacts.py` checks the shards
and reassembles the original:

```sh
python research/artifacts.py research/pipeline/dictionaries/japanese/data/rules/manifest.json
python research/artifacts.py research/experiments/sanskrit-vedic-v1/run_logs/tokenize/manifest.json --output /tmp/tokenize.training
```
