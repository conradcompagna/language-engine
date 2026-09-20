# Wiktionary DB Forms Surface Audit

## Scope

- Generated from: `tmp_wiktionary_db_audit_2026-04-11.json`
- Included Wiktionary-style DBs (`34`): ang.sqlite, ar.sqlite, bn.sqlite, de.sqlite, el.sqlite, es.sqlite, fa.sqlite, fr.sqlite, ga.sqlite, grc.sqlite, hbo.sqlite, he.sqlite, hi.sqlite, hy.sqlite, id.sqlite, it.sqlite, ja.sqlite, ko.sqlite, la.sqlite, lzh-wiktionary.sqlite, lzh.sqlite, nl.sqlite, pa.sqlite, pt.sqlite, ru.sqlite, sw.sqlite, ta.sqlite, th.sqlite, tl.sqlite, tr.sqlite, ur.sqlite, vi.sqlite, zh-Hant.sqlite, zh.sqlite
- Excluded non-Wiktionary / empty DBs: grc-lsj.sqlite, ja-jmdict.sqlite, ko-krdict.sqlite, zh-cc-cedict.sqlite, zh-Hant-cc-cedict.sqlite, sa.sqlite, vo.sqlite

## Method

- `word-count mismatch`: whitespace-delimited segment count in `form_text` differs from whitespace-delimited segment count in `entries.headword`
- `1_to_M`: headword is one space-delimited segment, form is multiple
- `M_to_1`: headword is multiple segments, form is one
- `M_to_M_diff`: both are multiword, but with different segment counts
- `zero-shared characters`: `headword` and `form_text` share no non-space, non-punctuation Unicode characters after NFC normalization
- `exact duplicate entries`: duplicate `entries` rows where every payload column except `id` is identical
- `mergeable headword duplicates`: same entry payload except `forms`, same headword, multiple rows
- `duplicate form rows`: duplicate `(entry_id, form_text, morph_tags, romanization)` groups inside `forms`
- These are heuristic anomaly signals, not automatic deletion rules. They are especially noisy for languages with script alternants, transliteration layers, or productive multiword constructions.

## Overall

- Entries scanned: `5,592,231`
- Form rows scanned: `26,332,734`
- Word-count mismatch rows: `3,709,148` (`14.09%`)
- Zero-shared-character rows: `1,116,244` (`4.24%`)
- Exact duplicate entry groups: `574` with `579` extra rows
- Mergeable headword-duplicate groups: `297` with `327` extra rows
- Duplicate form-row groups within entries: `391,463` with `448,424` extra rows

## Per-Language Summary

