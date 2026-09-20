# Grapheme Pronunciation Profile Completeness Audit

## Scope

This report evaluates `static/grapheme_pronunciation_profiles.js` against the app's supported language set and against the practical requirement you stated: the rules do not need polished end-user romanization, but they do need to provide a comprehensive grapheme-to-sound representation for the grapheme clusters and codepoint decompositions the app will emit. In other words, every supported language should have some usable `PHON` output, and complex clusters should expose both a cluster-level sound and a decomposed part-level sound.

The review is focused on completeness, not linguistic perfection. A rule may be approximate and still count as acceptable if it gives a stable, legible mapping for the grapheme and its decomposed parts.

## Executive Summary

The file is a solid first-generation coverage layer, but it is **not yet comprehensive enough** to satisfy the app-wide requirement.

The strongest parts are:

- Korean: algorithmic Hangul decomposition is the best-covered system in the file.
- Japanese kana: hiragana, katakana, yoon, small vowels, sokuon, choonpu, and several foreign-sound combinations are represented well.
- Arabic/Persian/Urdu: broad codepoint coverage with combining-mark handling is already substantial.
- Greek, Russian, Armenian, and most Latin-script languages: these have broad codepoint coverage and workable span maps.
- Abugidas: Hindi, Sanskrit, Bengali, Punjabi, and Tamil all have a real compositional model rather than only flat lookup tables.

The main blockers are:

- Chinese and Classical Chinese are still effectively unsupported. The `han` profile returns empty sound values.
- Japanese Kanji are also effectively unsupported because `analyzeJapanese()` explicitly returns empty sound for Han content.
- Irish (`ga`) is registered by the app but has no alias or profile in the file.
- Biblical Hebrew / Ancient Hebrew (`hbo`) is registered by the app but has no alias or profile in the file.
- Several families are "broad but shallow": they cover many codepoints, but still miss a number of multi-codepoint grapheme behaviors that users will expect to see represented in `PHON`.

So the current state is good enough for a partial rollout, but not good enough to claim comprehensive support across all active languages in the app.

## Method

I compared the rule file against the active language registry and the current analyzer design.

The critical completeness questions were:

1. Does every app language resolve to a profile or alias?
2. Does the profile emit non-empty sound values for the graphemes users will actually see?
3. Does the profile expose decomposed part-level sounds for complex clusters?
4. Does it at least provide a fallback representation when true pronunciation is ambiguous?

That last point matters because your requirement is usability, not perfect phonology. If a cluster cannot be resolved elegantly, it still needs a visible mapping rather than silence.

## Language-by-Language Assessment

### 1. Strong Coverage

**Korean (`ko`)**

This is the strongest implementation in the file. Precomposed Hangul syllables are decomposed algorithmically into choseong, jungseong, and jongseong, and compatibility jamo are also mapped. That means both the surface syllable and its internal decomposition are represented. For the `PHON` use case, this is exactly the right pattern.

**Japanese kana layer (`ja`)**

Kana coverage is strong: base kana, dakuten/handakuten, small kana, yoon combinations, sokuon, choonpu, foreign-sound katakana, and Ainu small katakana extensions are all represented in some fashion. This is enough to make `PHON` genuinely useful on kana-heavy text.

**Arabic, Persian, Urdu (`ar`, `fa`, `ur`)**

These profiles have broad base-letter coverage and explicit combining-mark handling. The file also includes a large extension block for additional Arabic-script codepoints, which is exactly the sort of "no-gap fallback" layer a comprehensive system needs. The output is approximate, but the decomposition story is good: base letters and marks each get mapped.

**Greek and Ancient Greek (`el`, `grc`)**

These are in decent shape. Letters, diphthongs, rough breathing, and several compatibility characters are represented. Ancient Greek especially benefits from having a separate profile instead of being forced through modern Greek rules.

**Russian and Armenian (`ru`, `hy`)**

These are simple-script profiles with strong one-codepoint coverage. They are not deeply context-sensitive, but they do meet the grapheme-to-sound requirement much better than silence would.

### 2. Adequate but Needs Expansion

**Hindi, Sanskrit, Bengali, Punjabi, Tamil**

