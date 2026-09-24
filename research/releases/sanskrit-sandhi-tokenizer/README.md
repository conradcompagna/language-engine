---
license: other
license_name: conrad-compagna-model-evaluation-1.0
license_link: LICENSE
language:
- sa
library_name: pytorch
tags:
- trankit
- tokenization
- sandhi-splitting
- multiword-token-expansion
- sanskrit
inference: false
---

# Sanskrit Sandhi Tokenizer and Multiword Expander

I trained these components to recover underlying Sanskrit words from the fused
surface forms encountered in actual Sanskrit texts. They supply the sandhi
segmentation stage of [Language Engine](https://github.com/conradcompagna/language-engine).

I used the **Digital Corpus of Sanskrit (DCS)** to preserve both sides of the
problem: a fused surface token and its annotated underlying words. The tokenizer
learns boundaries and expansion candidates; a character-level sequence-to-sequence
model learns to recover the underlying forms, including changes at sandhi
boundaries. This goes beyond inserting spaces into the surface string.

## How I built it

The dataset builder walks DCS chapters in corpus order and preserves CoNLL-U
multiword-token range rows instead of flattening away the fused forms. I used
the surface forms as tokenizer input and the annotated underlying words as
expansion targets. The selected run's retained MWT development input spans
1,590 DCS chapters; the evaluation record gives its reference reconstruction and
exact file identities. A separate focused-subset builder records another
preparation track in the development archive.

The selected tokenizer and expander come from `trankit_save_sa_dcs_v1`.
The historical `sanskrit-vedic` runtime alias is a file-layout identifier: these
released components were trained on the DCS track. I retained a separate
Vedic-treebank experiment during development.

## Evaluation

| Development measure | Score |
|---|---:|
| Surface-token F1, selected tokenizer checkpoint | 97.09% |
| Sentence-boundary F1, selected tokenizer checkpoint | 79.39% |
| Expanded-word F1, selected MWT checkpoint with reference boundaries | 93.91% |

The tokenizer scores come from the historical evaluation at stored checkpoint
epoch 20. I re-evaluated the selected expander on 24 September 2026 using the
retained DCS development input: 73,807 sentences with 97,960 expansion candidates,
spanning 1,590 chapters. The reference was rebuilt from those source chapters
with the original exporter.

The MWT score uses **reference surface boundaries and expansion flags** and the
reader's dictionary ensemble. It measures expanded words across the development
text, including unsplit words. The stage-specific scores and exact checkpoint,
reference and prediction hashes are in [evaluation.json](evaluation.json).

## Use the released components

Input uses DCS-style **IAST transliteration**. For example, the released
model expands `athātaḥ` to `atha` + `atas`, restoring the underlying word forms.
The checkpoints use Trankit's native adapter/head and MWT formats. The release
includes a small CPU loader for those components and uses the upstream
XLM-RoBERTa base encoder. It does not load the Language Engine application.

```python
from huggingface_hub import snapshot_download
import importlib.util
from pathlib import Path

root = Path(snapshot_download("conradcompagna/sanskrit-sandhi-tokenizer"))
spec = importlib.util.spec_from_file_location("released_model", root / "load_model.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
predict = module.load_model(root)
result = predict("yogas cittavṛttinirodhaḥ")
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

The underlying texts and annotations are from Oliver Hellwig's
[Digital Corpus of Sanskrit](https://github.com/OliverHellwig/sanskrit/tree/master/dcs/data),
2010–2024, distributed under CC BY 4.0. The task architecture is
[Trankit](https://github.com/nlp-uoregon/trankit), and the shared pretrained encoder
is [XLM-RoBERTa](https://huggingface.co/FacebookAI/xlm-roberta-base).
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Downloads

[Hugging Face model and files](https://huggingface.co/conradcompagna/sanskrit-sandhi-tokenizer) ·
[Complete GitHub ZIP](https://github.com/conradcompagna/language-engine/releases/download/models-2026-09-24/sanskrit-sandhi-tokenizer.zip)

The package contains the selected native weights, evaluation record, artifact
hashes, source credits and runtime requirements.

## Release terms

My original weights and accompanying code are available for research, education,
experimentation and evaluation under the [Model Evaluation License](LICENSE).
Commercial deployment or redistribution of those weights requires my permission.
Third-party assets retain the terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
