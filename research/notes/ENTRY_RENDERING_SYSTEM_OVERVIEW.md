# Entry Rendering System Overview

This document explains the active dictionary entry rendering path in the hybrid stack. It is intentionally blunt. The system is not conceptually impossible, but it is more convoluted than it should be, and several bugs come from the same basic problem: the code does not keep a strict separation between "the token the user selected", "the dictionary entry's own headword", and "the form row that caused the entry to match".

The active files are:

- `static/dictionary_client_hybrid.js`
- `static/reader_wikt.js`
- `router.py`
- `dict_lookup_sqlite.py`

Everything else is either backup code or from an older architecture and should be ignored unless you are doing archaeology.

## 1. The short version

The current active pipeline has these stages:

1. The client intercepts `/lookup` or `/lookup_dp_only`.
2. The client runs segmentation and dictionary matching against a compact in-browser index.
3. The client sends winner refs to `/js/hydrate`.
4. The server loads full SQLite entries and form rows.
5. The server canonicalizes those hydrated entries into `entry_store`.
6. The client rehydrates local lookup stubs from `entry_store`.
7. The client normalizes fields like `surface_form`, `morph_base`, and `morph_info`.
8. The client splits entries into "shown" and "other definitions".
9. The client builds `entry_groups`.
10. `reader_wikt.js` renders the final HTML.

That means the visible popup row is not produced in one place. It is assembled incrementally across both Python and JavaScript.

This is the main reason bugs feel confusing: the display row you see is the end result of several layers mutating the same conceptual entry.

## 2. The key fields and what they are supposed to mean

These are the fields that matter most.

### `headword`

This is supposed to be the dictionary entry's own title. For a true lemma entry, this is the real entry head.

### `surface_form`

This is supposed to be the actual text that matched the user's token. In other words, this is the selected surface spelling, not the dictionary's preferred headword.

### `morph_base`

This is what the renderer shows on the `Base:` line. In practice it is being used as "canonical base" or "lemma base", but it is not guaranteed to come from one source. Sometimes it comes from the entry itself, sometimes it is inferred from the matched form path.

### `morph_info`

This is what the renderer shows on the `Morph:` line. It is not a pure morphological feature set. It is really a bag of tags collected from whatever source happened to supply them. That can include form-row tags like `canonical`, `alternative`, and `redirect`.

### `_matched_forms`

This is the most important low-level field for understanding the bugs. It holds the actual form rows that matched. Each matched form can carry:

- `form_text`
- `display_text`
- `form_roman`
- `tags`
- `index_keys`

Those `tags` are where things like `redirect`, `alternative`, and `canonical` come from in the active lookup path.

### `_match_kind` and `_match_source`

These are used to mark whether the hit was found through the headword index or the form index. The system relies on this distinction more than it should. A lot of visible behavior changes based on whether an entry is still marked as a form hit by the time it reaches rendering.

## 3. The active flow from lookup to popup

### Stage A: fetch interception

`wrapFetch()` in `static/dictionary_client_hybrid.js` intercepts the dictionary calls. For normal reading lookups it routes into `hybridSegmentAndHydrate()`. For panel-only token lookups it routes into `hybridDpOnlyLookup()`.

At this stage there is still no full SQLite entry data. The client only has surface text, NLP hints, and winner refs from the compact key index.

### Stage B: client-side surface lookup

`buildSinglePassSurfaceLookup()` in `static/dictionary_client_hybrid.js` does the dynamic programming lookup over the compact index. This produces local entry-like stubs and a fill structure.

Those stubs are not final entries. They are half-lookup, half-display objects.

This matters because some display-oriented fields get attached early, before the full SQLite row exists.

### Stage C: hydration boundary

`hydrateWinnerRefs()` in `static/dictionary_client_hybrid.js` posts the winner refs to `/js/hydrate`.

The server route in `router.py` remaps those refs to internal candidate objects and calls `hydrate_winner_refs()` in `dict_lookup_sqlite.py`.