| DB | Forms | Mismatch | Rate | 1_to_M | M_to_1 | M_to_M_diff | Zero-share | Rate | Exact Dup Entry Extras | Mergeable Entry Extras | Dup Form Extras |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ang.sqlite` | 379,703 | 244 | 0.06% | 176 | 58 | 10 | 4,536 | 1.19% | 3 | 16 | 27,830 |
| `ar.sqlite` | 1,568,067 | 2,722 | 0.17% | 148 | 32 | 2,542 | 1,110 | 0.07% | 10 | 4 | 12,079 |
| `bn.sqlite` | 67,239 | 14,443 | 21.48% | 14,106 | 149 | 188 | 2,335 | 3.47% | 0 | 0 | 579 |
| `de.sqlite` | 3,669,555 | 1,784,151 | 48.62% | 1,709,492 | 5,408 | 69,251 | 724 | 0.02% | 45 | 15 | 75,203 |
| `el.sqlite` | 510,352 | 16,236 | 3.18% | 15,928 | 180 | 128 | 7,440 | 1.46% | 7 | 0 | 3,751 |
| `es.sqlite` | 1,628,748 | 37,434 | 2.30% | 35,048 | 446 | 1,940 | 1,016 | 0.06% | 29 | 29 | 4,856 |
| `fa.sqlite` | 191,124 | 76,879 | 40.22% | 30,334 | 2,258 | 44,287 | 10,112 | 5.29% | 1 | 0 | 32,005 |
| `fr.sqlite` | 617,178 | 102,111 | 16.54% | 100,143 | 718 | 1,250 | 798 | 0.13% | 28 | 0 | 33,357 |
| `ga.sqlite` | 597,657 | 239,196 | 40.02% | 236,295 | 140 | 2,761 | 9,407 | 1.57% | 6 | 3 | 12,108 |
| `grc.sqlite` | 1,415,188 | 49,168 | 3.47% | 49,115 | 15 | 38 | 58,312 | 4.12% | 2 | 0 | 78,363 |
| `hbo.sqlite` | 40,720 | 281 | 0.69% | 0 | 281 | 0 | 17 | 0.04% | 4 | 32 | 0 |
| `he.sqlite` | 163,694 | 2,632 | 1.61% | 2,297 | 184 | 151 | 2,056 | 1.26% | 0 | 0 | 5,387 |
| `hi.sqlite` | 517,534 | 301,663 | 58.29% | 199,184 | 213 | 102,266 | 13,923 | 2.69% | 2 | 2 | 2,593 |
| `hy.sqlite` | 1,136,448 | 274,999 | 24.20% | 274,259 | 441 | 299 | 415 | 0.04% | 0 | 2 | 46,255 |
| `id.sqlite` | 44,154 | 6,825 | 15.46% | 5,625 | 957 | 243 | 760 | 1.72% | 11 | 5 | 275 |
| `it.sqlite` | 1,133,527 | 149,450 | 13.18% | 146,928 | 1,366 | 1,156 | 489 | 0.04% | 33 | 5 | 39,308 |
| `ja.sqlite` | 1,058,263 | 224,615 | 21.22% | 224,613 | 2 | 0 | 513,993 | 48.57% | 11 | 24 | 13,480 |
| `ko.sqlite` | 448,924 | 3,389 | 0.75% | 2,962 | 416 | 11 | 56,704 | 12.63% | 1 | 25 | 4,525 |
| `la.sqlite` | 2,546,142 | 54,725 | 2.15% | 54,218 | 149 | 358 | 1,705 | 0.07% | 192 | 24 | 4,203 |
| `lzh-wiktionary.sqlite` | 293,770 | 107 | 0.04% | 72 | 35 | 0 | 71,229 | 24.25% | 13 | 24 | 373 |
| `lzh.sqlite` | 82,663 | 1 | 0.00% | 0 | 1 | 0 | 15,089 | 18.25% | 0 | 0 | 0 |
| `nl.sqlite` | 513,466 | 51,253 | 9.98% | 50,763 | 364 | 126 | 10,336 | 2.01% | 9 | 9 | 14,912 |
| `pa.sqlite` | 106,325 | 50,942 | 47.91% | 50,252 | 27 | 663 | 5,873 | 5.52% | 0 | 1 | 73 |
| `pt.sqlite` | 670,469 | 41,910 | 6.25% | 37,735 | 837 | 3,338 | 704 | 0.10% | 66 | 27 | 2,930 |
| `ru.sqlite` | 2,230,009 | 63,319 | 2.84% | 58,168 | 4,684 | 467 | 108,087 | 4.85% | 58 | 9 | 17,945 |
| `sw.sqlite` | 356,739 | 67,487 | 18.92% | 67,168 | 189 | 130 | 273 | 0.08% | 0 | 1 | 3,021 |
| `ta.sqlite` | 330,620 | 11,672 | 3.53% | 11,477 | 82 | 113 | 60 | 0.02% | 2 | 1 | 3,446 |
| `th.sqlite` | 11,351 | 59 | 0.52% | 55 | 2 | 2 | 912 | 8.03% | 1 | 0 | 234 |
| `tl.sqlite` | 207,259 | 2,857 | 1.38% | 2,023 | 501 | 333 | 49,372 | 23.82% | 16 | 20 | 7,095 |
| `tr.sqlite` | 3,115,794 | 36,396 | 1.17% | 31,632 | 755 | 4,009 | 540 | 0.02% | 1 | 1 | 837 |
| `ur.sqlite` | 67,678 | 36,407 | 53.79% | 29,811 | 580 | 6,016 | 9,971 | 14.73% | 0 | 0 | 439 |
| `vi.sqlite` | 24,834 | 5,361 | 21.59% | 379 | 4,738 | 244 | 15,488 | 62.37% | 2 | 0 | 216 |
| `zh-Hant.sqlite` | 293,770 | 107 | 0.04% | 72 | 35 | 0 | 71,229 | 24.25% | 13 | 24 | 373 |
| `zh.sqlite` | 293,770 | 107 | 0.04% | 72 | 35 | 0 | 71,229 | 24.25% | 13 | 24 | 373 |

## Highest Mismatch Rates

- `hi.sqlite`: `301,663` / `517,534` (`58.29%`)
- `ur.sqlite`: `36,407` / `67,678` (`53.79%`)
- `de.sqlite`: `1,784,151` / `3,669,555` (`48.62%`)
- `pa.sqlite`: `50,942` / `106,325` (`47.91%`)
- `fa.sqlite`: `76,879` / `191,124` (`40.22%`)
- `ga.sqlite`: `239,196` / `597,657` (`40.02%`)
- `hy.sqlite`: `274,999` / `1,136,448` (`24.20%`)
- `vi.sqlite`: `5,361` / `24,834` (`21.59%`)
- `bn.sqlite`: `14,443` / `67,239` (`21.48%`)
- `ja.sqlite`: `224,615` / `1,058,263` (`21.22%`)

## Highest Zero-Shared Rates

- `vi.sqlite`: `15,488` / `24,834` (`62.37%`)
- `ja.sqlite`: `513,993` / `1,058,263` (`48.57%`)
- `lzh-wiktionary.sqlite`: `71,229` / `293,770` (`24.25%`)
- `zh-Hant.sqlite`: `71,229` / `293,770` (`24.25%`)
- `zh.sqlite`: `71,229` / `293,770` (`24.25%`)
- `tl.sqlite`: `49,372` / `207,259` (`23.82%`)
- `lzh.sqlite`: `15,089` / `82,663` (`18.25%`)
- `ur.sqlite`: `9,971` / `67,678` (`14.73%`)
- `ko.sqlite`: `56,704` / `448,924` (`12.63%`)
- `th.sqlite`: `912` / `11,351` (`8.03%`)

## Most Duplicate Form Rows

- `grc.sqlite`: `78,363` extra form rows across `62,663` duplicate groups
- `de.sqlite`: `75,203` extra form rows across `56,100` duplicate groups
- `hy.sqlite`: `46,255` extra form rows across `42,864` duplicate groups
- `it.sqlite`: `39,308` extra form rows across `37,757` duplicate groups
- `fr.sqlite`: `33,357` extra form rows across `32,351` duplicate groups
- `fa.sqlite`: `32,005` extra form rows across `31,226` duplicate groups
- `ang.sqlite`: `27,830` extra form rows across `27,334` duplicate groups
- `ru.sqlite`: `17,945` extra form rows across `14,350` duplicate groups
- `nl.sqlite`: `14,912` extra form rows across `8,361` duplicate groups
- `ja.sqlite`: `13,480` extra form rows across `12,476` duplicate groups

## Per-Language Notes

### ang.sqlite

- Forms: `379,703`
- Word-count mismatch: `244` (`0.06%`) | `1_to_M=176` `M_to_1=58` `M_to_M_diff=10`
- Zero-shared characters: `4,536` (`1.19%`)
- Exact duplicate entries: `3` extra rows in `3` groups
- Mergeable headword duplicates: `16` extra rows in `15` groups
- Duplicate form rows within entry: `27,830` extra rows in `27,334` groups
- Mismatch examples:
  - `on` -> `a/languages M to Z` [redirect;alternative]
  - `on` -> `a/languages M to Z` [redirect;alternative]
  - `-ian` -> `2 Anglian` [class]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `f` -> `F` [uppercase]
  - `f` -> `ꝼ` [redirect;alternative]

### ar.sqlite

- Forms: `1,568,067`
- Word-count mismatch: `2,722` (`0.17%`) | `1_to_M=148` `M_to_1=32` `M_to_M_diff=2,542`
- Zero-shared characters: `1,110` (`0.07%`)
- Exact duplicate entries: `10` extra rows in `10` groups
- Mergeable headword duplicates: `4` extra rows in `3` groups
- Duplicate form rows within entry: `12,079` extra rows in `11,677` groups
- Mismatch examples:
  - `سلم` -> `سَلِم m and plural of variety` [canonical]
  - `سلم` -> `alternative collective سِلَام` [canonical]
  - `و` -> `و / و` [canonical]
- Zero-share examples:
  - `أنا` -> `ـِيَ` [enclitic]
  - `أنا` -> `ـِي` [enclitic]
  - `مرأة` -> `نِسَاء` [plural]

### bn.sqlite

- Forms: `67,239`
- Word-count mismatch: `14,443` (`21.48%`) | `1_to_M=14,106` `M_to_1=149` `M_to_M_diff=188`
- Zero-shared characters: `2,335` (`3.47%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `579` extra rows in `573` groups
- Mismatch examples:
  - `কলকাতা` -> `কলকাতা য়` [locative]
  - `কলকাতা` -> `কলকাতাকে  / kolkatake (semantically definite))` [indefinite;objective]
  - `কলকাতা` -> `Objective Note: In some dialects` [(no tags)]
