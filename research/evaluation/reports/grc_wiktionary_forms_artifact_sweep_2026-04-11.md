# Ancient Greek Wiktionary Forms Artifact Sweep

## Scope

- Database scanned: `dict_sqlite/grc.sqlite`
- Entries: `60,050`
- Form rows: `1,415,188`
- Criterion used: a `forms` row is good only if it gives the segmenter a legitimate surface form that should map back to the entry's lemma/headword.

## Executive Summary

These are the main artifact families I found in the Ancient Greek `forms` table:

| Family | Size | Judgment |
| --- | ---: | --- |
| Declension/conjugation/class labels fossilized as forms | `19,791` rows / `17,539` entries | Safe first-pass delete |
| Article + lemma phrase cells on non-function-word entries | `1,314` rows / `312` entries | Safe delete with curated article list |
| Exact duplicate form rows within the same entry | `62,663` duplicate groups / `78,363` extra rows / `2,662` entries | Safe dedupe |
| Canonical/alternative note text in `form_text` | smaller mixed bucket, at least `1,902` rows / `1,634` entries outside obvious declension labels | Review before delete |
| Romanization field polluted with article+lemma phrases while `form_text` is valid | `7,661` rows / `7,108` entries | Real artifact, but not a `form_text` deletion target by segmenter criterion |

The two most important high-confidence cleanup targets are:

1. table metadata serialized as forms
2. article cells from nominal/adjectival tables serialized as forms

## High-Confidence Deletion Families

### 1. Declension/conjugation/class labels stored as forms

- Count: `19,791` rows across `17,539` entries
- Typical values:
  - `First declension`
  - `Second declension`
  - `Third declension`
  - `First and second declension`
  - `third declension`
- Representative entries:
  - `σκύλος` noun
  - `κύων` noun
  - `Κύπρος` name
  - `δύο` num
  - `λύκος` noun

These are pure paradigm metadata. They are not surface forms and should never be fed to the segmenter.

This family is the cleanest first-pass deletion target.

### 2. Article + lemma phrase cells serialized as forms

- Count: `1,314` rows across `312` non-function entries
- Typical pattern: a noun/adjective/name entry has a multiword `form_text` beginning with an article, e.g. article + inflected noun/adjective phrase
- Representative rows:
  - `κύων` noun: `ἡ κῠ́ων`, `αἱ κῠ́νες`, `τῆς κῠνός`, `τῇ κῠνῐ́`, `ταῖς κῠσῐ́`
  - `χάλιξ` noun: `ἡ χᾰ́λῐξ`, `αἱ χᾰ́λῐκες`, `τῆς χᾰ́λῐκος`, `τῇ χᾰ́λῐκῐ`
  - `ἵππος` noun: `ἡ ῐ̔́ππος`, `αἱ ῐ̔́πποι`

These are not inflected forms of the lemma alone. They are article-bearing phrase cells copied out of declension tables.

This is the same artifact family that shows up in the `ὁ` / `ὁμοπάτωρ` style cases.

### 3. Standalone article cells leaked onto noun/adjective entries

I did not treat this as a separate counted family because the article entries themselves are also contaminated, which makes fully automatic counting noisy. But the pattern is real and recurring.

Representative rows:

