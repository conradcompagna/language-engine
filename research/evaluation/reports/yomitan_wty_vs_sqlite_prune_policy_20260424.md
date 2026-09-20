# Yomitan/wty Rules vs `sqlite_prune_policy.py`

Date: 2026-04-24

## Scope

This compares the Claude report on Yomitan/wty Kaikki postprocessing against the active Language Engine runtime compact-index prune layer:

- Policy module: `sqlite_prune_policy.py`
- Runtime caller: `dict_lookup_sqlite.py::build_compact_key_index()`
- Active static dictionary path: `build_compact_key_index()` -> `_collect_pruned_alias_hits()` -> `sqlite_prune_policy`

This layer prunes what gets emitted into the compact client index (`hw` and `fw`). It does not rewrite the raw SQLite dictionary files, and it does not run on Gemini/custom entries. It also has less information than raw Kaikki conversion: by this point the code usually has only entry fields plus flattened `forms.form_text`, `forms.morph_tags`, and `forms.romanization`.

## Current Policy Summary

The current runtime prune policy already does these things:

| Area | Current behavior |
| --- | --- |
| Entry quality | Drops entries whose gloss bucket is `missing`, `symbol_only`, or `non_latin_only`. |
| Entry dedupe | Virtually dedupes surviving entries by `(headword, romanization, pos, glosses)` before compact-index emission. |
| Form dedupe | For a single `form_text`, dedupes per survivor by `(survivor_entry_id, morph_tags, romanization)`. |
| Hard form tags | Drops forms tagged `class`, `classifier`, `counter`, `table-tags`, `inflection-template`, `multiword-construction`, or `includes-article`. |
| Always-keep tags | Keeps reading/romanization/transliteration/script-sidecar tags before most cuts. |
| Text junk | Drops blank text, alternation labels, Roman numerals, class/stem/accent codes, broken templates, English prose notes, and Hebrew mishkal placeholders. |
| Exact blacklists | Has small exact blacklists for `ja`, `ko`, `ko-krdict`, and `grc`. |
| Rule A | Drops form rows whose whitespace word count differs from the headword, with CJK/Greek/Vietnamese and reading-tag exemptions. |
| Fanout | Drops non-exempt form surfaces whose surviving-entry fanout is greater than 10. |
| Exact whitelists | Keeps reviewed exceptions for a few DBs. |

Relevant code anchors:

- `sqlite_prune_policy.py`: hard tags at line 68, always-keep tags at line 117, exact blacklists at line 168, entry cuts at line 377, occurrence cuts at line 529, fanout at line 546.
- `dict_lookup_sqlite.py`: runtime survivor context at line 370, prune collection at line 433, fanout bucket finalization at line 504, form variant dedupe at line 526, always-keep bypass at line 538, occurrence cut call at line 543.

## Already Doing From the Yomitan/wty Ruleset

| Yomitan/wty rule | Current status | Notes |
| --- | --- | --- |
| Drop no-gloss entries except special fallbacks | Partial | Current `entry_cut_reason()` drops missing glosses and also drops symbol-only/non-Latin-only glosses. It does not implement Yomitan's Greek no-gloss participle redirect fallback. |
| Drop form rows tagged `inflection-template` | Yes | Exact hard-tag cut. |
| Drop form rows tagged `table-tags` | Yes | Exact hard-tag cut. |
| Drop form rows tagged `class` | Yes | Exact hard-tag cut. |
| Drop form rows tagged `includes-article` | Yes | Exact hard-tag cut. |
| Drop form rows tagged `multiword-construction` | Yes | Exact hard-tag cut. |
| Drop obvious table/prose/template artifacts | Partial/stronger | Yomitan catches many through source-specific preprocessing and tag whitelists. Current policy catches them with English-prose, template-leak, Roman numeral, class-code, alternation-label, and Hebrew-placeholder regexes. |
| Drop many compound/periphrastic helper forms | Partial/stronger as pruning | Current Rule A and `multiword-construction` cut many German/French/Italian/etc. helper phrases. This reduces junk, but it drops the whole row rather than rewriting it into a useful stripped surface. |
| Keep reading/romanization/transliteration sidecars available | Different but intentional | Yomitan often routes these into a `reading` field or drops romanization form rows. Current policy intentionally keeps reading/romanization/transliteration tags because the reader uses cross-script/reading matches. |
| Remove duplicate form variants | Partial | Current runtime dedupes duplicate form rows after entry dedupe. It does not apply Yomitan's general `form == headword` cut. |

## Yomitan/wty Rules Not Currently Done