This is the point where the real SQLite data enters the pipeline.

### Stage D: SQLite hydration

`hydrate_winner_refs()` in `dict_lookup_sqlite.py` reads from the SQLite `entries` table and, for form hits, joins through the `forms` table.

The important behavior is:

- headword hits hydrate the entry row
- form hits hydrate the entry row plus matched form metadata

For form hits, the server explicitly appends matched form records into `_matched_forms`.

There is no evidence in the active code that strings like `redirect`, `alternative`, or `canonical` are invented at runtime. The active code forwards them from the matched form tags that came out of SQLite, then later reuses them for display and filtering.

That does not mean the final behavior is correct. It only means the tags are not being synthetically fabricated from nothing.

## 4. Server canonicalization

After hydration, `router.py` canonicalizes entries in `_canonical_entry_payload()`.

This function is a major source of complexity because it tries to produce one normalized entry format from multiple upstream shapes.

Important behaviors in `_canonical_entry_payload()`:

1. It sets `headword` from the entry.
2. It sets `surface_form` only if a form match supplied a different visible form.
3. It pulls `morph_info` from the entry if already present.
4. If no `morph_info` is set, it falls back to `_matched_forms[].tags`.
5. If no `morph_base` is set and there are matched forms, it sets `morph_base = headword`.

That last point is why you can get outputs like:

- headword `は`
- base `は`
- morph `redirect, alternative`

If the hydrated entry has a matched form row whose text is also `は`, the system still treats it as a matched form source for `morph_info`, and it still uses the entry headword as `morph_base`. The result is a self-referential display that looks nonsensical to a human even though it follows the current rules.

## 5. Client normalization after hydration

Once the server returns `entry_store`, the client runs `hydrateLookupEntry()` and then `normalizeCanonicalEntryRuntime()`.

This is another major mutation layer.

`normalizeCanonicalEntryRuntime()` does all of the following:

- normalizes POS fields
- normalizes reading and romanization
- sets `head`
- fills `morph_info` from commentary in some cases
- fills `morph_base` from lemma in some cases
- if `_matched_forms` exists, fills `morph_base` from `headword`
- if `_matched_forms` exists and `morph_info` is missing, collects morph bundles from `_matched_forms[].tags`
- normalizes `forms.rows`

This means `morph_info` and `morph_base` are not single-source fields. They are composite fields produced by fallback logic.

That is workable only if the fallback rules are very strict. Right now they are not strict enough.

## 6. Where display headwords come from

The renderer does not directly print `entry.headword` everywhere.

The client first builds grouped display objects in `attachWiktForms()` inside `static/dictionary_client_hybrid.js`.

The crucial rule is:

- if `_match_source === "form"` and `surface_form !== headword`, then show the surface spelling
- otherwise show the base headword

This is why your `氏` example can show mixed headlines like `氏`, `し`, and `うじ`.

The code is not trying to say "everything in this popup should headline the selected token". It is trying to say "only form-derived hits with a distinct surface spelling should headline the surface spelling".

That is a design choice, not just a renderer accident.

It is also probably the wrong design for your use case.

## 7. Where alternate/redirect rows get filtered

After hydration and normalization, `splitEntriesForHover()` in `static/dictionary_client_hybrid.js` applies a soft filter.

This function contains an `_ALT_FILTER_TAGS` set:

- `alternative`
- `redirect`
- `hangeul`
- `eumhun`
- `syllable`

Then it classifies entries as explicit alternates if those tags appear in any of these places:

- `entry.morph_info`
- `entry._matched_forms[].tags`
- `entry._commentary`
- `entry.forms.rows`

That means an entry can get shoved into the alternate bucket purely because those tags are present somewhere in the hydrated row, regardless of whether the selected surface is identical to the headword.

