# Hydration-First Rendering Reference

This document describes the refactored active dictionary rendering system in the hybrid SQLite architecture. It is written as a future maintenance reference, not a design pitch. The goal of the refactor was to stop the client from inventing or reconstructing dictionary row semantics late in the pipeline and to make Python hydration the single authoritative source of truth for what each popup row means.

## Core Principle

The system now treats every winner ref from compact-mode DP as an exact lookup handle into SQLite. A headword match and a form match are different refs. They are hydrated separately. Each hydrated row carries explicit row semantics. The JavaScript client is then responsible for wiring those rows back onto segments, filtering them, deduping them at the end, and rendering them. It is not supposed to infer what the headword should be, what the base should be, or whether a row is alternate by scanning unrelated fields.

In practical terms:

- Python decides what a row is.
- JavaScript displays what Python says the row is.
- Final dedupe is the only intended merge step in the active path.

## Active Pipeline

The active lookup chain is still:

1. Trankit or dp-only lookup produces segment text and NLP hints.
2. `dictionary_engine_hybrid.js` / `dictionary_client_hybrid.js` run compact-index DP and choose winner refs.
3. Winner refs are sent to `/js/hydrate`.
4. Python hydrates each exact ref from SQLite.
5. Python builds one explicit display payload per hydrated ref.
6. JavaScript attaches those hydrated rows back to the segment.
7. JavaScript performs final dedupe.
8. `reader_wikt.js` renders the explicit fields.

That means the active contract now depends on exact ref identity, not payload hashing or heuristic row reconstruction.

## Exact Identity Model

Compact-mode refs already had exact numeric SQLite identity before this refactor:

- headword ref: `storage_kind`, `db_alias`, `entry_row_id`
- form ref: `storage_kind`, `db_alias`, `entry_row_id`, `form_row_id`

The refactor keeps that model and leans into it harder.

In `router.py`, `/js/hydrate` now returns one payload row per exact ref. The `entry_store` is keyed by ref identity, and `ref_to_key` maps each winner ref wire key back to that same hydrated row key. The active route no longer interns or semantically merges hydrated rows before they reach the client.

Separate from ref identity, each hydrated row also carries a stable `runtime_entry_id` derived from the true SQLite entry row identity:

- `runtime_entry_id = storage_kind|db_alias|entry_row_id`

That field is used for final dedupe and debugging. It is not derived from payload content, so the old bug where headword-hit and form-hit variants of the same SQLite row received different synthetic identities is removed from the active hydrate path.

## The New Python Payload Builder

The most important change is in `router.py`. The active hydrate route now builds display rows through `_build_hydrated_display_payload()` instead of relying on the old fallback-heavy canonical payload behavior.

That builder produces explicit fields for each row:

- `runtime_entry_id`
- `ref_key`
- `match_kind`
- `display_headword`
- `lemma_headword`
- `display_reading`
- `entry_reading`
- `morph_info`
- `morph_base`
- `is_alternate_match`

It also passes through normal dictionary content like POS, glosses, forms, etymology, and related lists.

The key point is that these fields are now row-specific, not synthesized by scanning other unrelated row data.

## Headword-Match Path

For a headword match, hydration is intentionally boring:

- `display_headword` is the entry headword
- `lemma_headword` is the entry headword
- `display_reading` is the entry reading
- `entry_reading` is the entry reading
- `morph_info` is not invented
- `morph_base` is not invented
- `is_alternate_match` is false unless explicitly present in the row payload itself

In other words, headword rows are copied through directly. There is no late surface-switching logic anymore.

## Form-Match Path

For a form match, the builder overlays only the exact triggering form row and does not scan the rest of the entry to decide row meaning.

The form-match row is built as:

- `display_headword = matched form text`
- `lemma_headword = SQLite entry headword`
- `display_reading = matched form romanization if present, else entry reading`
- `entry_reading = entry reading`
- `morph_info = [exact triggering form tag bundle]`
- `morph_base = lemma_headword`
- `is_alternate_match = true` only if that exact triggering form tag bundle contains an alternate-bucket tag

This is the main architectural cleanup. The row now remembers the matched form explicitly. The client no longer has to guess whether the row should headline the surface or the lemma by comparing `surface_form !== headword`.

## Gemini Path

Gemini entries remain the only sanctioned fallback path for commentary/lemma-derived morph metadata.

For Gemini:

