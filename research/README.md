# Research and build infrastructure

Everything in this directory is **offline work**. None of it runs in production. It is
the record of how the models, dictionaries and datasets that Language Engine loads at
runtime were actually built, evaluated, and in many cases abandoned.

The deployed application is at the repository root. If you only want to see what the
service does, stop at the root [README](../README.md) and do not read further.

## Layout

| Directory | Contents |
|---|---|
| [`pipeline/`](pipeline/) | Code that produced something the runtime loads. See [pipeline/README.md](pipeline/README.md) for the end-to-end build chains. |
| [`evaluation/`](evaluation/) | Regression tests, benchmarks, latency measurements, and the dictionary/corpus audit reports. |
| [`experiments/`](experiments/) | Work that did not ship. Each subdirectory has an `OUTCOME.md` stating what was tried and why it was dropped. |
| [`notes/`](notes/) | Architecture and design documents written during development. |
| [`datasets/`](datasets/) | Dataset cards: label inventories, token counts, provenance. No corpora. |
| [`models/`](models/) | Training configuration and label vocabulary for every finished model run. No weights. |

## Which runs shipped

[`STATUS.md`](STATUS.md) labels every training run **Shipped**, **Superseded** or
**Abandoned**, and gives the evidence for each label. The labels are not a judgement
call: [`tools/check_provenance.py`](tools/check_provenance.py) compares the byte size
of every artefact each run produced against the models the deployed service loads, and
regenerates the table. Run it yourself against a model store to reproduce the result.

This matters because the directory names are unreliable. The deployed `sanskrit-vedic`
model was not produced by `trankit_save_sa_vedic_v1`; it came from the DCS run. The
deployed Tagalog model is `tgl_v1`'s tagger and lemmatiser combined with `tgl_v2`'s
multi-word-token expander. Ten Arabic runs produced nothing that ships.

## What is deliberately not here

Model weights, dictionary databases, training corpora, and the per-job outputs of
large annotation runs. The scripts that build them are here; the products are not.
Where a run produced tens of thousands of intermediate files, an aggregate record of
that volume is published instead of the files — see
[`pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json`](pipeline/datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json).

Most scripts here expect input paths that existed on the development machine. They are
published as a record of method, not as a turnkey pipeline. Each one names its inputs
and outputs at the top.
