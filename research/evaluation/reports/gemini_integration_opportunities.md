# Gemini Integration Opportunities for Language Engine

## Scope and method

I reviewed the active server, reader, dictionary, and document-handling paths rather than the many historical copy files in the repo. The most relevant files for this analysis were:

- `router.py`
- `api_services.py`
- `gemini_dict.py`
- `gemini_log.py`
- `db.py`
- `config.py`
- `static/llm_assistant.js`
- `static/reader.js`
- `static/dictionary_client.js`
- `static/user_contributions.js`
- `pipeline_common.py`
- `language_registry.py`
- `universal_normalization.py`
- `document_handling.py`
- `templates/reader.html`

The short version is that the app already has much stronger deterministic infrastructure than a typical LLM product: normalization, multilingual lookup, client-side dictionary merging, POS and dependency overlays, document ingestion, user annotations, and some flashcard/SRS hooks. That matters because the best Gemini integrations here are not "replace the existing pipeline." The best ones are targeted places where Gemini can repair, explain, summarize, draft, rank, or personalize on top of the deterministic core.

That distinction is the main thesis of this memo.

## What is already integrated

Right now Gemini is integrated in two direct user-facing places.

1. Synthetic dictionary entry creation

- The paid-only `POST /api/mt_gloss` path in `router.py` calls `gemini_dict.generate_entry(...)`.
- `gemini_dict.py` generates a structured JSON response, converts it into TSV rows, writes the output to `gemini_generated_tsvs/<lang>.tsv`, and the client injects those rows into the live dictionary engine through `static/dictionary_client.js`.
- The reader exposes this via the "CREATE SYNTHETIC ENTRY" flow in `static/reader.js`.

2. Chat assistant

- The paid-only `POST /api/llm_query` path in `router.py` calls `api_services.query_gemini(...)`.
- The UI in `static/llm_assistant.js` sends the current reader text plus the user question.
- Usage is budgeted per user through `ApiUsage` in `db.py` and surfaced in `/api/llm_usage`.

There is also infrastructure around those features:

- Token accounting and tier gating in `db.py` and `config.py`
- Full request/response logging in `gemini_log.py`
- Account surfacing in `templates/account.html`

So the app already has the beginnings of an LLM platform layer, not just two isolated API calls.

## The most important architectural conclusion

Language Engine already has a clear "engine room":

- `universal_normalization.py` cleans and remaps text.
- `pipeline_common.py` builds structured token-level results.
- `language_registry.py` gives you per-language hooks.
- `static/dictionary_client.js` and the client dictionary engine merge dictionary data on the browser side.
- `static/reader.js` already renders a very rich token-centric UI.

That means Gemini should mostly be used in four roles:

- Explanation: turn structured pipeline output into useful human guidance.
- Recovery: help when deterministic lookup fails or is low confidence.
- Drafting: create candidate entries, notes, cards, or summaries that are then reviewed or validated.
- Personalization: tailor study material, rankings, and recommendations to a specific reader.

Gemini should usually not be used as the first-pass parser, tokenizer, or dictionary engine. Those deterministic layers already exist, they are fast, and they are inspectable. In this product, LLMs are strongest when they are downstream of the pipeline or strategically called only on failures.

## Current weaknesses in the existing Gemini usage

Before expanding Gemini into more surfaces, I would harden the two existing integrations. The codebase and the generated artifacts make that necessary.

### 1. Synthetic entry generation is currently too eager to persist

The current flow in `gemini_dict.py` is a single-shot generate-and-write pipeline:

- send one request
- parse one JSON object
- write directly into the per-language TSV
- inject into the live client dictionary

That is fast, but it creates quality debt. The generated TSVs already show noisy output patterns: duplicate glosses, questionable canonical forms, malformed morphology, odd romanization, missegmented or low-confidence entries, and inconsistent POS choices. In other words, the app is treating Gemini output as production lexicographic data too early.

The right direction is not to remove Gemini here. The right direction is to turn this into a draft-and-validate pipeline.

### 2. The chatbot is under-grounded relative to the richness of the app

`static/llm_assistant.js` sends mostly plain reader text via `getRenderedText()`. It can optionally prepend a short localStorage conversation summary, but the model does not receive the strongest signals the app already has:

- clicked token
- lemma
- UPOS/XPOS
- dependency relation
- dictionary candidates
- exact fill strategy
- whether the token was unknown, lemma-derived, or synthetic
- grammar overlay data
- g2p/pronunciation output
- document slice or visible sentence boundaries

So the assistant is being asked to solve language-learning questions from lossy text instead of the structured token analysis the app already computed. That is why the current chatbot is useful but unreliable. It is effectively a generic text chat living beside a high-signal language engine.

