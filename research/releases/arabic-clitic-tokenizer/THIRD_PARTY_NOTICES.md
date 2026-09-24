# Third-party sources

## Trankit

Minh Van Nguyen, Viet Dac Lai, Amir Pouran Ben Veyseh and Thien Huu Nguyen.
*Trankit: A Light-Weight Transformer-based Toolkit for Multilingual Natural
Language Processing.* EACL 2021 System Demonstrations.
https://github.com/nlp-uoregon/trankit — Apache License 2.0.
Trankit's MWT implementation is adapted from Stanford Stanza.

## XLM-RoBERTa

Alexis Conneau et al. *Unsupervised Cross-lingual Representation Learning at Scale.*
ACL 2020. https://huggingface.co/FacebookAI/xlm-roberta-base — MIT license.
The base encoder is downloaded separately from its upstream publisher.

## CAMeL Tools and Arabic news text

CAMeL Lab. https://github.com/CAMeL-Lab/camel_tools — MIT-licensed software.
Teacher resources: calima-msa-r13 morphology database and MLE disambiguator;
the CAMeL data catalogue identifies their separate license as GPL v2:
https://github.com/CAMeL-Lab/camel-tools-data/blob/main/catalogue-1.5.json
Neither CAMeL software nor its teacher weights/databases are bundled.

Training text: Leipzig Corpora Collection, ara_news_2022 10K sample.
https://wortschatz.uni-leipzig.de/en/download/Arabic
The release contains trained task components, not the news corpus.
Changes to teacher supervision are documented in the corpus-building scripts.
