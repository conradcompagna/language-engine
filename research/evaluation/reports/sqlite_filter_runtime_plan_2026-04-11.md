# SQLite Filter Runtime Plan

## Scope

- Goal: avoid destructive DB edits and instead suppress junk at compact-index build time
- Active hook point: `dict_lookup_sqlite.py::build_compact_key_index()`
- Related cache freshness logic: `language_engine/http/index_cache.py::_js_index_cache_is_fresh()`
- Supporting audit data:
  - `tmp_wiktionary_db_audit_2026-04-11.json`
  - `tmp_sqlite_filter_plan_audit_2026-04-11.json`

## What The Current Runtime Actually Does

`build_compact_key_index()` currently indexes:

- every non-empty `entries.headword`
- every non-empty `forms.form_text`

with only two built-in exclusions on forms:

- `classifier`
- `counter`

That means almost all junk currently goes straight into `hw` or `fw`.

Important constraint: the compact index stores real SQLite row ids. Hydration later uses those row ids directly. So:

- dropping candidates at index-build time is easy
- deduping exact form rows within one entry is easy
- broad cross-entry canonicalization is not index-only; if you want metadata union, you also need a hydrate-time overlay

## Main Research Findings

### 1. Merging on `headword + pos + glosses` alone is too broad

I measured duplicate-entry groups keyed only by byte-identical:

- `headword`
- `pos`
- `glosses`

and then checked whether the grouped rows also differ in other metadata (`romanization`, `commentary`, `lemma`, `etymology`, `etymology_number`, `source`, `entry_id`, `tags`, `format`).

Top risk cases:

| DB | Extra Entries In `headword+pos+glosses` Groups | Extra Entries With Other Metadata Differences |
| --- | ---: | ---: |
| `ja.sqlite` | 1,826 | 1,799 |
| `ru.sqlite` | 359 | 292 |
| `la.sqlite` | 216 | 0 |
| `ar.sqlite` | 157 | 143 |
| `pt.sqlite` | 93 | 0 |
| `lzh.sqlite` | 74 | 74 |
| `de.sqlite` | 60 | 0 |
| `es.sqlite` | 58 | 0 |
| `grc.sqlite` | 16 | 14 |
| `he.sqlite` | 16 | 16 |

Conclusion:

- for some DBs like `de`, `es`, `la`, this merge key is often safe
- for others like `ja`, `ar`, `ru`, `grc`, `he`, `lzh`, it is not safe as a blanket rule

So the proposed survivor selection key is too loose as a global rule.

### 2. Your strict alphabetic form filter would catch a lot, but it would also overfire

I modeled your proposed form filter on a candidate set of alphabetic-script DBs:

- `ang`, `de`, `el`, `es`, `fr`, `ga`, `grc`, `hy`, `id`, `it`, `la`, `nl`, `pt`, `ru`, `sw`, `tl`, `tr`

Rule modeled:

- for those languages only
- remove any form whose piece count differs from the headword
- remove any form with zero shared characters with the headword
- always preserve rows tagged `romanization`

Projected impact:

| DB | Rows Removed By Mismatch/Zero-Share Union | Mismatch Rows | Zero-Share Rows | `romanization` Saves |
| --- | ---: | ---: | ---: | ---: |
| `de.sqlite` | 1,784,838 | 1,784,151 | 724 | 0 |
| `hy.sqlite` | 275,321 | 274,999 | 415 | 0 |
| `ga.sqlite` | 248,423 | 239,196 | 9,407 | 0 |
| `grc.sqlite` | 87,118 | 49,168 | 58,312 | 0 |
| `la.sqlite` | 56,366 | 54,725 | 1,705 | 0 |
| `ru.sqlite` | 151,704 | 63,319 | 108,086 | 1 |
| `fr.sqlite` | 102,755 | 102,111 | 798 | 0 |
| `pt.sqlite` | 42,513 | 41,910 | 704 | 0 |
| `el.sqlite` | 21,410 | 16,236 | 7,440 | 0 |
| `ang.sqlite` | 4,773 | 244 | 4,536 | 0 |
| `tl.sqlite` | 51,389 | 2,857 | 49,372 | 0 |

Conclusion:

- the rule is strong enough to remove lots of junk
- but it is also strong enough to remove large amounts of real data

### 3. `romanization` is too narrow as the only always-allow exemption

Literal `romanization` tag rows are rare:

- total across included Wiktionary DBs: `383`
- `ko.sqlite`: `375`
- `he.sqlite`: `5`
- `it.sqlite`: `2`
- `ru.sqlite`: `1`

That means a `romanization` allowlist alone will not protect most legitimate cross-script or alternate-orthography forms.

Other large script/orthography tags already present in the data include:

- `Baybayin`: `35,364`
- `hanja`: `16,991`
- `hangeul`: `13,446`
- `CJK`: `11,837`
- `Urdu`: `11,004`
- `Hindi`: `8,977`
- `shinjitai`: `410`
- `Romaji`: `495`

