# FiNERweb label taxonomy — parameter sweeps

## The problem

FiNERweb's fine-grained entity labels are too numerous and too unevenly populated to
train against directly. A coarse label set is needed. Imposing a standard one (PER/LOC/
ORG/MISC) throws away most of what the data distinguishes, and for the historical and
non-European languages in this project those four categories are a poor fit.

So the coarse set was derived from the label inventory itself: embed the label strings,
find which labels co-occur and cluster together, and cut the hierarchy where the
clusters stay internally coherent.

## What is in here

Roughly eighty scripts, each a variant of that procedure:

- **clustering method** — centroid, pairwise-edge, online, snowball (inductive and
  recursive), chain-merge
- **weighting** — unweighted, frequency-weighted, parent-weighted, candidate-weight
  gated
- **acceptance criterion** — internal coherence at 70/79/80/84/85/89/90, cluster purity
  at 90, member purity at 90, nearest-neighbour cutoff at 50 with and without damping
- **seeding** — manual seed regions, ontology seeds, child-seeded, full-label,
  original-label, user-grouped 50/50
- **special cases** — whether to split a "cultural reference" bucket, whether to drop
  low-frequency legal and award/sport labels, threshold filters at 50/60/75/90

Plus the audit scripts that checked each grouping against the text, and the report
writers that produced the threshold ladders used to compare them.

## Outcome

The selected method is in `research/pipeline/taxonomy/`: fastText label
embeddings, Louvain community detection over label co-occurrence, centroid clustering
with a frequency-weighted internal-coherence gate at 90. The dataset builders for the
chosen schemes are in `research/pipeline/taxonomy/dataset_builders/`, and the resulting
models are recorded in `research/models/` — the `vie_*` and `san_*` families are
comparisons between selected label schemes.

## A note on method

The experiment varies clustering, weighting, seeding, and acceptance thresholds
explicitly, with audit scripts and reports retained alongside the variants. This
makes the selected taxonomy traceable to its design criteria and provides a basis
for comparing downstream NER models trained with different label schemes.
