# Wiktionary DB Form Tagset Audit

## Scope

- Generated from: `tmp_wiktionary_db_audit_2026-04-11.json`
- This report focuses on `forms.morph_tags` and tag-derived anomaly signals.

## Flagging Heuristic

- A full `tagset` is flagged when any of the following holds:
  - it appears on at least `20` rows and at least `95%` of those rows have a headword/form word-count mismatch
  - it appears on at least `20` rows and at least `95%` of those rows have zero shared characters with the headword
  - it contains the tag `class`
- An individual `tag` is flagged when any of the following holds:
  - the tag is `class`
  - it appears on at least `50` rows and at least `95%` of those rows have a headword/form word-count mismatch
  - it appears on at least `50` rows and at least `95%` of those rows have zero shared characters with the headword
- A flag means "strong review target", not "delete blindly". Some flags are real metadata leakage; others are productive multiword constructions or cross-script alternants.

## Cross-Language Recurring Flags

### Individual Tags

| Tag | Total Rows Across DBs | DB Count | Example DBs |
| --- | ---: | ---: | --- |
| `includes-article` | 910,698 | 1 | `de.sqlite` (910,698) |
| `multiword-construction` | 792,607 | 3 | `de.sqlite` (701,100), `fr.sqlite` (91,303), `la.sqlite` (204) |
| `weak` | 467,751 | 1 | `de.sqlite` (467,751) |
| `future` | 448,886 | 5 | `de.sqlite` (421,439), `el.sqlite` (10,185), `fa.sqlite` (8,154), `sw.sqlite` (6,116) |
| `future-ii` | 217,817 | 1 | `de.sqlite` (217,817) |
| `perfect` | 206,720 | 5 | `de.sqlite` (139,067), `fr.sqlite` (22,772), `hy.sqlite` (36,900), `sw.sqlite` (3,058) |
| `pluperfect` | 206,144 | 4 | `de.sqlite` (140,594), `fa.sqlite` (13,506), `fr.sqlite` (15,180), `hy.sqlite` (36,864) |
| `future-i` | 203,622 | 1 | `de.sqlite` (203,622) |
| `negative` | 144,744 | 3 | `de.sqlite` (108,552), `he.sqlite` (2,066), `pt.sqlite` (34,126) |
| `class` | 137,764 | 12 | `ang.sqlite` (3,720), `de.sqlite` (6,739), `el.sqlite` (9), `es.sqlite` (5,009) |
| `definite` | 92,536 | 1 | `ga.sqlite` (92,536) |
| `presumptive` | 64,940 | 3 | `hi.sqlite` (49,868), `pa.sqlite` (8,940), `ur.sqlite` (6,132) |
| `past` | 39,952 | 3 | `pa.sqlite` (19,836), `sw.sqlite` (12,232), `ur.sqlite` (7,884) |
| `present` | 37,686 | 2 | `pa.sqlite` (26,904), `ur.sqlite` (10,782) |
| `Baybayin` | 35,364 | 1 | `tl.sqlite` (35,364) |
| `progressive` | 29,716 | 2 | `el.sqlite` (2,955), `fa.sqlite` (26,761) |
| `adjectival` | 20,952 | 3 | `hi.sqlite` (16,494), `pa.sqlite` (4,164), `ur.sqlite` (294) |
| `hanja` | 16,991 | 1 | `ko.sqlite` (16,991) |
| `hangeul` | 13,446 | 1 | `ko.sqlite` (13,446) |
| `irrealis` | 12,232 | 1 | `sw.sqlite` (12,232) |

### Full Tagsets

| Tagset | Total Rows Across DBs | DB Count | Example DBs |
| --- | ---: | ---: | --- |
| `class` | 131,025 | 11 | `ang.sqlite` (3,720), `el.sqlite` (9), `es.sqlite` (5,009), `ga.sqlite` (4) |
| `Baybayin` | 35,364 | 1 | `tl.sqlite` (35,364) |
| `dative;definite;singular` | 30,629 | 1 | `ga.sqlite` (30,629) |
| `hanja` | 16,991 | 1 | `ko.sqlite` (16,991) |
| `accusative;definite;includes-article;masculine;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `accusative;definite;includes-article;plural;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `accusative;includes-article;indefinite;masculine;mixed;singular` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;definite;feminine;includes-article;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;definite;includes-article;masculine;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;definite;includes-article;neuter;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;definite;includes-article;plural;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;feminine;includes-article;indefinite;mixed;singular` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;includes-article;indefinite;masculine;mixed;singular` | 16,262 | 1 | `de.sqlite` (16,262) |
| `dative;includes-article;indefinite;mixed;neuter;singular` | 16,262 | 1 | `de.sqlite` (16,262) |
| `definite;feminine;genitive;includes-article;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `definite;genitive;includes-article;masculine;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `definite;genitive;includes-article;neuter;singular;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `definite;genitive;includes-article;plural;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `definite;includes-article;nominative;plural;weak` | 16,262 | 1 | `de.sqlite` (16,262) |
| `feminine;genitive;includes-article;indefinite;mixed;singular` | 16,262 | 1 | `de.sqlite` (16,262) |

## Per-Language Tag Audit

### ang.sqlite

- Distinct full tagsets: `154`
- Distinct individual tags: `49`
- Flagged tagsets kept in this report: `2`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 32,703 | 0.02% | 0.03% |
| `nominative;plural` | 10,465 | 0.08% | 0.14% |
| `alternative` | 10,370 | 0.49% | 1.65% |
| `accusative;plural` | 9,511 | 0.08% | 0.15% |
| `accusative;singular` | 8,357 | 0.06% | 0.18% |
| `genitive;singular` | 8,232 | 0.06% | 0.15% |
| `dative;singular` | 8,179 | 0.07% | 0.15% |
| `nominative;singular` | 8,105 | 0.01% | 0.07% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 152,042 | 0.01% | 0.21% |
| `plural` | 151,466 | 0.02% | 0.17% |
| `feminine` | 65,191 | 0.00% | 0.12% |
| `neuter` | 61,063 | 0.00% | 0.14% |
| `masculine` | 59,432 | 0.00% | 0.13% |
| `nominative` | 56,971 | 0.02% | 0.22% |
| `genitive` | 54,651 | 0.02% | 0.16% |
| `accusative` | 54,537 | 0.02% | 0.27% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 3,720 | 2.93% | 96.72% | >=95% zero-char-overlap, contains class |
| `lowercase` | 21 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 3,720 | 2.93% | 96.72% | tag is class, >=95% zero-char-overlap |

### ar.sqlite

- Distinct full tagsets: `2,195`
- Distinct individual tags: `108`
- Flagged tagsets kept in this report: `0`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `noun-from-verb` | 17,780 | 0.01% | 0.06% |
| `canonical;masculine` | 11,379 | 0.14% | 0.00% |
| `definite;nominative;singular;triptote` | 10,116 | 0.02% | 0.02% |
| `definite;genitive;singular;triptote` | 10,116 | 0.02% | 0.02% |
| `accusative;definite;singular;triptote` | 10,114 | 0.02% | 0.02% |
| `definite;informal;singular;triptote` | 10,112 | 0.02% | 0.04% |
| `indefinite;informal;singular;triptote` | 9,490 | 0.00% | 0.08% |
| `construct;informal;singular;triptote` | 9,487 | 1.58% | 0.08% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 716,533 | 0.23% | 0.03% |
| `feminine` | 594,615 | 0.07% | 0.03% |
| `masculine` | 561,019 | 0.01% | 0.09% |
| `plural` | 532,233 | 0.14% | 0.12% |
| `active` | 523,872 | 0.00% | 0.04% |
| `triptote` | 467,653 | 0.43% | 0.06% |
| `indicative` | 376,052 | 0.00% | 0.03% |
| `dual` | 364,948 | 0.17% | 0.01% |

Flagged tagsets: none under the current heuristic.

Flagged individual tags: none under the current heuristic.

### bn.sqlite

- Distinct full tagsets: `137`
- Distinct individual tags: `69`
- Flagged tagsets kept in this report: `3`
- Flagged individual tags kept in this report: `3`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `alternative` | 4,368 | 3.07% | 1.53% |
| `definite;locative;plural` | 4,250 | 15.51% | 0.02% |
| `definite;locative;singular` | 3,679 | 17.91% | 0.03% |
| `definite;objective;plural` | 3,500 | 18.86% | 0.03% |
| `definite;nominative;plural` | 3,262 | 20.20% | 0.03% |
| `definite;genitive;plural` | 3,262 | 20.20% | 0.03% |
| `` | 2,931 | 99.97% | 74.92% |
| `definite;nominative;singular` | 2,929 | 30.59% | 0.03% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `definite` | 26,740 | 22.38% | 0.03% |
| `plural` | 14,858 | 17.77% | 0.03% |
| `singular` | 13,000 | 25.75% | 0.03% |
| `objective` | 10,531 | 29.83% | 0.04% |
| `locative` | 10,486 | 17.25% | 0.02% |
| `familiar` | 9,473 | 1.14% | 0.22% |
| `second-person` | 9,469 | 1.10% | 0.22% |
| `genitive` | 8,404 | 18.56% | 0.02% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `` | 2,931 | 99.97% | 74.92% | >=95% word-count mismatch |
| `comparative` | 1,514 | 100.00% | 0.00% | >=95% word-count mismatch |
| `superlative` | 1,514 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `` | 2,931 | 99.97% | 74.92% | >=95% word-count mismatch |
| `comparative` | 1,514 | 100.00% | 0.00% | >=95% word-count mismatch |
| `superlative` | 1,514 | 100.00% | 0.00% | >=95% word-count mismatch |