### 3. The current chat memory is cheap but weak

The assistant remembers recent exchanges by saving truncated summaries in localStorage. That is better than nothing, but it is brittle, token-inefficient, and not anchored to actual objects in the reading session. A much stronger memory model would be object-based:

- current document
- current page
- current paragraph
- current token/span
- recent looked-up words
- recent generated synthetic entries
- user notes

The app already has many of those objects; the chatbot currently does not exploit them.

### 4. Observability exists, but quality control does not yet fully use it

`gemini_log.py` is already logging enough data to build meaningful evals. That is valuable. But the app does not yet appear to use those logs to do any of the following:

- track per-task failure rates
- compare prompt versions
- detect bad canonicalization
- detect malformed entry shapes
- detect contradiction between Gemini output and dictionary lookup
- surface review queues for suspicious entries

That should become a first-class internal workflow.

## High-priority new Gemini integrations

These are the places I think Gemini would add the most product value with the least architectural friction.

## 1. A grounded token explainer, not just a free-form chat

This is the single strongest opportunity.

The reader already has rich token state in `static/reader.js` and `pipeline_common.py`. Instead of sending only plain rendered text, add targeted token-level actions such as:

- Explain this word in plain English
- Why did the app choose this lemma?
- Why is this token unknown?
- Why was this sense shown and the others filtered out?
- Explain this inflection
- Break down this compound
- Explain this dependency relation in context

Each action should send a structured payload built from the existing pipeline, not just a free-text question. For example:

- token surface
- lemma and lemma_raw
- UPOS and XPOS
- feats
- dependency relation and head
- candidate dictionary entries
- selected dictionary entry
- grammar overlay entries
- neighboring sentence text
- whether lookup came from exact, lemma, greedy, or synthetic resolution

This would make Gemini substantially stronger without needing a better model. It would also reduce hallucination because the job becomes interpretation of known data rather than open-ended reconstruction.

Product-wise, this is stronger than the floating chatbot because it is attached to the actual learning moment.

Main code touchpoints:

- `static/reader.js`
- `pipeline_common.py`
- `api_services.py`
- potentially a new endpoint like `/api/llm/explain_token`

## 2. Unknown-token recovery before synthetic dictionary generation

Right now the main unknown-token LLM action is "create synthetic entry." That is often too late in the decision tree.

A better sequence is:

1. deterministic lookup fails
2. deterministic fuzzy/normalization/lemma heuristics run
3. Gemini proposes one of:
   - normalized spelling
   - likely segmentation
   - likely lemma
   - likely compound decomposition
   - likely script/romanization repair
4. the app re-runs the existing deterministic lookup engine on that proposal
5. only if nothing valid resolves do you offer synthetic entry creation

This is important because many unknown tokens are not truly missing vocabulary. They are:

- inflected forms
- compounds
- sandhi-affected forms
- OCR noise
- user spelling mistakes
- script normalization issues
- segmentation issues

Gemini is very good at proposing repair candidates. Your existing engine is much better than Gemini at deciding whether the repaired candidate really belongs in the dictionary. That combination is stronger than immediately generating a new lexical row.

Main code touchpoints:

- `static/reader.js`
- `static/dictionary_client.js`
- `gemini_dict.py`
- a new recovery endpoint rather than reusing `/api/mt_gloss`

## 3. A draft-review-approve workflow for synthetic entries

If synthetic dictionary entries remain a core premium feature, they should become reviewable objects rather than immediate TSV writes.

The ideal path is:

- Gemini generates a candidate
- local validators check shape, duplicates, POS sanity, form sanity, and canonical-form sanity
- the user sees the draft in a side-panel review card
- the user can edit gloss, POS, canonical form, and commentary
- only approved entries are persisted to the server TSV

You could also split generation into stages:

- stage 1: canonical form + POS + 1-3 glosses
- stage 2: optional forms table on demand

That would lower cost and lower damage from bad morphology. The current generated TSVs suggest that full paradigm generation is often where the model goes off the rails.

This is a very natural fit for the app because the reader already has side panel UX and user dictionary creation UX. The synthetic-entry draft flow can look and feel similar to the custom entry form, just pre-filled.

Main code touchpoints:

- `gemini_dict.py`
- `static/reader.js`
- `router.py`
- `db.py` if you add a draft table

## 4. Gemini-assisted authoring for custom dictionary entries and normalization rules

The custom entry UI in `static/reader.js` is still mostly manual. That is a great place for Gemini.

Useful actions:

- Draft custom dictionary entry from current token and context
- Suggest better gloss wording
- Suggest likely part of speech
- Suggest alternate forms
- Suggest normalization rule from repeated user corrections
- Convert a user note into a clean dictionary-style definition

