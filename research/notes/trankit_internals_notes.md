# Trankit tuning — what each fix actually does to your reader

Context: your reader runs Trankit on every `/lookup`. When a user highlights text, Trankit tokenizes it, splits multi-word tokens (MWTs), tags each token with UPOS/XPOS/features, builds a dependency tree, and computes lemmas for dictionary lookup. Each of the knobs below changes one of those stages. When something goes wrong at a stage, the user sees it as a specific kind of visible glitch — wrong segmentation, broken dictionary lookup, a dep-tree that looks disjoint, etc.

Every fix below is a **monkey-patch in your own backend** ([language_registry.py](../../language_registry.py) or [trankit_mwt_expansion.py](../../trankit_mwt_expansion.py)). Nothing edits the Trankit install directly, and everything reverts on next restart if you back it out.

Items marked **Already done** are wired in your current code. Items marked **Pending** are suggested next steps with user-visible justification.

---

## Fix 1 — Beam search for MWT expansion (Pending)

### What this is in plain terms

An MWT is one written form that expands into several words. French `au` → `à le`. Arabic `للبيت` → `ل + البيت`. Sanskrit compounds that are one visual chunk but multiple grammatical words. Trankit expands these character-by-character with a small neural model.

By default that model uses **greedy decoding** — at each character position, it picks the single most likely next character and moves on. It never second-guesses itself.

Beam search (size 3) keeps the top 3 candidate outputs alive in parallel and at the end picks whichever one had the highest total probability. About 3× the compute; still microseconds per MWT.

### Where users notice this in your reader

- A Sanskrit compound expands into the wrong pieces, so dictionary lookup fails on each piece.
- A French or Arabic clitic gets a garbled split, and your popup shows no definition for either half.
- The surface word looks right but the grammar panel shows suspicious `+`-joined forms.

### What changes if you fix it

Cases where the locally-best next character leads nowhere good — greedy commits to it anyway and produces garbage — now recover, because beam search keeps a backup plan alive. Most MWTs in most languages are already easy enough that greedy is fine; the fix matters for the long tail (unusual compounds, rare verb forms).

### How to wire it

Your [trankit_mwt_expansion.py:262-312](../../trankit_mwt_expansion.py) already defines `set_mwt_decoding_headroom(pipeline, max_dec_len=400, beam_size=None)`. You're already calling it from [language_registry.py:645](../../language_registry.py) but without a beam value. Change:

```python
applied = set_mwt_decoding_headroom(_trankit_pipeline, max_dec_len=400)
```

to:

```python
applied = set_mwt_decoding_headroom(_trankit_pipeline, max_dec_len=400, beam_size=3)
```

Then open `trankit_mwt_expansion.py` and confirm the helper actually writes `beam_size` into both `trainer_args["beam_size"]` and `inner_model.beam_size` — same pattern it uses for `max_dec_len`. If it doesn't yet, add those two lines.

**Status:** Pending.

---

## Fix 2 — Same max-length + beam fix for the lemmatizer (Pending)

### What this is in plain terms

The **lemmatizer** takes an inflected word (`running`, `gelaufen`, `δεδωκότες`) and produces its dictionary form (`run`, `laufen`, `δίδωμι`). It's a separate seq2seq model from the MWT expander, but with the same two defaults:

- `max_dec_len = 50` — output capped at 50 characters.
- `beam_size = 1` — greedy decoding, same as MWT.

You already fixed both of these for the MWT side. The lemmatizer has the same problem and the same fix.

### Where users notice this in your reader

- A long German compound lemma gets truncated, dictionary lookup misses.
- A heavily-inflected Greek/Sanskrit form gets the wrong lemma because the decoder chose a bad first character and couldn't recover (same greedy trap as MWT).
- The grammar panel shows the inflected surface as the "dictionary form" because seq2seq failed silently and something else kicked in.

### What changes if you fix it

- No more lemma truncation on long dictionary forms.
- Better recovery on rare/unfamiliar inflections.

### How to wire it