### de.sqlite

- Distinct full tagsets: `3,629`
- Distinct individual tags: `165`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `10`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `dative;singular` | 88,000 | 0.08% | 0.01% |
| `genitive;singular` | 86,031 | 0.08% | 0.02% |
| `genitive` | 80,619 | 0.01% | 0.00% |
| `accusative;singular` | 75,104 | 0.08% | 0.01% |
| `nominative;singular` | 75,010 | 0.08% | 0.01% |
| `definite;genitive;plural` | 59,886 | 0.07% | 0.02% |
| `definite;nominative;plural` | 59,884 | 0.07% | 0.02% |
| `accusative;definite;plural` | 59,884 | 0.07% | 0.02% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 2,058,533 | 53.71% | 0.01% |
| `plural` | 1,342,899 | 46.77% | 0.01% |
| `includes-article` | 910,698 | 99.93% | 0.00% |
| `definite` | 711,400 | 64.57% | 0.01% |
| `multiword-construction` | 701,100 | 99.84% | 0.00% |
| `genitive` | 624,972 | 36.70% | 0.02% |
| `subjunctive` | 611,555 | 75.13% | 0.00% |
| `mixed` | 581,534 | 78.26% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `accusative;definite;includes-article;masculine;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `accusative;definite;includes-article;plural;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `accusative;includes-article;indefinite;masculine;mixed;singular` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;definite;feminine;includes-article;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;definite;includes-article;masculine;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;definite;includes-article;neuter;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;definite;includes-article;plural;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;feminine;includes-article;indefinite;mixed;singular` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;includes-article;indefinite;masculine;mixed;singular` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `dative;includes-article;indefinite;mixed;neuter;singular` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `definite;feminine;genitive;includes-article;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |
| `definite;genitive;includes-article;masculine;singular;weak` | 16,262 | 99.95% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `includes-article` | 910,698 | 99.93% | 0.00% | >=95% word-count mismatch |
| `multiword-construction` | 701,100 | 99.84% | 0.00% | >=95% word-count mismatch |
| `weak` | 467,751 | 97.27% | 0.00% | >=95% word-count mismatch |
| `future` | 421,439 | 99.90% | 0.00% | >=95% word-count mismatch |
| `future-ii` | 217,817 | 99.99% | 0.00% | >=95% word-count mismatch |
| `future-i` | 203,622 | 99.80% | 0.00% | >=95% word-count mismatch |
| `pluperfect` | 140,594 | 99.76% | 0.00% | >=95% word-count mismatch |
| `perfect` | 139,067 | 99.76% | 0.00% | >=95% word-count mismatch |
| `negative` | 108,552 | 99.95% | 0.00% | >=95% word-count mismatch |
| `class` | 6,739 | 96.44% | 0.00% | tag is class, >=95% word-count mismatch |

### el.sqlite

- Distinct full tagsets: `660`
- Distinct individual tags: `93`
- Flagged tagsets kept in this report: `22`
- Flagged individual tags kept in this report: `7`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `genitive;singular` | 17,185 | 0.05% | 0.00% |
| `singular;vocative` | 16,660 | 0.02% | 0.00% |
| `accusative;singular` | 16,554 | 0.05% | 0.02% |
| `nominative;singular` | 16,549 | 0.05% | 0.00% |
| `accusative;plural` | 14,813 | 0.09% | 0.01% |
| `nominative;plural` | 14,653 | 0.09% | 0.01% |
| `plural;vocative` | 14,643 | 0.07% | 0.01% |
| `genitive;plural` | 13,626 | 0.10% | 0.03% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 236,209 | 0.44% | 0.75% |
| `singular` | 218,583 | 3.49% | 0.14% |
| `indicative` | 120,829 | 6.99% | 1.27% |
| `active` | 80,117 | 9.80% | 2.92% |
| `accusative` | 77,636 | 0.04% | 0.23% |
| `nominative` | 77,316 | 0.03% | 0.20% |
| `genitive` | 77,268 | 0.03% | 0.23% |
| `vocative` | 77,113 | 0.02% | 0.03% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `active;first-person;future;imperfective;indicative;progressive;singular` | 1,908 | 100.00% | 0.00% | >=95% word-count mismatch |
| `active;first-person;future;indicative;perfective;singular` | 1,857 | 96.77% | 0.00% | >=95% word-count mismatch |
| `active;future;imperfective;perfective;subjunctive` | 1,452 | 100.00% | 76.79% | >=95% word-count mismatch |
| `active;participle;past` | 1,343 | 97.92% | 0.00% | >=95% word-count mismatch |
| `continuative;first-person;future;imperfective;indicative;passive;singular` | 1,314 | 100.00% | 0.00% | >=95% word-count mismatch |
| `continuative;future;imperfective;perfective;progressive;subjunctive` | 897 | 100.00% | 77.15% | >=95% word-count mismatch |
| `active;indeclinable;participle;perfect` | 481 | 99.17% | 0.00% | >=95% word-count mismatch |
| `future;imperfective;passive;perfective;subjunctive` | 432 | 100.00% | 66.67% | >=95% word-count mismatch |
| `` | 406 | 99.75% | 6.65% | >=95% word-count mismatch |
| `first-person;future;imperfective;indicative;passive;progressive;singular` | 144 | 100.00% | 0.00% | >=95% word-count mismatch |
| `active;future;imperfective;indicative;plural;third-person` | 90 | 98.89% | 0.00% | >=95% word-count mismatch |
| `literally` | 71 | 74.65% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `future` | 10,185 | 97.18% | 21.12% | >=95% word-count mismatch |
| `progressive` | 2,955 | 99.97% | 23.42% | >=95% word-count mismatch |
| `subjunctive` | 2,858 | 100.00% | 74.35% | >=95% word-count mismatch |
| `continuative` | 2,239 | 99.91% | 31.67% | >=95% word-count mismatch |
| `` | 406 | 99.75% | 6.65% | >=95% word-count mismatch |
| `literally` | 73 | 73.97% | 100.00% | >=95% zero-char-overlap |
| `class` | 9 | 100.00% | 100.00% | tag is class |

### es.sqlite

- Distinct full tagsets: `738`
- Distinct individual tags: `130`
- Flagged tagsets kept in this report: `2`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 68,473 | 0.01% | 0.00% |
| `feminine` | 30,070 | 0.00% | 0.00% |
| `feminine;plural` | 30,044 | 0.00% | 0.00% |
| `masculine;plural` | 24,204 | 0.00% | 0.00% |
| `accusative;combined-form;formal;imperative;object-singular;object-third-person;second-person;singular` | 20,163 | 0.00% | 0.11% |
| `accusative;combined-form;formal;imperative;object-plural;object-third-person;plural;second-person` | 20,163 | 0.00% | 0.11% |
| `accusative;combined-form;infinitive;object-singular;object-third-person` | 20,091 | 0.00% | 0.00% |
| `accusative;combined-form;infinitive;object-plural;object-third-person` | 20,091 | 0.00% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `combined-form` | 723,812 | 0.01% | 0.05% |
| `plural` | 705,978 | 2.07% | 0.04% |
| `second-person` | 627,085 | 1.64% | 0.05% |
| `imperative` | 616,658 | 0.55% | 0.07% |
| `singular` | 604,334 | 2.72% | 0.05% |
| `accusative` | 415,524 | 0.01% | 0.06% |
| `object-third-person` | 402,204 | 0.01% | 0.05% |
| `object-plural` | 361,914 | 0.01% | 0.06% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 5,009 | 99.86% | 0.00% | >=95% word-count mismatch, contains class |
| `masculine;singular` | 23 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 5,009 | 99.86% | 0.00% | tag is class, >=95% word-count mismatch |

### fa.sqlite

- Distinct full tagsets: `258`
- Distinct individual tags: `90`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `5`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `first-person;indicative;past;singular` | 4,454 | 1.21% | 0.00% |
| `indicative;past;second-person;singular` | 4,454 | 1.21% | 0.00% |
| `first-person;indicative;past;plural` | 4,454 | 1.21% | 0.00% |
| `indicative;past;plural;second-person` | 4,454 | 1.21% | 0.00% |
| `indicative;past;plural;third-person` | 4,454 | 1.21% | 0.00% |
| `indicative;past;singular;third-person` | 4,452 | 1.21% | 0.00% |
| `Tajik` | 4,216 | 97.44% | 100.00% |
| `error-unrecognized-form;indicative` | 3,874 | 51.81% | 50.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `indicative` | 123,241 | 43.59% | 3.02% |
| `plural` | 79,017 | 42.21% | 0.01% |
| `singular` | 76,020 | 44.33% | 0.04% |
| `past` | 59,538 | 46.12% | 1.24% |
| `present` | 59,532 | 25.93% | 0.76% |
| `second-person` | 52,512 | 41.03% | 0.02% |
| `first-person` | 48,056 | 44.31% | 0.00% |
| `third-person` | 47,836 | 46.60% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Tajik` | 4,216 | 97.44% | 100.00% | >=95% word-count mismatch, >=95% zero-char-overlap |
| `indicative;present;progressive;singular;third-person` | 2,240 | 99.82% | 0.00% | >=95% word-count mismatch |
| `first-person;indicative;past;plural;progressive` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `first-person;indicative;past;progressive;singular` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `first-person;indicative;plural;present;progressive` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `first-person;indicative;present;progressive;singular` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;past;plural;progressive;second-person` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;past;plural;progressive;third-person` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;past;progressive;second-person;singular` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;past;progressive;singular;third-person` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;plural;present;progressive;second-person` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |
| `indicative;plural;present;progressive;third-person` | 2,227 | 99.87% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `progressive` | 26,761 | 99.86% | 0.04% | >=95% word-count mismatch |
| `pluperfect` | 13,506 | 99.82% | 0.00% | >=95% word-count mismatch |
| `future` | 8,154 | 99.78% | 0.00% | >=95% word-count mismatch |
| `Tajik` | 4,243 | 96.82% | 99.41% | >=95% word-count mismatch, >=95% zero-char-overlap |
| `direct-object` | 342 | 100.00% | 0.00% | >=95% word-count mismatch |

### fr.sqlite

- Distinct full tagsets: `257`
- Distinct individual tags: `104`
- Flagged tagsets kept in this report: `25`
- Flagged individual tags kept in this report: `4`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 58,387 | 0.02% | 0.02% |
| `feminine` | 18,933 | 0.04% | 0.01% |
| `feminine;plural` | 15,465 | 0.03% | 0.00% |
| `masculine;plural` | 15,457 | 0.02% | 0.00% |
| `alternative` | 10,885 | 8.92% | 1.24% |
| `conditional;first-person;plural` | 8,605 | 1.26% | 0.02% |
| `conditional;plural;second-person` | 8,604 | 1.26% | 0.00% |
| `future;indicative;singular;third-person` | 8,533 | 0.16% | 0.04% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 297,032 | 6.79% | 0.03% |
| `indicative` | 230,568 | 15.28% | 0.04% |
| `singular` | 190,316 | 5.89% | 0.05% |
| `second-person` | 148,440 | 12.32% | 0.03% |
| `first-person` | 132,897 | 8.03% | 0.05% |
| `present` | 121,139 | 14.63% | 0.09% |
| `third-person` | 116,595 | 2.06% | 0.04% |
| `subjunctive` | 113,129 | 15.53% | 0.04% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `gerund;multiword-construction;participle;present` | 7,501 | 98.75% | 0.15% | >=95% word-count mismatch |
| `anterior;indicative;multiword-construction;past` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `conditional;multiword-construction;perfect` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `first-person;imperative;multiword-construction;plural` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;indicative;multiword-construction;perfect` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `imperative;multiword-construction;plural;second-person` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `imperative;multiword-construction;second-person;singular` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `indicative;multiword-construction;perfect;present` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `indicative;multiword-construction;pluperfect` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `multiword-construction;past;subjunctive` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `multiword-construction;pluperfect;subjunctive` | 7,430 | 100.00% | 0.00% | >=95% word-count mismatch |
| `infinitive;multiword-construction` | 7,430 | 99.69% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `multiword-construction` | 91,303 | 99.72% | 0.08% | >=95% word-count mismatch |
| `perfect` | 22,772 | 99.99% | 0.00% | >=95% word-count mismatch |
| `pluperfect` | 15,180 | 100.00% | 0.00% | >=95% word-count mismatch |
| `anterior` | 7,590 | 100.00% | 0.00% | >=95% word-count mismatch |