| Missing rule | Current gap |
| --- | --- |
| Closed tag vocabulary for rendered chips | Current prune policy does not whitelist display tags or silently drop unknown chips like `construct`, `triptote`, `hard-stem`, etc. This is more of a renderer/hydration formatting concern than compact-index pruning. |
| POS short-code mapping | Not implemented in prune policy. Current DB keeps raw POS strings. |
| Full form-tag blacklist | Current policy does not cut `canonical`, `error-unknown-tag`, `error-unrecognized-form`, `obsolete`, `archaic`, `used-in-the-form`, `romanization`, `dated`, or `auxiliary`. It intentionally keeps romanization/reading-style rows. |
| Identity-only form tags | Does not cut forms whose only tag is `singular`, `nominative`, or `infinitive`. |
| `combined-form` tag stripping | Does not strip `combined-form` while preserving the row. Some such rows may be dropped by Rule A, but the tag is not cleaned. |
| General `form_text == headword` cut | Not done at runtime. The converter only has limited special cases: Korean exact-self forms and exact-self alternative forms. |
| General hyphen-prefix form cut | Does not cut forms beginning with ASCII `-` or U+2010. Some exact Greek blacklist items catch isolated cases, but there is no global structural rule. |
| Pre-form string surgery | Does not strip German/French pronouns, Irish articles/prepositions, Italian `avere`/`non`, or Portuguese `nao`. |
| Spanish `haber` auxiliary exact blacklist | Not implemented. Rule A does not catch one-word auxiliaries like `he`, `ha`, `han`, etc. Fanout may catch only some. |
| German/French/Italian compound-tense tag filters | Not implemented as tag-specific filters. Rule A/hard tags catch many multiword cases but not all one-word or already-stripped residues. |
| Canonical form -> reading promotion | Not implemented. Current policy usually leaves canonical-tagged forms as form rows unless another rule cuts them. |
| Yomitan ALT target orthography normalization | Not implemented in this runtime policy. Some lookup-key normalization happens through the JS normalizer, but Yomitan's redirect-target normalization is a source-conversion rule, not the same thing. |
| Inflection-sense extraction | Not possible in this module from flattened SQLite rows. This belongs in raw Kaikki conversion. |
| Sense-level alt-of quality filter | Not implemented. Forms/redirects marked misspelling, misconstruction, nonstandard, pronunciation-spelling, obsolete, or abbreviation are not filtered as a Yomitan-style group. |
| Form-tag compression/merge/sort | Not implemented. This is a display/tag-presentation cleanup, not index pruning. |
| Sense-tag intersection for common entry-level tags | Not implemented. Also a display cleanup. |
| Synonym/example caps | Not implemented here. Current compact index does not carry synonym/example payloads. |
| Per-edition oddities | Not implemented: Italian placeholder gloss deletion, Russian unknown-etymology deletion, French `qu'/que/en` form skip, Japanese `pos == romanization` entry skip, Japanese noun conjugation suppression, English rare/nonstandard/dialectal form skips, Finnish OOM-break hacks, Greek no-gloss participle redirect. |
| Entry-level vs sense-level `alt_of` distinction | Not represented at this layer. The flattened forms table does not preserve enough raw sense provenance to reproduce this exactly. |

## Recommended Rules To Start Doing

These are the ones I would add first because they are low-risk, fit the current runtime policy shape, and do not require raw Kaikki sense trees.

### 1. Add identity-only tag cuts

Add a rule to drop a form when its normalized tag set is exactly one of:

- `singular`
- `nominative`
- `infinitive`

Why: These are usually lemma-self rows, not useful inflections. This directly ports a Yomitan rule and should be small/blast-radius-limited.

Implementation fit: Add to `occurrence_tag_cut_reason()` after splitting tags. Keep the current always-keep bypass before it.

### 2. Add general hyphen-prefix form cuts

Drop forms whose stripped `form_text` starts with:

- `-`
- `U+2010` non-breaking hyphen

Why: These are usually suffix/stem-template fragments. This is a direct Yomitan structural rule and fits `occurrence_text_cut_reason()`.

Implementation fit: Add a `hard_text:hyphen_prefix` reason near the blank/text-junk checks.

### 3. Add general exact-headword form cuts

Drop a form row when `form_text == headword`, unless it has an always-keep reading/romanization/transliteration/script tag.

Why: The headword key already emits a hit. Keeping an identical form hit mostly adds duplicate match paths and can let low-value form metadata compete with the lemma entry.

Implementation fit: Add to `occurrence_cut_reason()` after exact whitelist/always-keep handling and before text/prose rules.

### 4. Add a small safe subset of Yomitan's missing hard tags

Start with:

- `error-unknown-tag`
- `used-in-the-form`
- `auxiliary`

Do not add globally yet:

- `error-unrecognized-form`
- `archaic`
- `dated`
- `obsolete`
- `romanization`
- `canonical`

Why: `error-unknown-tag` and `used-in-the-form` are strong garbage signals. `auxiliary` is likely to catch parasitic helper rows. But `error-unrecognized-form` can contain real Irish/Tamil/Punjabi/Tagalog mutations, and archaic/dated/obsolete forms are useful for a historical reading app. Romanization rows are intentionally preserved. Canonical rows need the reading-promotion work below before they can be safely removed.

Implementation fit: Extend `HARD_DROP_TAGS` only with the safe subset first, then audit.

### 5. Add Spanish `haber` auxiliary exact blacklist

For `es` verb form rows where the entry is not `haber`, drop exact auxiliary forms such as `he`, `has`, `ha`, `hemos`, `han`, `habia`, `hubiera`, `hubiese`, etc.

