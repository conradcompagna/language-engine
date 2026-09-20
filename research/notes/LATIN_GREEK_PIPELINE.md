# Latin & Ancient Greek Support — Evidence Dump

Scope: everything in this codebase that is specifically about **Latin (`la`)** and
**Ancient Greek (`grc`)** — how the dictionaries were built, how the datasets
were created, normalization, and transliteration/romanization. Every claim
below is backed by a file path (and line numbers where useful) actually
present in the repo at `C:\Users\conra\Desktop\universal - js hybrid`. Where
something could not be directly confirmed (e.g. a source file no longer
exists), that is stated explicitly rather than guessed.

Most of the construction evidence lives in the archived
`_deprecated_nonruntime_20260514_184819\` folder — this is the build-time
workshop (one-off conversion/audit scripts, vendored third-party libraries,
raw source dumps, QA reports). The **live runtime** only touches the finished
artifacts: `dict_sqlite/grc.sqlite`, `dict_sqlite/grc-lsj.sqlite`,
`dict_sqlite/la.sqlite`, plus the Trankit model files under
`training/trankit_save_ja_ner_v2/xlm-roberta-base/{latin,ancient-greek}/`.

---

## 1. Where la/grc sit in the live architecture

`language_registry.py` registers both as ordinary entries in the same
generic `LANGUAGE_REGISTRY` dict that every other language uses — there is
**no bespoke Python module** for Latin or Greek (no `latin/` or `greek/`
folder like the old Phase-1 `chinese/`/`japanese/` modules):

```python
# language_registry.py:328-338
"la": {
    "folder": "wiktionary_general",
    "trankit_name": "latin",  # UD_Latin-ITTB
    "has_ner": True,
    "aliases": ["latin"],
    "dict_class": "wiktionary_general.dictionary:WiktionaryDict",
    "dict_file": "wiktionary general pipeline/converted_tsv/dict-latin.tsv",
    "dict_kwargs": {"lang_code": "la"},
    "hooks_path": "wiktionary_general.pipeline:HOOKS",
    "lang_config_file": "wiktionary_general/lang_config_la.json",
},
```

```python
# language_registry.py:361-375
"grc": {
    "folder": "wiktionary_general",
    "trankit_name": "ancient-greek",  # UD_Ancient_Greek-PROIEL
    "has_ner": True,
    "aliases": ["ancient-greek", "ancientgreek"],
    "dict_class": "wiktionary_general.dictionary:WiktionaryDict",
    "dict_file": "wiktionary general pipeline/converted_tsv/dict-ancientgreek.tsv",
    "dict_kwargs": {"lang_code": "grc"},
    "default_dict_source": "wiktionary",
    "hooks_path": "wiktionary_general.pipeline:HOOKS",
    "lang_config_file": "wiktionary_general/lang_config_grc.json",
    "dict_sources": {
        "wiktionary": {"label": "Wiktionary", "dict_file": "wiktionary general pipeline/converted_tsv/dict-ancientgreek.tsv"},
    },
},
```

Both flow through the same 2 active lookup chains documented in
`AGENTS.md`/`CLAUDE.md` (Trankit NLP server-side → client-side DP
segmentation → `/js/hydrate` → `reader_wikt.js` rendering) — there is no
special-cased lookup path for either language. `wiktionary_general/` is a
shared, language-agnostic dictionary loader; `reader_wikt.js` registers `la`,
`latin`, `grc`, `ancient-greek`, `ancientgreek` into the same shared
Wiktionary rendering adapter as every other language
(`static/reader_wikt.js:5-38`, `:1405-1439`) — no per-language popup renderer
exists for either.

**Note on `dict-latin.tsv` / `dict-ancientgreek.tsv`**: the path
`wiktionary general pipeline/` (with spaces) that `language_registry.py`
still points at no longer exists at the live repo root — it only survives
inside `_deprecated_nonruntime_20260514_184819\wiktionary general pipeline\`.
The TSV *build* pipeline is archived; only the already-built
`dict_sqlite/*.sqlite` databases are actually read at runtime. This matches
`AGENTS.md`'s account of Phase 2 (Wiktionary TSV) being superseded by Phase 3
(SQLite).

---

## 2. The dictionaries themselves — what's actually in `dict_sqlite/`

Three SQLite files carry Latin/Greek lexical data:

| File | Entries | Form rows | Built | Source |
|---|---|---|---|---|
| `dict_sqlite/la.sqlite` | 879,020 | 2,546,142 | 2026-03-24 | `dict-latin.tsv` (Wiktionary/kaikki) |
| `dict_sqlite/grc.sqlite` | 60,050 | 1,415,188–1,416,757 | 2026-03-24 | `dict-ancientgreek.tsv` (Wiktionary/kaikki) |
| `dict_sqlite/grc-lsj.sqlite` | 116,497 | 7,156 | 2026-04-11 | Perseus LSJ lexicon (`source_label: 'lsj'`) |

Confirmed directly from each database's own `meta` table, e.g.:

```
grc.sqlite meta:
  lang_code       grc
  source_tsv      C:\Users\conra\Desktop\universal\wiktionary general pipeline\converted_tsv\dict-ancientgreek.tsv
  entry_count     60050
  form_count      1416757
  created_at      2026-03-24T17:58:27Z

grc-lsj.sqlite meta:
  lang_code       grc
  source_label    lsj
  entry_count     116497
  created_at      2026-04-11T20:15:54Z
```

**Important architectural fact, verified in `language_registry.py:372-374` and
`router.py:5421`**: `grc-lsj.sqlite` exists on disk but is **not wired into
the active `dict_sources` for `grc`** — only `"wiktionary"` is registered.
The LSJ database was built, but it is currently a dormant/parked artifact,
not part of the live lookup chain. (`router.py:5421` separately treats the
literal key `"lsj"` as a reserved/excluded key wherever `dict_sources` are
enumerated, which is consistent with LSJ having been deliberately held back
rather than merely forgotten.)

Schema (identical across all three files): `entries(id, headword,
romanization, pos, glosses[json], forms[json], commentary, lemma, etymology,
etymology_number, source, entry_id, tags, format)` and `forms(id, entry_id,
form_text, morph_tags, romanization)`.

---

## 3. Dataset origin — how the Wiktionary-derived `la.sqlite` / `grc.sqlite` were built

**Pipeline**: kaikki.org wiktextract JSON Lines dump → `convert_jsonl_to_tsv.py`
→ TSV → `convert_tsv_to_sqlite.py` → SQLite.

- Raw source confirmed on disk:
  `_deprecated_nonruntime_20260514_184819\wiktionary general pipeline\rawjsonforconversion\kaikki.org-dictionary-AncientGreek (1).jsonl`
  (kaikki.org is the site that runs Tatu Ylonen's `wiktextract` scraper over
  the English Wiktionary dump and republishes it as JSONL per language). The
  equivalent Latin `.jsonl` no longer survives on disk — inferred, not
  directly confirmed, that the same converter produced `dict-latin.tsv`,
  based on identical schema/columns and the recorded `source_tsv` path.

- Converter: `_deprecated_nonruntime_20260514_184819\wiktionary general pipeline\convert_jsonl_to_tsv.py`.
  Output columns: `headword\tpos\tromanization\tglosses\tforms` (line 356).
  `word` → headword; kaikki's raw `pos` string is passed through unmodified;
  `forms` extracted as `[form_text, "tag1;tag2", romanization]` triples;
  `senses` → glosses. No etymology or IPA extraction happens at this stage.

- **Romanization for Greek is not computed by this repo's code — it is a
  passthrough of whatever Wiktionary itself already tagged.**
  `extract_romanization()` (lines 83-89):

  ```python
  def extract_romanization(forms: list) -> str:
      """Pull the romanization string from the forms array."""
      for f in forms:
          tags = f.get("tags", [])
          if tags == ["romanization"]:
              return f.get("form", "")
      return ""
  ```

  Verified byte-identical against the raw dump: for σκύλος the JSONL contains
  `{"form": "σκῠ́λος", ...}` followed by `{"form": "skŭ́los", "tags":
  ["romanization"]}` — matching `grc.sqlite`'s stored value exactly. The
  macron/breve/rough-breathing-as-"h" scholarly convention you see in
  `grc.sqlite` (e.g. `κύων → kŭ́ōn`, `χώρα → khṓrā`, `φῶς → phôs`) originates
  in **Wiktionary's own `Module:grc-translit` / declension templates**,
  already expanded into surface strings by kaikki's scraper before this
  repo's converter ever sees the data. There is no `transliterate`/
  `romanize`/`_greek`/`beta_code` function anywhere in `convert_jsonl_to_tsv.py`.

- **Latin gets no romanization**, correctly, for the same reason in reverse —
  `extract_romanization()` just finds nothing tagged `["romanization"]` in
  Wiktionary's Latin entries (Latin is already Latin-script). Confirmed
  empirically: `la.sqlite`'s `romanization` column is non-empty in only a
  handful of the 879,020 rows (noise, not a real feature).

- `dict-latin.tsv`/`dict-ancientgreek.tsv` themselves no longer exist on disk
  anywhere in the repo — only the built `.sqlite` files remain, plus the QA
  report files (Section 6) which preserve indirect evidence of their content.

---

## 4. The second Greek dictionary: Perseus LSJ import

Separately from the Wiktionary pipeline, `grc-lsj.sqlite` was built from the
**Liddell–Scott–Jones Greek-English Lexicon**, sourced from the
`PerseusDL/lexica` GitHub repository (Perseus TEI XML), packaged as
`lexica-master.zip` — the zip file itself still exists at
`_deprecated_nonruntime_20260514_184819\wiktionary general pipeline\rawjsonforconversion\lexica-master.zip`.
Confirmed in `_deprecated_nonruntime_20260514_184819\reports\transparency_attribution_inventory.md:235`:
*"Wiktionary/Kaikki-derived Ancient Greek TSV/SQLite, plus Perseus LSJ lexica
(github.com/PerseusDL/lexica), CC BY-SA 4.0."*

Three build scripts, representing sequential rebuild attempts:

1. **`convert_lsj_to_sqlite.py`** — first pass. Streams the TEI XML out of the
   zip (`ZIP_PATH = .../rawjsonforconversion/lexica-master.zip`,
   `LSJ_DIR_IN_ZIP = "lexica-master/CTS_XML_TEI/perseus/pdllex/grc/lsj/"`).
   Extracts glosses from `<tr>` elements grouped by `<sense>`, POS from
   `<gramGrp><gram type="pos">` / `<itype>` / gender-tag inference / regex
   fallback, gender from `<gen>` betacode symbols (`o(`/`h(`/`to/`).

   Its transliteration is a **flat, diacritic-stripping betacode→Latin
   character map** — this is the direct cause of the "aaatos"-style
   romanization seen in `grc-lsj.sqlite` (e.g. `ἀάατος → aaatos`):

   ```python
   _BETA_TO_ROMAN = {
       "a": "a", "b": "b", "g": "g", "d": "d", "e": "e",
       "z": "z", "h": "e", "q": "th", "i": "i", "k": "k",
       "l": "l", "m": "m", "n": "n", "c": "x", "o": "o",
       "p": "p", "r": "r", "s": "s", "t": "t", "u": "u",
       "f": "ph", "x": "kh", "y": "ps", "w": "o", "v": "w",
   }

   def betacode_to_romanization(beta: str) -> str:
       beta_clean = clean_betacode(beta).lower()
       beta_clean = re.sub(r"[/\\=\(\)\+\|]", "", beta_clean)  # strips accent/breathing/length FIRST
       ...
   ```

   Every betacode accent/breathing/vowel-length marker (`/ \ = ( ) + |`) is
   regex-stripped *before* the character map runs, so the romanization is
   necessarily flat — a deliberate simplification for a search/sort key, not
   a scholarly display transliteration.

2. **`convert_lsj_zip_to_sqlite.py`** — a more elaborate rewrite (docstring:
   *"bypasses the broken TSV conversion"*), re-parsing the same zip via
   streaming `ET.iterparse`, with its own `betacode_to_greek()` (betacode →
   Greek Unicode, no external `betacode` package dependency) and a second,
   **richer** `greek_to_romanization()` (lines 469-532) that *does* reattach
   rough breathing as leading "h", iota subscript as trailing "i", and
   acute/grave/circumflex/diaeresis via `unicodedata.normalize("NFD"/"NFC")` —
   more faithful than the flat version, but still without the
   macron/vowel-length logic the Wiktionary-sourced `grc.sqlite` has.

3. **`regenerate_grc_lsj_sqlite.py`** — third-stage cleanup/merge, not a
   re-parse: reads the intermediate `grc-lsj.rebuilt.sqlite`, drops unusable
   entries, redirects duplicate headwords, and merges in generated inflected
   forms (see Section 5) from a TSV, writing the final
   `grc-lsj.regenerated.sqlite`.

---

## 5. Generating full inflectional paradigms for Greek

`export_grc_lsj_greek_inflexion.py` generates complete Ancient Greek
inflectional paradigms from LSJ headwords, using three vendored third-party
libraries by James Tauber (jtauber), all confirmed via each project's own
`README.md`/`setup.py` inside the deprecated tree:

| Vendored folder | Upstream project |
|---|---|
| `tmp_inflexion_master\inflexion-master\` | `inflexion` — github.com/jtauber/inflexion (MIT) |
| `tmp_greek_inflexion_master\greek-inflexion-master\` | `greek-inflexion` — github.com/jtauber/greek-inflexion |
| `tmp_greek_accentuation_master\greek-accentuation-master\` | `greek-accentuation` — github.com/jtauber/greek-accentuation (MIT) |

The script imports directly from the vendored source trees:

```python
from accent import calculate_accent, debreath, rebreath, strip_accents
from greek_accentuation.characters import strip_length as do_strip_length
from inflexion import Inflexion
from inflexion.lexicon import Lexicon
from inflexion.stemming import StemmingRuleSet
```

For each LSJ headword (noun/adjective/verb), it discovers candidate stemming
"families" via `StemmingRuleSet.possible_stems`/`possible_stems2` (rules
loaded from the vendored `stemming.yaml`), builds a one-word `Lexicon`, then
calls `Inflexion.generate()` for every matching stemming-rule key — i.e. it
**generates the full paradigm** (all case×number×gender combinations for
nominals; all tense×voice×mood×person×number combinations for verbs) purely
from the lemma, using the vendored library's declension/conjugation rules.
Accent placement is computed separately via `calculate_accent()`
(`greek-inflexion`'s own accent engine, built on `greek-accentuation`).

Output goes to a TSV report (`reports/grc_lsj_greek_inflexion_paradigms.tsv`),
explicitly inspection-only. `regenerate_grc_lsj_sqlite.py` then merges those
generated forms into `grc-lsj.regenerated.sqlite`
(`reports/grc_lsj_regeneration_summary.json`: `generated_rows_inserted:
884289, final_form_count: 914813`).

**This is a separate mechanism from, and should not be confused with, the
1.4M forms in the Wiktionary-derived `grc.sqlite`** — those come from
Wiktionary's own pre-existing declension tables (scraped, not generated), per
`reports/grc_wiktionary_forms_artifact_sweep_2026-04-11.md`
(`Entries: 60,050 … Form rows: 1,415,188`). Two different Greek dictionaries,
two different form-generation mechanisms.

Unrelated cleanup note: `tmp_greek_patch_import/` patches the **Trankit tag
tables and JS normalization layer**, not the linguistic libraries — see
Section 8.

---

## 6. Normalization — what actually happens to Latin/Greek text

Read in full: `universal_normalization.py` (1013 lines). **There is no
grc/la-specific character-range carve-out in this file** — unlike Sanskrit
(which gets a dedicated Devanagari→IAST transliterator, lines 40-128) or
Arabic (a dedicated diacritics-stripping regex, lines 24-28), Latin and
Ancient Greek are handled entirely by generic, language-agnostic Unicode
logic:

- All text is normalized via `unicodedata.normalize("NFKC", text)`
  (`DEFAULT_NORMALIZATION_FORM = "NFKC"`, line 19).
- `strip_non_bmp()` (lines 202-208) removes anything outside the Basic
  Multilingual Plane — this matters for Latin specifically, since the
  Wiktionary-sourced `la.sqlite` contains literal astral-plane alchemical
  symbols (U+1F702 FIRE, U+1F704 WATER, U+263D/E MOON PHASES, U+2643 JUPITER,
  etc. — see Section 7) that this strip prevents from ever reaching Trankit.
- The one place preservation-vs-stripping matters, `_is_ancient_keep_char()`
  (lines 354-359), keeps Unicode general categories **L** (letter), **M**
  (mark), **N** (number), and whitespace:

  ```python
  def _is_ancient_keep_char(ch: str) -> bool:
      """Keep letters, combining marks, digits, and whitespace; strip everything else."""
      if ch.isspace():
          return True
      cat = unicodedata.category(ch)
      return bool(cat) and cat[0] in ("L", "M", "N")
  ```

  Because combining marks (category `M`) are kept by this generic rule,
  **polytonic Greek accents (acute/grave/circumflex, rough/smooth breathing,
  iota subscript) and Latin macrons survive without any grc/la-specific
  code** — it's an emergent property of the letter/mark/number allowlist, not
  a bespoke rule written for these languages.
- `_FORCED_STRIP_PUNCTUATION_LANGS = frozenset()` (line 30) is empty — no
  language is forced through the stricter path by default.
- `_LANGUAGE_ALIASES` (lines 134-178) resolves `grc`/`ancient greek`/
  `ancient-greek` → `grc` and `la`/`latin` → `la` (lines 171-175) for alias
  lookups only; it doesn't change normalization behavior.

**Conclusion**: the correct rendering of Ancient Greek polytonic diacritics
and Latin macrons in this app is not the result of dedicated Greek/Latin
normalization code — it "just works" because the generic
letter/mark/number-preserving filter used for every language happens to
retain the Unicode combining-mark blocks these scripts rely on.

---

## 7. Dataset quality-control specific to Latin/Greek

Three audit sweeps in `_deprecated_nonruntime_20260514_184819\reports\`,
run across every dictionary but with concrete, quotable Latin/Greek numbers:

**a) Non-script-marks inventory** (`headword_non_script_marks/dict-{ancientgreek,latin}.md`)
— scans every headword/form for codepoints outside the expected script +
combining-diacritic set.
- Greek: 60,050 rows / 1,422,098 form surfaces; 35 distinct junk codepoints,
  76,444 occurrences. Notable finds: stray spaces/hyphens in compound
  glosses, a soft-hyphen-joined 21-part compound
  (λοπαδοτεμαχοσελαχογαλεοκρανιολειψανοδριμυποτριμματοσιλφιοκαραβομελιτοκατακεχυμενοκιχλεπικοσσυφοφαττοπεριστεραλεκτρυονοπτοκεφαλλιοκιγκλοπελειολαγῳοσιραιοβαφητραγανοπτερύγων,
  the Aristophanes food-name), a literal typo macron (`U+00AF`) on `ἵ¯κοντο`.
- Latin: 879,023 rows / 2,677,716 form surfaces; 76 distinct junk codepoints,
  367,409 occurrences — including literal **alchemical symbol codepoints**
  (U+1F702 FIRE, U+1F704 WATER, U+1F70A VINEGAR, U+263D/E MOON PHASES,
  U+2643 JUPITER, U+263F MERCURY) scraped as part of headword/form text from
  Wiktionary entries about alchemical Latin terminology.

**b) Synthetic-collapse audit** (`synthetic_collapses/`) — flags dictionary
rows whose gloss is an auto-generated inflection note (e.g. `"vocative
masculine singular of pius"`) that got collapsed onto the wrong headword.
Counts: `la: 94,328 collapses`, `grc: 22,366` (compare `de: 260,244`,
`es: 673,718`). Sample rows: `pie,pius,vocative masculine singular of
pius,masculine;singular;vocative` (Latin); `κύων,κύω,present active
participle of κύω (kúō),active;participle;present` (Greek).
`TAG_ANALYSIS.md`/`TAG_ANALYSIS_ROUND2.md` explicitly single out Greek/Latin
as **clean, high-precision cases**, not problem cases: *"mediopassive /
active / passive / middle / reflexive / causative / agentive — KEEP.
Greek/Latin/Italian/Hindi morphology. Excellent precision"*; Greek dialect
tags (`attic/doric/ionic/cretan/epic/katharevousa`) also collapse cleanly.

**c) "Gloss-of-contains" collapse audit**
(`yomitan_contains_of_collapse_audit_20260424/gloss_of_contains_collapses/`)
— `la.tsv` (879,020 entries / 119,274 flagged rows), `grc.tsv` (60,050 /
26,074 flagged rows), and **`grc-lsj.tsv` (116,497 entries / 0 flagged
rows)** — the Perseus LSJ dictionary shows zero hits for this rule, because
LSJ's glosses are genuine lexicographic definitions rather than Wiktionary's
auto-generated "inflection of X" redirect-style glosses that this rule
targets.

**Overall**: Latin/Greek do not show unusually broken data relative to other
languages — the QA docs call them out as comparatively *clean* (Italian's
`the`-parsing bug and German/English "prose noise" are the flagged problem
cases). Collapse volume scales with dictionary size, not language-specific
breakage.

---

## 8. Trankit models, NER, and treebanks

Both languages have their own dedicated Trankit model files at
`training/trankit_save_ja_ner_v2/xlm-roberta-base/{latin,ancient-greek}/`:
tokenizer, tagger, lemmatizer, and NER models. Neither has an
`mwt_expander.pt` (unlike e.g. modern Greek `el`, French, or Italian) —
consistent with `UD_Latin-ITTB` and `UD_Ancient_Greek-PROIEL` not annotating
multi-word-token contractions the way French `du` (`de`+`le`) does.

**NER label sets differ between the two, reflecting different source
corpora**:

```
ancient-greek.ner-vocab.json: O, {B,E,I,S}-ETHNIC_CIVIC_GROUP, {B,E,I,S}-LOC,
                               {B,E,I,S}-MISC, {B,E,I,S}-PER
latin.ner-vocab.json:         O, {B,E,I,S}-GROUP, {B,E,I,S}-LOCATION,
                               {B,E,I,S}-PERSON
```

**Latin NER** is trained from a real external annotated corpus — the
**Herodotos Latin NER dataset** (Ovid, Pliny the Elder, Pliny the Younger,
etc., CRF-tagged), per
`_deprecated_nonruntime_20260514_184819\reports\transparency_attribution_inventory.md:213`
and `training\nerdump\training_data\lat_herodotos_latin_ner\README.md`:
*"Trankit BIO conversion of the Herodotos Latin NER CRF files. Label
expansion: GEO → LOCATION, GRP → GROUP, PRS → PERSON."* License: AGPL-3.0
(per local license file) — flagged in the attribution report as needing
review before any public/commercial release.

**Ancient Greek NER** is trained from **Pausanias's *Description of Greece***
(Perseus TLG0525), per
`transparency_attribution_inventory.md:234` (*"finished NER model folder
grc_pausanias_ethnic_civic_misc … REVIEW exact upstream source/license before
public attribution"*) and the model's own README:
*"Source: training\nerdump\anc\tlg0525_pausanias_ner_recreated\pausanias_grc2_ner_all*.conll.
Remap rule: MISC + proposed_label ETHNIC_CIVIC_GROUP → ETHNIC_CIVIC_GROUP;
all other MISC → MISC; PER/LOC/O unchanged."* The ultimate source is
`training\nerdump\anc\tlg0525.tlg001.perseus-grc2.xml` (Perseus CTS-canonical
XML). Each extracted entity in `pausanias_grc2_ner_recreation_report.json`
carries a per-span confidence score (e.g. `0.9918459057807922`), and a
`conf90`-filtered variant exists — indicating the entities were
auto-extracted/scored by some NER tool run over the Perseus text and then
converted into aligned BIO format, rather than hand-annotated from scratch.
Two vendored academic Ancient Greek NER projects sit in the same folder
(`NEReus-main.zip`, `Ancient_Classic_Ner-main.zip`) as plausible tools behind
that scoring step, though no script directly naming `tlg0525`/`pausanias`
survives to confirm the exact generation command.

**Gemini was NOT used for Latin/Greek NER.** Grepping the whole repo for
Gemini+NER combinations turns up hits only for Sanskrit
(`training/dcs_sanskrit_trankit_mwt_subset_10pct/gemini_sanskrit_ner_batch_runner.py`,
`build_final_sanskrit_gemini_ner_dataset.py`) — confirming Gemini-silver-label
NER was a real, deliberate technique used for Sanskrit specifically, but
never applied to `grc` or `la`, which instead used genuine external annotated
corpora (Herodotos for Latin, Pausanias/Perseus for Greek).

**Treebanks**: `language_registry.py` comments say `UD_Latin-ITTB` and
`UD_Ancient_Greek-PROIEL`. The Perseus dependency is functional, not just a
comment — `training/perseus/` (deprecated tree) contains a full local mirror
of a Perseus-based Greek treebank pipeline
(`convert_perseus_greek_to_conllu.py`, `UD_Ancient_Greek-Perseus/` CoNLL-U
splits, `latin_greek_treebanks_v2.1_texts.zip`, `TAGSETS.xml`), plus Latin
treebank source XML (`_tmp_treebanks_inspect/Latin/texts/*.perseus-lat1.tb.xml`,
e.g. `phi0474.phi013.perseus-lat1.tb.xml`) used in `UD_Latin-LLCT` prep. The
live credits page confirms this in plain language —
`templates/about.html:694`: *"Morphological analysis is done by a
custom-trained model based on the Perseus Ancient Greek corpus, as is
lemmatization."*

One discrepancy worth flagging: `transparency_attribution_inventory.md:233`
names **`UD_Ancient_Greek-PTNK`**, not PROIEL, as the treebank actually
backing the UD tokenizer/tagger/parser (CC BY-SA 4.0) — either the
`language_registry.py` comment is stale, the treebank was swapped after that
report was written, or the two documents describe different pipeline
stages. Independent evidence that the deployed parser emits PROIEL/AGDT-style
dependency labels regardless of exact treebank version:
`tmp_greek_patch_import/ancient_greek_tag_diff_report.md` lists deprel labels
(`SBJ, ATR, OBJ_AP, ATR_CO, COORD, AuxC, AuxP, PRED, ExD`) — the distinctive
AGDT/PROIEL tagset.

Sentence-boundary handling: `language_registry.py`'s per-treebank
punctuation-to-ASCII remapping (used for e.g. Classical Chinese and Vedic
Sanskrit, whose treebanks were annotated *without* native punctuation) has
**no entry for `UD_Latin-ITTB` or `UD_Ancient_Greek-PROIEL`**
(`language_registry.py:802-819`) — both treebanks were annotated with normal
punctuation intact, so no special sentence-boundary massaging is needed for
either language.

---

## 9. Gemini synthetic dictionary generation policy for Latin/Greek

`gemini_dict.py` is the live fallback that generates a dictionary entry
on-the-fly via Gemini Flash Lite when a token has no match in the static
SQLite dictionaries. Its language-policy tables treat `la` and `grc`
differently by design:

```python
# gemini_dict.py:50-53 — romanization requirement
LANGS_REQUIRING_ROMANIZATION: frozenset[str] = frozenset({
    "zh", "lzh", "ja", "ko", "th", "ar", "fa", "ur", "hi",
    "ta", "bn", "pa", "he", "hbo", "hy", "ru", "el", "grc",
})
```

`grc` requires Gemini to produce a romanization for every generated entry
(non-Latin script); `la` does not appear in this set (already Latin-script).

```python
# gemini_dict.py:59-97 — inflecting-UPOS map
"la":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
"grc": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
```

Both are marked as fully-inflecting languages (identical inflecting-UPOS set
to Modern Greek, Old English, Sanskrit, and Russian) — this controls whether
Gemini is asked to also produce a `lemma` and `morphological properties`
field for a generated entry, versus just glosses for non-inflecting
languages.

The system prompt (`gemini_dict.py:230-265`) uses **Latin as its first
worked example** for the lemmatization/morphology-labeling instructions, and
also includes an Ancient Greek example:

```
Latin — portārum (noun): lemma=porta, morphological properties=genitive plural feminine
Ancient Greek — ἔλυσαν (verb): lemma=λύω, morphological properties=aorist tense, active voice, third person plural
```

Separately, live per-token romanization (used when an entry needs a
romanization but wasn't otherwise generated) is done by a dedicated,
simpler Gemini call (`gemini_dict.py:2009-2013`):

```
"You are a romanization tool. For each token provided, output its pronunciation "
"written in plain English letters (romanized). Use ONLY English letters, "
"no IPA, no original script, no explanations. One romanization per token."
```

This is a distinct, simpler mechanism from the bulk Wiktionary-derived
romanization (Section 3) — it only fires for live/custom-entry generation,
not the pre-built dictionaries.

---

## 10. Other Greek-specific patch work

`_deprecated_nonruntime_20260514_184819\tmp_greek_patch_import\` (3 files)
patches the **Trankit tag tables and JS normalization layer** specifically
for Ancient Greek (unrelated to the linguistic vendored libraries in Section
5):

- `ancient_greek_tag_diff_report.md` — diff of the trained model's tagset
  against `TRANKIT_TAGS.js`.
- `ancient_greek_trankit_patch.js` — a generated `XPOS_GRC` lookup table
  built from Perseus's `TAGSETS.xml` + `ancient-greek.vocabs.json`.
- `dictionary_normalization_layer_greek_patched.js` — adds
  `ANCIENT_GREEK_APOSTROPHE_EQUIVALENTS_RE`, `ANCIENT_GREEK_FINAL_SIGMA_RE`,
  `ANCIENT_GREEK_IOTA_SUBSCRIPT_RE`, `ANCIENT_GREEK_STRIP_MARKS_RE`,
  `ANCIENT_GREEK_EDITORIAL_MARKS_RE` — regexes used for dictionary-key
  lookup normalization (matching a query against a headword regardless of
  final-sigma form, iota-subscript presence, or editorial bracket marks).

---

## 11. What was searched for and found nothing

Per the repo's "no speculation" rule, these are explicit negative results
from real greps across the entire repo (active + deprecated), not omissions:

- **CLTK** (Classical Language Toolkit) — zero hits anywhere.
- **Diorisis**, **Logeion** — zero hits anywhere.
- **A dedicated Latin transliteration function** — does not exist; Latin
  never needed one.
- **A Latin principal-parts generator** — "principal parts" only appears
  inside scraped Wiktionary gloss text, not as codebase logic.
- **A dedicated Greek-dialect-normalization subsystem** — the only
  dialect-related code is the QA tag-list recognizing
  `attic/doric/ionic/cretan/epic/katharevousa` as valid Wiktionary
  form-variant tags (Section 7b) — not a bespoke conversion feature.
- **Gemini-generated silver-standard NER for Latin or Greek** — refuted;
  that technique was used for Sanskrit only (Section 8).