So if you want a reversible runtime filter, you need a broader "always allow script-alternate forms" concept, not just `romanization`.

## Question 1: Other Rules Worth Adding

Yes. These are the additional rules I would add.

### Global Safe Rules

1. Drop headword candidates where `pos` is `symbol` or `syllable`.
2. Drop headword candidates where `pos` is `char` or `character` outside an explicit script-preserving allowlist.
3. Drop headword candidates whose headword is combining marks / formatting chars only.
4. Drop forms tagged `class`.
5. Drop exact duplicate form rows within the same entry, keyed by `(form_text, morph_tags, romanization)`.
6. Drop exact duplicate entries only when the entire payload matches, or when every non-forms field matches and the only difference is duplicate forms content.
7. Drop any headword or form whose normalized lookup key is empty after the same normalization pipeline used for indexing.

### Strong Additional Preserve Rules

These should bypass heuristic junk filters:

1. `romanization`
2. script-alternate tags such as `Baybayin`, `hanja`, `hangeul`, `CJK`, `Urdu`, `Hindi`, `Romaji`, `shinjitai`
3. language-level bypass buckets for East Asian DBs: `ja`, `ko`, `vi`, `zh`, `zh-Hant`, `lzh`

### Good Language-Specific Denylists

These are not safe globally, but they are strong runtime-filter candidates when applied per language:

1. `includes-article`
   - very strong junk-for-segmentation signal in `de.sqlite`
2. `multiword-construction`
   - strong "analytic phrase form" signal in `de`, `fr`, `la`
3. article-token phrase heuristics
   - useful for `grc`
   - useful for `ga`
4. `class`-like table labels by text pattern
   - e.g. `declension`, `conjugation`, `stem`, `accent-a`, `velar-stem`

### One Important Revision To Your Zero-Share Rule

Do not use literal character overlap.

Use folded base-letter overlap instead:

- lowercase
- NFD-decompose
- strip combining marks
- then compare base letters

Reason: literal overlap wrongly treats these as unrelated:

- `a-` vs `a-with-macron`
- `y` vs `y-with-macron`
- accented Greek variants

## Question 2: Does Your Proposed Rule Set Break Anything Important?

Yes.

### A. `headword + pos + glosses` merge is too aggressive

This is the biggest design risk.

It would collapse many groups that still differ in meaningful metadata:

- `ja.sqlite`: `1,799` risky extra entries
- `ar.sqlite`: `143`
- `ru.sqlite`: `292`
- `grc.sqlite`: `14`
- `he.sqlite`: `16`
- `lzh.sqlite`: `74`

Best conclusion:

- do not merge on those 3 fields alone as a global rule

### B. Literal zero-shared-character filtering breaks real alternate spellings

Examples from the sweep:

- `la.sqlite`: `a-` -> `a-with-macron`
- `ang.sqlite`: `a-` -> `a-with-macron`
- `ang.sqlite`: `on` -> runic-script form
- `tl.sqlite`: Latin headwords with `Baybayin` forms

Those are not junk. They are alternate orthographies or historical-script forms.

### C. Zero-share filtering also breaks real suppletive paradigms

Examples:

- `hy.sqlite`: Armenian pronoun suppletion like `yes` -> `im` / `indz`
- `el.sqlite`: Modern Greek suppletion like `mia` -> `enos`

So zero-share cannot be a blanket runtime rule even inside alphabetic-script languages.

### D. Piece-count mismatch filtering breaks legitimate multiword forms

Examples:

- `de.sqlite`: `der freie`, `am freiesten`
- `fr.sqlite`: `avoir + past participle` constructions
- `ga.sqlite`: `an cat`, `na cait`, `leis an gcat`
- `hy.sqlite`: `կազմակերպում եմ`
- `grc.sqlite`: some multiword rows are junk, but others are real article-bearing phrase cells copied from tables

This rule is only safe if your product decision is:

- "we do not want phrase-level analytic forms in the compact index"

If that is the decision, fine. But it is not a pure junk filter.

### E. East-Asian-only bypass is not enough

Important non-East-Asian exceptions from the sweep:

- `tl.sqlite` has `Baybayin`
- `ang.sqlite` has runic alternants
- `la.sqlite` and `ang.sqlite` have diacritic alternants

So the bypass cannot just be "East Asian".

### F. `char` is not enough; you must handle `character`

The DBs mostly use `character`, not `char`.

Examples of `character` headword counts:

- `zh.sqlite`: `20,200`
- `ja.sqlite`: `5,602`
- `ko.sqlite`: `3,915`
- `vi.sqlite`: `2,940`

Outside East Asian, `character` counts are much smaller and are good runtime-filter targets.

### G. Index-build-only canonicalization is incomplete

If you drop duplicate entries at index build time but do not also apply a hydrate-time overlay:

- the survivor entry will hydrate
- but metadata from dropped siblings will not be merged in

So the "take missing metadata from duplicates and write it into the main one" part cannot be solved by index build alone.

## Best Way To Go

After the sweep, I do not think the best first version is:

