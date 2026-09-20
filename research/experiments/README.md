# Experiments

Work that did not reach production. It is here because the record of what was tried and
rejected is part of how the shipped system was arrived at, and because a reader should
be able to tell at a glance which directories are load-bearing and which are not.

Every subdirectory has an `OUTCOME.md` stating what was attempted, what happened, and
why it stopped. Nothing in this directory is imported by the runtime or by
`research/pipeline/`.

| Directory | Outcome |
|---|---|
| [`arabic-cameltools/`](arabic-cameltools/) | Ten runs integrating CAMeL Tools morphology and tokenization for Arabic. Abandoned; the shipped Arabic model came from a plain UD run. |
| [`arabic-onnx-adapter-bank/`](arabic-onnx-adapter-bank/) | One shared INT8 encoder with per-language adapter inputs. Prototyped, not shipped. |
| [`sanskrit-vedic-v1/`](sanskrit-vedic-v1/) | Sanskrit trained on the Vedic UD treebank. Superseded by the DCS run. |
| [`rarelangs-per-language/`](rarelangs-per-language/) | Six per-language splits of the rare-language batch. None completed; the pooled run shipped. |
| [`finerweb-taxonomy-sweeps/`](finerweb-taxonomy-sweeps/) | ~80 parameter variants behind the chosen NER label taxonomy. |
| [`amharic-lexicon-induction/`](amharic-lexicon-induction/) | Unsupervised bilingual lexicon induction for Amharic. Unrelated to the product. |
