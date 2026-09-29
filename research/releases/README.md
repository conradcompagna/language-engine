# Released research models

I trained these components for the linguistic problems encountered while building
Language Engine: Arabic clitic segmentation, Sanskrit sandhi splitting and
semantic annotation over authentic Sanskrit texts.

| Model | Research contribution | Model card and results |
|---|---|---|
| Arabic clitic tokenizer and MWT expander | CAMeL teacher annotations over real news text, systematic correction rules, transformer tokenization and learned expansion | [Read the model card](arabic-clitic-tokenizer/README.md) |
| Sanskrit sandhi tokenizer and MWT expander | DCS surface/underlying-word supervision that recovers word forms across sandhi boundaries | [Read the model card](sanskrit-sandhi-tokenizer/README.md) |
| Sanskrit interpretive NER | An 18-category semantic inventory trained from Gemini-assisted annotations of authentic DCS texts | [Read the model card](sanskrit-interpretive-ner/README.md) |

Each card links the trained weights on Hugging Face and a complete GitHub release
download. The native components run on CPU with the included loader. The
[complete component inventory and training scores](../models/TRAINING_RESULTS.md)
place these releases within the multilingual application.