This is almost certainly why your `は (wa)` particle result feels irrational. The code is not asking "is this entry semantically just the headword?" It is asking "does any attached form/commentary metadata contain alternate-like tags?"

So the current system can do something like this:

1. hydrate a normal-looking dictionary row
2. merge in an attached form row
3. pull `redirect, alternative` into `morph_info`
4. classify the row as alternate
5. still display a `Base:` line equal to the headword

That combination is logically ugly but entirely consistent with the current implementation.

## 8. Are `redirect` and `alternative` synthetically appended?

Based on the active code, not in the literal sense.

I did not find active runtime code that invents the literal strings `redirect`, `alternative`, or `canonical` by itself.

What the code does do is:

1. read form-row tags from SQLite into `_matched_forms[].tags`
2. promote those tags into `morph_info`
3. inspect those tags again during alternate filtering
4. render them in the morph line

So the tags are not fabricated, but they are reused in too many jobs:

- matching provenance
- morph display
- alternate filtering

That reuse is the architectural problem.

## 9. Why simple cases break

The root problem is that the system uses the same tag bundle for three different concerns:

1. why the entry matched
2. how the entry should be displayed
3. whether the entry should be demoted behind "Other definitions"

That is too much responsibility for one field.

The second problem is that the renderer does not have a single authoritative "display surface for this popup row". Instead it reconstructs that decision late from:

- `headword`
- `surface_form`
- `_match_source`
- whether `surface_form !== headword`

That is why cases that should be obvious to a user are not obvious to the code.

## 10. The fix in plain language

The clean fix is not "change one if statement". The clean fix is to separate concerns.

### Fix 1: store the selected display surface explicitly

Every hydrated row shown in a popup should carry one dedicated field meaning:

"this is the exact text that should headline the row for this lookup context"

That should not be reconstructed from `headword` plus `_match_source`.

### Fix 2: keep dictionary headword separate

`headword` should stay the entry's actual dictionary headword. It should not double as the display headline.

### Fix 3: stop using morph tags as alternate-filter control flow

Tags like `redirect` and `alternative` should not by themselves decide whether a row is hidden or demoted. Filtering should be based on explicit row class or source semantics, not a free-form tag bag that is also shown to the user.

### Fix 4: special-case identical surface/headword matches

If the matched form text is identical to the entry headword, the system should usually suppress the self-referential display pattern:

- no `Base:` line unless it actually clarifies something
- no form-derived "surface" styling if nothing changed
- no alternate demotion based only on identical-form tags

### Fix 5: reduce duplicate logic

Right now similar display shaping exists in both `router.py` and `dictionary_client_hybrid.js`. The active renderer is client-driven, so the client should be the single place that decides row display semantics.

## 11. My current diagnosis of your two examples

### `氏` example

The mixed `氏`, `し`, and `うじ` display is happening because the system is still honoring dictionary headword identity for some rows and only showing the selected surface for rows that remain marked as form-derived in the expected way.

### `は (wa)` example

The most likely explanation is:

1. SQLite supplied a matched form row tagged `redirect, alternative`
2. that tag bundle was promoted into `morph_info`
3. the alternate filter saw those tags and treated the row as alternate-like
4. `morph_base` was still derived as `headword`, yielding `Base: は`

So yes, the result is irrational from a UI perspective. But it is not random. It is the direct consequence of overloaded fields and fallback-heavy normalization.

## 12. Bottom line

The entry rendering system is not broken because one renderer function is sloppy. It is broken because too many stages are allowed to reinterpret the same entry.

The biggest structural mistakes are:

- `surface_form` is optional and reconstructed too late
- `morph_info` is being used as both display text and classification input
- `_matched_forms` is a raw provenance structure that leaks directly into display semantics
- alternate filtering relies on tag content instead of explicit intent
- headword display logic depends on `_match_source` surviving intact

If you want this system to become predictable, the next step should be to define one explicit per-row display contract and make the renderer consume that contract directly instead of inferring it from mixed metadata.