### ga.sqlite

- Distinct full tagsets: `337`
- Distinct individual tags: `95`
- Flagged tagsets kept in this report: `38`
- Flagged individual tags kept in this report: `3`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `error-unrecognized-form` | 67,333 | 0.01% | 0.00% |
| `dative;definite;singular` | 30,629 | 99.98% | 0.08% |
| `definite;genitive;singular` | 15,320 | 99.96% | 0.10% |
| `definite;nominative;singular` | 15,319 | 99.97% | 0.08% |
| `genitive;indefinite;singular` | 15,192 | 0.02% | 0.18% |
| `dative;indefinite;singular` | 15,192 | 0.02% | 0.16% |
| `indefinite;nominative;singular` | 15,190 | 0.02% | 0.14% |
| `indefinite;singular;vocative` | 15,188 | 99.91% | 0.16% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 264,702 | 44.30% | 3.39% |
| `plural` | 197,676 | 48.80% | 0.09% |
| `error-unrecognized-form` | 110,261 | 18.99% | 0.03% |
| `indefinite` | 101,035 | 24.81% | 0.20% |
| `definite` | 92,536 | 99.98% | 0.10% |
| `indicative` | 90,705 | 51.43% | 4.89% |
| `genitive` | 86,995 | 29.52% | 0.09% |
| `dative` | 85,619 | 49.05% | 0.12% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `dative;definite;singular` | 30,629 | 99.98% | 0.08% | >=95% word-count mismatch |
| `definite;genitive;singular` | 15,320 | 99.96% | 0.10% | >=95% word-count mismatch |
| `definite;nominative;singular` | 15,319 | 99.97% | 0.08% | >=95% word-count mismatch |
| `indefinite;singular;vocative` | 15,188 | 99.91% | 0.16% | >=95% word-count mismatch |
| `definite;nominative;plural` | 9,959 | 99.97% | 0.14% | >=95% word-count mismatch |
| `dative;definite;plural` | 9,956 | 100.00% | 0.13% | >=95% word-count mismatch |
| `definite;genitive;plural` | 9,955 | 99.97% | 0.12% | >=95% word-count mismatch |
| `indefinite;plural;vocative` | 9,881 | 99.86% | 0.23% | >=95% word-count mismatch |
| `error-unrecognized-form;future` | 4,623 | 100.00% | 0.02% | >=95% word-count mismatch |
| `conditional;plural;second-person` | 4,329 | 99.95% | 0.00% | >=95% word-count mismatch |
| `comparative;error-unrecognized-form` | 3,669 | 99.97% | 0.08% | >=95% word-count mismatch |
| `error-unrecognized-form;superlative` | 3,669 | 99.97% | 0.11% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `definite` | 92,536 | 99.98% | 0.10% | >=95% word-count mismatch |
| `superlative` | 3,669 | 99.97% | 0.11% | >=95% word-count mismatch |
| `class` | 4 | 100.00% | 0.00% | tag is class |

### grc.sqlite

- Distinct full tagsets: `525`
- Distinct individual tags: `103`
- Flagged tagsets kept in this report: `3`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 24,882 | 3.58% | 6.57% |
| `dative;plural` | 24,138 | 3.14% | 37.33% |
| `active;indicative;singular;third-person` | 21,412 | 0.00% | 1.27% |
| `active;indicative;plural;third-person` | 20,899 | 0.02% | 1.13% |
| `class` | 18,946 | 99.94% | 100.00% |
| `dative;neuter;plural` | 16,353 | 0.01% | 38.64% |
| `active;optative;singular;third-person` | 16,305 | 0.01% | 0.95% |
| `active;plural;subjunctive;third-person` | 14,886 | 0.00% | 0.28% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 465,131 | 2.64% | 6.12% |
| `singular` | 439,401 | 2.38% | 0.99% |
| `active` | 381,013 | 0.01% | 0.91% |
| `middle` | 346,107 | 7.54% | 1.50% |
| `dual` | 322,383 | 2.03% | 1.15% |
| `third-person` | 310,172 | 3.55% | 0.98% |
| `passive` | 307,387 | 8.38% | 1.54% |
| `second-person` | 290,169 | 3.25% | 1.42% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 18,946 | 99.94% | 100.00% | >=95% word-count mismatch, >=95% zero-char-overlap, contains class |
| `uppercase` | 32 | 0.00% | 100.00% | >=95% zero-char-overlap |
| `lowercase` | 30 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 18,946 | 99.94% | 100.00% | tag is class, >=95% word-count mismatch, >=95% zero-char-overlap |

### hbo.sqlite

- Distinct full tagsets: `1`
- Distinct individual tags: `1`
- Flagged tagsets kept in this report: `0`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `inflected` | 40,720 | 0.69% | 0.04% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `inflected` | 40,720 | 0.69% | 0.04% |

Flagged tagsets: none under the current heuristic.

Flagged individual tags: none under the current heuristic.

### he.sqlite