Add a sibling helper next to `set_mwt_decoding_headroom` in [trankit_mwt_expansion.py](../../trankit_mwt_expansion.py). Same shape, but walk every `LemmaWrapper` on the pipeline:

```python
def set_lemma_decoding_headroom(pipeline, max_dec_len=400, beam_size=3):
    applied = []
    for lang_name in pipeline._lang_configs:
        # grab the lemmatizer wrapper the same way the MWT helper grabs the MWT wrapper
        # then set trainer_args["max_dec_len"], inner_model.max_dec_len,
        # trainer_args["beam_size"], inner_model.beam_size
        ...
    return applied
```

Invoke it from [language_registry.py](../../language_registry.py) right after the MWT call at line 645.

**Status:** Pending. Same load-time gotcha as MWT: the checkpoint's saved args win on load, so you have to overwrite them *after* the model is loaded, not in `get_args()`.

---

## Fix 3 — Disable the "dictionary override" on small-training-data languages (Pending)

### What this is in plain terms

During training, Trankit builds a cheat sheet: a dictionary of `(surface form → known correct output)` from whatever showed up in training data. At inference, **if the input surface was in that cheat sheet, the dictionary answer is used and the neural model is not even run**. This applies to both MWT and lemmatization. Trankit calls it `ensemble_dict`.

For languages with large, clean training sets (French, Spanish, modern Arabic): the cheat sheet is accurate and skipping the neural model is a free speed win.

For languages with small or noisy training sets (Sanskrit, Classical Chinese, any of your custom-trained ones): every error in training data is **permanently baked in**. Your neural model never gets a chance to correct it because it never runs on those forms.

### Where users notice this in your reader

