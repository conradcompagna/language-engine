# Selected-checkpoint development evaluations

I used these scripts to measure the selected native model components against retained development material where the historical training logs did not preserve the final component score. The result records identify the checkpoint, input and reference by SHA-256; they distinguish these new measurements from scores recovered from the original training runs.

The commands below take existing model and corpus files as explicit inputs. Paths such as `inputs/arabic.pt` stand for the matching artifacts identified in the result records. The scripts run model inference on CPU and write metrics to a separate output directory.

## Multiword expansion

`reevaluate_mwt.py` runs the selected seq2seq MWT checkpoint, then its dictionary ensemble, and scores both with Trankit's bundled CoNLL UD scorer. The reported measure is **Words F1**, which evaluates the expanded word sequence. Token and sentence scores are also retained to identify the boundary conditions entering the expander.

| Language | Input supplied to the MWT component | Seq2seq Words F1 | Dictionary ensemble Words F1 |
|---|---|---:|---:|
| Arabic | Retained selected-tokenizer development predictions | 97.788250 | 98.089852 |
| Sanskrit | Retained gold surface boundaries and MWT flags from the full DCS development export | 92.811879 | 93.911494 |
| Turkish | Development reference collapsed to gold surface boundaries and MWT flags | 99.593099 | 99.674479 |
| Hebrew | Development reference collapsed to gold surface boundaries and MWT flags | 98.154076 | 98.303457 |
| Tagalog | Retained selected-tokenizer development predictions | 97.379606 | 97.379606 |

These measurements use different corpora and input stages. Each character stream is checked against its reference before model inference. Arabic and Tagalog include the errors in the retained tokenizer predictions; the other three measurements isolate expansion given gold surface boundaries. The model checkpoints are native PyTorch artifacts, before deployment quantization.

For Arabic or Tagalog:

```sh
python reevaluate_mwt.py --checkpoint inputs/arabic.pt --input inputs/arabic-tokenizer-dev.conllu --reference inputs/arabic-dev-fixed.conllu --language-code ar --input-kind retained-tokenizer --output-dir outputs/arabic
```

For Sanskrit, use `--input-kind retained-gold-boundaries`, the retained input and the matching reconstructed reference described below. For Turkish and Hebrew, pass the development reference as both `--input` and `--reference` and select `--input-kind collapse-gold-reference`; the script converts MWT ranges into one surface token with `MWT=Yes` before expansion. Feeding already-expanded gold words directly to this loader would duplicate MWT children.

The Tagalog reference is the retained `tgl-dev.udfixed.conllu`: its token IDs, forms, lemmas and tag fields match all 37,045 rows of the original development file, while its dependency repairs allow the UD scorer to read the file.

The evaluator writes `seq2seq_only.conllu`, `dictionary_ensemble.conllu`, and `result.json`. The prediction files contain corpus text; the published evidence records contain metrics and fingerprints.

## Sanskrit MWT reference

`recover_sanskrit_mwt_reference.py` reconstructs the reference corresponding to the retained MWT input. It reads the ordered chapter IDs from that input, resolves them through the original DCS chapter metadata, and calls the original `build_dcs_trankit_full_dataset.py` exporter on those chapters.

```sh
python recover_sanskrit_mwt_reference.py --input inputs/sanskrit-tokenizer-dev.conllu --chapter-info inputs/chapter-info.xml --corpus-root inputs/dcs/conllu/files --exporter build_dcs_trankit_full_dataset.py --output-dir outputs/sanskrit-reference
```

The exporter is preserved in `research/pipeline/datasets/build_dcs_trankit_full_dataset.py`. The recovered reference contains **1,590 chapters**, **73,807 nonempty sentences**, and **97,960 MWT ranges**. This is the full retained development export, distinct from the alternative 10% preparation subset. Its expected SHA-256 is:

```text
21459f1e618f77c58c38c04353be66ff84a966165842455832d74d455dfc81f1
```

Both the reference text and the corpus chapter IDs stay in the local output directory; the published result identifies the source files and their hashes.

## Japanese named entities

`reevaluate_japanese_ner.py` loads the selected epoch-49 Japanese NER checkpoint and evaluates **507 pretokenized development sentences**, **12,287 tokens**, and **795 gold entities** from UD Japanese GSD r2.10 NE. The retained original training command names this corpus and model directory. BIO reference tags are converted to BIOES, then compared with predicted tags using Trankit's entity scorer.

```sh
python reevaluate_japanese_ner.py --model-store inputs/japanese-model-store --dev-bio inputs/japanese-dev.bio --training-command inputs/japanese-command.txt --cache-dir ner-cache --output-dir outputs/japanese-ner
```

The model store is the original Trankit cache root: it contains the XLM-R base cache files under `xlm-roberta-base/` and the selected checkpoint and vocabulary under `xlm-roberta-base/customized-ner/`. The script copies those files to its scratch cache and runs offline. Use a short cache path on Windows because legacy cached model filenames are long.

Expected entity micro scores are **84.656797% precision**, **79.119497% recall**, and **81.794538% F1**. This is the NER component on gold pretokenized sentences; the tokenizer is not invoked.

## Sanskrit morphology and dependency parsing

`evaluate_sanskrit_parser.py` evaluates the selected epoch-74 tagger/parser on **1,525 development sentences** and **9,787 gold-expanded words**. All seven label-to-index dictionaries regenerated from the retained 10,000-sentence training subset match the selected runtime vocabulary. The development file is named by the training recipe retained alongside that subset.

```sh
python evaluate_sanskrit_parser.py --model inputs/sanskrit-vedic.tagger.mdl --vocab inputs/sanskrit-vedic.vocabs.json --dev inputs/sanskrit-parser-dev.conllu --cache parser-cache --output outputs/sanskrit-parser.json
```

Expected results are **90.099111% UPOS**, **81.076939% UFeats**, **72.739348% UAS**, and **62.256054% LAS**. Tokenization, MWT expansion and lemmatization are not invoked; the input supplies gold sentence and expanded-word boundaries. XPOS is a constant `_` label in this corpus, so its 100% value is not presented as a substantive tagging result.

This script checks the expected checkpoint, vocabulary and development hashes and the stored epoch before inference. Its JSON records UD scores on the 0–1 scale; the values above are percentages.

## Recorded environments and verification

MWT expansion and Japanese NER were evaluated with Python 3.12, Trankit 1.1.1, PyTorch `2.12.0.dev20260217+cu128`, and four CPU threads; the installed CUDA build does not change the explicitly CPU execution. Sanskrit parsing was evaluated with Python 3.10.20, pristine Trankit 1.1.1, PyTorch `2.6.0+cpu`, and four CPU threads.

The portable MWT script reproduces both Arabic prediction files byte-for-byte and produces the same collapsed Turkish and Hebrew inputs as the original helper. The portable Sanskrit reference recovery reproduces the exact reference hash above. The portable Japanese evaluator reproduces the entity scores above.