- Distinct full tagsets: `129`
- Distinct individual tags: `41`
- Flagged tagsets kept in this report: `3`
- Flagged individual tags kept in this report: `4`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 7,173 | 1.62% | 0.00% |
| `indefinite;plural` | 6,005 | 0.48% | 0.00% |
| `canonical;masculine` | 5,357 | 1.25% | 0.00% |
| `feminine;possessed-form;second-person;singular` | 5,244 | 0.00% | 0.00% |
| `feminine;first-person;masculine;possessed-form;singular` | 5,231 | 0.00% | 0.00% |
| `construct;singular` | 4,570 | 0.37% | 0.00% |
| `masculine;plural;possessed-form;third-person` | 3,895 | 0.00% | 0.00% |
| `feminine;plural;possessed-form;third-person` | 3,895 | 0.00% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `feminine` | 73,412 | 0.10% | 0.02% |
| `masculine` | 72,286 | 0.15% | 0.02% |
| `plural` | 66,279 | 0.12% | 0.01% |
| `singular` | 66,164 | 0.07% | 0.02% |
| `possessed-form` | 41,563 | 0.00% | 0.00% |
| `second-person` | 37,985 | 0.04% | 0.02% |
| `third-person` | 34,172 | 0.04% | 0.02% |
| `future` | 25,733 | 0.07% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 2,186 | 0.00% | 23.92% | contains class |
| `imperative;negative` | 2,066 | 100.00% | 71.30% | >=95% word-count mismatch |
| `Biblical-Hebrew;pausal` | 82 | 97.56% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 2,186 | 0.00% | 23.92% | tag is class |
| `negative` | 2,066 | 100.00% | 71.30% | >=95% word-count mismatch |
| `Biblical-Hebrew` | 87 | 96.55% | 0.00% | >=95% word-count mismatch |
| `pausal` | 84 | 97.62% | 0.00% | >=95% word-count mismatch |

### hi.sqlite

- Distinct full tagsets: `244`
- Distinct individual tags: `73`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `3`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `oblique;singular` | 14,815 | 0.22% | 0.44% |
| `singular;vocative` | 14,815 | 0.22% | 0.44% |
| `direct;singular` | 14,699 | 0.22% | 0.41% |
| `direct;plural` | 13,632 | 0.25% | 0.37% |
| `oblique;plural` | 13,478 | 0.24% | 0.37% |
| `plural;vocative` | 13,475 | 0.24% | 0.37% |
| `Urdu` | 11,004 | 5.75% | 100.00% |
| `counterfactual;formal;masculine;past;plural;second-person` | 6,597 | 75.02% | 0.39% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 272,806 | 64.15% | 0.60% |
| `feminine` | 216,046 | 71.10% | 0.65% |
| `masculine` | 212,582 | 69.11% | 0.64% |
| `singular` | 203,717 | 56.74% | 0.51% |
| `second-person` | 194,386 | 81.47% | 0.51% |
| `present` | 156,636 | 94.75% | 0.54% |
| `indicative` | 145,616 | 80.43% | 0.44% |
| `past` | 130,681 | 90.86% | 0.42% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Urdu` | 11,004 | 5.75% | 100.00% | >=95% zero-char-overlap |
| `feminine;first-person;indicative;past;plural;third-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;first-person;indicative;past;singular;third-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;first-person;indicative;plural;present;third-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;first-person;indicative;present;singular` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;first-person;plural;present;subjunctive;third-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;first-person;present;singular;subjunctive` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;formal;indicative;past;plural;second-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;formal;indicative;plural;present;second-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;formal;plural;present;second-person;subjunctive` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;indicative;past;second-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |
| `feminine;indicative;plural;present;second-person` | 4,948 | 99.96% | 0.40% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `presumptive` | 49,868 | 99.20% | 0.47% | >=95% word-count mismatch |
| `adjectival` | 16,494 | 99.94% | 0.41% | >=95% word-count mismatch |
| `Urdu` | 11,004 | 5.75% | 100.00% | >=95% zero-char-overlap |

### hy.sqlite

- Distinct full tagsets: `460`
- Distinct individual tags: `133`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `2`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `definite;nominative;plural` | 33,912 | 0.06% | 0.01% |
| `definite;nominative;singular` | 31,735 | 0.06% | 0.01% |
| `dative;definite;singular` | 18,890 | 0.06% | 0.01% |
| `instrumental;singular` | 18,819 | 4.69% | 0.03% |
| `instrumental;possessive;second-person;singular` | 18,387 | 4.81% | 0.02% |
| `first-person;instrumental;possessive;singular` | 18,385 | 4.80% | 0.01% |
| `dative;plural` | 17,965 | 5.54% | 0.01% |
| `dative;first-person;plural;possessive` | 17,845 | 4.94% | 0.01% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 589,394 | 22.92% | 0.03% |
| `plural` | 495,526 | 27.44% | 0.01% |
| `possessive` | 376,480 | 1.29% | 0.01% |
| `second-person` | 316,066 | 27.72% | 0.02% |
| `first-person` | 315,295 | 27.65% | 0.01% |
| `indicative` | 255,738 | 86.91% | 0.03% |
| `nominative` | 192,691 | 0.12% | 0.01% |
| `dative` | 162,572 | 1.74% | 0.02% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `first-person;indicative;perfect;present;singular` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `first-person;indicative;pluperfect;singular` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;perfect;plural;present;second-person` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;perfect;present;second-person;singular` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;perfect;present;singular;third-person` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;pluperfect;plural;second-person` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;pluperfect;second-person;singular` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `indicative;pluperfect;singular;third-person` | 6,127 | 100.00% | 0.07% | >=95% word-count mismatch |
| `first-person;future;indicative;past;singular` | 5,419 | 100.00% | 0.00% | >=95% word-count mismatch |
| `first-person;future;indicative;singular` | 5,419 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;indicative;past;plural;second-person` | 5,419 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;indicative;past;second-person;singular` | 5,419 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `perfect` | 36,900 | 100.00% | 0.07% | >=95% word-count mismatch |
| `pluperfect` | 36,864 | 100.00% | 0.07% | >=95% word-count mismatch |

### id.sqlite

- Distinct full tagsets: `163`
- Distinct individual tags: `97`
- Flagged tagsets kept in this report: `6`
- Flagged individual tags kept in this report: `4`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 19,840 | 1.47% | 0.01% |
| `canonical` | 6,648 | 0.29% | 0.03% |
| `alternative` | 4,119 | 11.90% | 5.24% |
| `redirect;alternative` | 3,048 | 13.06% | 12.34% |
| `superlative` | 2,761 | 97.28% | 0.00% |
| `comparative` | 2,697 | 99.93% | 0.00% |
| `active` | 1,165 | 0.26% | 0.09% |
| `passive` | 935 | 0.53% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 19,840 | 1.47% | 0.01% |
| `alternative` | 8,288 | 13.40% | 8.58% |
| `canonical` | 6,649 | 0.29% | 0.03% |
| `redirect` | 3,048 | 13.06% | 12.34% |
| `superlative` | 2,761 | 97.28% | 0.00% |
| `comparative` | 2,698 | 99.89% | 0.00% |
| `passive` | 1,454 | 0.34% | 0.00% |
| `active` | 1,432 | 0.21% | 0.07% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `superlative` | 2,761 | 97.28% | 0.00% | >=95% word-count mismatch |
| `comparative` | 2,697 | 99.93% | 0.00% | >=95% word-count mismatch |
| `alternative;initialism` | 103 | 96.12% | 95.15% | >=95% word-count mismatch, >=95% zero-char-overlap |
| `abbreviation;acronym;acronym;alternative` | 51 | 100.00% | 9.80% | >=95% word-count mismatch |
| `uppercase` | 22 | 4.55% | 95.45% | >=95% zero-char-overlap |
| `lowercase` | 20 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `superlative` | 2,761 | 97.28% | 0.00% | >=95% word-count mismatch |
| `comparative` | 2,698 | 99.89% | 0.00% | >=95% word-count mismatch |
| `acronym` | 104 | 100.00% | 9.62% | >=95% word-count mismatch |
| `initialism` | 104 | 96.15% | 95.19% | >=95% word-count mismatch, >=95% zero-char-overlap |

### it.sqlite

- Distinct full tagsets: `1,154`
- Distinct individual tags: `133`
- Flagged tagsets kept in this report: `2`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 74,104 | 0.01% | 0.00% |
| `feminine` | 29,936 | 0.00% | 0.00% |
| `participle;past` | 29,079 | 0.15% | 0.03% |
| `conditional;singular;third-person` | 29,039 | 18.67% | 0.00% |
| `conditional;plural;third-person` | 29,021 | 18.66% | 0.00% |
| `feminine;plural` | 27,953 | 0.00% | 0.01% |
| `masculine;plural` | 27,935 | 0.00% | 0.03% |
| `auxiliary` | 25,426 | 4.04% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 546,771 | 13.07% | 0.01% |
| `singular` | 421,951 | 17.90% | 0.04% |
| `indicative` | 354,530 | 18.68% | 0.04% |
| `third-person` | 298,510 | 18.68% | 0.03% |
| `second-person` | 270,422 | 16.20% | 0.02% |
| `first-person` | 269,432 | 17.55% | 0.03% |
| `present` | 210,025 | 17.41% | 0.05% |
| `subjunctive` | 177,754 | 18.68% | 0.02% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `uppercase` | 34 | 2.94% | 97.06% | >=95% zero-char-overlap |
| `lowercase` | 26 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags: none under the current heuristic.

### ja.sqlite

