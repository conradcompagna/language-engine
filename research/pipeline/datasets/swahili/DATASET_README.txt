Swahili dataset rebuilt from SWH_UDT-main.zip

Files:
- swahili_ud_train_big.conllu
- swahili_ud_dev_big.conllu

Construction:
- Included every sentence with complete HEAD+DEPREL annotation.
- Deduplicated overlapping human files.
- Human-annotated material kept separate from silver auto-annotation for dev.
- Dev contains only human-annotated sentences.
- Train = remaining human complete sentences + all unique complete auto-annotated sentences.

Counts:
- unique human complete sentences: 243
- unique human complete tokens: 4193
- unique auto complete sentences used: 4519
- unique auto complete tokens used: 50137
- train sentences: 4737
- train tokens: 53925
- dev sentences: 25
- dev tokens: 405

Notes:
- Autoanno/filtered_after_rule_anno.conllu and Autoanno/missing_deps.conllu are byte-identical in this archive, so only one copy was used.
- This is not an official UD release. Most of the size comes from silver auto-annotation.
