---
license: other
license_name: conrad-compagna-model-evaluation-1.0
license_link: LICENSE
language:
- sa
library_name: pytorch
tags:
- trankit
- named-entity-recognition
- semantic-annotation
- sanskrit
- llm-annotation
inference: false
---

# Sanskrit Interpretive Named-Entity Recognition

I built this model to identify the people, substances, practices and concepts
discussed in authentic Sanskrit texts. It extends named-entity recognition into
an **18-category semantic inventory** designed for close reading and corpus
analysis, and supplies the Sanskrit NER stage of [Language Engine](https://github.com/conradcompagna/language-engine).

**The source texts are real DCS documents; Gemini generated the annotations.**
I used the corpus to define a useful interpretive task, validated the returned
tokens, applied recorded annotation corrections, and trained a compact
XLM-R/Trankit adapter and sequence-labelling head on the resulting corpus.

## Semantic inventory

ANIMAL, ASTRO, BODY, CONCEPT, DEITY, DISEASE, FOOD, GROUP, MEASURE, MEDICINE,
PERSON, PLACE, PLANT, PROCEDURE, RITUAL, SUBSTANCE, TEXT and TOOL.

The saved vocabulary has 73 BIOES labels: four boundary labels for each of the
18 categories, plus `O`. This supports semantic analysis of Sanskrit literature
alongside conventional person and place recognition.

## Corpus and training

I prepared ten-sentence annotation jobs from DCS corpus text, called
`gemini-2.5-flash-lite`, and checked returned token sequences against the inputs.
The final build combines 1,765 usable chunks from 1,800 scheduled chunks,
131,507 token rows, 43,622 non-`O` annotation rows and 237 recorded fixes.
The selected run is
`san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5`, using the
corrected annotations and a 95/5 development split.

The checkpoint records **54.28% development entity F1**, selected at stored
epoch 29. This is exact-span entity F1 against the retained Gemini-assisted
reference annotations. The evaluation uses the same 18-category semantic inventory described above.

## Use the released components

Input is one already-tokenized Sanskrit sentence in IAST transliteration; the NER release preserves the supplied token sequence.
The checkpoint uses Trankit's native adapter/head format and the supplied BIOES vocabulary. The release
includes a small CPU loader for those components and uses the upstream
XLM-RoBERTa base encoder. It does not load the Language Engine application.

```python
from huggingface_hub import snapshot_download
import importlib.util
from pathlib import Path

root = Path(snapshot_download("conradcompagna/sanskrit-interpretive-ner"))
spec = importlib.util.spec_from_file_location("released_model", root / "load_model.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
predict = module.load_model(root)
result = predict(["yogas", "cittavṛttinirodhaḥ"])
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

Source texts: Oliver Hellwig, [Digital Corpus of Sanskrit](https://github.com/OliverHellwig/sanskrit/tree/master/dcs/data),
2010–2024 (CC BY 4.0). Annotation assistance: Google Gemini 2.5 Flash Lite.
Architecture: [Trankit](https://github.com/nlp-uoregon/trankit), Nguyen et al.,
EACL 2021. Base encoder: [XLM-RoBERTa](https://huggingface.co/FacebookAI/xlm-roberta-base),
Conneau et al. Corpus preparation, annotation workflow, corrections, task design
and model training: Conrad Compagna.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Downloads

[Hugging Face model and files](https://huggingface.co/conradcompagna/sanskrit-interpretive-ner) ·
[Complete GitHub ZIP](https://github.com/conradcompagna/language-engine/releases/download/models-2026-09-24/sanskrit-interpretive-ner.zip)

The package contains the selected native weights, evaluation record, artifact
hashes, source credits and runtime requirements.

## Release terms

My original weights and accompanying code are available for research, education,
experimentation and evaluation under the [Model Evaluation License](LICENSE).
Commercial deployment or redistribution of those weights requires my permission.
Third-party assets retain the terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
