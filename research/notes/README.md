# Design and implementation guides

Start with the [application architecture](../../docs/BUILD_PROCESS.md#runtime-architecture). These
guides explain the engineering decisions behind inference, lexical search,
document interaction, and classical-language support, with links to their
implementation and research evidence.

| Guide | What it explains |
|---|---|
| [Multilingual inference and lexical search](NLP_HUB_CONSTRUCTION_REPORT.md) | Model integration, compact indexes, and batched hydration |
| [Dictionary hydration contract](HYDRATION_FIRST_RENDERING_REFERENCE.md) | Exact identity, matched forms, morphology, and provenance |
| [Dictionary rendering](RENDERING_ARCHITECTURE.md) | Popup, side-panel, and annotation responsibilities |
| [Document loading and lookup](LOOKUP_RENDERING_PIPELINE_MAP.md) | Source formats, geometry, selection, and shared lookup flow |
| [Multi-word tokens](MWT_SYSTEM.md) | Surface spans, expanded words, and dictionary alignment |
| [Latin and Ancient Greek](LATIN_GREEK_PIPELINE.md) | Lexical construction, inflectional resources, normalization, and NER |
| [Trankit inference internals](TRANKIT_INTERNALS_PRODUCTION_INFERENCE_REPORT.md) | Tokenization, tagging, lemmatization, and model execution |
| [Trankit implementation notes](trankit_internals_notes.md) | Pipeline components and linguistic feature design |
| [Deployment, authentication, and billing](DEPLOYMENT_AUTH_BILLING.md) | Application services and deployment configuration |
| [Third-party content and licensing](THIRD_PARTY_CONTENT_AND_LICENSING_REPORT.md) | Source attribution and content provenance |

[Research results](../EVIDENCE.md) connect these design choices to corpus
construction, model training, and recorded measurements.
