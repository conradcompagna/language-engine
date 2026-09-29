# Experiments

Development experiments for Language Engine. Each folder holds the scripts and logs
of one line of work and a README describing what was tried and what was adopted.
Maintained build code is in [`../pipeline/`](../pipeline/).

| Folder | Subject | Outcome |
|---|---|---|
| [arabic-cameltools/](arabic-cameltools/) | CAMeL Tools morphology as supervision for Arabic segmentation | Superseded by the corrected teacher-data build in `pipeline/datasets/arabic/` |
| [arabic-onnx-adapter-bank/](arabic-onnx-adapter-bank/) | One shared ONNX encoder with language adapters supplied as inputs | Adopted in the production CPU runtime |
| [sanskrit-vedic-v1/](sanskrit-vedic-v1/) | Sanskrit models trained on the Vedic UD treebank | Superseded by Digital Corpus of Sanskrit (DCS) training |
| [rarelangs-per-language/](rarelangs-per-language/) | Pooled versus per-language training for low-resource languages | Pooled run used for Bengali and Punjabi |
| [finerweb-taxonomy-sweeps/](finerweb-taxonomy-sweeps/) | Parameter sweeps for deriving coarse NER label sets from FiNERweb | Informed the schemes in `pipeline/taxonomy/` |
| [amharic-lexicon-induction/](amharic-lexicon-induction/) | Inducing an Amharic–English dictionary from monolingual corpora | Not used in the application |
