# Language-specific Trankit integration

The reader adapts a shared Trankit pipeline to the linguistic and orthographic
requirements of its supported languages. Integration code lives in
[language_registry.py](../../language_registry.py) and
[trankit_mwt_expansion.py](../../trankit_mwt_expansion.py), keeping application
policy alongside the registry and alignment adapters.

## Implemented integration points

| Concern | Implementation |
|---|---|
| Model and display selection | Registry entries connect language codes, model names, treebank settings, and display configurations. |
| Multi-word-token decoding | `set_mwt_decoding_headroom()` configures a 400-character decoding limit and an explicit beam setting at initialization. |
| Lemmatization policy | Registry flags select identity-lemma behavior where configured; dictionary-first handling separates cached predictions from model misses. |
| Sentence boundaries | Treebank-specific punctuation mappings adapt input to tokenizer training conventions. |
| Long input handling | Tokenizer/chunking hooks account for model input limits and punctuation boundaries. |
| Entity recognition | Custom NER routing combines language-specific supervision with the shared inference pipeline. |

[Multi-word-token alignment](MWT_SYSTEM.md) connects expanded words to visible
source spans. [Corpus and model build chains](../pipeline/README.md) explain
the supervision behind Sanskrit and other language integrations.

## Inference engineering

The [inference report](TRANKIT_INTERNALS_PRODUCTION_INFERENCE_REPORT.md) records
the shared ONNX encoder, adapter packs, dictionary-first execution, and stage
costs examined during optimization. [Recorded session measurements](../evaluation/README.md#onnx-session-tuning)
compare runtime settings on a fixed input, with annotation fingerprints
connecting timing measurements to the resulting analyses.