This is a better use of Gemini than automatic persistence because the user is already in an editing mindset. In other words, Gemini acts as an authoring assistant, not a silent database writer.

This is especially valuable for low-resource languages or domain-specific corpora where users may want to curate their own lexicon over time.

Main code touchpoints:

- `static/reader.js`
- `router.py` user dictionary endpoints
- possibly a new `/api/llm/draft_user_entry` endpoint

## 5. Community synthesis and deduplication

The app already has user-contributed dictionary entries and token annotations in:

- `db.py`
- `router.py`
- `static/user_contributions.js`

That opens a strong Gemini opportunity that is not currently used: summarizing community knowledge.

For a headword with multiple community entries or notes, Gemini could:

- merge overlapping glosses
- produce a short canonical summary
- cluster senses
- extract common disagreements
- produce "community consensus" vs "minority interpretation"

This is especially useful when many users are reading difficult material and gradually building explanations around the same terms.

The important part is that Gemini should summarize user content, not replace it. This is a synthesis task, which LLMs are good at, and it would make the community layer much more usable.

Main code touchpoints:

- `static/user_contributions.js`
- `router.py`
- possibly a new `/api/community_summary` endpoint

## 6. Document-level reading aids

The document ingestion layer is more sophisticated than a normal text box:

- PDF support
- DOCX support
- EPUB support
- page-aware extraction
- original-view support
- visible-slice rendering in `static/reader.js`

That means Gemini can do more than answer generic questions. It can become a document-reading copilot.

High-value document-level actions:

- Summarize current page
- Summarize current paragraph
- Translate current passage more naturally than dictionary glosses
- Explain what this paragraph is doing rhetorically
- List the 5 hardest words on this page
- List recurring names, entities, or concepts
- Explain how this sentence connects to the previous one
- Give a "what to notice before reading" pre-brief

The key is scoping. Send the current visible page or paragraph, not the entire document. The app already knows the current view context, so this is practical and likely cheap enough.

This would make Gemini feel integrated into the reading workflow rather than bolted on as a detached chat bubble.

Main code touchpoints:

- `document_handling.py`
- `static/reader.js`
- `api_services.py`

## 7. Flashcard and SRS enrichment

`static/reader.js` contains a flashcard overlay and calls to `reading_srs` endpoints. Even if that subsystem is still incomplete or partially wired, the direction is clear: the app wants to move from lookup to learning.

Gemini can materially strengthen that layer by generating study content around cards:

- one-sentence definition tuned to the learner level
- minimal pair or confusion warning
- mnemonic
- cloze sentence
- example sentence from the current reading
- "why this form looks different from the lemma"
- short grammar hint
- user-specific hint after repeated misses

This is one of the best places to use Gemini because flashcards tolerate drafted content better than dictionary storage does. A weak mnemonic is annoying; a bad dictionary row pollutes the engine. The risk profile is much better here.

If the SRS backend is not fully live yet, I would still design Gemini hooks now because this is a very strong premium feature once the deterministic scheduling layer is stable.

Main code touchpoints:

- `static/reader.js`
- whatever backend owns `reading_srs`
- `db.py` if card metadata is persisted

## 8. Offline lexicon-gap mining and curation tools

This is not as flashy, but it may be one of the highest ROI uses of Gemini for you as the maintainer.

You already have:

- Gemini logs
- generated TSVs
- user lookups
- unknown tokens
- user dictionary entries

That is enough to build an offline curation pipeline:

- collect high-frequency unknown tokens by language
- cluster spelling variants
- ask Gemini for candidate lemmas and gloss drafts
- compare against existing dictionary sources
- queue only the highest-confidence candidates for manual review

This would let Gemini strengthen the actual dictionary coverage over time rather than only helping one user in one session.

It also fits the product extremely well because your app lives or dies on dictionary quality and coverage.

Main code touchpoints:

- `logs/gemini_comms.jsonl`
- `gemini_generated_tsvs/`
- possibly a new offline maintenance script rather than a live route

## 9. OCR and extraction cleanup for difficult documents

`document_handling.py` already does a lot with PDFs and DOCX. But hard documents often fail because of line breaks, broken words, page artifacts, or OCR noise.

Gemini can help selectively here, but only as an optional repair step. Good tasks:

- remove obvious OCR artifacts
- reconstruct hyphen-broken words
- normalize weird spacing
- detect when a line break split one lexical item
- classify extracted text as prose vs table vs metadata

This should never replace the raw extraction. It should be a second representation:

- raw extraction
- Gemini-cleaned reading text

That gives users a safety valve without losing transparency.

Main code touchpoints:

- `document_handling.py`
- `static/reader.js`

## 10. Better search and fuzzy rescue