- The same word always lemmatizes to the same wrong dictionary form, no matter the context. (That's the signature — the cheat sheet is context-free, so if it's wrong it's wrong always.)
- A Sanskrit MWT expands into the same wrong pieces every time, even when you know your retrained model should handle it.

### What changes if you fix it

For flagged languages only: the seq2seq actually runs on every input, with the quality improvements you got from retraining. Well-trained languages keep the dictionary shortcut.

### How to wire it

Add a per-language flag `"disable_dict_ensemble": True` to the relevant rows in `LANGUAGE_REGISTRY`. Extend both `set_mwt_decoding_headroom` and the new `set_lemma_decoding_headroom` to check each language against that flag and, if set, do:

```python
inner_model.loaded_args["ensemble_dict"] = False
inner_model.ensemble_dict = False
```

Candidates for turning it off: Sanskrit, Classical Chinese, probably Ancient Greek and Old English. Keep it on for French, Spanish, modern Chinese/Japanese.

**Status:** Pending. Worth A/B-ing before flipping — for a language where training was actually good, turning this off is pure slowdown.

---

## Fix 4 — Per-language character normalization before tokenization (Pending)

### What this is in plain terms

Every language has quirky punctuation. Sanskrit ends sentences with `।` (single danda) or `॥` (double danda) instead of a period. Urdu uses `۔`. Hebrew text often contains niqqud (vowel points like `ְ ָ ַ`) that weren't in training data.

Trankit already has a **per-language substitution hook** — it lives in `tokenizer_utils.py:89-92` and does things like `۔ → .` for Urdu and `- → ،` for Uyghur. It runs right before text is fed to the model. You don't see it, but it matters: if training normalized a character and runtime doesn't, the model sees something it didn't learn to handle.

### Where users notice this in your reader

- Sentence splits fail in Sanskrit around dandas — a whole paragraph becomes one giant sentence, or conversely, chunks get fragmented weirdly.
- Hebrew with niqqud produces different segmentation than the same text without niqqud (because XLM-R sees them as different tokens).
- Persian text with or without ZWNJ gets treated differently even when it shouldn't.

### What changes if you fix it

Consistent preprocessing between training and runtime. Sentence boundaries become more reliable. The user's view of the text doesn't change, but the structure Trankit exposes (sentences, tokens, segments) matches what your dictionaries and UI expect.

### How to wire it

You already have the right patch point: [language_registry.py:582-597](../../language_registry.py) monkey-patches `wordpiece_tokenize_from_raw_text` for the char-level-tokenize case. Extend that same closure to also do per-language string replacements. Drive it from a new registry field:

```python
# in LANGUAGE_REGISTRY rows:
"char_replacements": {"।": ".", "॥": "."},
```

And in the patched function:

```python
def _patched_wp_tokenize(..., treebank_name):
    replacements = _char_replacement_map.get(treebank_name)
    if replacements:
        for old, new in replacements.items():
            sent_text = sent_text.replace(old, new)
    if treebank_name in _char_level_treebanks:
        treebank_name = "UD_Chinese-GSD"
    return _orig_wp_tokenize(...)
```

Start with Sanskrit (`।`, `॥` → `.`). Consider Hebrew (strip niqqud via a regex). Consider Persian (normalize ZWNJ).

**Status:** Pending. Cleanly additive to the existing patch you already have in place.

---

## Fix 5 — Force the lemmatizer to trust its own seq2seq (Pending)

### What this is in plain terms

The lemmatizer has two brains working in parallel:

1. **seq2seq** — generates the lemma character-by-character. This is the "real" lemmatizer.
2. **edit classifier** — a second head that predicts one of three decisions: `identity` (return surface unchanged), `lower` (return surface lowercased), `none` (actually use the seq2seq output).

At runtime, the edit classifier wins. So even if seq2seq correctly produces `give` from `gave`, if the edit classifier says `identity`, the user gets `gave` back as the "dictionary form."

For **highly inflected languages** — Sanskrit, Ancient Greek, Finnish, Arabic, Old English — the edit classifier often gets biased toward `identity` because training data contains many short function words that really are their own lemma. Once biased, it overrides seq2seq on words that absolutely need transformation.

### Where users notice this in your reader

- In Sanskrit, a clearly inflected form comes back as its own lemma — dictionary lookup fails because the inflected surface isn't a dictionary headword.
- In Arabic, the lemma column shows the fully-inflected verb instead of the root/stem.
- Same pattern in any fusional language: if you expected aggressive lemmatization but see surface forms coming through unchanged, this is the culprit.

### What changes if you fix it

For flagged languages, seq2seq output is always used. User-visible effect: dictionary lookup stops falling through for inflected forms.

### How to wire it

Monkey-patch `LemmaWrapper.predict` (or the internal `edit_word` call) in [language_registry.py](../../language_registry.py). You already patch `LemmaWrapper.__init__` and `.predict` at lines 548-578 for identity-lemma languages; this is the inverse — languages where you want seq2seq forced ON. Pattern:

```python
_force_seq2seq_treebanks = {
    info["trankit_treebank"]
    for info in LANGUAGE_REGISTRY.values()
    if info.get("lemma_force_seq2seq") and info.get("trankit_treebank")
}
# wrap predict so that for these treebanks, edit_id is forced to 0
```

Before flipping per language, add a debug hook that logs the edit-ID distribution on a representative corpus. If `identity` is firing on, say, 80% of Sanskrit tokens, flip the flag on Sanskrit.

**Status:** Pending. The "audit first, flip second" order matters — on languages where identity is correct most of the time (isolating languages, English), forcing seq2seq makes lemmas *worse*.

---

## Fix 6 — Raise `max_input_length` for long-paragraph languages (Pending)

### What this is in plain terms

The tokenizer has a per-language cap on how many subword pieces can fit in one chunk of input. Many languages default to 400 pieces even though XLM-R (the underlying embedding model) can actually handle 512. A few specific languages (Japanese, Spanish, Russian, Persian, Italian, some Chinese) are already set to 512. Others aren't.

When a paragraph is longer than the cap, Trankit cuts it into chunks and processes each chunk independently. The cut happens at a guessed sentence boundary, but if the guess is off, you get a bad split.

### Where users notice this in your reader

- On long academic PDF paragraphs (common in Sanskrit, Latin, Classical Chinese, Ancient Greek texts), sentence boundaries jump to odd places.
- The dependency tree gets split into multiple disconnected trees mid-paragraph.
- Two consecutive lookups on the same paragraph produce different sentence boundaries depending on where the cut landed.

### What changes if you fix it

Fewer artificial chunks. Fewer split dependency trees. Long paragraphs get treated as one unit up to the XLM-R hard ceiling.

### How to wire it

Monkey-patch `trankit.utils.tbinfo.tbname2max_input_length` at module import time from [language_registry.py](../../language_registry.py). Pattern:

```python
import trankit.utils.tbinfo as _tbinfo
for info in LANGUAGE_REGISTRY.values():
    tb = info.get("trankit_treebank")
    if tb and info.get("bump_max_input_length"):
        _tbinfo.tbname2max_input_length[tb] = 512
```

Then flag the languages you care about in the registry. Safe to do for any XLM-R-base language since 512 is the model's actual ceiling.

**Status:** Pending. Lowest-effort recommendation in the list.

---

## Fix 7 — Punctuation-aware chunk split in the tagger (Pending, harder)

### What this is in plain terms

Even after the tokenizer chunks a paragraph, the **tagger** has its own separate 512-piece limit. When a single sentence is longer than 512 pieces (rare in English, real in Sanskrit/Latin/Classical Chinese), the tagger splits the sentence at an arbitrary piece-count boundary — no awareness of commas, clauses, or punctuation. **Each chunk then gets its own independent dependency tree.** Cross-chunk grammatical arcs cannot exist.

The user sees a long sentence rendered as two disconnected grammar trees. Silently. No error, no warning — it just looks like two sentences even though your NER/lookup treats them as one.

### Where users notice this in your reader

- A long Sanskrit sentence's dependency tree shows a break at an unnatural position, with half the sentence floating disconnected from the other half.
- Same pattern on long Classical Chinese passages or Latin sentences with many subordinate clauses.
- UD overlay arrows end abruptly in the middle of a sentence.

### What changes if you fix it

Chunks get cut at the nearest punctuation/clause boundary instead of at "whatever the 502nd piece happens to be." Each chunk is a more natural sub-unit, so its independent dependency tree is at least internally coherent.

### How to wire it

Monkey-patch the chunking loop in `trankit.iterators.tagger_iterators` from [language_registry.py](../../language_registry.py) (same patching style you already use for `tokenizer_utils`). Override the piece-level length check so it prefers to break at a punctuation-marked position within the last N pieces of the window.

**Status:** Pending. Most involved fix on the list. Worth doing last, after the easy wins above, and specifically before the app is used heavily for long-paragraph academic texts.

---

## Already done — just for reference

These are wired in your current code, so you don't need to re-do them. Listed so you can compare against the pending items and spot the pattern.

| Fix | Where it's wired |
|---|---|
| MWT decoder length raised to 400 (Sanskrit compounds no longer get truncated) | [language_registry.py:644-645](../../language_registry.py), [trankit_mwt_expansion.py:262-312](../../trankit_mwt_expansion.py) |
| Thai tokenized character-by-character instead of by whitespace | [language_registry.py:582-597](../../language_registry.py) |
| Thai + Sanskrit use identity lemmatization (lemma = surface, no broken seq2seq firing) | [language_registry.py:540-578](../../language_registry.py) |

---

## Priority order for the pending work

If you're picking one at a time:

1. **Fix 1** — two-line change, direct user-visible MWT quality improvement. Do this first.
2. **Fix 6** — one-line-per-language registry flag, no new helper. Improves long-paragraph behavior across the board.
3. **Fix 2** — new helper mirroring the MWT one. Moderate effort, broad lemma quality improvement.
4. **Fix 4** — extends an existing patch. Specific to languages with non-standard punctuation (Sanskrit, Hebrew).
5. **Fix 3** — add the flag and the override; audit per language before flipping.
6. **Fix 5** — audit first (log edit-ID distribution), flip second. Biggest potential lemma-quality win on fusional languages.
7. **Fix 7** — most involved. Only matters at scale with long-paragraph texts.
