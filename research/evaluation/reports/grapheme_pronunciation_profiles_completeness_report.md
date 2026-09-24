# Grapheme analysis across writing systems

I built the grapheme layer to make the internal structure of written words
inspectable: a reader can examine a cluster, its constituent codepoints and the
sound mappings supplied by a language profile. The implementation combines
algorithmic decomposition with script-specific tables and multi-character rules.

## Different scripts need different models

| Writing system | Representation and engineering work |
|---|---|
| Hangul | Algorithmic decomposition of syllables into initial consonant, vowel and final consonant, with compatibility-jamo mappings |
| Japanese kana | Base kana, voicing marks, small-kana combinations, gemination, long vowels and multi-character sound mappings |
| Arabic-script languages and Hebrew | Base-letter and combining-mark analysis with language-specific overrides and span mappings |
| Indic abugidas | Consonants, independent vowels, dependent vowel signs, virama suppression, nukta forms and compositional cluster analysis |
| Thai | Analysis of prefix vowels, vowel cores, codas, tone marks and silent markers |
| Greek and Ancient Greek | Separate profiles for letter values, diphthongs and breathing marks |
| Latin-script languages | Unicode decomposition, generic letter coverage and language-specific digraph/trigraph mappings |

The output keeps whole-cluster and part-level analysis together. These are
orthographic sound mappings; the rule layer does not determine context-dependent
word pronunciation. Han characters, including Japanese kanji, retain a separate
profile whose grapheme-level sound field is empty.

## Implementation

The maintained source is under
[`frontend/linguistics/pronunciation/`](../../../frontend/linguistics/pronunciation/).
Tables, analysis algorithms and language selection have separate responsibilities.

| Source | Role |
|---|---|
| [graphemes.mjs](../../../frontend/linguistics/pronunciation/graphemes.mjs) | Cluster segmentation, decomposition and language-profile selection |
| [profiles.mjs](../../../frontend/linguistics/pronunciation/profiles.mjs) | Script families, sound maps and analyzer dispatch |
| [east-asian-analysis.mjs](../../../frontend/linguistics/pronunciation/east-asian-analysis.mjs) | Hangul decomposition, kana composition and Greek analysis |
| [abugida-analysis.mjs](../../../frontend/linguistics/pronunciation/abugida-analysis.mjs) | Compositional consonant/vowel/mark handling |
| [semitic-analysis.mjs](../../../frontend/linguistics/pronunciation/semitic-analysis.mjs) | Arabic-script and Hebrew analysis |
| [thai-analysis.mjs](../../../frontend/linguistics/pronunciation/thai-analysis.mjs) | Thai cluster rules |
| [latin-analysis.mjs](../../../frontend/linguistics/pronunciation/latin-analysis.mjs) | Latin-script decomposition and span mappings |
| [public-api.mjs](../../../frontend/linguistics/pronunciation/public-api.mjs) | Cluster, part and text-analysis interfaces for the reader |

This layer complements dictionary pronunciation and morphological analysis by
exposing how the written form itself is assembled.
