---
license: other
license_name: conrad-compagna-model-evaluation-1.0
license_link: LICENSE
language:
- ar
library_name: pytorch
tags:
- trankit
- tokenization
- multiword-token-expansion
- arabic
- teacher-supervision
inference: false
---

# Arabic Clitic Tokenizer and Multiword Expander

I built this Arabic segmentation model for [Language Engine](https://github.com/conradcompagna/language-engine)
by turning CAMeL Tools analyses of authentic news text into training supervision,
correcting recurring teacher errors, and training an XLM-R/Trankit tokenizer and
a character-level sequence-to-sequence multiword expander.

The tokenizer identifies surface boundaries and expansion candidates; the
expander recovers attached conjunctions, prepositions and pronominal clitics.
For example, the released model expands `وبالكتاب` into `و` + `ب` + `الكتاب`.
CAMeL Tools is part of the training-data construction process; inference runs
through the trained components.

## How I built it

I processed the 10,000-sentence `ara_news_2022` corpus with CAMeL's
`calima-msa-r13` MLE disambiguator and `atbtok` segmentation. I converted the
surface/expansion pairs into CoNLL-U with a 95/5 train/development split.
The correction pass addresses false nisba/proper-name splits, truncated
expansions, unanalysed forms and suffix/preposition cases before training.
The selected tokenizer and MWT checkpoint come from `t_ar10k2`.

The tokenizer learns task adapters and a classification head over XLM-RoBERTa;
the MWT component is a character-level LSTM sequence-to-sequence model combined
with its learned expansion dictionary. These are separate model architectures.

## Evaluation

| Development measure | Score |
|---|---:|
| Surface-token F1, selected tokenizer checkpoint | 99.86% |
| Sentence-boundary F1, selected tokenizer checkpoint | 97.49% |
| Expanded-word F1, selected MWT checkpoint with dictionary ensemble | 98.09% |

The tokenizer scores come from the evaluation at stored checkpoint epoch 11.
The MWT score was re-evaluated on 24 September 2026 against the retained corrected
CAMeL-teacher development reference, using the retained tokenizer predictions.
It measures expanded words across the development text, not accuracy only on
tokens that require splitting. These are development-set measurements against
the corrected supervision; the separate CAMeL comparison record documents
individual segmentation decisions rather than a general system ranking.

## Use the released components

Input is Arabic-script text.
The checkpoints use Trankit's native adapter/head and MWT formats. The release
includes a small CPU loader for those components and uses the upstream
XLM-RoBERTa base encoder. It does not load the Language Engine application.

```python
from huggingface_hub import snapshot_download
import importlib.util
from pathlib import Path

root = Path(snapshot_download("conradcompagna/arabic-clitic-tokenizer"))
spec = importlib.util.spec_from_file_location("released_model", root / "load_model.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
predict = module.load_model(root)
result = predict("وبالكتاب يقرأ الطالب في المدرسة.")
```

Use **Python 3.10** and the tested versions in `requirements.txt`. The base encoder downloads on
first use; the adapter/head weights come from this release. The weights are the
native training checkpoints; Language Engine's shared INT8 deployment format is
documented separately in the [CPU build record](https://github.com/conradcompagna/language-engine/blob/main/docs/BUILD_PROCESS.md#3-package-inference-for-cpu-deployment).

## Artifact and source record

[artifact-manifest.json](artifact-manifest.json) records checkpoint sizes and
SHA-256 identities; [evaluation.json](evaluation.json) records the evaluation
source, split and scores. The [Language Engine training record](https://github.com/conradcompagna/language-engine/blob/main/research/models/TRAINING_RESULTS.md)
places these components in the wider multilingual system.

## Credits

- [CAMeL Tools](https://github.com/CAMeL-Lab/camel_tools), developed by CAMeL Lab,
  supplies the teacher analyses; its code and downloaded data have separate licenses.
- The Arabic news source is the Leipzig Corpora Collection's `ara_news_2022`
  10,000-sentence sample; the training text and CAMeL resources are not bundled here.
- [Trankit](https://github.com/nlp-uoregon/trankit), Nguyen et al., EACL 2021,
  supplies the adapter training and inference architecture.
- [XLM-RoBERTa](https://huggingface.co/FacebookAI/xlm-roberta-base), Conneau et al.,
  supplies the pretrained multilingual encoder.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for source terms and citations.

## Downloads

[Hugging Face model and files](https://huggingface.co/conradcompagna/arabic-clitic-tokenizer) ·
[Complete GitHub ZIP](https://github.com/conradcompagna/language-engine/releases/download/models-2026-09-24/arabic-clitic-tokenizer.zip)

The package contains the selected native weights, evaluation record, artifact
hashes, source credits and runtime requirements.

## Release terms

My original weights and accompanying code are available for research, education,
experimentation and evaluation under the [Model Evaluation License](LICENSE).
Commercial deployment or redistribution of those weights requires my permission.
Third-party assets retain the terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