- Zero-share examples:
  - `কলকাতা` -> `Objective Note: In some dialects` [(no tags)]
  - `SN` -> `~` [canonical]
  - `মাস` -> `Objective Note: In some dialects` [(no tags)]

### de.sqlite

- Forms: `3,669,555`
- Word-count mismatch: `1,784,151` (`48.62%`) | `1_to_M=1,709,492` `M_to_1=5,408` `M_to_M_diff=69,251`
- Zero-shared characters: `724` (`0.02%`)
- Exact duplicate entries: `45` extra rows in `45` groups
- Mergeable headword duplicates: `15` extra rows in `15` groups
- Duplicate form rows within entry: `75,203` extra rows in `56,100` groups
- Mismatch examples:
  - `frei` -> `am freiesten` [superlative]
  - `frei` -> `am freisten` [superlative]
  - `frei` -> `der freie` [definite;includes-article;masculine;nominative;singular;weak]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `a` [nominative;singular]
  - `A` -> `a` [definite;nominative;plural]

### el.sqlite

- Forms: `510,352`
- Word-count mismatch: `16,236` (`3.18%`) | `1_to_M=15,928` `M_to_1=180` `M_to_M_diff=128`
- Zero-shared characters: `7,440` (`1.46%`)
- Exact duplicate entries: `7` extra rows in `7` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `3,751` extra rows in `2,935` groups
- Mismatch examples:
  - `ένας` -> `μίαν (mían¹⁺²)` [accusative;feminine]
  - `ένας` -> `μίαν (mían¹⁺²)` [accusative;feminine]
  - `ένας` -> `μίαν (mían¹⁺²)` [accusative;feminine]
