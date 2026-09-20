# Repository contents

## Included

**Runtime.** The Flask/JavaScript application, language configurations, neural
inference and dictionary lookup infrastructure, and deployment templates. This is
everything at the repository root.

**Build infrastructure.** Under [`research/`](../research/): the code that produced the
models, datasets and dictionaries the runtime loads; the evaluation and audits that
gated them; the experiments that did not ship; and design notes. Under
[`extras/`](../extras/): two standalone applications.

## Not included, and why

| Excluded | Reason |
|---|---|
| Model weights (`.mdl`, `.pt`, ONNX bundles) | Large binaries; several derive from licensed corpora. The training configuration and label vocabulary for every run are published in `research/models/`. |
| Dictionary databases (42 SQLite files) | Third-party lexical content under its own licences. The converters and importers that build them are published in `research/pipeline/dictionaries/`. |
| Training corpora (CoNLL-U treebanks, BIO corpora, n-gram tables) | Third-party datasets with their own terms. Dataset cards recording size, labels and provenance are published in `research/datasets/`. |
| The Sanskrit synthetic NER corpus | The product of the annotation run. Its construction, validation, cost, tag distribution and per-wave logs are published; the corpus itself is not. |
| Per-job artefacts of large annotation runs | 1,852 jobs produced roughly 19,000 intermediate files. A representative sample plus an aggregate record of the volume is published instead: `research/pipeline/datasets/sanskrit/gemini_ner/`. |
| Account and subscription records, customer documents, analytics | Personal data. |
| Live environment files, credentials, keys, logs, caches, backups | Operational. |

The intent is that the process is fully legible and the products are not redistributed.
Every script names its inputs; the datasets and dictionaries are obtainable from their
original sources.

Configuration examples require your own settings. Third-party notices are preserved in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

The GitHub code is maintained separately from the deployed sites and original
development workspaces. See [setup](SETUP.md) for required resources and launch
instructions.