- `τρίσμακαρ` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `περίφρων` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `καλλίθριξ` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `χρυσώψ` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `ἀργής` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `τρήρων` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`
- `ἰσῆλιξ` adj: `ὁ`, `οἱ`, `τοῦ`, `τῷ`, `τοῖς`

This is the same table-cell leakage as the article+lemma phrases above, just with the article cell fossilized by itself.

If you build a curated Ancient Greek article-form list, these are safe deletion targets too.

### 4. Exact duplicate form rows within the same entry

- Count:
  - `62,663` duplicate groups
  - `78,363` extra rows beyond the first copy
  - `2,662` affected entries
- Safe dedupe key:
  - `(entry_id, form_text, morph_tags, romanization)`

Worst entries:

- `γίγνομαι` verb: `2,199` extra rows
- `θνῄσκω` verb: `1,309` extra rows
- `ἀποστερέω` verb: `1,139` extra rows
- `λανθάνω` verb: `758` extra rows
- `πλήσσω` verb: `530` extra rows

Representative duplicate example:

- `θνῄσκω` has identical rows repeated `33` times for forms such as:
  - `τέθνηκε` `active;imperative;second-person;singular`
  - `τέθνηκε` `active;indicative;singular;third-person`
  - `τέθνηκεν` `active;indicative;singular;third-person`
  - `τέθνηκᾰ` `active;first-person;indicative;singular`

These duplicates add no segmenter value and are safe to collapse.

## Review Buckets

### 5. Canonical/alternative note text fossilized as `form_text`

This is real, but it is a mixed bucket and needs a tighter deletion rule.

- Loose size: at least `1,902` rows across `1,634` entries outside obvious `declension`/`conjugation` labels
- Representative bad values:
  - `first`
  - `Josephus`
  - `Letter of Aristeas`
  - `Ionic`
  - `Doric`
  - `Epic`
  - `uncontracted`
  - `. Quoted by comic poet Alexis`

Why this needs review:

- some rows in this area are clearly metadata or source labels
- some others are transliterated surface forms or mixed-script variants

So this family is real, but I would not bulk-delete it without one more pass to separate note text from intentional alternate forms.

### 6. Romanization field misaligned with `form_text`

- Count: `7,661` rows across `7,108` entries
- Pattern: the Greek `form_text` is a single inflected word, but the `romanization` includes an article+lemma phrase
- Representative rows:
  - `σκύλος` noun: `σκῠ́λει` with romanization `tōî skŭ́lei`
  - `λύκος` noun: `λῠ́κῳ` with romanization `tōî lŭ́kōi`
  - `μηχανή` noun: `μᾱχᾰνᾷ` with romanization `tāî mākhănāî`
  - `βασιλεύς` noun: `βᾰσῐλεῖ` with romanization `tōî băsĭleî`

This is a real conversion artifact, but by the segmenter criterion it is not a first-pass deletion family, because the `form_text` itself is still a legitimate surface form.

It matters for display/alignment cleanup, not for immediate `form_text` pruning.

## Things I Would Not Bulk-Delete

### Multiword verb forms as a whole

- There are `29,717` multiword non-class form rows total
- `26,626` of those belong to verbs

Examples like these may be legitimate periphrastic or analytic verbal forms rather than garbage:

- `γεγενημένοι εἴημεν`
- `γεγενημένος εἴη`
- `γεγενημένω εἰήτην`

So I would not use a blanket rule like "delete all multiword forms."

The bad multiword family is specifically the article-prefixed nominal/adjectival phrase cells above.

### Latin-script/transliterated forms as a whole

There are many non-Greek `form_text` rows. Some are clearly junk, but some are transliterated alternants like `me`, `moi`, `emoí`. Whether those should stay depends on whether you want any support for romanized lookup.

So I would not use a blanket rule like "delete every ASCII-bearing form row."

## Provenance Note

For the known article-cell leakage cases already checked directly (`καλλίθριξ`, `μελάνθριξ`, `ὁμοπάτωρ`):

- the current SQLite importer is not inventing the bad rows
- the archived TSV already contains them
- the current JSONL→TSV and TSV→SQLite scripts do not split multiword forms into single words

So the relevant mechanism is table-cell leakage already present before SQLite import, not a later token-splitting bug inside the SQLite conversion step.

## Recommended Cleanup Order

### Safe first pass

1. Delete all rows where `morph_tags` includes `class`
2. Delete all rows where `form_text` is a declension/conjugation label
3. Deduplicate exact `(entry_id, form_text, morph_tags, romanization)` repeats
4. Delete article-prefixed nominal/adjectival phrase cells using a curated Ancient Greek article list
5. Delete standalone bare article cells on non-article entries using the same curated article list

### Second pass after a tighter predicate

1. canonical/alternative note text
2. source-label rows
3. transliteration-only rows, if you decide the segmenter should be Greek-script-only

## Bottom Line

The strongest systematic conversion artifacts in `grc.sqlite` are:

1. table metadata as forms
2. article table cells as forms
3. exact duplicate form rows

Those are the families I would clean first.