The abugida framework is a strong architectural choice. It handles consonants, independent vowels, vowel signs, virama suppression, marks, and nukta-derived forms. That means complex graphemes are not just lookup entries; they are actually composed. For completeness, this is much better than a flat table.

The weakness is that the model is still orthography-driven rather than language-specific in the deeper sense. It does not attempt Hindi schwa deletion, Punjabi-specific reductions, Tamil contextual alternations, or Sanskrit sandhi. That is acceptable for now. The larger issue is edge coverage: these scripts have a very long tail of conjunct behavior, archaic signs, and presentation patterns. The system is directionally correct, but it should be tested aggressively against real corpus output.

**Thai**

Thai has a real parser rather than only a letter map, which is good. It recognizes prefix vowels, vowel cores, codas, tone marks, and silent markers. That said, Thai orthography is one of the hardest systems in the app, and this model is still heuristic. It will often produce a useful decomposition display, but it likely under-covers complex vowel arrangements, silent letters, and orthographic patterns around `รร`, `ฤ`, stacked forms, and tone-class interactions. I would rate it "promising but incomplete."

**Latin-script languages: Vietnamese, Turkish, Indonesian, Tagalog, Swahili, Latin, French, Italian, Spanish, German, Dutch, Portuguese, Old English**

This entire block benefits from a strong fallback strategy: NFKD decomposition, large generic Latin coverage, and language-specific span maps. That gives wide codepoint coverage, which is exactly what you want for completeness. Even when the span map misses a digraph or trigraph, the user still gets part-level output.

The limitation is span completeness. These languages have many frequent multigraphs that are not exhaustively represented. So the system is broad, but not uniformly deep. For `PHON`, that is acceptable as long as the fallback remains visible and readable.

### 3. Major Gaps

**Chinese, Traditional Chinese, Classical Chinese (`zh`, `zh-hant`, `lzh`)**

This is the biggest gap. The `han` profile explicitly returns empty sound values. That means the file currently provides no useful `PHON` output for Chinese-family languages. Under your standard, that fails completeness.

A perfect solution would require real readings, but you do not need perfection here. You need representation. At minimum, Han needs a deterministic fallback policy such as:

- emit a placeholder like `han` or `?` per codepoint,
- emit Unicode block/category labels,
- emit an explicit "unmapped Han grapheme" token,
- or route through a per-language approximate table for the most frequent characters.

Any of those would be better than empty output. Right now the system says nothing.

**Japanese Kanji**

Because `analyzeJapanese()` returns empty sound for Han content, Japanese text that contains Kanji also falls into the same hole. Kana are well covered, but mixed-script Japanese is not comprehensive unless Han characters are represented somehow.

**Irish (`ga`)**

Irish is in the app registry but is absent from the pronunciation file. Since the generic Latin profile exists, the minimum viable fix is straightforward: add `ga -> irish` aliasing and create an Irish profile that inherits generic Latin plus Irish digraph/trigraph rules. Without that, Irish currently has no language-specific coverage at all.

**Biblical Hebrew / Ancient Hebrew (`hbo`)**

This language is also in the app registry but absent from the file. It should at least alias to the Hebrew profile as a baseline, even if a later version adds Biblical-Hebrew-specific rules.

## Overall Verdict

The file is **architecturally good** and already useful for many languages, but it is **not yet comprehensive across the app**. The failure is not in the general design. The failure is in coverage boundaries:

- some app languages are missing entirely,
- Han-script output is blank,
- and a few complex writing systems still need broader tail coverage.

## Recommended Next Steps

1. Treat Han coverage as the highest-priority blocker. Empty output is worse than approximate output.
2. Add missing registry languages immediately: `ga` and `hbo`.
3. Add a "never silent" fallback rule: if a grapheme cannot be pronounced, emit a visible placeholder instead of `""`.
4. Build a corpus-based audit pass per script family to find unmapped graphemes from real app text.
5. Expand multigraph span maps gradually, especially for Thai and the Latin-script languages.

## Final Assessment

If the question is "Is this file a good foundation?" the answer is yes.

If the question is "Is it already comprehensive enough for every active language in the app?" the answer is no. The biggest reason is Han-script silence, followed by missing Irish and Biblical Hebrew profiles. Once those are addressed, the remaining issues are mostly iterative refinement rather than structural incompleteness.
