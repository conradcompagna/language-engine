# Multi-word tokens and source alignment

A written token can correspond to several linguistic words, as with French
`du` and the words `de` + `le`. The reader keeps both representations: a visible
surface span for document interaction and child analyses for morphology,
dictionary lookup, and dependency inspection.

## Backend representation

[trankit_mwt_expansion.py](../../trankit_mwt_expansion.py) adapts Trankit's expanded
words to surface tokens. It records expanded children and text, maps word IDs
to surface indexes, and selects a representative dependency edge. Additional
external child edges can be carried as `mwt_extra_edges`.

[pipeline_common.py](../../pipeline_common.py) builds `segments`,
`segment_offsets`, and the linguistic overlays used by the reader. Child data
travels with the parent through `mwt_parts`; document selection remains tied to
the original written surface. Derived child spans describe their alignment to
that surface, while the child's linguistic spelling remains available separately.

## Browser responsibilities

| Responsibility | Source |
|---|---|
| Child and lemma alignment inputs | [alignment-inputs.mjs](../../frontend/dictionary/client/alignment-inputs.mjs) |
| Dictionary surface alignment | [surface-alignment.mjs](../../frontend/dictionary/client/surface-alignment.mjs) |
| Child fill spans and payload assembly | [child-fill-slices.mjs](../../frontend/dictionary/client/child-fill-slices.mjs), [mwt-slices.mjs](../../frontend/dictionary/client/mwt-slices.mjs) |
| Reader child context and anchors | [mwt-context.mjs](../../frontend/reader/mwt-context.mjs), [mwt-anchors.mjs](../../frontend/reader/mwt-anchors.mjs) |
| Grammatical inspection | [grammar-popup.mjs](../../frontend/reader/grammar-popup.mjs), [token-map.mjs](../../frontend/reader/token-map.mjs) |

This division keeps linguistic word identity available during lexical matching
while letting the interface anchor its controls to the document's actual text.
[Realignment regressions](../evaluation/test_mwt_realign_dp.py) exercise the
dynamic-programming alignment. The [Sanskrit experiment record](../experiments/sanskrit-vedic-v1/OUTCOME.md)
connects this application feature to corpus construction and model training.