The reader UI references fuzzy and normalization-style workflows. Gemini can help here, but again only as a proposal engine.

Example uses:

- "What word did the user probably mean?"
- "Is this likely a sandhi form, typo, or segmentation error?"
- "What are the top 3 plausible normalized forms?"

Then the existing dictionary engine can verify the candidates.

This is especially useful for languages with compounding, script variance, or unstable OCR. It is a narrow, practical LLM job and fits your architecture well.

## Medium-priority integrations

These are good ideas, but I would do them after the items above.

## 11. Personalized reading coach

Once you have more structured history, Gemini can generate:

- weekly study recaps
- "words you keep missing"
- "grammar patterns you seem shaky on"
- suggested next reading difficulty
- a personalized review packet from recent sessions

This is valuable, but it depends on better event capture and probably stronger study-state storage than I can clearly see in the current active backend.

## 12. Pro-tier model differentiation and routing

`config.py` currently gives both basic and pro the same Gemini model name. The account page messaging suggests pro is supposed to get a better model or at least better AI treatment.

There is a clear opportunity to route different tasks differently:

- cheap model for quick token explanations
- better model for hard morphology or community synthesis
- maybe longer-context model for document summaries

This is less about "where" to integrate Gemini and more about making each Gemini surface economically sane.

## 13. Teacher/admin tooling

If this app eventually supports classrooms or shared reading groups, Gemini could help teachers:

- summarize where students struggled in a passage
- identify common unknown terms
- build quizzes from a reading
- generate guided reading questions

I mention it because the architecture could support it later, but I would not prioritize it now.

## Places I would explicitly avoid using Gemini

Some parts of the app should stay deterministic-first.

### 1. Core lookup and segmentation

Do not turn `/lookup` into an LLM-first experience. `pipeline_common.py`, `language_registry.py`, and the dictionary engine are doing exactly the sort of work that should remain fast, inspectable, and stable.

### 2. Automatic permanent dictionary writes without review

The current synthetic TSV flow is already riskier than ideal. I would move away from more silent persistence, not toward it.

### 3. Replacing grammar overlays or UD overlays

Those are structured features with pedagogical value because they are consistent. Gemini should explain them, not replace them.

### 4. Broad free-form "translate the whole app state" calls

If you send giant raw rendered text blobs plus long chat history, costs rise while grounding gets worse. Use scoped, typed tasks instead.

## Recommended build order

If I were sequencing this for actual product impact, I would do it in this order.

### Phase 1: Harden what already exists

- Add validation and draft review to synthetic entry generation.
- Split synthetic entry generation into smaller subtasks.
- Improve chat grounding by sending structured token and dictionary context.
- Start building internal evals from `gemini_comms.jsonl` and generated TSV artifacts.

### Phase 2: Add the best new user-facing surfaces

- Token explainer actions in the popup/panel
- Unknown-token repair before synthetic-entry creation
- Gemini drafting for custom dictionary entries
- Page/paragraph summary actions

### Phase 3: Convert Gemini into a learning engine

- Flashcard enrichment
- Community summary and dedupe
- Personalized review and study recaps

### Phase 4: Use Gemini to improve the product itself

- Offline lexicon gap mining
- Synthetic-entry QA dashboard
- Extraction repair workflow for hard documents

## Concrete implementation advice

A few practical rules would keep these integrations strong.

1. Prefer many small structured endpoints over one big chat endpoint.

Examples:

- `/api/llm/explain_token`
- `/api/llm/repair_unknown`
- `/api/llm/draft_user_entry`
- `/api/llm/summarize_passage`
- `/api/llm/enrich_flashcard`

2. Make Gemini propose and the engine verify.

That pattern fits this codebase better than direct LLM authority.

3. Persist draft state separately from production state.

This is especially important for dictionary content.

4. Build confidence scoring and review queues.

The logs and generated TSVs already justify this.

5. Scope context tightly.

Visible sentence, paragraph, token, and selected dictionary entry are usually enough. Do not default to sending the whole rendered document.

6. Reuse the structured data the app already computes.

You already have lemmas, POS, dependencies, grammar overlays, and dictionary candidate sets. Those should become first-class prompt inputs.

## Final recommendation

If you want Gemini to make this app materially stronger, the best move is not to spread generic chat everywhere. The best move is to make Gemini more local, more typed, and more subordinate to the deterministic language engine you already built.

The highest-leverage additions are:

- grounded token explanations
- unknown-token repair before synthetic generation
- reviewed synthetic-entry drafting
- Gemini-assisted authoring for custom entries
- document and flashcard enrichment
- offline lexicon-gap mining

If you do just those well, Gemini stops being a side feature and starts becoming a real force multiplier for the reader, the dictionary, and the learning loop.
