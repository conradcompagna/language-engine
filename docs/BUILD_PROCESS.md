# From linguistic resources to Language Engine

Language Engine grew from two connected problems: obtaining useful linguistic
analysis across modern and historical languages, and making that analysis usable
inside a document reader. I developed the model preparation, dictionary conversion,
CPU inference and browser interaction as parts of the same system.

For a short route through the evidence, read the [selected model map](../research/STATUS.md),
the [training results](../research/models/README.md#selected-training-results), and
the [request architecture](ARCHITECTURE.md). The
[artifact record](../research/models/deployed_artifacts.json) identifies the model
files checked against production on 23 September 2026 without distributing weights.

## 1. Construct language-appropriate supervision

The model collection combines existing Trankit resources with components trained
for particular corpora and tasks. Selection happens at component level: a language
can use a tokenizer from one run, a tagger/lemmatizer from another, and a separately
trained NER adapter. The shared model-store directory name is not a language list.

| Construction problem | Transformation and evidence |
|---|---|
| Sanskrit sandhi | [DCS full-corpus builder](../research/pipeline/datasets/build_dcs_trankit_full_dataset.py) preserves fused surface tokens and underlying MWT children; the [subset builder](../research/pipeline/datasets/build_dcs_trankit_mwt_subset.py) concentrates training on MWT-bearing chapters. |
| Sanskrit entity supervision | The [validated annotation runner](../research/pipeline/datasets/sanskrit/gemini_sanskrit_ner_batch_runner.py) checks returned tokens, saves usage and resumes completed jobs; the [final builder](../research/pipeline/datasets/sanskrit/build_final_sanskrit_gemini_ner_dataset.py) combines validated BIO output and recorded corrections. |
| Historical-language NER | [Old English OEDT](../research/datasets/ang_oedt/README.md) and [Ancient Greek Pausanias](../research/datasets/grc_pausanias_ethnic_civic_misc/README.md) document corpus conversion and task-specific label decisions. |
| Multilingual label inventories | [Taxonomy construction](../research/pipeline/taxonomy/) and [dataset builders](../research/pipeline/taxonomy/dataset_builders/) connect label embeddings, co-occurrence clustering and candidate schemes to training data. |
| Source-specific splits | [Dataset cards](../research/datasets/README.md), per-run configurations and the [evidence index](../research/EVIDENCE.md) record the source, label scheme and split used by each published example. |

The DCS subset records seed 1337, 1,309 training chapters and 146 development
chapters, producing 70,355 training sentences and 9,349 development sentences.
The Sanskrit NER annotation record contains 1,852 API jobs; its final corpus
summary records 1,765 usable chunks, 131,507 token rows and 237 recorded fixes.
These are construction measurements; model evaluation is recorded separately.

## 2. Train, compare and select components

[train_ner.py](../research/pipeline/models/train_ner.py) validates BIO inputs,
drives Trankit training and preserves run evidence and finished artifacts.
[TRAINING_RUN.md](../research/pipeline/models/TRAINING_RUN.md) gives its input,
environment and output contract. The [model collection](../research/models/)
retains configurations and label vocabularies for 29 finished NER runs.

The [selection table](../research/STATUS.md) connects the active language aliases
to the retained work. Examples include Arabic's separate tokenizer/MWT and
tagger/lemma choices, Tagalog's v1/v2 combination, and Sanskrit's DCS components
plus its corrected supervised NER run. Four selected NER examples have published
best-development scores: Old English 88.20 F1, Ancient Greek 78.81, Sanskrit 54.28
and Vietnamese 91.72, each on its own labels and split; the
[saved score excerpts](../research/evaluation/results/selected_ner_training.json)
preserve their source-log hashes and selected epochs.

The artifact inventory distinguishes three facts: a file is provisioned, it is
selected by the registry, and it matches a retained training output. Those facts
are recorded separately so a cached upstream model is not counted as custom training.
Historical source-run identification remains recorded only where supported by the
retained files; every listed deployment asset nevertheless has a SHA-256 identity.

## 3. Package inference for CPU deployment

```mermaid
flowchart TB
    Data["Prepared corpora and task labels"] --> Train["Train and compare components"]
    Train --> Select["Select checkpoints per language and task"]
    Select --> Export["Shared XLM-R graph and adapter export"]
    Export --> Quant["INT8 encoder and adapter packs"]
    Select --> Heads["PyTorch task heads, lemma and MWT"]
    Quant --> Runtime["CPU inference runtime"]
    Heads --> Runtime
```

The deployed bundle uses one shared dynamic-INT8 ONNX encoder with language/task
adapter inputs, rather than an independent full encoder per language. The measured
encoder is **278,515,512 bytes**, compared with **1,110,086,874 bytes** recorded for
the floating-point export: approximately **75% smaller**. The bundle contains 96
adapter packs; its 34 stored aliases include historical resources beyond the 27
current language IDs and Traditional Chinese override.

The [bundle builder](../research/pipeline/models/build_trankit_compressed_runtime_artifacts.py),
[compressed runtime](../trankit_compressed_runtime.py), and
[live-switch integration](../trankit_onnx_live_switch.py) show the export/load path.
The loader also dynamically quantizes supported PyTorch task modules. The
[ORT measurements](../research/evaluation/README.md#onnx-session-tuning) compare
session settings within the INT8 runtime; the file-size result above measures
compression, not a before/after linguistic-accuracy comparison.

## 4. Engineer the dictionaries

The 42 provisioned SQLite files bring heterogeneous lexical resources into a
shared entry/form schema. [Source converters](../research/pipeline/dictionaries/)
handle Wiktionary/Kaikki, JMdict, KRDict, CC-CEDICT, Chinese Notes, LSJ and
Bosworth–Toller, followed by source-specific repairs and
[dictionary audits](../research/evaluation/reports/).

### Reconstructing Sanskrit inflection lookup from DCS

The selected Sanskrit dictionary is built from **Digital Corpus of Sanskrit**
data. [build_sa_sqlite.py](../research/pipeline/datasets/sanskrit/build_sa_sqlite.py)
joins the lemma catalog to token-level `LemmaId` references, interprets grammar
codes and morphological features, and collects observed surface and unsandhied forms.
It then removes headword duplicates and deduplicates the resulting form records.
The verified local build contains **180,000 entries and 479,041 forms**.

A simplified join illustrates the mechanism: a catalog entry with lemma ID `42`
and a corpus token carrying `LemmaId=42` become an entry and an associated form;
the token's case/number features travel with the form. The IDs here are synthetic.
The resulting inflection inventory consists of attested corpus forms, which makes
it useful for recognizing text while retaining its lexical provenance.

The older Monier-Williams conversion is another retained dictionary-development
path; it should not be confused with this selected DCS SQLite build.

### Preserve source databases; derive the browser index

[dict_lookup_sqlite.py](../dict_lookup_sqlite.py) opens dictionaries read-only.
[sqlite_prune_policy.py](../sqlite_prune_policy.py) filters and collapses records
when deriving lookup material, preserving the provisioned source databases during
normal runtime. This separates source preservation from the reader's display policy.

The compact index carries lookup keys and stable database/row references. The
browser [dictionary engine](../frontend/dictionary/engine/) uses those records,
neural lemmas and morphology for candidate selection and segmentation; the
[client](../frontend/dictionary/client/) deduplicates winning references and requests
full records in batches. SQLite hydration returns definitions, matching forms and
provenance only after selection. Shared key normalization keeps both sides aligned.

## 5. Connect analysis to the reading product

Document rendering preserves the page or passage while the selected text passes
through [universal normalization](../universal_normalization.py), the
[language registry](../language_registry.py) and
[surface/token alignment](../pipeline_common.py). Browser overlays reconnect the
NLP and dictionary results to the original selection.

[Gemini services](../language_engine/gemini/README.md) form a separate request
branch for contextual glosses, entry generation, translation, entities and semantic
decomposition. Their modules preserve prompt construction, response schemas and
usage handling. [Authentication](../auth.py), [billing](../payments.py), quotas,
document capture and persistence make these services part of a deployed application.

## Reconstruction checklist

| Step | Public material | Separately supplied input / result |
|---|---|---|
| Inspect product mechanics | [Fixture demo and setup](SETUP.md), [browser source](../frontend/README.md), [tests](../tests/) | Synthetic fixtures run without private models or dictionaries. |
| Reconstruct supervision | Dataset cards, corpus builders, annotation validators, split summaries | Obtain the relevant source revision and rights; supply corpora or authorized annotation input. |
| Train selected tasks | Run configurations, trainer, vocabularies, saved evaluation excerpts | Training environment and corpus files; preserve input hashes, seeds and selected outputs. |
| Rebuild dictionaries | Source converters, DCS join, repair/audit scripts | Authorized lexical sources; output the common SQLite entry/form schema. |
| Export CPU assets | Encoder/bundle builders and ORT tuning tools | Selected checkpoints and export dependencies; compare against the artifact inventory when using the original assets. |
| Assemble an instance | [Runtime architecture](ARCHITECTURE.md), [resource paths](SETUP.md), deployment templates | Model store, compressed bundle, SQLite files, new account database and your own service credentials. |
| Verify behavior | [Development commands](DEVELOPMENT.md), fixture tests, lexical/alignment checks and evaluation tools | Real-data evaluations use their own documented corpora and splits. |

The [reproduction guide](../research/REPRODUCIBILITY.md) supplies runnable public
checks and trainer commands. Historical one-off builders retain their original
input assumptions; adapt those paths in a separate workspace. The public record
provides code, configurations, selected results and artifact identities while
weights, complete dictionaries and training corpora remain separately provisioned.
