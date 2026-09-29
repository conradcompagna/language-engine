# Checkpoint re-evaluation scripts

For seven selected components the training logs did not keep the final development
score. These scripts load the saved checkpoint and score it on the retained development
data. The results are the asterisked values in [`../../models/README.md`](../../models/README.md).

| Script | Evaluates |
|---|---|
| `reevaluate_mwt.py` | MWT expanders for Arabic, Sanskrit, Turkish, Hebrew and Tagalog (expanded-word F1, CoNLL UD scorer) |
| `recover_sanskrit_mwt_reference.py` | Rebuilds the Sanskrit MWT reference (1,590 DCS chapters, 97,960 MWT ranges) with the original exporter |
| `reevaluate_japanese_ner.py` | Japanese NER on 507 development sentences from UD Japanese GSD r2.10 NE |
| `evaluate_sanskrit_parser.py` | Sanskrit POS, features and dependency parser on 1,525 development sentences |
| `verification.json` | Hashes of the checkpoints, inputs and references used for each result |

## Results

| Component | Result |
|---|---|
| Arabic MWT | 98.09 expanded-word F1 (tokenizer predictions as input) |
| Sanskrit MWT | 93.91 (gold surface boundaries as input) |
| Turkish MWT | 99.67 (gold surface boundaries as input) |
| Hebrew MWT | 98.30 (gold surface boundaries as input) |
| Tagalog MWT | 97.38 (tokenizer predictions as input) |
| Japanese NER | 84.66 precision, 79.12 recall, 81.79 F1 (gold tokenization) |
| Sanskrit parser | 90.10 UPOS, 81.08 UFeats, 72.74 UAS, 62.26 LAS (gold word boundaries) |

## Usage

Each script takes the checkpoint, input and reference files as arguments. The MWT and
Japanese NER scripts write `result.json` to `--output-dir`; the Sanskrit reference
script writes `recovery.json`; the parser script writes the JSON file given by
`--output`. Run any script with `--help` for its arguments.
Example:

```sh
python reevaluate_mwt.py --checkpoint arabic.pt --input arabic-tokenizer-dev.conllu \
  --reference arabic-dev.conllu --language-code ar --input-kind retained-tokenizer \
  --output-dir outputs/arabic
```

The model checkpoints and corpora are not included in the repository.
