# Development experiments

These records show how model, data, and architecture choices developed into the
reading platform. Each `OUTCOME.md` connects a specific problem to the approach
tested, the retained result, and its relationship to the application.

| Development path | What it demonstrates |
|---|---|
| [Arabic morphology](arabic-cameltools/OUTCOME.md) | Comparing morphology-derived segmentation with the selected UD training path |
| [Shared ONNX encoder](arabic-onnx-adapter-bank/OUTCOME.md) | Prototyping adapter inputs and INT8 inference for a multilingual runtime |
| [Sanskrit supervision](sanskrit-vedic-v1/OUTCOME.md) | Moving from a Vedic UD experiment to DCS multi-word-token supervision |
| [Pooled language training](rarelangs-per-language/OUTCOME.md) | Recording the selected pooled run alongside per-language configurations |
| [FiNERweb taxonomy](finerweb-taxonomy-sweeps/OUTCOME.md) | Comparing clustering, weighting, and acceptance criteria for multilingual labels |
| [Amharic lexicon induction](amharic-lexicon-induction/OUTCOME.md) | A separate low-resource NLP study using embedding alignment and morphology |

Application build tools are maintained in [pipeline/](../pipeline/); these directories
preserve the development experiments and their original artifacts.
