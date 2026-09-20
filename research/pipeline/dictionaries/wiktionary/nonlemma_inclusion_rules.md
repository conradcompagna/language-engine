# Yomitan Non-Lemma Inclusion Rules and Tag Set

Generated: 2026-03-05T14:11:48
Zips scanned: kty-ar-en.zip, kty-fa-en.zip, kty-hi-en.zip, kty-id-en.zip, kty-te-en.zip, kty-th-en.zip, kty-tr-en.zip, kty-ur-en.zip

## Observed Structural Rule

A term-bank row is treated as non-lemma when:
- `raw[2]` contains token `non-lemma`.

Observed in these zips, `raw[2]` for non-lemma rows is effectively just:
- `non-lemma`

Non-lemma row shape observed:
- `raw[3]` (POS display field) is empty for all non-lemma rows scanned.
- `raw[5]` is a list of mappings: `[base_lemma, [morph_labels...]]`

Non-lemma rows scanned: 3,776,457
Rows with unexpected defs shape: 0

## Non-Lemma Gate Tags (raw[2] token set)

- `non-lemma`: 3,776,457

Top raw[2] full strings on non-lemma rows:
- `non-lemma`: 3,776,457

POS field values on non-lemma rows (top):
- `<empty>`: 3,776,457

## Full Non-Lemma Morphology Label Set

Unique labels in `raw[5][*][1]`: 4,161
Complete list written to:
- `wiktionary general pipeline\nonlemma_morph_label_set_full.tsv`

Top 50 labels:
- `plural`: 58,118
- `verbal noun`: 55,878
- `causative`: 44,292
- `inferential`: 33,736
- `passive`: 27,717
- `first-person plural future`: 27,020
- `second-person plural future`: 27,020
- `conditional`: 27,000
- `third-person plural future`: 26,994
- `third-person singular aorist`: 26,993
- `third-person plural aorist`: 26,993
- `first-person plural aorist`: 26,992
- `third-person singular inferential`: 26,992
- `third-person plural inferential`: 26,991
- `second-person plural aorist`: 26,990
- `first-person plural inferential`: 26,990
- `second-person plural inferential`: 26,990
- `third-person plural progressive`: 26,990
- `third-person plural necessitative`: 26,990
- `third-person plural continuative`: 26,989
- `third-person singular future`: 26,989
- `third-person singular progressive`: 26,989
- `first-person plural progressive`: 26,989
- `second-person plural progressive`: 26,989
- `third-person singular necessitative`: 26,989
- `first-person plural necessitative`: 26,989
- `second-person plural necessitative`: 26,989
- `third-person singular continuative`: 26,988
- `first-person plural continuative`: 26,988
- `second-person plural continuative`: 26,988
- `second-person plural imperative`: 21,939
- `alternative`: 20,702
- `second-person singular future`: 20,275
- `third-person singular conditional`: 20,246
- `second-person singular aorist`: 20,244
- `first-person plural conditional`: 20,244
- `third-person plural conditional`: 20,244
- `second-person singular inferential`: 20,243
- `second-person plural conditional`: 20,243
- `second-person singular progressive`: 20,242
- `second-person singular necessitative`: 20,242
- `second-person singular continuative`: 20,241
- `dative first-person singular`: 17,455
- `nominative second-person singular`: 16,427
- `nominative first-person plural`: 16,427
- `nominative second-person plural`: 16,427
- `accusative first-person singular definite`: 16,427
- `accusative first-person plural definite`: 16,427
- `accusative second-person plural definite`: 16,427
- `dative first-person plural`: 16,427