- Distinct full tagsets: `158`
- Distinct individual tags: `77`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `5`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 86,167 | 31.00% | 1.27% |
| `causative` | 66,997 | 21.72% | 55.53% |
| `redirect;alternative` | 47,496 | 2.70% | 60.38% |
| `volitional` | 43,241 | 22.39% | 56.48% |
| `negative` | 43,069 | 17.58% | 53.46% |
| `conjunctive` | 40,348 | 24.17% | 56.81% |
| `formal` | 40,182 | 25.80% | 55.89% |
| `imperfective` | 32,101 | 22.67% | 56.78% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `negative` | 138,869 | 28.97% | 55.16% |
| `alternative` | 91,828 | 1.41% | 39.40% |
| `stem` | 88,673 | 16.50% | 48.54% |
| `canonical` | 86,167 | 31.00% | 1.27% |
| `continuative` | 81,708 | 20.94% | 56.80% |
| `formal` | 79,050 | 30.85% | 57.17% |
| `past` | 76,786 | 26.05% | 48.64% |
| `hypothetical` | 72,155 | 23.46% | 56.52% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `error-unrecognized-form` | 664 | 100.00% | 2.71% | >=95% word-count mismatch |
| `conditional;error-unrecognized-form` | 655 | 100.00% | 2.90% | >=95% word-count mismatch |
| `conditional;error-unrecognized-form;negative` | 593 | 100.00% | 3.20% | >=95% word-count mismatch |
| `Rōmaji` | 422 | 0.47% | 100.00% | >=95% zero-char-overlap |
| `error-unrecognized-form;imperative` | 419 | 100.00% | 2.86% | >=95% word-count mismatch |
| `shinjitai` | 396 | 0.00% | 99.49% | >=95% zero-char-overlap |
| `desiderative;error-unrecognized-form` | 387 | 100.00% | 2.84% | >=95% word-count mismatch |
| `desiderative;error-unrecognized-form;negative` | 387 | 100.00% | 3.10% | >=95% word-count mismatch |
| `causative;error-unrecognized-form` | 380 | 100.00% | 2.63% | >=95% word-count mismatch |
| `error-unrecognized-form;potential` | 360 | 100.00% | 2.22% | >=95% word-count mismatch |
| `error-unrecognized-form;passive` | 294 | 100.00% | 2.72% | >=95% word-count mismatch |
| `error-unrecognized-form;negative;potential` | 240 | 100.00% | 2.50% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `error-unrecognized-form` | 5,147 | 100.00% | 2.78% | >=95% word-count mismatch |
| `polite` | 1,603 | 100.00% | 2.68% | >=95% word-count mismatch |
| `desiderative` | 1,257 | 100.00% | 10.26% | >=95% word-count mismatch |
| `Rōmaji` | 495 | 1.01% | 100.00% | >=95% zero-char-overlap |
| `shinjitai` | 410 | 0.00% | 97.80% | >=95% zero-char-overlap |

### ko.sqlite

- Distinct full tagsets: `170`
- Distinct individual tags: `100`
- Flagged tagsets kept in this report: `9`
- Flagged individual tags kept in this report: `8`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `hanja` | 16,991 | 1.18% | 95.76% |
| `indicative;informal;non-past;polite` | 14,065 | 0.03% | 3.35% |
| `informal;interrogative;non-past;polite` | 14,065 | 0.03% | 3.35% |
| `hangeul` | 13,446 | 0.62% | 98.68% |
| `causative;informal` | 11,763 | 0.03% | 2.98% |
| `conditional;informal` | 11,763 | 0.03% | 2.98% |
| `formal;noun-from-verb;past` | 11,755 | 0.03% | 3.63% |
| `informal;noun-from-verb;past` | 11,755 | 0.03% | 3.59% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `formal` | 195,769 | 0.03% | 2.58% |
| `informal` | 192,607 | 0.04% | 3.33% |
| `polite` | 144,359 | 0.06% | 2.92% |
| `past` | 98,819 | 0.02% | 3.62% |
| `non-past` | 78,704 | 0.03% | 2.80% |
| `interrogative` | 74,346 | 0.02% | 4.02% |
| `indicative` | 73,333 | 0.07% | 2.17% |
| `noun-from-verb` | 40,764 | 0.02% | 3.57% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `hanja` | 16,991 | 1.18% | 95.76% | >=95% zero-char-overlap |
| `hangeul` | 13,446 | 0.62% | 98.68% | >=95% zero-char-overlap |
| `class` | 8,611 | 0.77% | 100.00% | >=95% zero-char-overlap, contains class |
| `eumhun` | 2,637 | 99.54% | 98.67% | >=95% word-count mismatch, >=95% zero-char-overlap |
| `revised` | 944 | 0.11% | 100.00% | >=95% zero-char-overlap |
| `McCune-Reischauer` | 929 | 0.11% | 100.00% | >=95% zero-char-overlap |
| `Yale` | 731 | 0.14% | 100.00% | >=95% zero-char-overlap |
| `McCune-Reischauer;romanization` | 188 | 2.13% | 100.00% | >=95% zero-char-overlap |
| `Yale;romanization` | 187 | 2.14% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `hanja` | 16,991 | 1.18% | 95.76% | >=95% zero-char-overlap |
| `hangeul` | 13,446 | 0.62% | 98.68% | >=95% zero-char-overlap |
| `class` | 8,611 | 0.77% | 100.00% | tag is class, >=95% zero-char-overlap |
| `eumhun` | 2,638 | 99.55% | 98.67% | >=95% word-count mismatch, >=95% zero-char-overlap |
| `McCune-Reischauer` | 1,117 | 0.45% | 100.00% | >=95% zero-char-overlap |
| `revised` | 944 | 0.11% | 100.00% | >=95% zero-char-overlap |
| `Yale` | 918 | 0.54% | 100.00% | >=95% zero-char-overlap |
| `romanization` | 375 | 2.13% | 100.00% | >=95% zero-char-overlap |

### la.sqlite

- Distinct full tagsets: `546`
- Distinct individual tags: `114`
- Flagged tagsets kept in this report: `34`
- Flagged individual tags kept in this report: `4`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 732,238 | 0.28% | 0.01% |
| `genitive` | 32,291 | 0.00% | 0.03% |
| `genitive;singular` | 27,633 | 0.01% | 0.07% |
| `accusative;singular` | 25,320 | 0.01% | 0.06% |
| `ablative;singular` | 25,075 | 0.01% | 0.16% |
| `singular;vocative` | 24,968 | 0.01% | 0.10% |
| `accusative;neuter;plural` | 24,959 | 0.00% | 0.04% |
| `neuter;nominative;plural` | 24,933 | 0.00% | 0.04% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 848,785 | 0.13% | 0.08% |
| `canonical` | 751,312 | 0.27% | 0.01% |
| `plural` | 719,849 | 0.06% | 0.07% |
| `active` | 451,444 | 3.53% | 0.12% |
| `feminine` | 338,230 | 0.00% | 0.03% |
| `indicative` | 335,998 | 4.63% | 0.10% |
| `neuter` | 325,691 | 0.00% | 0.03% |
| `masculine` | 321,575 | 0.08% | 0.03% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `active;future;infinitive` | 5,360 | 99.68% | 0.17% | >=95% word-count mismatch |
| `active;infinitive;perfect;potential` | 5,333 | 100.00% | 0.08% | >=95% word-count mismatch |
| `future;infinitive;passive` | 4,472 | 100.00% | 0.11% | >=95% word-count mismatch |
| `future;infinitive;passive;perfect` | 4,472 | 100.00% | 0.00% | >=95% word-count mismatch |
| `infinitive;passive;perfect` | 4,472 | 100.00% | 0.02% | >=95% word-count mismatch |
| `future;indicative;passive;perfect` | 4,400 | 98.07% | 0.05% | >=95% word-count mismatch |
| `indicative;passive;perfect` | 4,400 | 98.07% | 0.05% | >=95% word-count mismatch |
| `indicative;passive;pluperfect` | 4,400 | 98.07% | 0.05% | >=95% word-count mismatch |
| `passive;perfect;subjunctive` | 4,400 | 98.07% | 0.05% | >=95% word-count mismatch |
| `passive;pluperfect;subjunctive` | 4,400 | 98.07% | 0.05% | >=95% word-count mismatch |
| `active;future;infinitive;perfect` | 652 | 100.00% | 0.00% | >=95% word-count mismatch |
| `active;future;indicative;perfect` | 636 | 95.44% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `potential` | 5,333 | 100.00% | 0.08% | >=95% word-count mismatch |
| `multiword-construction` | 204 | 100.00% | 0.00% | >=95% word-count mismatch |
| `` | 56 | 100.00% | 3.57% | >=95% word-count mismatch |
| `class` | 14 | 14.29% | 0.00% | tag is class |

### lzh-wiktionary.sqlite

- Distinct full tagsets: `181`
- Distinct individual tags: `80`
- Flagged tagsets kept in this report: `1`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `redirect;alternative` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 101,598 | 0.00% | 13.91% |
| `alternative` | 17,382 | 0.24% | 64.53% |
| `Traditional-Chinese;alternative` | 10,117 | 0.09% | 23.07% |
| `Simplified-Chinese;alternative` | 9,986 | 0.30% | 53.73% |
| `Traditional-Chinese` | 7,723 | 0.00% | 1.28% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `alternative` | 179,010 | 0.05% | 31.24% |
| `redirect` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 112,739 | 0.03% | 17.99% |
| `Traditional-Chinese` | 18,767 | 0.05% | 14.09% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |
| `Second-Round-Simplified-Chinese` | 970 | 0.00% | 91.24% |
| `Hokkien` | 696 | 0.14% | 51.58% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |

### lzh.sqlite