- Zero-share examples:
  - `δύση` -> `Δ` [redirect;alternative]
  - `δυτικός` -> `Δ` [redirect;alternative]
  - `δυτικός` -> `Δ` [redirect;alternative]

### es.sqlite

- Forms: `1,628,748`
- Word-count mismatch: `37,434` (`2.30%`) | `1_to_M=35,048` `M_to_1=446` `M_to_M_diff=1,940`
- Zero-shared characters: `1,016` (`0.06%`)
- Exact duplicate entries: `29` extra rows in `29` groups
- Mergeable headword duplicates: `29` extra rows in `29` groups
- Duplicate form rows within entry: `4,856` extra rows in `4,675` groups
- Mismatch examples:
  - `A` -> `a/languages M to Z` [redirect;alternative]
  - `A` -> `a/languages M to Z` [redirect;alternative]
  - `lente` -> `f same meaning` [canonical]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `al` [redirect;alternative]
  - `A` -> `à` [redirect;alternative]

### fa.sqlite

- Forms: `191,124`
- Word-count mismatch: `76,879` (`40.22%`) | `1_to_M=30,334` `M_to_1=2,258` `M_to_M_diff=44,287`
- Zero-shared characters: `10,112` (`5.29%`)
- Exact duplicate entries: `1` extra rows in `1` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `32,005` extra rows in `31,226` groups
- Mismatch examples:
  - `هل` -> `spelling ҳил` [Tajik]
  - `حلال` -> `spelling ҳалол` [Tajik]
  - `جهاد` -> `spelling ҷиҳод` [Tajik]
- Zero-share examples:
  - `هل` -> `spelling ҳил` [Tajik]
  - `حلال` -> `spelling ҳалол` [Tajik]
  - `جهاد` -> `spelling ҷиҳод` [Tajik]

### fr.sqlite

- Forms: `617,178`
- Word-count mismatch: `102,111` (`16.54%`) | `1_to_M=100,143` `M_to_1=718` `M_to_M_diff=1,250`
- Zero-shared characters: `798` (`0.13%`)
- Exact duplicate entries: `28` extra rows in `28` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `33,357` extra rows in `32,351` groups
- Mismatch examples:
  - `abhorrer` -> `avoir + past participle` [infinitive;multiword-construction]
  - `abhorrer` -> `ayant + past participle` [gerund;multiword-construction;participle;present]
  - `abhorrer` -> `present indicative of avoir + past participle` [indicative;multiword-construction;perfect;present]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `f` -> `F` [uppercase]
  - `y` -> `Y` [uppercase]

### ga.sqlite

- Forms: `597,657`
- Word-count mismatch: `239,196` (`40.02%`) | `1_to_M=236,295` `M_to_1=140` `M_to_M_diff=2,761`
- Zero-shared characters: `9,407` (`1.57%`)
- Exact duplicate entries: `6` extra rows in `6` groups
- Mergeable headword duplicates: `3` extra rows in `3` groups
- Duplicate form rows within entry: `12,108` extra rows in `11,556` groups
- Mismatch examples:
  - `cat` -> `a chait` [indefinite;singular;vocative]
  - `cat` -> `a chata` [indefinite;plural;vocative]
  - `cat` -> `an cat` [definite;nominative;singular]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `an` [redirect;alternative]
  - `A` -> `'s` [redirect;alternative]

### grc.sqlite

- Forms: `1,415,188`
- Word-count mismatch: `49,168` (`3.47%`) | `1_to_M=49,115` `M_to_1=15` `M_to_M_diff=38`
- Zero-shared characters: `58,312` (`4.12%`)
- Exact duplicate entries: `2` extra rows in `2` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `78,363` extra rows in `62,663` groups
- Mismatch examples:
  - `σκύλος` -> `Third declension` [class]
  - `σκύλος` -> `Third declension` [class]
  - `κύων` -> `Third declension` [class]
- Zero-share examples:
  - `σκύλος` -> `Third declension` [class]
  - `σκύλος` -> `skŭ́lesĭ` [dative;plural]
  - `σκύλος` -> `skŭ́lesĭn` [dative;plural]

### hbo.sqlite

- Forms: `40,720`
- Word-count mismatch: `281` (`0.69%`) | `1_to_M=0` `M_to_1=281` `M_to_M_diff=0`
- Zero-shared characters: `17` (`0.04%`)
- Exact duplicate entries: `4` extra rows in `4` groups
- Mergeable headword duplicates: `32` extra rows in `32` groups
- Duplicate form rows within entry: `0` extra rows in `0` groups
- Mismatch examples:
  - `אֲבִי הָעֶזְרִי` -> `הָֽעֶזְרִֽי` [inflected]
  - `אֲבִי הָעֶזְרִי` -> `הָֽעֶזְרִי` [inflected]
  - `אֲבִי הָעֶזְרִי` -> `הָעֶזְרִֽי` [inflected]
