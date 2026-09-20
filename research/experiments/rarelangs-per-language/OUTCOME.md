# Per-language rare-language splits — abandoned

## What was tried

The rare-language batch covers Akkadian, Amharic, Assamese, Bengali, Coptic, Egyptian,
Georgian, Marathi, Middle French, Old East Slavic, Old Japanese, Prakrit and Punjabi —
UD treebanks that are individually too small to train a usable model. The pooled run
`trankit_save_rarelangs_v1` trains on all of them together.

Six per-language splits were then attempted, to see whether a single language could be
fine-tuned out of the pool: `v1as` (Assamese), `v1bn` (Bengali), `v1mr` (Marathi),
`v1ojp` (Old Japanese), `v1pa` (Punjabi), `v1pkt` (Prakrit).

## What happened

None produced model weights, and none produced a training log — they stopped before
training began. The individual treebanks are too small to train against directly, which
is the reason for pooling in the first place.

## What shipped

The pooled run, which produced the deployed `bengali-custom` and `punjabi-custom`
models. `research/pipeline/datasets/process_rarelangs.py` builds the pooled dataset.

This directory holds no files beyond this note; the six run directories contain only
empty output trees. It exists so that the six names are accounted for rather than
silently absent.
