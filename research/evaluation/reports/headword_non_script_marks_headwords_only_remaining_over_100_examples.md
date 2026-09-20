# Remaining High-frequency Headword Marks Not Already Normalized Out

- Source: headwords only across all real TSV dictionaries in `wiktionary general pipeline/converted_tsv`
- Forms are excluded from this report
- Included only when total headword hits > 100
- Excluded as already normalized out when the current lookup normalization collapses the standalone mark to an empty key
- Lookup normalization basis: NFKC, affix-marker translation, then hyphen removal
- Script-family filtering uses the same language-specific codepoint families as the main batch probe
- Examples: 10 deterministic pseudo-random real headword surfaces per remaining mark
- High-frequency headword marks considered: 12
- Excluded as already normalized out: 7
- Remaining marks in this file: 5

## Excluded Already-normalized Marks

- `U+0020` [space] (SPACE) - headword hits 241,990
- `U+002D` - (HYPHEN-MINUS) - headword hits 36,037
- `U+0027` ' (APOSTROPHE) - headword hits 5,742
- `U+002E` . (FULL STOP) - headword hits 3,973
- `U+002C` , (COMMA) - headword hits 1,116
- `U+FF0C` ， (FULLWIDTH COMMA) - headword hits 733
- `U+2026` … (HORIZONTAL ELLIPSIS) - headword hits 299

## `U+200C` [control/format]

- Unicode name: ZERO WIDTH NON-JOINER
- Category: `Cf`
- Headword hits: 1,877
- Dictionaries containing it: 3
- Per-dictionary headword totals: dict-persian: 1,875; dict-hindi: 1; dict-urdu: 1
- Examples:
  1. `dict-persian` | شکست‌خورده
  2. `dict-persian` | می‌گفتی
  3. `dict-persian` | کفش‌دوزک
  4. `dict-persian` | شگفت‌زده
  5. `dict-persian` | می‌گم
  6. `dict-persian` | لپ‌تاپ
  7. `dict-persian` | یخ‌زن
  8. `dict-persian` | می‌کنم
  9. `dict-persian` | می‌گفتند
  10. `dict-persian` | استادانه‌ترین

## `U+002A` *

- Unicode name: ASTERISK
- Category: `Po`
- Headword hits: 318
- Dictionaries containing it: 10
- Per-dictionary headword totals: dict-german: 154; dict-portuguese: 64; dict-russian: 25; dict-dutch: 24; dict-french: 20; dict-italian: 15; dict-vietnamese: 9; dict-spanish: 4; dict-japanese: 2; dict-turkish: 1
- Examples:
  1. `dict-german` | p*ppest
  2. `dict-italian` | f***
  3. `dict-portuguese` | f*do
  4. `dict-italian` | c***o
  5. `dict-german` | p*ppen
  6. `dict-french` | c*nnard
  7. `dict-german` | F*tz
  8. `dict-german` | Sch**sse
  9. `dict-french` | c*ls
  10. `dict-portuguese` | f*deras

## `U+2014` —

- Unicode name: EM DASH
- Category: `Pd`
- Headword hits: 274
- Dictionaries containing it: 2
- Per-dictionary headword totals: dict-chinese: 236; dict-russian: 38
- Examples:
  1. `dict-chinese` | 囡仔穿大人衫——大軀
  2. `dict-russian` | вход — рубль, выход — два
  3. `dict-chinese` | 豬八戒照鏡子——裡外不是人
  4. `dict-chinese` | 秋後的螞蚱——蹦躂不了幾天
  5. `dict-chinese` | 鴨仔跋落水——免驚死
  6. `dict-chinese` | 老婆擔遮——陰功
  7. `dict-chinese` | 便所彈吉他——臭彈
  8. `dict-chinese` | 鐵拐李踢足球——一腳踢
  9. `dict-russian` | конденсаты Бозе — Эйнштейна
  10. `dict-chinese` | 火燒棺材——大嘆

## `U+002F` /

- Unicode name: SOLIDUS
- Category: `Po`
- Headword hits: 157
- Dictionaries containing it: 16
- Per-dictionary headword totals: dict-portuguese: 23; dict-german: 22; dict-russian: 21; dict-french: 13; dict-japanese: 12; dict-spanish: 12; dict-vietnamese: 11; dict-dutch: 9; dict-italian: 8; dict-greek: 6; dict-turkish: 6; dict-indonesian: 4; dict-latin: 4; dict-thai: 3; dict-chinese: 2; dict-hebrew: 1
- Examples:
  1. `dict-russian` | т/м
  2. `dict-portuguese` | a/languages M to Z
  3. `dict-dutch` | t/m
  4. `dict-russian` | см/сек
  5. `dict-french` | N/M
  6. `dict-russian` | с/ч
  7. `dict-portuguese` | a/c
  8. `dict-german` | Neustadts/Westerwald
  9. `dict-greek` | δ/ντής
  10. `dict-german` | m/w/*

## `U+0060` \`

- Unicode name: GRAVE ACCENT
- Category: `Sk`
- Headword hits: 128
- Dictionaries containing it: 7
- Per-dictionary headword totals: dict-japanese: 96; dict-chinese: 6; dict-german: 6; dict-greek: 6; dict-hebrew: 6; dict-thai: 6; dict-russian: 2
- Examples:
  1. `dict-japanese` | (´・ω・\`)
  2. `dict-japanese` | \`period\`
  3. `dict-japanese` | \`lowbar\`(.\`lowbar\`.)\`lowbar\`
  4. `dict-greek` | \`period\`
  5. `dict-german` | \`lowbar\`
  6. `dict-japanese` | (^\`lowbar\`^)/\`tilde\`\`tilde\`\`tilde\`
  7. `dict-chinese` | \`num\`
  8. `dict-japanese` | m(\`lowbar\`\`lowbar\`)m
  9. `dict-chinese` | \`num\` \`num\`
  10. `dict-thai` | \`period\`