Why: Rule A cannot catch one-word helper forms. Yomitan uses an exact 42-form list because these are parser artifacts, not useful form redirects for arbitrary verbs.

Implementation fit: This needs either a DB-specific exact blacklist with a headword exception, or a small DB/POS-aware helper because the current `FORM_EXACT_BLACKLISTS` does not know the entry headword.

### 6. Add sense-level alt-of quality filtering where represented in tags

If a form row is an alt/alternative redirect and also has a quality tag, cut the worst quality classes first:

- `misspelling`
- `misconstruction`
- `pronunciation-spelling`
- possibly `nonstandard`

Be cautious with:

- `obsolete`
- `abbreviation`

Why: Yomitan drops these from sense-level alt-of form redirects to avoid diluting search results. For this app, obsolete and abbreviations can still matter in real texts, so I would not globally cut those without an audit.

Implementation fit: Add a helper that only triggers when tags include an alt signal such as `alt-of`, `alternative`, or `alternative-form`, plus a quality signal.

## Recommended But Not First

These are valuable, but they need either schema/rendering changes or more careful language-specific QA.

### Canonical form -> reading promotion

Yomitan promotes canonical forms into the entry reading for Latin, Russian, Ancient Greek, Arabic, and Persian, then drops the canonical form row. Current policy keeps canonical form rows as ordinary forms.

Recommendation: Implement this, but not as a blind `canonical` hard-tag cut. First add a pathway to expose canonical form text as `entries.romanization`/reading or as a hydration-time display field. Then drop canonical rows from `fw`.

Why: This can remove many redundant canonical rows and improve display for diacritics/vocalization, but dropping canonical rows without a replacement would lose useful display data.

### Language-specific form rewriting

Yomitan strips pronouns/articles/auxiliary prefixes for German, French, Irish, Italian, and Portuguese before deciding whether the form is useful.

Recommendation: Consider adding an `effective_form_text` preprocessing layer for form-key emission, not just a cut. This matters most for cases like German separable verbs and Irish mutations where the stripped surface can be a useful lookup key.

Why: Current Rule A often drops the entire multiword row. Yomitan sometimes converts it into a better form surface. That is search-quality work, not just index shrinkage.

Priority order:

1. German pronoun stripping for verb forms.
2. Irish article/preposition stripping.
3. French pronoun stripping and compound-tense drops.
4. Italian `avere`/`non` stripping and `)`-ending junk cut.
5. Portuguese `nao` stripping.

### Japanese-specific suppressions

Yomitan drops Japanese `pos == romanization` entries and, in Japanese-edition Japanese, suppresses noun conjugation-table rows that lack transliteration/kanji tags.

Recommendation: Audit before adopting. Current policy deliberately preserves reading/romanization sidecars, and the existing reports show only small Japanese cut counts. This is probably not the next high-value prune.

### Display tag cleanup

Closed tag vocabulary, redundant-tag removal, person/case/verb-form merging, tag sorting, and common-tag intersection are display improvements. They belong closer to hydration or `reader_wikt.js`, not in `sqlite_prune_policy.py`.

Recommendation: Do this later if popup tag noise is the problem. It will not materially shrink the compact index.

## Rules I Would Not Port Globally

| Yomitan/wty rule | Reason not to port globally |
| --- | --- |
| Drop `romanization` form rows | Language Engine uses romanization/transliteration/reading sidecars for cross-script lookup and display. Current always-keep behavior is intentional. |
| Drop `canonical` form rows immediately | Good idea only after canonical data is promoted into a reading/display field. |
| Drop `error-unrecognized-form` globally | Claude's report notes this can include real Irish/Tamil/Punjabi/Tagalog mutation or sandhi forms. |
| Drop `archaic`, `dated`, `obsolete` forms globally | This app supports historical/ancient reading. These forms may be legitimate lookup targets. Consider modern-language-only or opt-in pruning after audit. |
| Drop `abbreviation` alt-of globally | Abbreviations are real text forms and often useful in reading. |
| Finnish OOM break rules | Finnish is not in the documented active language set, and the rule is an edition-specific emergency hack. |
| Raw sense-tree inflection extraction in this module | The runtime SQLite prune layer no longer has the raw Kaikki sense structure needed to do it correctly. |

## Bottom Line

You are already doing the big runtime-prune equivalents: hard artifact tags, prose/template/class-code cleanup, broad multiword leakage via Rule A, entry-quality cuts, dedupe, and fanout cleanup.

The highest-value Yomitan rules missing from `sqlite_prune_policy.py` are:

1. identity-only tag cuts (`singular`, `nominative`, `infinitive`);
2. hyphen-prefix form cuts;
3. general exact-headword form cuts;
4. a small safe hard-tag expansion (`error-unknown-tag`, `used-in-the-form`, `auxiliary`);
5. Spanish `haber` auxiliary blacklist;
6. quality-filtered alt-of pruning for misspellings/misconstructions/pronunciation spellings.

The bigger architectural improvement is canonical-reading promotion. Do that as a separate change because it needs a replacement display path before canonical rows are cut.
