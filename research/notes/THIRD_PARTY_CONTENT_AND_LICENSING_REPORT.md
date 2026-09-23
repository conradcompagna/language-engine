# Third-party content and source provenance

Language Engine combines original application and research code with external
lexical resources, training corpora, model libraries, and browser components.
Provenance is recorded at the resource boundary so that software, data, and
generated artifacts can be inspected separately.

| Resource | Published record |
|---|---|
| Software dependencies and bundled notices | [Third-party notices](../../THIRD_PARTY_NOTICES.md), dependency manifests, and upstream notices alongside vendored assets |
| Dictionary and lexical sources | [Attribution inventory](../evaluation/reports/transparency_attribution_inventory.md) and [dictionary build chain](../pipeline/README.md#3-dictionaries) |
| NER corpora and label mapping | [Dataset cards](../datasets/README.md), [training configurations](../models/README.md), and [training record](../STATUS.md) |
| Included and external resources | [Publication contents](../../docs/PUBLICATION.md) and [setup](../../docs/SETUP.md) |

The maintained reader source is in [frontend/reader/](../../frontend/reader/),
with dictionary matching in [frontend/dictionary/](../../frontend/dictionary/).
PDF.js, Foliate, and Mammoth support the browser document workflows. Their
notices and licenses remain with their distributions.

SQLite hydration carries dictionary source fields into the
[display payload](HYDRATION_FIRST_RENDERING_REFERENCE.md). Corpus builders and
training records identify their inputs, transformations, and label policies.
Model weights and third-party corpora are provisioned separately from this
source release under their applicable upstream terms.

User-provided captures follow the access, storage, and isolation rules in the
[capture guide](../../docs/CAPTURES.md). Captured content and private operational
data are outside the published research archive.