- Distinct full tagsets: `1`
- Distinct individual tags: `2`
- Flagged tagsets kept in this report: `0`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `Simplified-Chinese;alternative` | 82,663 | 0.00% | 18.25% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `Simplified-Chinese` | 82,663 | 0.00% | 18.25% |
| `alternative` | 82,663 | 0.00% | 18.25% |

Flagged tagsets: none under the current heuristic.

Flagged individual tags: none under the current heuristic.

### nl.sqlite

- Distinct full tagsets: `350`
- Distinct individual tags: `118`
- Flagged tagsets kept in this report: `27`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 41,013 | 0.01% | 0.01% |
| `adverbial;predicative` | 23,941 | 0.01% | 0.01% |
| `diminutive;neuter` | 21,241 | 0.00% | 0.00% |
| `definite` | 16,076 | 0.01% | 0.01% |
| `feminine;indefinite;masculine;singular` | 16,073 | 0.01% | 0.01% |
| `indefinite;neuter;singular` | 16,073 | 0.01% | 0.01% |
| `indefinite;plural` | 16,073 | 0.01% | 0.01% |
| `partitive` | 16,073 | 0.01% | 0.01% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 209,708 | 14.43% | 2.02% |
| `plural` | 119,264 | 7.97% | 1.72% |
| `present` | 109,673 | 20.57% | 0.01% |
| `indefinite` | 92,861 | 0.19% | 0.01% |
| `past` | 88,754 | 19.19% | 0.01% |
| `second-person` | 85,317 | 19.74% | 3.93% |
| `archaic` | 66,678 | 19.82% | 3.45% |
| `neuter` | 60,983 | 0.10% | 1.32% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `adverbial;predicative;superlative` | 8,154 | 99.98% | 0.00% | >=95% word-count mismatch |
| `main-clause;present;second-person;singular` | 3,620 | 99.94% | 0.00% | >=95% word-count mismatch |
| `imperative;main-clause;present;singular` | 1,934 | 99.95% | 0.00% | >=95% word-count mismatch |
| `first-person;main-clause;present;singular` | 1,933 | 99.95% | 0.00% | >=95% word-count mismatch |
| `archaic;main-clause;past;plural;subjunctive` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `first-person;main-clause;past;singular` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `formal;main-clause;past;second-person;singular` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `main-clause;past;plural` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `main-clause;past;second-person;singular` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `main-clause;past;singular;third-person` | 1,892 | 99.95% | 0.00% | >=95% word-count mismatch |
| `Flanders;colloquial;main-clause;past;second-person;singular` | 1,891 | 99.95% | 0.00% | >=95% word-count mismatch |
| `archaic;formal;main-clause;majestic;past;second-person;singular` | 1,891 | 99.95% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 1,338 | 3.06% | 92.90% | tag is class |

### pa.sqlite

