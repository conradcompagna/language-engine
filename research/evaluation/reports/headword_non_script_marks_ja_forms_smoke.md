# Non-script Marks Inventory for `ja`

- Dictionary: `wiktionary general pipeline\converted_tsv\dict-japanese.tsv`
- TSV rows scanned: 139,215
- Headword surfaces scanned: 139,215
- Form surfaces scanned: 1,122,991
- Script family treated as in-family: Japanese family (Han + Hiragana + Katakana + related kana marks)
- Counted as junk: codepoints outside that family whose Unicode category starts with `P`, `S`, `Z`, `M`, or `C`
- Explicitly excluded from this pass: letters and decimal digits
- Distinct junk codepoints found: 219
- Total junk-codepoint occurrences: 349,670

| Glyph | Codepoint | Total | Headword | Forms | Category | Unicode name | Sample surfaces |
| --- | --- | ---: | ---: | ---: | --- | --- | --- |
| [space] | `U+0020` | 290,724 | 3,669 | 287,055 | `Zs` | SPACE | itaku nai; itaku nakatta; itai desu; itaku nai desu; itakatta desu |
| ^ | `U+005E` | 17,641 | 11 | 17,630 | `Sk` | CIRCUMFLEX ACCENT | 大きい ^-i; 酉 ^; 月 ^; 月 ^^†-nari; あい ^ |
| [ | `U+005B` | 8,274 | 0 | 8,274 | `Ps` | LEFT SQUARE BRACKET | 合い [ai]; 合う [au]; 合って [atte]; 合わないで [awanai de]; 合わなくて [awanakute] |
| ] | `U+005D` | 8,274 | 0 | 8,274 | `Pe` | RIGHT SQUARE BRACKET | 合い [ai]; 合う [au]; 合って [atte]; 合わないで [awanai de]; 合わなくて [awanakute] |
| - | `U+002D` | 5,697 | 1,208 | 4,489 | `Pd` | HYPHEN-MINUS | a-; 大きい ^-i; dai-; 月 ^^†-nari; -ai |
| （ | `U+FF08` | 4,198 | 1 | 4,197 | `Ps` | FULLWIDTH LEFT PARENTHESIS | KYなら（ば）; ケーワイなら（ば）; そうなら（ば）; 明らかなら（ば）; あきらかなら（ば） |
| ） | `U+FF09` | 4,198 | 1 | 4,197 | `Pe` | FULLWIDTH RIGHT PARENTHESIS | KYなら（ば）; ケーワイなら（ば）; そうなら（ば）; 明らかなら（ば）; あきらかなら（ば） |
| ' | `U+0027` | 3,330 | 291 | 3,039 | `Po` | APOSTROPHE | da'; imo'; oto'; on'yomi; hon'yaku shi |
| ( | `U+0028` | 2,401 | 26 | 2,375 | `Ps` | LEFT PARENTHESIS | kēwai nara (ba); -sō nara (ba); akiraka nara (ba); are nara (ba); anshin nara (ba) |
| ) | `U+0029` | 2,399 | 24 | 2,375 | `Pe` | RIGHT PARENTHESIS | kēwai nara (ba); -sō nara (ba); akiraka nara (ba); are nara (ba); anshin nara (ba) |
| : | `U+003A` | 590 | 0 | 590 | `Po` | COLON | short form: 合わす [awasu]; colloquial: 合わなきゃ [awanakya]; standard: 合わせられ [awaserare]; colloquial: 合わされ [awasare]; contraction: 合ってる [atteru] |
| † | `U+2020` | 566 | 0 | 566 | `Po` | DAGGER | 月 ^^†-nari; いく ^†yodan; 有り ^†-ri; 丸 ^^†-nari; 便 ^†-nari |
| . | `U+002E` | 287 | 112 | 175 | `Po` | FULL STOP | ..-; .--..; --.--; .-; -.--- |
| ` | `U+0060` | 108 | 96 | 12 | `Sk` | GRAVE ACCENT | `period`; `period``period`; (´・ω・`); ´・ω・`; (´･ω･`) |
| ~ | `U+007E` | 69 | 1 | 68 | `Sm` | TILDE | ~; ~gara; ~gari; ~garu; ~gare |
| … | `U+2026` | 65 | 11 | 54 | `Po` | HORIZONTAL ELLIPSIS | ま…こ; ……; ma…ko; 猶…ごとし; 猶…ごとし ^^†-ku |
| 、 | `U+3001` | 56 | 16 | 40 | `Po` | IDEOGRAPHIC COMMA | 茅萱、白茅; 、; らしかったら、らしいなら; 病は口より入り、禍は口より出ず; 瓜田に履を納れず、李下に冠を正さず |
| ○ | `U+25CB` | 52 | 12 | 40 | `So` | WHITE CIRCLE | ○; ○×; ま○こ; お○んこ; おま○こ |
| { | `U+007B` | 51 | 0 | 51 | `Ps` | LEFT CURLY BRACKET | {{{3}}} ko; {{{3}}} ki; {{{3}}} kuru; {{{3}}} kure; {{{3}}} koi |
| } | `U+007D` | 51 | 0 | 51 | `Pe` | RIGHT CURLY BRACKET | {{{3}}} ko; {{{3}}} ki; {{{3}}} kuru; {{{3}}} kure; {{{3}}} koi |
| & | `U+0026` | 36 | 6 | 30 | `Po` | AMPERSAND | &; R&B; ドラッグ&ドロップ; doraggu&doroppu; ドラッグ&ドロップする suru |
| / | `U+002F` | 33 | 12 | 21 | `Po` | SOLIDUS | π/; (^^)/`tilde``tilde``tilde`; /~~~; (^_^)/~~~; (;_;)/~~~ |
| % | `U+0025` | 25 | 0 | 25 | `Po` | PERCENT SIGN | じゅん%じょうだろ; じゅん%じょうで; じゅん%じょうだ; じゅん%じょうな; じゅん%じょうなら |
| , | `U+002C` | 23 | 7 | 16 | `Po` | COMMA | じょう, jō; ナンバー, nanbā; (This term, しい (shī), is the hiragana spelling of the above term.); : [noun] (rare, archaic, mythology) a beast that looks like a weasel; : [noun] (rare, archaic, mythology) a beast that looks like a wolf |
| _ | `U+005F` | 21 | 0 | 21 | `Pc` | LOW LINE | m(_ _)m; <(_ _)>; _(_^_)_; _(._.)_; (__) |
| ⠐ | `U+2810` | 20 | 20 | 0 | `So` | BRAILLE PATTERN DOTS-5 | ⠐⠡; ⠐⠣; ⠐⠩; ⠐⠫; ⠐⠪ |
| 〜 | `U+301C` | 20 | 2 | 18 | `Pd` | WAVE DASH | きゃ〜; キャ〜; 〜; ま〜; マ〜 |
| ～ | `U+FF5E` | 20 | 0 | 20 | `Sm` | FULLWIDTH TILDE | ～; ～がら; ～がり; ～がる; ～がれ |
| @ | `U+0040` | 16 | 5 | 11 | `Po` | COMMERCIAL AT | @; (@^^)/~~~; (@^^)/`tilde``tilde``tilde` |
| + | `U+002B` | 13 | 4 | 9 | `Sm` | PLUS SIGN | 蹳 足 + 發; C++; +α |
| ´ | `U+00B4` | 13 | 4 | 9 | `Sk` | ACUTE ACCENT | (´・ω・`); ´・ω・`; (´・ω・｀); (´･ω･`); （´・ω・｀） |
| ？ | `U+FF1F` | 12 | 6 | 6 | `Po` | FULLWIDTH QUESTION MARK | 何歳ですか？; 神を信じますか？; ご飯にする？お風呂にする？それとも私？; なにそれ？おいしいの？; そマ？ |
| × | `U+00D7` | 10 | 3 | 7 | `Sm` | MULTIPLICATION SIGN | ×; ○×; ○×ゲーム; ×いち; ×イチ |
| ◎ | `U+25CE` | 9 | 3 | 6 | `So` | BULLSEYE | ま◎こ; お◎んこ; ◎ |
| ● | `U+25CF` | 9 | 3 | 6 | `So` | BLACK CIRCLE | ま●こ; おま●こ; ● |
| ／ | `U+FF0F` | 9 | 1 | 8 | `Po` | FULLWIDTH SOLIDUS | 丁／挺; 本／灯; 戸／軒／棟; 本／筒; ＼(^o^)／ |
| " | `U+0022` | 8 | 0 | 8 | `Po` | QUOTATION MARK | 球体 : lit. a "spherical body"; 父母 : lit. "father-mother"; 伊邪那美命 : "she who invites"; 隣の芝生は青く見える "The neighbor's grass seems green" |
| ◯ | `U+25EF` | 8 | 2 | 6 | `So` | LARGE CIRCLE | ま◯こ; セッ◯ス |
| = | `U+003D` | 7 | 2 | 5 | `Sm` | EQUALS SIGN | = |
| ― | `U+2015` | 7 | 0 | 7 | `Pd` | HORIZONTAL BAR | ｷﾀ―――(ﾟ∀ﾟ)――――!! |
| ｀ | `U+FF40` | 7 | 2 | 5 | `Sk` | FULLWIDTH GRAVE ACCENT | (´・ω・｀); （´・ω・｀）; ´・ω・｀ |
| * | `U+002A` | 6 | 2 | 4 | `Po` | ASTERISK | ま*こ; ma*ko |
| 【 | `U+3010` | 6 | 1 | 5 | `Ps` | LEFT BLACK LENTICULAR BRACKET | 【 】; 【志ゆき】5; 【青】1; 【自主規制】; 【さくる】 |
| 】 | `U+3011` | 6 | 1 | 5 | `Pe` | RIGHT BLACK LENTICULAR BRACKET | 【 】; 【志ゆき】5; 【青】1; 【自主規制】; 【さくる】 |
| ? | `U+003F` | 5 | 3 | 2 | `Po` | QUESTION MARK | nani sore? oishii no?; nansai desu ka? |
| ☆ | `U+2606` | 5 | 2 | 3 | `So` | WHITE STAR | ま☆こ; ☆彡 |
| ⠠ | `U+2820` | 5 | 5 | 0 | `So` | BRAILLE PATTERN DOTS-6 | ⠠⠥; ⠠⠧; ⠠⠭; ⠠⠯; ⠠⠮ |
| 。 | `U+3002` | 5 | 4 | 1 | `Po` | IDEOGRAPHIC FULL STOP | 。; お元気ですか。; 。。。 |
| ; | `U+003B` | 4 | 2 | 2 | `Po` | SEMICOLON | (;_;)/~~~; (;`lowbar`;)/`tilde``tilde``tilde` |
| · | `U+00B7` | 4 | 2 | 2 | `Po` | MIDDLE DOT | ($··)/~~~; ($··)/`tilde``tilde``tilde` |
| – | `U+2013` | 4 | 0 | 4 | `Pd` | EN DASH | For pronunciation and definitions of しい – see the following entry.; For pronunciation and definitions of 刳る – see the following entry. |
| ㈪ | `U+322A` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH MOON | ㈪; ㈪ ^ |
| ㈫ | `U+322B` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH FIRE | ㈫; ㈫ ^ |
| ㈬ | `U+322C` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH WATER | ㈬; ㈬ ^ |
| ㈭ | `U+322D` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH WOOD | ㈭; ㈭ ^ |
| ㈮ | `U+322E` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH METAL | ㈮; ㈮ ^ |
| ㈯ | `U+322F` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH EARTH | ㈯; ㈯ ^ |
| ㈰ | `U+3230` | 4 | 1 | 3 | `So` | PARENTHESIZED IDEOGRAPH SUN | ㈰; ㈰ ^ |
| ㊊ | `U+328A` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH MOON | ㊊; ㊊ ^ |
| ㊋ | `U+328B` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH FIRE | ㊋; ㊋ ^ |
| ㊌ | `U+328C` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH WATER | ㊌; ㊌ ^ |
| ㊍ | `U+328D` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH WOOD | ㊍; ㊍ ^ |
| ㊎ | `U+328E` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH METAL | ㊎; ㊎ ^ |
| ㊏ | `U+328F` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH EARTH | ㊏; ㊏ ^ |
| ㊐ | `U+3290` | 4 | 1 | 3 | `So` | CIRCLED IDEOGRAPH SUN | ㊐; ㊐ ^ |
| © | `U+00A9` | 3 | 1 | 2 | `So` | COPYRIGHT SIGN | © |
| ⠥ | `U+2825` | 3 | 3 | 0 | `So` | BRAILLE PATTERN DOTS-136 | ⠥; ⠐⠥; ⠠⠥ |
| ⠧ | `U+2827` | 3 | 3 | 0 | `So` | BRAILLE PATTERN DOTS-1236 | ⠧; ⠐⠧; ⠠⠧ |
| ⠭ | `U+282D` | 3 | 3 | 0 | `So` | BRAILLE PATTERN DOTS-1346 | ⠭; ⠐⠭; ⠠⠭ |
| ⠮ | `U+282E` | 3 | 3 | 0 | `So` | BRAILLE PATTERN DOTS-2346 | ⠮; ⠐⠮; ⠠⠮ |
| ⠯ | `U+282F` | 3 | 3 | 0 | `So` | BRAILLE PATTERN DOTS-12346 | ⠯; ⠐⠯; ⠠⠯ |
| 〒 | `U+3012` | 3 | 1 | 2 | `So` | POSTAL MARK | 〒 |
| 〠 | `U+3020` | 3 | 1 | 2 | `So` | POSTAL MARK FACE | 〠 |
| 〶 | `U+3036` | 3 | 1 | 2 | `So` | CIRCLED POSTAL MARK | 〶 |
| [control/format] | `U+32501` | 3 | 1 | 2 | `Cn` | <unnamed> | 𲔁 |
| [control/format] | `U+33143` | 3 | 1 | 2 | `Cn` | <unnamed> | 𳅃 |
| ㌠ | `U+3320` | 3 | 1 | 2 | `So` | SQUARE SANTIIMU | ㌠ |
| ＼ | `U+FF3C` | 3 | 1 | 2 | `Po` | FULLWIDTH REVERSE SOLIDUS | ＼; ＼(^o^)／; ＼／ |
| ! | `U+0021` | 2 | 0 | 2 | `Po` | EXCLAMATION MARK | ｷﾀ―――(ﾟ∀ﾟ)――――!! |
| $ | `U+0024` | 2 | 1 | 1 | `Sc` | DOLLAR SIGN | ($··)/~~~; ($··)/`tilde``tilde``tilde` |
| ± | `U+00B1` | 2 | 0 | 2 | `Sm` | PLUS-MINUS SIGN | ±0 |
| 🈚 | `U+1F21A` | 2 | 1 | 1 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-7121 | 🈚 |
| 🈶 | `U+1F236` | 2 | 1 | 1 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-6709 | 🈶 |
| ” | `U+201D` | 2 | 0 | 2 | `Pf` | RIGHT DOUBLE QUOTATION MARK | する slide”; “to rub”: |
| △ | `U+25B3` | 2 | 1 | 1 | `So` | WHITE UP-POINTING TRIANGLE | △ |
| ◌ | `U+25CC` | 2 | 2 | 0 | `So` | DOTTED CIRCLE | ◌̄; ◌̂ |
| ◐ | `U+25D0` | 2 | 1 | 1 | `So` | CIRCLE WITH LEFT HALF BLACK | ◐ |
| ◑ | `U+25D1` | 2 | 1 | 1 | `So` | CIRCLE WITH RIGHT HALF BLACK | ◑ |
| ⠕ | `U+2815` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-135 | ⠕; ⠐⠕ |
| ⠗ | `U+2817` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-1235 | ⠗; ⠐⠗ |
| ⠝ | `U+281D` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-1345 | ⠝; ⠐⠝ |
| ⠞ | `U+281E` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-2345 | ⠞; ⠐⠞ |
| ⠟ | `U+281F` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-12345 | ⠟; ⠐⠟ |
| ⠡ | `U+2821` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-16 | ⠡; ⠐⠡ |
| ⠣ | `U+2823` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-126 | ⠣; ⠐⠣ |
| ⠩ | `U+2829` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-146 | ⠩; ⠐⠩ |
| ⠪ | `U+282A` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-246 | ⠪; ⠐⠪ |
| ⠫ | `U+282B` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-1246 | ⠫; ⠐⠫ |
| ⠱ | `U+2831` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-156 | ⠱; ⠐⠱ |
| ⠳ | `U+2833` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-1256 | ⠳; ⠐⠳ |
| ⠹ | `U+2839` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-1456 | ⠹; ⠐⠹ |
| ⠺ | `U+283A` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-2456 | ⠺; ⠐⠺ |
| ⠻ | `U+283B` | 2 | 2 | 0 | `So` | BRAILLE PATTERN DOTS-12456 | ⠻; ⠐⠻ |
| 〝 | `U+301D` | 2 | 2 | 0 | `Ps` | REVERSED DOUBLE PRIME QUOTATION MARK | 〝 〟; 〝 〞 |
| ㈱ | `U+3231` | 2 | 1 | 1 | `So` | PARENTHESIZED IDEOGRAPH STOCK | ㈱ |
| # | `U+0023` | 1 | 0 | 1 | `Po` | NUMBER SIGN | [[#Japanese\|]] |
| < | `U+003C` | 1 | 0 | 1 | `Sm` | LESS-THAN SIGN | <(_ _)> |
| > | `U+003E` | 1 | 0 | 1 | `Sm` | GREATER-THAN SIGN | <(_ _)> |
| \\ | `U+005C` | 1 | 1 | 0 | `Po` | REVERSE SOLIDUS | \\ |
| \| | `U+007C` | 1 | 0 | 1 | `Sm` | VERTICAL LINE | [[#Japanese\|]] |
| ̂ | `U+0302` | 1 | 1 | 0 | `Mn` | COMBINING CIRCUMFLEX ACCENT | ◌̂ |
| ̄ | `U+0304` | 1 | 1 | 0 | `Mn` | COMBINING MACRON | ◌̄ |
| 🈁 | `U+1F201` | 1 | 1 | 0 | `So` | SQUARED KATAKANA KOKO | 🈁 |
| 🈂 | `U+1F202` | 1 | 1 | 0 | `So` | SQUARED KATAKANA SA | 🈂 |
| 🈯 | `U+1F22F` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-6307 | 🈯 |
| 🈲 | `U+1F232` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-7981 | 🈲 |
| 🈳 | `U+1F233` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-7A7A | 🈳 |
| 🈴 | `U+1F234` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-5408 | 🈴 |
| 🈵 | `U+1F235` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-6E80 | 🈵 |
| 🈷 | `U+1F237` | 1 | 1 | 0 | `So` | SQUARED CJK UNIFIED IDEOGRAPH-6708 | 🈷 |
| 🉐 | `U+1F250` | 1 | 1 | 0 | `So` | CIRCLED IDEOGRAPH ADVANTAGE | 🉐 |
| 🔰 | `U+1F530` | 1 | 1 | 0 | `So` | JAPANESE SYMBOL FOR BEGINNER | 🔰 |
| “ | `U+201C` | 1 | 0 | 1 | `Pi` | LEFT DOUBLE QUOTATION MARK | “to rub”: |
| • | `U+2022` | 1 | 0 | 1 | `Po` | BULLET | ひだるい • |
| ‥ | `U+2025` | 1 | 1 | 0 | `Po` | TWO DOT LEADER | ‥ |
| ※ | `U+203B` | 1 | 1 | 0 | `Po` | REFERENCE MARK | ※ |
| № | `U+2116` | 1 | 1 | 0 | `So` | NUMERO SIGN | № |
| ↑ | `U+2191` | 1 | 1 | 0 | `Sm` | UPWARDS ARROW | ↑ |
| ↓ | `U+2193` | 1 | 1 | 0 | `Sm` | DOWNWARDS ARROW | ↓ |
| ∀ | `U+2200` | 1 | 0 | 1 | `Sm` | FOR ALL | ｷﾀ―――(ﾟ∀ﾟ)――――!! |
| ⊡ | `U+22A1` | 1 | 1 | 0 | `Sm` | SQUARED DOT OPERATOR | ⊡ |
| Ⓧ | `U+24CD` | 1 | 1 | 0 | `So` | CIRCLED LATIN CAPITAL LETTER X | Ⓧ |
| Ⓨ | `U+24CE` | 1 | 1 | 0 | `So` | CIRCLED LATIN CAPITAL LETTER Y | Ⓨ |
| ▴ | `U+25B4` | 1 | 1 | 0 | `So` | BLACK UP-POINTING SMALL TRIANGLE | ▴ |
| ▼ | `U+25BC` | 1 | 1 | 0 | `So` | BLACK DOWN-POINTING TRIANGLE | ▼ |
| ▽ | `U+25BD` | 1 | 1 | 0 | `So` | WHITE DOWN-POINTING TRIANGLE | ▽ |
| ◉ | `U+25C9` | 1 | 1 | 0 | `So` | FISHEYE | ◉ |
| ◬ | `U+25EC` | 1 | 1 | 0 | `So` | WHITE UP-POINTING TRIANGLE WITH DOT | ◬ |
| ☼ | `U+263C` | 1 | 1 | 0 | `So` | WHITE SUN WITH RAYS | ☼ |
| ♂ | `U+2642` | 1 | 1 | 0 | `So` | MALE SIGN | ♂ |
| ♪ | `U+266A` | 1 | 1 | 0 | `So` | EIGHTH NOTE | ♪ |
| ⛏ | `U+26CF` | 1 | 1 | 0 | `So` | PICK | ⛏ |
| ⛣ | `U+26E3` | 1 | 1 | 0 | `So` | HEAVY CIRCLE WITH STROKE AND TWO DOTS ABOVE | ⛣ |
| ⛨ | `U+26E8` | 1 | 1 | 0 | `So` | BLACK CROSS ON SHIELD | ⛨ |
| ⛩ | `U+26E9` | 1 | 1 | 0 | `So` | SHINTO SHRINE | ⛩ |
| ⛪ | `U+26EA` | 1 | 1 | 0 | `So` | CHURCH | ⛪ |
| ⛫ | `U+26EB` | 1 | 1 | 0 | `So` | CASTLE | ⛫ |
| ⛬ | `U+26EC` | 1 | 1 | 0 | `So` | HISTORIC SITE | ⛬ |
| ⛭ | `U+26ED` | 1 | 1 | 0 | `So` | GEAR WITHOUT HUB | ⛭ |
| ⛮ | `U+26EE` | 1 | 1 | 0 | `So` | GEAR WITH HANDLES | ⛮ |
| ⛯ | `U+26EF` | 1 | 1 | 0 | `So` | MAP SYMBOL FOR LIGHTHOUSE | ⛯ |
| ⛰ | `U+26F0` | 1 | 1 | 0 | `So` | MOUNTAIN | ⛰ |
| ⛱ | `U+26F1` | 1 | 1 | 0 | `So` | UMBRELLA ON GROUND | ⛱ |
| ⛲ | `U+26F2` | 1 | 1 | 0 | `So` | FOUNTAIN | ⛲ |
| ⛴ | `U+26F4` | 1 | 1 | 0 | `So` | FERRY | ⛴ |
| ⛶ | `U+26F6` | 1 | 1 | 0 | `So` | SQUARE FOUR CORNERS | ⛶ |
| ⛸ | `U+26F8` | 1 | 1 | 0 | `So` | ICE SKATE | ⛸ |
| ⛹ | `U+26F9` | 1 | 1 | 0 | `So` | PERSON WITH BALL | ⛹ |
| ⛻ | `U+26FB` | 1 | 1 | 0 | `So` | JAPANESE BANK SYMBOL | ⛻ |
| ⛼ | `U+26FC` | 1 | 1 | 0 | `So` | HEADSTONE GRAVEYARD SYMBOL | ⛼ |
| ⛾ | `U+26FE` | 1 | 1 | 0 | `So` | CUP ON BLACK SQUARE | ⛾ |
| ⠁ | `U+2801` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-1 | ⠁ |
| ⠃ | `U+2803` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-12 | ⠃ |
| ⠄ | `U+2804` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-3 | ⠄ |
| ⠅ | `U+2805` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-13 | ⠅ |
| ⠆ | `U+2806` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-23 | ⠆ |
| ⠇ | `U+2807` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-123 | ⠇ |
| ⠉ | `U+2809` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-14 | ⠉ |
| ⠊ | `U+280A` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-24 | ⠊ |
| ⠋ | `U+280B` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-124 | ⠋ |
| ⠌ | `U+280C` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-34 | ⠌ |
| ⠍ | `U+280D` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-134 | ⠍ |
| ⠎ | `U+280E` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-234 | ⠎ |
| ⠏ | `U+280F` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-1234 | ⠏ |
| ⠑ | `U+2811` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-15 | ⠑ |
| ⠓ | `U+2813` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-125 | ⠓ |
| ⠔ | `U+2814` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-35 | ⠔ |
| ⠖ | `U+2816` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-235 | ⠖ |
| ⠙ | `U+2819` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-145 | ⠙ |
| ⠚ | `U+281A` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-245 | ⠚ |
| ⠛ | `U+281B` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-1245 | ⠛ |
| ⠜ | `U+281C` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-345 | ⠜ |
| ⠬ | `U+282C` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-346 | ⠬ |
| ⠴ | `U+2834` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-356 | ⠴ |
| ⠵ | `U+2835` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-1356 | ⠵ |
| ⠷ | `U+2837` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-12356 | ⠷ |
| ⠽ | `U+283D` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-13456 | ⠽ |
| ⠾ | `U+283E` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-23456 | ⠾ |
| ⠿ | `U+283F` | 1 | 1 | 0 | `So` | BRAILLE PATTERN DOTS-123456 | ⠿ |
| ⮗ | `U+2B97` | 1 | 1 | 0 | `So` | SYMBOL FOR TYPE A ELECTRONICS | ⮗ |
| 〈 | `U+3008` | 1 | 1 | 0 | `Ps` | LEFT ANGLE BRACKET | 〈 〉 |
| 〉 | `U+3009` | 1 | 1 | 0 | `Pe` | RIGHT ANGLE BRACKET | 〈 〉 |
| 「 | `U+300C` | 1 | 1 | 0 | `Ps` | LEFT CORNER BRACKET | 「 」 |
| 」 | `U+300D` | 1 | 1 | 0 | `Pe` | RIGHT CORNER BRACKET | 「 」 |
| 『 | `U+300E` | 1 | 1 | 0 | `Ps` | LEFT WHITE CORNER BRACKET | 『 』 |
| 』 | `U+300F` | 1 | 1 | 0 | `Pe` | RIGHT WHITE CORNER BRACKET | 『 』 |
| 〔 | `U+3014` | 1 | 1 | 0 | `Ps` | LEFT TORTOISE SHELL BRACKET | 〔 〕 |
| 〕 | `U+3015` | 1 | 1 | 0 | `Pe` | RIGHT TORTOISE SHELL BRACKET | 〔 〕 |
| 〞 | `U+301E` | 1 | 1 | 0 | `Pe` | DOUBLE PRIME QUOTATION MARK | 〝 〞 |
| 〟 | `U+301F` | 1 | 1 | 0 | `Pe` | LOW DOUBLE PRIME QUOTATION MARK | 〝 〟 |
| 〰 | `U+3030` | 1 | 1 | 0 | `Pd` | WAVY DASH | 〰 |
| 〽 | `U+303D` | 1 | 1 | 0 | `Po` | PART ALTERNATION MARK | 〽 |
| ㈲ | `U+3232` | 1 | 1 | 0 | `So` | PARENTHESIZED IDEOGRAPH HAVE | ㈲ |
| ㈷ | `U+3237` | 1 | 1 | 0 | `So` | PARENTHESIZED IDEOGRAPH CONGRATULATION | ㈷ |
| [control/format] | `U+323B1` | 1 | 1 | 0 | `Cn` | <unnamed> | 𲎱 |
| ㊗ | `U+3297` | 1 | 1 | 0 | `So` | CIRCLED IDEOGRAPH CONGRATULATION | ㊗ |
| [control/format] | `U+32A34` | 1 | 1 | 0 | `Cn` | <unnamed> | 𲨴 |
| [control/format] | `U+32A37` | 1 | 1 | 0 | `Cn` | <unnamed> | 𲨷 |
| [control/format] | `U+32C19` | 1 | 1 | 0 | `Cn` | <unnamed> | 𲰙 |
| ㌉ | `U+3309` | 1 | 0 | 1 | `So` | SQUARE ONSU | ㌉ |
| ㌩ | `U+3329` | 1 | 0 | 1 | `So` | SQUARE NOTTO | ㌩ |
| ㍄ | `U+3344` | 1 | 0 | 1 | `So` | SQUARE MAIRU | ㍄ |
| ㍎ | `U+334E` | 1 | 0 | 1 | `So` | SQUARE YAADO | ㍎ |
| ㍼ | `U+337C` | 1 | 0 | 1 | `So` | SQUARE ERA NAME SYOUWA | ㍼ |
| ㍽ | `U+337D` | 1 | 0 | 1 | `So` | SQUARE ERA NAME TAISYOU | ㍽ |
| ㍾ | `U+337E` | 1 | 0 | 1 | `So` | SQUARE ERA NAME MEIZI | ㍾ |
| ！ | `U+FF01` | 1 | 0 | 1 | `Po` | FULLWIDTH EXCLAMATION MARK | 万国の労働者よ、団結せよ！ |
| ＊ | `U+FF0A` | 1 | 0 | 1 | `Po` | FULLWIDTH ASTERISK | ぽこ＊ん |
| ＝ | `U+FF1D` | 1 | 0 | 1 | `Sm` | FULLWIDTH EQUALS SIGN | ＝ |