- `commentary -> morph_info`
- `lemma -> morph_base`

That fallback is now intentionally blocked to non-Gemini dictionary rows. This is important because earlier code paths were allowing commentary and lemma-like fields to leak into ordinary Wiktionary-style entries and affect rendering or alternate filtering.

## JavaScript Normalization After Refactor

`normalizeCanonicalEntryRuntime()` in `static/dictionary_client_hybrid.js` is now much narrower in purpose.

It still performs safe cleanup:

- pinyin conversion
- POS normalization
- sense hydration
- array/shape normalization
- alias wiring for compatibility

But it no longer fills non-Gemini `morph_info` or `morph_base` from commentary, lemma, or `_matched_forms`. That matters because those old fallbacks were effectively mutating row semantics in the browser after hydration.

The client can still create compatibility aliases like `headword = display_headword`, but it is no longer constructing dictionary meaning from multiple sources.

## Final Dedupe Rules

Final dedupe now happens in `dedupeEntriesByIdentity()` and only after all hydrated rows for the token are present.

The dedupe base is `runtime_entry_id`.

Rules:

1. If a headword row exists for a given `runtime_entry_id`, it wins.
2. Same-text form rows for that same entry may merge their `morph_info` into the surviving headword row.
3. Different-text form rows do not merge into the headword row.
4. If there is no headword row, form rows only merge when they have the same displayed headword text.
5. Form rows for the same entry with different displayed matched forms remain separate rows.

This is the intended semantic merge step. It is late, explicit, and limited.

## Alternate Bucket Behavior

Alternate filtering was one of the main bug sources before the refactor because the code was scanning too many places:

- `entry.morph_info`
- `_matched_forms`
- commentary
- forms arrays
- synthetic merged bundles

That is no longer how the active path works.

The alternate bucket now depends on one explicit field only:

- `is_alternate_match`

That field is computed in Python from the exact triggering form row’s tag bundle. A headword row is not demoted just because some other form row on the same entry happens to carry `redirect` or `alternative`.

This directly fixes the class of bug where a token like `は` could be treated as redirect/alternative because alternate-like tags existed somewhere else in the entry’s broader form inventory.

## Renderer Contract

`reader_wikt.js` now renders row semantics from explicit payload fields instead of reconstructing them late.

The main rendering contract is:

- row headline: `display_headword`
- row reading: `display_reading`
- base line: `morph_base` / `lemma_headword`
- morph line: `morph_info`
- alternate bucketing: `is_alternate_match`

The renderer no longer invents a `Base:` line from `head !== text`, and it no longer decides that something is a surface row only because `base_headword !== row_headword`. It uses the explicit `is_form_match` flag carried through the grouped row object.

## Fill Rows and Segment-Level Objects

One subtle but important part of the cleanup is that segment-level and fill-row objects now also carry the explicit display/base fields through instead of re-deriving them from `headword`.

The helper `applyFillRepresentativeEntry()` now copies:

- `runtime_entry_id`
- `ref_key`
- `display_headword`
- `lemma_headword`
- `display_reading`
- `match_kind`
- `morph_info`
- `morph_base`
- `is_alternate_match`

That matters because even if popup row rendering is correct, side-panel state and fill-row state will drift if those intermediate objects still treat `headword` as “the lemma” in some places and “the displayed form” in others.

## What the Client No Longer Does

The active client path no longer:

- performs pre-dedupe semantic aggregation of hydrated form rows
- scans unrelated `_matched_forms` bundles to build row morph display
- builds alternate status from commentary or general form inventories
- decides late whether to show surface vs lemma by checking field equality
- builds composite `morph_base` for non-Gemini rows

Dead helper blocks related to pre-dedupe hydrated-form aggregation were also removed from the active client file to reduce confusion.

## Maintenance Guidance

If a future bug appears, the first debugging question should be:

"What exact hydrated row did Python emit for this ref?"

Not:

"What did the renderer infer from mixed fields?"

That is the intended architecture now. If a form row is showing the wrong headline, wrong reading, wrong base, wrong morph tags, or wrong alternate status, the bug should usually be traced to one of three places:

1. the compact ref selection
2. SQLite hydration of that exact ref
3. `_build_hydrated_display_payload()` in Python

The JavaScript side should mostly be suspected only for final dedupe, filtering, or plain display wiring.

That is the entire point of the overhaul: the system is supposed to display dictionary entries, not reinterpret them on the fly.
