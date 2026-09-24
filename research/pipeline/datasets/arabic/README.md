# Arabic teacher-supervised segmentation

I used CAMeL Tools to annotate authentic Arabic news sentences, converted the
surface/expansion pairs into CoNLL-U, corrected recurring morphological-analysis
errors and trained the tokenizer/MWT components selected in `t_ar10k2`.

- `build_cameltools_tokenizer_dataset.py` is the original corpus builder: 10K
  `ara_news_2022` text, `calima-msa-r13` MLE teacher, `atbtok`, 95/5 split.
- `fix_conllu.py` records the correction rules for false proper-name and nisba
  splits, truncated expansions, NOAN output and preposition/suffix forms.

These original programs preserve the working training-folder layout and input
filenames. The [selected training results](../../../models/TRAINING_RESULTS.md)
connect their corrected supervision to the deployed checkpoint scores.
The teacher resources and source news corpus retain their upstream terms.