- Zero-share examples:
  - `אִי` -> `ל` [inflected]
  - `כָּתַב` -> `וֹ` [inflected]
  - `מִן` -> `כֶּֽם` [inflected]

### he.sqlite

- Forms: `163,694`
- Word-count mismatch: `2,632` (`1.61%`) | `1_to_M=2,297` `M_to_1=184` `M_to_M_diff=151`
- Zero-shared characters: `2,056` (`1.26%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `5,387` extra rows in `5,269` groups
- Mismatch examples:
  - `ארץ` -> `form אָרֶץ` [Biblical-Hebrew;pausal]
  - `שמר` -> `אַל + Second person future tense` [imperative;negative]
  - `רב` -> `אַל + Second person future tense` [imperative;negative]
- Zero-share examples:
  - `ארץ` -> `קֶטֶל` [class]
  - `שמר` -> `אַל + Second person future tense` [imperative;negative]
  - `שמר` -> `קֶטֶל` [class]

### hi.sqlite

- Forms: `517,534`
- Word-count mismatch: `301,663` (`58.29%`) | `1_to_M=199,184` `M_to_1=213` `M_to_M_diff=102,266`
- Zero-shared characters: `13,923` (`2.69%`)
- Exact duplicate entries: `2` extra rows in `2` groups
- Mergeable headword duplicates: `2` extra rows in `2` groups
- Duplicate form rows within entry: `2,593` extra rows in `2,354` groups
- Mismatch examples:
  - `घृणा करना` -> `घृणा किया हुआ` [adjectival;direct;masculine;perfective;singular]
  - `घृणा करना` -> `घृणा किये हुए` [adjectival;masculine;oblique;perfective;singular]
  - `घृणा करना` -> `घृणा किये हुए` [adjectival;masculine;perfective;plural]
- Zero-share examples:
  - `विश्व` -> `وشوہ` [Urdu]
  - `विश्व` -> `وشوه` [Urdu]
  - `कुत्ता` -> `کُتّا` [Urdu]

### hy.sqlite

- Forms: `1,136,448`
- Word-count mismatch: `274,999` (`24.20%`) | `1_to_M=274,259` `M_to_1=441` `M_to_M_diff=299`
- Zero-shared characters: `415` (`0.04%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `2` extra rows in `2` groups
- Duplicate form rows within entry: `46,255` extra rows in `42,864` groups
- Mismatch examples:
  - `Հայաստանի Հանրապետություն` -> `Հայաստանի Հանրապետությունով (Hayastani Hanrapetutʻyamb, Hayastani Hanrapetutʻyunov*)` [instrumental;singular;singular-only]
  - `Հայաստանի Հանրապետություն` -> `Հայաստանի Հանրապետությունովս (Hayastani Hanrapetutʻyambs, Hayastani Hanrapetutʻyunovs*)` [first-person;instrumental;possessive;singular;singular-only]
  - `Հայաստանի Հանրապետություն` -> `Հայաստանի Հանրապետությունովդ (Hayastani Hanrapetutʻyambd, Hayastani Hanrapetutʻyunovd*)` [instrumental;possessive;second-person;singular;singular-only]
- Zero-share examples:
  - `ես` -> `իմ` [genitive;singular]
  - `ես` -> `ինձ` [dative;singular]
  - `ես` -> `ինձ` [accusative;singular]

### id.sqlite

- Forms: `44,154`
- Word-count mismatch: `6,825` (`15.46%`) | `1_to_M=5,625` `M_to_1=957` `M_to_M_diff=243`
- Zero-shared characters: `760` (`1.72%`)
- Exact duplicate entries: `11` extra rows in `10` groups
- Mergeable headword duplicates: `5` extra rows in `3` groups
- Duplicate form rows within entry: `275` extra rows in `218` groups
- Mismatch examples:
  - `gratis` -> `lebih gratis` [comparative]
  - `gratis` -> `paling gratis` [superlative]
  - `abdominal` -> `lebih abdominal` [comparative]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `f` -> `F` [uppercase]
  - `y` -> `Y` [uppercase]

### it.sqlite

- Forms: `1,133,527`
- Word-count mismatch: `149,450` (`13.18%`) | `1_to_M=146,928` `M_to_1=1,366` `M_to_M_diff=1,156`
- Zero-shared characters: `489` (`0.04%`)
- Exact duplicate entries: `33` extra rows in `33` groups
- Mergeable headword duplicates: `5` extra rows in `5` groups
- Duplicate form rows within entry: `39,308` extra rows in `37,757` groups
- Mismatch examples:
  - `i` -> `lo (l')` [masculine;singular]
  - `i` -> `la (l')` [feminine;singular]
  - `ipso facto` -> `issofatto` [alternative;vernacular]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `al` [redirect;alternative]
  - `A` -> `alla` [redirect;alternative]

### ja.sqlite

- Forms: `1,058,263`
- Word-count mismatch: `224,615` (`21.22%`) | `1_to_M=224,613` `M_to_1=2` `M_to_M_diff=0`
- Zero-shared characters: `513,993` (`48.57%`)
- Exact duplicate entries: `11` extra rows in `11` groups
- Mergeable headword duplicates: `24` extra rows in `23` groups
- Duplicate form rows within entry: `13,480` extra rows in `12,476` groups
- Mismatch examples:
  - `痛い` -> `itaku nai` [informal;negative]
  - `痛い` -> `itaku nakatta` [informal;negative;past]
  - `痛い` -> `itai desu` [formal]
- Zero-share examples:
  - `痛い` -> `itakaro` [imperfective;stem]
  - `痛い` -> `itaku` [continuative;stem]
  - `痛い` -> `itai` [stem;terminative]

### ko.sqlite

- Forms: `448,924`
- Word-count mismatch: `3,389` (`0.75%`) | `1_to_M=2,962` `M_to_1=416` `M_to_M_diff=11`
- Zero-shared characters: `56,704` (`12.63%`)
- Exact duplicate entries: `1` extra rows in `1` groups
- Mergeable headword duplicates: `25` extra rows in `14` groups
- Duplicate form rows within entry: `4,525` extra rows in `4,413` groups
- Mismatch examples:
  - `犬` -> `개 견` [eumhun]
  - `馬` -> `말 마` [eumhun]
  - `馬` -> `성 마` [eumhun]
- Zero-share examples:
  - `犬` -> `개 견` [eumhun]
  - `馬` -> `말 마` [eumhun]
  - `馬` -> `성 마` [eumhun]

### la.sqlite

- Forms: `2,546,142`
- Word-count mismatch: `54,725` (`2.15%`) | `1_to_M=54,218` `M_to_1=149` `M_to_M_diff=358`
- Zero-shared characters: `1,705` (`0.07%`)
- Exact duplicate entries: `192` extra rows in `191` groups
- Mergeable headword duplicates: `24` extra rows in `24` groups
- Duplicate form rows within entry: `4,203` extra rows in `4,144` groups
- Mismatch examples:
  - `pie` -> `magis piē` [comparative]
  - `pie` -> `maximē piē` [superlative]
  - `pie` -> `summē piē` [superlative]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `f` -> `F` [uppercase]
  - `a-` -> `ā-` [canonical]

### lzh-wiktionary.sqlite

- Forms: `293,770`
- Word-count mismatch: `107` (`0.04%`) | `1_to_M=72` `M_to_1=35` `M_to_M_diff=0`
- Zero-shared characters: `71,229` (`24.25%`)
- Exact duplicate entries: `13` extra rows in `13` groups
- Mergeable headword duplicates: `24` extra rows in `20` groups
- Duplicate form rows within entry: `373` extra rows in `332` groups
- Mismatch examples:
  - `thank you` -> `thankq` [alternative]
  - `thank you` -> `thank橋` [alternative]
  - `thank you` -> `thank桥` [alternative]
- Zero-share examples:
  - `book` -> `卜` [alternative]
  - `A` -> `a` [lowercase]
  - `A` -> `a` [lowercase]

### lzh.sqlite

- Forms: `82,663`
- Word-count mismatch: `1` (`0.00%`) | `1_to_M=0` `M_to_1=1` `M_to_M_diff=0`
- Zero-shared characters: `15,089` (`18.25%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `0` extra rows in `0` groups
- Mismatch examples:
  - `高樓 大廈` -> `高楼大厦` [Simplified-Chinese;alternative]
- Zero-share examples:
  - `鈔錢` -> `钞钱` [Simplified-Chinese;alternative]
  - `謙謙` -> `谦谦` [Simplified-Chinese;alternative]
  - `贈與` -> `赠与` [Simplified-Chinese;alternative]

### nl.sqlite

- Forms: `513,466`
- Word-count mismatch: `51,253` (`9.98%`) | `1_to_M=50,763` `M_to_1=364` `M_to_M_diff=126`
- Zero-shared characters: `10,336` (`2.01%`)
- Exact duplicate entries: `9` extra rows in `8` groups
- Mergeable headword duplicates: `9` extra rows in `9` groups
- Duplicate form rows within entry: `14,912` extra rows in `8,361` groups
- Mismatch examples:
  - `abject` -> `het abjectst` [adverbial;predicative;superlative]
  - `abject` -> `het abjectste` [adverbial;predicative;superlative]
  - `abrupt` -> `het abruptst` [adverbial;predicative;superlative]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `aa` [redirect;alternative]
  - `f` -> `F` [uppercase]

### pa.sqlite

- Forms: `106,325`
- Word-count mismatch: `50,942` (`47.91%`) | `1_to_M=50,252` `M_to_1=27` `M_to_M_diff=663`
- Zero-shared characters: `5,873` (`5.52%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `1` extra rows in `1` groups
- Duplicate form rows within entry: `73` extra rows in `70` groups
- Mismatch examples:
  - `پینا` -> `پِ کے` [conjunctive]
  - `پینا` -> `پِنْدے پِنْدے` [progressive]
  - `پینا` -> `پِݨ آلا` [error-unrecognized-form;participle]
- Zero-share examples:
  - `زبان` -> `ਜ਼ਬਾਨ` [Gurmukhi]
  - `اسلام` -> `ਇਸਲਾਮ` [Gurmukhi]
  - `پانی` -> `ਪਾਣੀ` [Gurmukhi]

### pt.sqlite

- Forms: `670,469`
- Word-count mismatch: `41,910` (`6.25%`) | `1_to_M=37,735` `M_to_1=837` `M_to_M_diff=3,338`
- Zero-shared characters: `704` (`0.10%`)
- Exact duplicate entries: `66` extra rows in `65` groups
- Mergeable headword duplicates: `27` extra rows in `27` groups
- Duplicate form rows within entry: `2,930` extra rows in `2,787` groups
- Mismatch examples:
  - `abater` -> `não abatas` [imperative;negative;second-person;singular]
  - `abater` -> `não abata` [imperative;negative;singular;third-person]
  - `abater` -> `não abatamos` [first-person;imperative;negative;plural]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `ao` [redirect;alternative]
  - `A` -> `na` [redirect;alternative]

### ru.sqlite

- Forms: `2,230,009`
- Word-count mismatch: `63,319` (`2.84%`) | `1_to_M=58,168` `M_to_1=4,684` `M_to_M_diff=467`
- Zero-shared characters: `108,087` (`4.85%`)
- Exact duplicate entries: `58` extra rows in `58` groups
- Mergeable headword duplicates: `9` extra rows in `9` groups
- Duplicate form rows within entry: `17,945` extra rows in `14,350` groups
- Mismatch examples:
  - `к` -> `к (k)` [canonical]
  - `к` -> `к (k)` [canonical]
  - `к` -> `к (k)` [canonical]
- Zero-share examples:
  - `собака` -> `velar-stem` [class]
  - `собака` -> `accent-a` [class]
  - `собака` -> `velar-stem` [class]

### sw.sqlite

- Forms: `356,739`
- Word-count mismatch: `67,487` (`18.92%`) | `1_to_M=67,168` `M_to_1=189` `M_to_M_diff=130`
- Zero-shared characters: `273` (`0.08%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `1` extra rows in `1` groups
- Duplicate form rows within entry: `3,021` extra rows in `3,010` groups
- Mismatch examples:
  - `fa` -> `positive subject concord + -likufa` [past]
  - `fa` -> `negative subject concord + -kufa` [negative;past]
  - `fa` -> `positive subject concord + -nakufa` [present;third-person]
- Zero-share examples:
  - `kilo` -> `VII` [canonical]
  - `Papa` -> `IX` [canonical]
  - `Papa` -> `X` [plural]

### ta.sqlite

- Forms: `330,620`
- Word-count mismatch: `11,672` (`3.53%`) | `1_to_M=11,477` `M_to_1=82` `M_to_M_diff=113`
- Zero-shared characters: `60` (`0.02%`)
- Exact duplicate entries: `2` extra rows in `2` groups
- Mergeable headword duplicates: `1` extra rows in `1` groups
- Duplicate form rows within entry: `3,446` extra rows in `3,315` groups
- Mismatch examples:
  - `அடி` -> `past of அடித்துவிடு (aṭittuviṭu)` [imperative;perfect;present;singular]
  - `அடி` -> `past of அடித்துவிட்டிரு (aṭittuviṭṭiru)` [past;perfect]
  - `அடி` -> `future of அடித்துவிடு (aṭittuviṭu)` [future;imperative;perfect;plural]
- Zero-share examples:
  - `ஃ` -> `அக்கு` [redirect;alternative]
  - `ࢳ` -> `equivalent ங` [Tamil]
  - `மாதம்` -> `௴` [alternative]

### th.sqlite

- Forms: `11,351`
- Word-count mismatch: `59` (`0.52%`) | `1_to_M=55` `M_to_1=2` `M_to_M_diff=2`
- Zero-shared characters: `912` (`8.03%`)
- Exact duplicate entries: `1` extra rows in `1` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `234` extra rows in `183` groups
- Mismatch examples:
  - `ตุ๊ก ๆ` -> `ตุ๊กตุ๊ก` [redirect;alternative]
  - `ทุก ๆ` -> `ทุกทุก` [redirect;alternative]
  - `ภูมิศาสตร์` -> `ภูมิ ศาสตร์` [canonical]
- Zero-share examples:
  - `วัด` -> `แห่ง` [classifier]
  - `จาน` -> `ใบ` [classifier]
  - `จาน` -> `ลูก` [classifier]

### tl.sqlite

- Forms: `207,259`
- Word-count mismatch: `2,857` (`1.38%`) | `1_to_M=2,023` `M_to_1=501` `M_to_M_diff=333`
- Zero-shared characters: `49,372` (`23.82%`)
- Exact duplicate entries: `16` extra rows in `15` groups
- Mergeable headword duplicates: `20` extra rows in `18` groups
- Duplicate form rows within entry: `7,095` extra rows in `6,441` groups
- Mismatch examples:
  - `Saudi Arabia` -> `Saudi` [redirect;alternative]
  - `Hong Kong` -> `Hongkong` [alternative]
  - `Hong Kong` -> `Hongkong` [redirect;alternative]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `A` -> `ᜀ` [redirect;alternative]
  - `A` -> `ᜀ` [redirect;alternative]

### tr.sqlite

- Forms: `3,115,794`
- Word-count mismatch: `36,396` (`1.17%`) | `1_to_M=31,632` `M_to_1=755` `M_to_M_diff=4,009`
- Zero-shared characters: `540` (`0.02%`)
- Exact duplicate entries: `1` extra rows in `1` groups
- Mergeable headword duplicates: `1` extra rows in `1` groups
- Duplicate form rows within entry: `837` extra rows in `726` groups
- Mismatch examples:
  - `sol` -> `sol muyum"` [error-unrecognized-form;first-person;present;singular]
  - `sol` -> `sol musun"` [error-unrecognized-form;present;second-person;singular]
  - `sol` -> `sol mu"` [error-unrecognized-form;present;singular;third-person]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `f` -> `F` [uppercase]
  - `y` -> `Y` [uppercase]

### ur.sqlite

- Forms: `67,678`
- Word-count mismatch: `36,407` (`53.79%`) | `1_to_M=29,811` `M_to_1=580` `M_to_M_diff=6,016`
- Zero-shared characters: `9,971` (`14.73%`)
- Exact duplicate entries: `0` extra rows in `0` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `439` extra rows in `439` groups
- Mismatch examples:
  - `کیا` -> `کِس نے` [ergative;singular]
  - `کیا` -> `کِنَھوں نے` [ergative;plural]
  - `کیا` -> `کس کا` [genitive;singular]
- Zero-share examples:
  - `کیا` -> `क्या` [Hindi]
  - `کیا` -> `क्या` [Hindi]
  - `کیا` -> `किया` [Hindi]

### vi.sqlite

- Forms: `24,834`
- Word-count mismatch: `5,361` (`21.59%`) | `1_to_M=379` `M_to_1=4,738` `M_to_M_diff=244`
- Zero-shared characters: `15,488` (`62.37%`)
- Exact duplicate entries: `2` extra rows in `2` groups
- Mergeable headword duplicates: `0` extra rows in `0` groups
- Duplicate form rows within entry: `216` extra rows in `200` groups
- Mismatch examples:
  - `OK` -> `ô kê` [alternative]
  - `OK` -> `ô kê` [alternative]
  - `modem` -> `mô đêm` [alternative]
- Zero-share examples:
  - `A` -> `a` [lowercase]
  - `may` -> `𦁼` [CJK]
  - `may` -> `埋` [CJK]

### zh-Hant.sqlite

- Forms: `293,770`
- Word-count mismatch: `107` (`0.04%`) | `1_to_M=72` `M_to_1=35` `M_to_M_diff=0`
- Zero-shared characters: `71,229` (`24.25%`)
- Exact duplicate entries: `13` extra rows in `13` groups
- Mergeable headword duplicates: `24` extra rows in `20` groups
- Duplicate form rows within entry: `373` extra rows in `332` groups
- Mismatch examples:
  - `thank you` -> `thankq` [alternative]
  - `thank you` -> `thank橋` [alternative]
  - `thank you` -> `thank桥` [alternative]
- Zero-share examples:
  - `book` -> `卜` [alternative]
  - `A` -> `a` [lowercase]
  - `A` -> `a` [lowercase]

### zh.sqlite

- Forms: `293,770`
- Word-count mismatch: `107` (`0.04%`) | `1_to_M=72` `M_to_1=35` `M_to_M_diff=0`
- Zero-shared characters: `71,229` (`24.25%`)
- Exact duplicate entries: `13` extra rows in `13` groups
- Mergeable headword duplicates: `24` extra rows in `20` groups
- Duplicate form rows within entry: `373` extra rows in `332` groups
- Mismatch examples:
  - `thank you` -> `thankq` [alternative]
  - `thank you` -> `thank橋` [alternative]
  - `thank you` -> `thank桥` [alternative]
- Zero-share examples:
  - `book` -> `卜` [alternative]
  - `A` -> `a` [lowercase]
  - `A` -> `a` [lowercase]