- broad `headword + pos + glosses` survivor merging
- plus blanket piece-count / zero-share filtering across all alphabetic languages

I think the best first version is:

1. conservative, mostly-safe runtime suppression
2. per-language policy buckets
3. cacheable filter plans
4. shadow mode before hard suppression
5. only later: broad canonical survivor merging with a hydrate overlay

## Recommended Architecture

### New Module

Create `sqlite_filter.py`.

Core responsibilities:

1. build a per-DB `FilterPlan`
2. decide which headwords/forms are indexable
3. remap safe duplicate entries to canonical survivors
4. record merged overlay data for hydration
5. expose stats for debug/reporting

Suggested objects:

- `FilterConfig`
- `FilterPlan`
- `EntryDecision`
- `FormDecision`
- `CanonicalGroup`

### FilterPlan Contents

`FilterPlan` should cache at least:

- `drop_entry_ids`
- `drop_form_ids`
- `canonical_entry_id_by_entry_id`
- `merged_entry_overlay_by_canonical_entry_id`
- `duplicate_form_signatures_by_entry_id`
- `stats`

### Hook Points

1. `dict_lookup_sqlite.py::build_compact_key_index()`
   - load `FilterPlan`
   - skip dropped entry/form rows
   - remap safe duplicate entries to canonical ids
2. `dict_lookup_sqlite.py::hydrate_winner_refs()`
   - remap duplicate refs to canonical ids
   - apply merged overlay for the survivor entry
3. `language_engine/http/index_cache.py::_js_index_cache_is_fresh()`
   - invalidate on filter config / filter code version too, not just DB mtime

## Comprehensive Implementation Plan

### Phase 1: Safe Runtime Filtering Only

Implement only the low-risk rules first.

1. Add `sqlite_filter.py`.
2. Add a small editable rules file, e.g. `sqlite_filter_rules.json`.
3. Build `FilterPlan` per DB and cache it under `runtime_cache/sqlite_filter/`.
4. Apply only these rules initially:
   - drop `symbol`
   - drop `syllable`
   - drop `char` and `character` outside an allowlist
   - drop combining-only headwords
   - drop forms tagged `class`
   - drop exact duplicate forms within the same entry
   - drop exact duplicate entries only when all non-forms metadata already matches
5. Add stats logging but keep a `shadow_mode` flag so you can compare "would drop" vs "did drop".

This phase is safe, reversible, and does not require synthetic form refs.

### Phase 2: Language-Bucket Filtering

Add policy buckets:

1. `east_asian_bypass`
2. `strict_alpha_candidate`
3. `review_only`

Then add per-bucket rules:

- East Asian:
  - preserve `character`
  - preserve script-alternate tags
- Strict alpha:
  - allow folded-base overlap checks
  - deny `class`
  - optionally deny known per-language analytic/junk tagsets
- Review-only:
  - only apply global safe rules

Do not turn on blanket zero-share removal yet.

### Phase 3: Per-Language Heuristics

Add explicit, opt-in language rules where the data clearly supports them.

Examples:

1. `grc`
   - deny article-table artifacts
   - deny class labels
2. `de`
   - optionally deny `includes-article`
   - optionally deny `multiword-construction`
3. `fr`
   - optionally deny `multiword-construction`
4. `ga`
   - optionally deny article-bearing table phrases

This should be config-driven, not hardcoded deep in the builder.

### Phase 4: Conservative Cross-Entry Canonicalization

Only after Phases 1-3 are stable:

1. canonicalize groups only when:
   - `headword`, `pos`, `glosses` are identical
   - and every other non-forms metadata field is identical, or only differs by empty-vs-non-empty
2. choose survivor by score:
   - most non-empty metadata fields
   - then most unique forms
   - then lowest row id as stable tie-break
3. merge only missing fields
4. if two non-empty fields conflict, do not auto-merge; record a conflict and keep the group out of auto-canonicalization

This avoids the `ja/ar/ru/grc/he/lzh` failure mode.

### Phase 5: Hydration Overlay

To support metadata union without DB mutation:

1. build `merged_entry_overlay_by_canonical_entry_id`
2. at hydrate time, fetch survivor row normally
3. apply overlay:
   - union exact-unique forms
   - fill empty commentary/lemma/etymology/source/tags fields
4. keep the original DB unchanged

Without this phase, cross-entry metadata union is incomplete.

### Phase 6: Debuggability

Add filter diagnostics:

1. counts by rule
2. counts by language
3. sample dropped rows
4. sample canonical merges
5. a version string / fingerprint in the compact-index payload

This should show up in the debug panel so the filter remains tweakable and reversible.

## Final Recommendation

The best first implementation is:

1. `sqlite_filter.py`
2. runtime-only suppression
3. safe headword/form pruning
4. exact duplicate-form dedupe
5. conservative duplicate-entry handling only
6. no broad `headword + pos + glosses` merging yet
7. no blanket literal zero-share rule
8. no blanket mismatch rule outside explicit language policies

That gives you a reversible system that can be iterated safely without corrupting the underlying DBs.