- Distinct full tagsets: `225`
- Distinct individual tags: `63`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `8`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `Shahmukhi` | 3,669 | 1.14% | 99.92% |
| `error-unrecognized-form;future;indicative;masculine;singular` | 2,301 | 57.02% | 0.13% |
| `error-unrecognized-form;feminine;future;indicative;singular` | 2,301 | 57.11% | 0.17% |
| `error-unrecognized-form;indicative;masculine;present;singular` | 2,232 | 99.91% | 0.22% |
| `error-unrecognized-form;feminine;indicative;present;singular` | 2,232 | 100.00% | 0.27% |
| `error-unrecognized-form;masculine;present;singular;subjunctive` | 2,232 | 99.91% | 0.36% |
| `error-unrecognized-form;feminine;present;singular;subjunctive` | 2,232 | 100.00% | 0.40% |
| `error-unrecognized-form;masculine;past;present;presumptive;singular` | 1,980 | 99.90% | 0.15% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 76,162 | 58.55% | 0.33% |
| `masculine` | 40,566 | 61.91% | 0.25% |
| `error-unrecognized-form` | 40,077 | 64.86% | 0.24% |
| `feminine` | 39,831 | 62.32% | 0.29% |
| `indicative` | 34,077 | 61.01% | 0.27% |
| `present` | 26,904 | 96.99% | 0.19% |
| `third-person` | 21,354 | 67.94% | 0.29% |
| `past` | 19,836 | 99.87% | 0.24% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Shahmukhi` | 3,669 | 1.14% | 99.92% | >=95% zero-char-overlap |
| `error-unrecognized-form;feminine;indicative;present;singular` | 2,232 | 100.00% | 0.27% | >=95% word-count mismatch |
| `error-unrecognized-form;feminine;present;singular;subjunctive` | 2,232 | 100.00% | 0.40% | >=95% word-count mismatch |
| `error-unrecognized-form;indicative;masculine;present;singular` | 2,232 | 99.91% | 0.22% | >=95% word-count mismatch |
| `error-unrecognized-form;masculine;present;singular;subjunctive` | 2,232 | 99.91% | 0.36% | >=95% word-count mismatch |
| `error-unrecognized-form;feminine;past;present;presumptive;singular` | 1,980 | 100.00% | 0.20% | >=95% word-count mismatch |
| `error-unrecognized-form;masculine;past;present;presumptive;singular` | 1,980 | 99.90% | 0.15% | >=95% word-count mismatch |
| `Gurmukhi` | 1,707 | 0.76% | 99.94% | >=95% zero-char-overlap |
| `error-unrecognized-form;feminine;indicative;past;singular` | 1,656 | 100.00% | 0.36% | >=95% word-count mismatch |
| `error-unrecognized-form;indicative;masculine;past;singular` | 1,656 | 99.88% | 0.30% | >=95% word-count mismatch |
| `counterfactual;error-unrecognized-form;feminine;past;singular` | 1,320 | 100.00% | 0.45% | >=95% word-count mismatch |
| `feminine;indicative;present;singular;third-person` | 1,320 | 100.00% | 0.45% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `present` | 26,904 | 96.99% | 0.19% | >=95% word-count mismatch |
| `past` | 19,836 | 99.87% | 0.24% | >=95% word-count mismatch |
| `presumptive` | 8,940 | 99.80% | 0.09% | >=95% word-count mismatch |
| `adjectival` | 4,164 | 99.95% | 0.34% | >=95% word-count mismatch |
| `Shahmukhi` | 3,669 | 1.14% | 99.92% | >=95% zero-char-overlap |
| `Gurmukhi` | 1,709 | 0.76% | 99.94% | >=95% zero-char-overlap |
| `agentive` | 1,650 | 100.00% | 0.00% | >=95% word-count mismatch |
| `prospective` | 1,650 | 100.00% | 0.00% | >=95% word-count mismatch |

### pt.sqlite

- Distinct full tagsets: `429`
- Distinct individual tags: `106`
- Flagged tagsets kept in this report: `12`
- Flagged individual tags kept in this report: `3`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 44,026 | 0.09% | 0.01% |
| `feminine;plural` | 18,316 | 0.02% | 0.03% |
| `feminine` | 17,857 | 0.00% | 0.03% |
| `masculine;plural` | 14,985 | 0.00% | 0.01% |
| `redirect;alternative` | 10,097 | 6.33% | 2.99% |
| `alternative` | 9,466 | 7.73% | 0.81% |
| `participle;past` | 6,940 | 0.07% | 0.01% |
| `first-person;preterite;singular` | 6,889 | 0.07% | 0.03% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 341,697 | 6.33% | 0.02% |
| `singular` | 259,395 | 5.69% | 0.03% |
| `indicative` | 209,626 | 0.20% | 0.01% |
| `first-person` | 168,940 | 4.47% | 0.03% |
| `third-person` | 164,020 | 8.78% | 0.03% |
| `second-person` | 163,035 | 8.78% | 0.02% |
| `subjunctive` | 122,509 | 1.21% | 0.04% |
| `present` | 89,049 | 0.65% | 0.06% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `imperative;negative;plural;third-person` | 6,823 | 99.94% | 0.06% | >=95% word-count mismatch |
| `first-person;imperative;negative;plural` | 6,810 | 99.94% | 0.06% | >=95% word-count mismatch |
| `imperative;negative;second-person;singular` | 6,771 | 99.94% | 0.06% | >=95% word-count mismatch |
| `imperative;negative;singular;third-person` | 6,771 | 99.94% | 0.06% | >=95% word-count mismatch |
| `imperative;negative;plural;second-person` | 6,758 | 99.94% | 0.04% | >=95% word-count mismatch |
| `comparative` | 1,273 | 99.29% | 0.16% | >=95% word-count mismatch |
| `class` | 1,158 | 98.79% | 0.00% | >=95% word-count mismatch, contains class |
| `Brazil;imperative;negative;plural;third-person` | 44 | 100.00% | 0.00% | >=95% word-count mismatch |
| `Brazil;imperative;negative;second-person;singular` | 44 | 100.00% | 0.00% | >=95% word-count mismatch |
| `Brazil;imperative;negative;singular;third-person` | 44 | 100.00% | 0.00% | >=95% word-count mismatch |
| `uppercase` | 34 | 2.94% | 100.00% | >=95% zero-char-overlap |
| `lowercase` | 33 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `negative` | 34,126 | 99.94% | 0.06% | >=95% word-count mismatch |
| `comparative` | 1,306 | 99.31% | 0.15% | >=95% word-count mismatch |
| `class` | 1,158 | 98.79% | 0.00% | tag is class, >=95% word-count mismatch |

### ru.sqlite

- Distinct full tagsets: `674`
- Distinct individual tags: `128`
- Flagged tagsets kept in this report: `4`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `canonical` | 202,687 | 0.16% | 0.00% |
| `genitive;plural` | 91,477 | 0.02% | 0.65% |
| `nominative;plural` | 91,392 | 0.02% | 0.80% |
| `class` | 90,030 | 19.61% | 98.41% |
| `feminine;instrumental` | 70,681 | 0.00% | 0.31% |
| `instrumental;plural` | 63,900 | 0.02% | 0.89% |
| `dative;plural` | 63,888 | 0.02% | 0.88% |
| `plural;prepositional` | 63,885 | 0.02% | 0.88% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 719,683 | 3.01% | 0.78% |
| `canonical` | 421,597 | 0.09% | 0.01% |
| `masculine` | 404,073 | 0.15% | 0.49% |
| `feminine` | 373,469 | 0.21% | 0.71% |
| `singular` | 342,709 | 6.59% | 1.76% |
| `neuter` | 284,134 | 0.21% | 0.65% |
| `accusative` | 282,395 | 0.16% | 1.18% |
| `nominative` | 237,445 | 0.01% | 1.23% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 90,030 | 19.61% | 98.41% | >=95% zero-char-overlap, contains class |
| `error-unrecognized-form` | 88 | 88.64% | 97.73% | >=95% zero-char-overlap |
| `uppercase` | 40 | 2.50% | 97.50% | >=95% zero-char-overlap |
| `lowercase` | 40 | 0.00% | 97.50% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `class` | 90,030 | 19.61% | 98.41% | tag is class, >=95% zero-char-overlap |

### sw.sqlite

- Distinct full tagsets: `199`
- Distinct individual tags: `66`
- Flagged tagsets kept in this report: `21`
- Flagged individual tags kept in this report: `9`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `object-concord;relative` | 8,651 | 100.00% | 0.00% |
| `indicative;object-concord;plural;second-person` | 8,385 | 0.00% | 0.00% |
| `infinitive` | 6,165 | 0.02% | 0.00% |
| `first-person;present;singular` | 6,111 | 0.00% | 0.00% |
| `class-1;class-2;object-concord;relative;singular` | 5,858 | 0.00% | 0.00% |
| `class-1;class-2;object-concord;plural;relative` | 5,858 | 0.00% | 0.00% |
| `class-3;class-4;object-concord;relative;singular` | 5,858 | 0.00% | 0.00% |
| `class-3;class-4;object-concord;plural;relative` | 5,858 | 0.00% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 153,430 | 0.02% | 0.01% |
| `object-concord` | 153,046 | 5.65% | 0.02% |
| `plural` | 114,971 | 0.03% | 0.05% |
| `third-person` | 109,823 | 8.38% | 0.00% |
| `relative` | 94,351 | 9.17% | 0.03% |
| `indicative` | 58,695 | 0.00% | 0.00% |
| `gnomic` | 54,955 | 0.00% | 0.00% |
| `present` | 51,962 | 23.53% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `object-concord;relative` | 8,651 | 100.00% | 0.00% | >=95% word-count mismatch |
| `already-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `consecutive` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `consecutive;subjunctive` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;negative` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `if-not-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `if-when-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `irrealis;negative;past` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `irrealis;negative;present` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `irrealis;past` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `irrealis;present` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `irrealis` | 12,232 | 100.00% | 0.00% | >=95% word-count mismatch |
| `past` | 12,232 | 100.00% | 0.00% | >=95% word-count mismatch |
| `consecutive` | 6,116 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future` | 6,116 | 100.00% | 0.00% | >=95% word-count mismatch |
| `already-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `if-not-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `if-when-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `not-yet-form` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |
| `perfect` | 3,058 | 100.00% | 0.00% | >=95% word-count mismatch |

### ta.sqlite

- Distinct full tagsets: `198`
- Distinct individual tags: `79`
- Flagged tagsets kept in this report: `6`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `error-unrecognized-form;singular` | 42,852 | 0.59% | 0.00% |
| `error-unrecognized-form;plural` | 32,226 | 0.60% | 0.00% |
| `nominative;singular` | 7,144 | 0.59% | 0.01% |
| `accusative;singular` | 7,143 | 0.59% | 0.00% |
| `dative;singular` | 7,143 | 0.59% | 0.00% |
| `benefactive;singular` | 7,143 | 0.59% | 0.00% |
| `instrumental;singular` | 7,143 | 0.59% | 0.00% |
| `ablative;singular` | 7,143 | 0.59% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `singular` | 173,280 | 1.40% | 0.00% |
| `plural` | 119,384 | 2.02% | 0.00% |
| `error-unrecognized-form` | 111,190 | 0.50% | 0.00% |
| `future` | 83,715 | 8.12% | 0.00% |
| `negative` | 68,946 | 7.42% | 0.00% |
| `affective` | 57,451 | 0.30% | 0.00% |
| `third-person` | 45,966 | 0.30% | 0.00% |
| `present` | 42,666 | 4.14% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `cohortative;future;negative` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;imperative;perfect;plural` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;infinitive;negative` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |
| `future;negative;potential` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |
| `imperative;perfect;present;singular` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |
| `past;perfect` | 1,641 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `perfect` | 4,923 | 100.00% | 0.00% | >=95% word-count mismatch |

### th.sqlite

- Distinct full tagsets: `26`
- Distinct individual tags: `23`
- Flagged tagsets kept in this report: `0`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `abstract-noun` | 5,178 | 0.00% | 0.00% |
| `classifier` | 1,903 | 0.00% | 46.87% |
| `alternative` | 1,802 | 0.28% | 0.83% |
| `redirect;alternative` | 1,472 | 0.48% | 0.27% |
| `alternative;archaic;dated;obsolete` | 414 | 0.00% | 0.24% |
| `alternative;obsolete` | 370 | 0.00% | 0.00% |
| `canonical` | 56 | 83.93% | 0.00% |
| `alternative;interjection` | 27 | 0.00% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `abstract-noun` | 5,178 | 0.00% | 0.00% |
| `alternative` | 4,212 | 0.28% | 0.47% |
| `classifier` | 1,903 | 0.00% | 46.87% |
| `redirect` | 1,472 | 0.48% | 0.27% |
| `obsolete` | 794 | 0.00% | 0.13% |
| `archaic` | 438 | 0.00% | 0.23% |
| `dated` | 420 | 0.00% | 0.24% |
| `canonical` | 56 | 83.93% | 0.00% |

Flagged tagsets: none under the current heuristic.

Flagged individual tags: none under the current heuristic.

### tl.sqlite

- Distinct full tagsets: `187`
- Distinct individual tags: `76`
- Flagged tagsets kept in this report: `7`
- Flagged individual tags kept in this report: `4`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `Baybayin` | 35,364 | 0.12% | 99.88% |
| `error-unrecognized-form` | 21,830 | 1.37% | 19.56% |
| `canonical` | 19,761 | 0.40% | 0.01% |
| `alternative` | 12,221 | 6.69% | 0.38% |
| `redirect;alternative` | 8,284 | 5.83% | 25.62% |
| `error-unrecognized-form;locative` | 6,893 | 0.00% | 0.00% |
| `error-unrecognized-form;objective` | 6,808 | 0.03% | 10.55% |
| `benefactive;error-unrecognized-form` | 5,720 | 0.00% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `error-unrecognized-form` | 79,190 | 0.56% | 9.20% |
| `Baybayin` | 35,364 | 0.12% | 99.88% |
| `progressive` | 32,396 | 0.80% | 5.96% |
| `alternative` | 22,925 | 6.23% | 9.54% |
| `canonical` | 19,761 | 0.40% | 0.01% |
| `objective` | 17,395 | 0.01% | 12.43% |
| `infinitive` | 16,735 | 0.04% | 5.46% |
| `formal` | 15,872 | 0.76% | 5.97% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Baybayin` | 35,364 | 0.12% | 99.88% | >=95% zero-char-overlap |
| `inferior;plural` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |
| `inferior;singular` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |
| `plural;relative` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |
| `plural;superior` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |
| `relative;singular` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |
| `singular;superior` | 78 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Baybayin` | 35,364 | 0.12% | 99.88% | >=95% zero-char-overlap |
| `inferior` | 156 | 100.00% | 0.00% | >=95% word-count mismatch |
| `relative` | 156 | 100.00% | 0.00% | >=95% word-count mismatch |
| `superior` | 156 | 100.00% | 0.00% | >=95% word-count mismatch |

### tr.sqlite

- Distinct full tagsets: `343`
- Distinct individual tags: `81`
- Flagged tagsets kept in this report: `2`
- Flagged individual tags kept in this report: `0`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `error-unrecognized-form` | 46,548 | 16.60% | 0.02% |
| `inferential` | 38,553 | 0.05% | 0.00% |
| `inferential;singular;third-person` | 30,845 | 0.05% | 0.00% |
| `first-person;inferential;plural` | 30,845 | 0.05% | 0.00% |
| `inferential;plural;second-person` | 30,845 | 0.05% | 0.00% |
| `inferential;plural;third-person` | 30,845 | 0.05% | 0.00% |
| `aorist;singular;third-person` | 30,843 | 0.05% | 0.00% |
| `aorist;first-person;plural` | 30,843 | 0.05% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 1,474,975 | 0.90% | 0.01% |
| `singular` | 1,098,890 | 1.10% | 0.02% |
| `second-person` | 879,022 | 0.92% | 0.01% |
| `third-person` | 865,222 | 1.04% | 0.01% |
| `first-person` | 591,134 | 1.34% | 0.02% |
| `negative` | 550,073 | 0.52% | 0.00% |
| `inferential` | 298,176 | 0.05% | 0.00% |
| `conditional` | 268,436 | 2.17% | 0.00% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `uppercase` | 32 | 3.12% | 100.00% | >=95% zero-char-overlap |
| `lowercase` | 29 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags: none under the current heuristic.

### ur.sqlite

- Distinct full tagsets: `260`
- Distinct individual tags: `68`
- Flagged tagsets kept in this report: `40`
- Flagged individual tags kept in this report: `16`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `Hindi` | 8,975 | 5.26% | 99.97% |
| `canonical;masculine` | 2,517 | 0.12% | 0.00% |
| `canonical` | 2,335 | 0.56% | 0.13% |
| `direct;singular` | 1,689 | 0.18% | 0.00% |
| `oblique;singular` | 1,684 | 0.18% | 0.00% |
| `singular;vocative` | 1,684 | 0.18% | 0.00% |
| `direct;plural` | 1,683 | 0.30% | 0.00% |
| `oblique;plural` | 1,678 | 0.18% | 0.00% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `plural` | 19,600 | 65.71% | 0.37% |
| `singular` | 19,318 | 66.57% | 0.35% |
| `present` | 10,782 | 95.21% | 0.37% |
| `masculine` | 10,415 | 58.54% | 1.20% |
| `Hindi` | 8,977 | 5.26% | 99.97% |
| `feminine` | 8,480 | 64.94% | 0.71% |
| `first-person` | 8,336 | 99.81% | 0.06% |
| `second-person` | 8,336 | 99.81% | 0.06% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `Hindi` | 8,975 | 5.26% | 99.97% | >=95% zero-char-overlap |
| `future;indicative;masculine` | 878 | 100.00% | 1.03% | >=95% word-count mismatch |
| `indicative;masculine;present` | 876 | 100.00% | 0.91% | >=95% word-count mismatch |
| `masculine;past;present;presumptive` | 876 | 100.00% | 0.91% | >=95% word-count mismatch |
| `masculine;present;subjunctive` | 876 | 100.00% | 0.91% | >=95% word-count mismatch |
| `feminine;indicative;present` | 864 | 100.00% | 0.46% | >=95% word-count mismatch |
| `feminine;future;indicative` | 722 | 100.00% | 0.55% | >=95% word-count mismatch |
| `feminine;past;present;presumptive` | 720 | 100.00% | 0.42% | >=95% word-count mismatch |
| `feminine;present;subjunctive` | 648 | 100.00% | 0.46% | >=95% word-count mismatch |
| `future;masculine;subjunctive` | 588 | 100.00% | 1.36% | >=95% word-count mismatch |
| `feminine;future;subjunctive` | 576 | 100.00% | 0.69% | >=95% word-count mismatch |
| `indicative;masculine;past` | 294 | 100.00% | 1.36% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `present` | 10,782 | 95.21% | 0.37% | >=95% word-count mismatch |
| `Hindi` | 8,977 | 5.26% | 99.97% | >=95% zero-char-overlap |
| `first-person` | 8,336 | 99.81% | 0.06% | >=95% word-count mismatch |
| `second-person` | 8,336 | 99.81% | 0.06% | >=95% word-count mismatch |
| `third-person` | 8,336 | 99.81% | 0.04% | >=95% word-count mismatch |
| `past` | 7,884 | 96.19% | 0.41% | >=95% word-count mismatch |
| `perfective` | 7,854 | 96.29% | 0.08% | >=95% word-count mismatch |
| `habitual` | 7,848 | 96.33% | 0.00% | >=95% word-count mismatch |
| `continuative` | 7,560 | 100.00% | 0.00% | >=95% word-count mismatch |
| `subjunctive` | 7,514 | 96.15% | 0.32% | >=95% word-count mismatch |
| `presumptive` | 6,132 | 100.00% | 0.18% | >=95% word-count mismatch |
| `future` | 2,992 | 95.19% | 0.84% | >=95% word-count mismatch |

### vi.sqlite

- Distinct full tagsets: `23`
- Distinct individual tags: `24`
- Flagged tagsets kept in this report: `6`
- Flagged individual tags kept in this report: `6`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `CJK` | 11,837 | 12.61% | 100.00% |
| `alternative` | 4,329 | 19.89% | 3.33% |
| `classifier` | 4,243 | 52.11% | 48.76% |
| `redirect;alternative` | 3,046 | 18.84% | 10.54% |
| `Hán-Nôm` | 929 | 1.18% | 99.89% |
| `diminutive;reduplication` | 88 | 100.00% | 0.00% |
| `canonical` | 85 | 50.59% | 11.76% |
| `lowercase` | 80 | 0.00% | 98.75% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `CJK` | 11,837 | 12.61% | 100.00% |
| `alternative` | 7,421 | 19.59% | 6.43% |
| `classifier` | 4,260 | 52.00% | 48.85% |
| `redirect` | 3,046 | 18.84% | 10.54% |
| `Hán-Nôm` | 929 | 1.18% | 99.89% |
| `reduplication` | 142 | 100.00% | 0.00% |
| `diminutive` | 88 | 100.00% | 0.00% |
| `canonical` | 85 | 50.59% | 11.76% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `CJK` | 11,837 | 12.61% | 100.00% | >=95% zero-char-overlap |
| `Hán-Nôm` | 929 | 1.18% | 99.89% | >=95% zero-char-overlap |
| `diminutive;reduplication` | 88 | 100.00% | 0.00% | >=95% word-count mismatch |
| `lowercase` | 80 | 0.00% | 98.75% | >=95% zero-char-overlap |
| `uppercase` | 78 | 1.28% | 96.15% | >=95% zero-char-overlap |
| `reduplication` | 54 | 100.00% | 0.00% | >=95% word-count mismatch |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `CJK` | 11,837 | 12.61% | 100.00% | >=95% zero-char-overlap |
| `Hán-Nôm` | 929 | 1.18% | 99.89% | >=95% zero-char-overlap |
| `reduplication` | 142 | 100.00% | 0.00% | >=95% word-count mismatch |
| `diminutive` | 88 | 100.00% | 0.00% | >=95% word-count mismatch |
| `lowercase` | 80 | 0.00% | 98.75% | >=95% zero-char-overlap |
| `uppercase` | 78 | 1.28% | 96.15% | >=95% zero-char-overlap |

### zh-Hant.sqlite

- Distinct full tagsets: `181`
- Distinct individual tags: `80`
- Flagged tagsets kept in this report: `1`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `redirect;alternative` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 101,598 | 0.00% | 13.91% |
| `alternative` | 17,382 | 0.24% | 64.53% |
| `Traditional-Chinese;alternative` | 10,117 | 0.09% | 23.07% |
| `Simplified-Chinese;alternative` | 9,986 | 0.30% | 53.73% |
| `Traditional-Chinese` | 7,723 | 0.00% | 1.28% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `alternative` | 179,010 | 0.05% | 31.24% |
| `redirect` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 112,739 | 0.03% | 17.99% |
| `Traditional-Chinese` | 18,767 | 0.05% | 14.09% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |
| `Second-Round-Simplified-Chinese` | 970 | 0.00% | 91.24% |
| `Hokkien` | 696 | 0.14% | 51.58% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |

### zh.sqlite

- Distinct full tagsets: `181`
- Distinct individual tags: `80`
- Flagged tagsets kept in this report: `1`
- Flagged individual tags kept in this report: `1`

Top tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `redirect;alternative` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 101,598 | 0.00% | 13.91% |
| `alternative` | 17,382 | 0.24% | 64.53% |
| `Traditional-Chinese;alternative` | 10,117 | 0.09% | 23.07% |
| `Simplified-Chinese;alternative` | 9,986 | 0.30% | 53.73% |
| `Traditional-Chinese` | 7,723 | 0.00% | 1.28% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |

Top individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate |
| --- | ---: | ---: | ---: |
| `alternative` | 179,010 | 0.05% | 31.24% |
| `redirect` | 138,567 | 0.01% | 25.77% |
| `Simplified-Chinese` | 112,739 | 0.03% | 17.99% |
| `Traditional-Chinese` | 18,767 | 0.05% | 14.09% |
| `canonical` | 3,120 | 0.42% | 0.00% |
| `` | 1,294 | 0.00% | 9.66% |
| `Second-Round-Simplified-Chinese` | 970 | 0.00% | 91.24% |
| `Hokkien` | 696 | 0.14% | 51.58% |

Flagged tagsets:

| Tagset | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |

Flagged individual tags:

| Tag | Rows | Mismatch Rate | Zero-Share Rate | Reasons |
| --- | ---: | ---: | ---: | --- |
| `lowercase` | 52 | 0.00% | 100.00% | >=95% zero-char-overlap |
