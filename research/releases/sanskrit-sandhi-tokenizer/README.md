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

A Sanskrit tokenizer and sandhi expander that recovers the underlying words from
fused surface forms, used for Sanskrit in
[Language Engine](https://github.com/conradcompagna/language-engine).

Training data is the **Digital Corpus of Sanskrit (DCS)**, which records both the fused
surface token and its underlying words. The tokenizer learns word boundaries and which
tokens need expansion; a character-level sequence-to-sequence model recovers the
underlying forms, including the sound changes at sandhi boundaries.

## Training

The dataset builder walks DCS chapters in corpus order and preserves CoNLL-U
multiword-token range rows instead of flattening away the fused forms. I used
the surface forms as tokenizer input and the annotated underlying words as
expansion targets. The development data spans 1,590 DCS chapters.

The tokenizer and expander come from run `trankit_save_sa_dcs_v1`. Language Engine
loads them under the model name `sanskrit-vedic`, which is a leftover from an earlier
Vedic-treebank experiment; these components were trained on DCS.

## Evaluation

| Development measure | Score |
|---|---:|
| Surface-token F1, selected tokenizer checkpoint | 97.09% |
| Sentence-boundary F1, selected tokenizer checkpoint | 79.39% |
| Expanded-word F1, selected MWT checkpoint with reference boundaries | 93.91% |

The tokenizer scores come from the historical evaluation at stored checkpoint
epoch 20. The expander was re-evaluated on 24 September 2026 on the DCS development
data: 73,807 sentences with 97,960 expansion candidates across 1,590 chapters.

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
native training checkpoints; Language Engine serves them through a shared INT8 ONNX
encoder, built by [these scripts](https://github.com/conradcompagna/language-engine/tree/main/research/pipeline/models).

## Artifact and source record

[artifact-manifest.json](artifact-manifest.json) records checkpoint sizes and
SHA-256 identities; [evaluation.json](evaluation.json) records the evaluation
source, split and scores. Scores for every Language Engine component are in the
[model record](https://github.com/conradcompagna/language-engine/blob/main/research/models/README.md).

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
