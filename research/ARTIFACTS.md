# Published research artifacts

Large evidence files are divided by their meaning, without dropping records:

| Artifact | Organization |
| --- | --- |
| [Japanese morphology](pipeline/dictionaries/japanese/data/rules/manifest.json) | Rule families; token rules further grouped by consecutive part-of-speech families |
| [LSJ/Wiktionary report](evaluation/reports/grc_lsj_vs_wiktionary_samples.md) | Introduction, LSJ samples and Wiktionary samples |
| [Vedic tokenizer log](experiments/sanskrit-vedic-v1/run_logs/tokenize/manifest.json) | Epochs 0–6 and the recorded partial epoch 7 |

Each manifest records ordering, original SHA-256 and byte length, plus checksums
for every part. Text manifests also retain original line offsets. JSON assembly
preserves object and record order and the original UTF-8 formatting.

```sh
python research/artifacts.py research/pipeline/dictionaries/japanese/data/rules/manifest.json
python research/artifacts.py research/experiments/sanskrit-vedic-v1/run_logs/tokenize/manifest.json --output /tmp/tokenize.training
```

Without `--output`, the command verifies reconstruction without writing a file.
Generated assembled files belong outside the source tree. `pytest` checks all
three historical digests and the analyzer's rule-loader compatibility.

The Japanese analyzer loads the manifest automatically, while retaining support
for an external legacy bundle or CSV data directory.

`tools/check_provenance.py` screens candidates by size, then verifies artifact
identity with `--hash`. Pair those matches with configurations, inputs, and logs
to trace model selection across the training record.
