# Research and build infrastructure

Start with the [construction story and supporting evidence](../docs/BUILD_PROCESS.md)
for the selected artifacts and the process connecting them to the application.

This is the development record behind Language Engine: multilingual model training,
task-specific corpus construction, dictionary engineering, and inference optimization.
The guides connect implementation choices to the scripts, configurations, and recorded
outputs that produced them.

## Three paths through the work

1. **Build models for historical and low-resource languages.** Follow the
   [build chains](pipeline/README.md) from Sanskrit sandhi supervision and
   Gemini-assisted annotations over authentic texts to model training and application integration.
2. **Make multilingual inference practical to serve.** Follow the
   [runtime-artifact pipeline](pipeline/README.md#2-runtime-model-artefacts) through
   ONNX export, INT8 quantization, and session tuning, with
   [evaluation tools and measurements](evaluation/README.md).
3. **Turn heterogeneous dictionaries into one reading interface.** Follow the
   [dictionary pipeline](pipeline/README.md#3-dictionaries) through source conversion,
   language-specific normalization, lexical indexing, and batch hydration.

## Supporting records

| Directory | What to explore |
|---|---|
| [pipeline/](pipeline/) | Dataset builders, trainers, model conversion, and dictionary tooling |
| [models/](models/) | Scores for all 61 selected custom components, stock-model identities, and 29 retained NER run configurations |
| [datasets/](datasets/) | Corpus provenance, label inventories, and token counts |
| [evaluation/](evaluation/) | Regression harnesses, profiling tools, and recorded measurements |
| [experiments/](experiments/) | Design alternatives and the decisions that shaped the application |
| [notes/](notes/) | Development records for inference, lookup, rendering, and deployment |

[STATUS.md](STATUS.md) records the historical mapping between training runs and
application artifacts. The [application overview](../README.md) and
[architecture](../docs/BUILD_PROCESS.md#runtime-architecture) describe the reading platform itself.

## Construction records

Scripts identify the inputs, transformations and outputs at each stage.
Aggregate records, such as the [Sanskrit annotation run](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json),
make the scale, validation, and cost of the work inspectable.

The [evidence index](EVIDENCE.md) connects each research path to its data, training
configuration, and evaluation record. The [training procedure](REPRODUCIBILITY.md)
explains corpus validation, trainer configuration and artifact tracking.
