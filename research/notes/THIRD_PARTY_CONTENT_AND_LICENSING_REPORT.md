# Language Engine: Third-Party Content and Licensing Review Packet

Prepared: May 13, 2026

This report summarizes the current state of Language Engine as it relates to third-party content, third-party software, model training data, dictionary sources, and public attribution. It is intended for external legal/compliance review. It is not legal advice.

## Executive Summary

Current working conclusion:

- The public info/credits page does **not** need to list ordinary server-side software dependencies merely because the hosted app uses them.
- The public info/credits page probably does **not** need to list model training datasets merely because server-side models were trained on them, provided the app does not distribute the datasets, distribute the trained model weights, or expose substantial copied training data in outputs.
- The main public attribution surface is **dictionary and lexical content**, because dictionary entries and adapted lexical data are shown to users.
- Client-side JavaScript/CSS/font assets may require preserved copyright/license notices when distributed to browsers, but that does not necessarily require prominent public "credit" on the info page. A third-party notices file or preserved license headers may be enough.
- Dead or legacy server routes that still import/use AGPL or similar packages should be removed/disabled if not part of the product. If kept public, they need separate analysis.
- Marketing screenshots/videos and Chrome-extension page capture raise separate content/privacy questions, not normal dependency-attribution questions.

## Current App Facts

Language Engine is a hosted web application. Users upload or enter text/documents, then read with dictionary lookup, NLP annotation, dependency parsing, NER, sentence translation, and AI assistance.

Active reader path:

- Main reader template: `templates/reader_jshybrid.html`
- Active shared reader JavaScript: `static/reader.js`
- Active dictionary stack: `static/dictionary_client_hybrid.js`, `static/dictionary_engine_hybrid.js`, `static/reader_wikt.js`
- Active backend lookup route: `/lookup`, which returns Trankit/NLP analysis only
- Active dictionary hydration route: `/js/hydrate`
- Active compact dictionary index route: `/js/dict/<lang>/index`

Current document handling:

- PDFs use browser PDF.js in the active reader path.
- Ebooks use Foliate JS in the active reader path.
- DOCX uses browser Mammoth.js in the active reader path.
- Frozen web snapshots are produced by the Chrome extension and consumed as HTML snapshots.
- PyMuPDF/fitz, ebooklib, pdfplumber, pypdf/PyPDF2, python-docx, docx2pdf, BeautifulSoup/lxml document routes appear in legacy server-side document handling code, but they are not the active reader path as currently understood.

Important correction:

- The current info page still contains a sentence saying "PDF.js, PyMuPDF, ebooklib, and related parsing tools turn uploaded documents..." This is inaccurate for the active reader path. PyMuPDF and ebooklib should not be represented as active reader dependencies unless the legacy server routes are intentionally retained as public product functionality.

## Current Public Info Page Structure

The current `templates/credits.html` page includes these public sections:

- Dependency Map
- NLP Pipeline
- Specific Model Training Data
- Dictionary Sources
- General App Infrastructure
- Review Before Public Release

Current working conclusion:

- Most of these are useful as provenance or transparency, but not strictly necessary public attribution.
- "Review Before Public Release" should not be public-facing.
- The section most likely to remain legally useful is "Dictionary Sources."

## Software Dependencies

### Server-side software

Examples:

- Flask, SQLAlchemy, Flask-Login, Flask-CORS
- requests stack
- Stripe Python SDK
- Trankit
- PyTorch
- ONNX / ONNX Runtime
- NumPy and related transitive dependencies

Current conclusion:

- For a hosted SaaS app, ordinary server-side packages generally do not require public attribution on an info/credits page.
- They may require internal license inventory.
- They may require notices if the server code, Docker image, binary package, source bundle, or environment is distributed.
- They are not the main public attribution issue for the current hosted app.

### Client-side software served to users

Examples:

- PDF.js
- Foliate JS
- JSZip
- DOMPurify
- Mammoth.js
- marked
- Google Fonts / Inter if self-hosted or bundled

Current conclusion:

- These assets are distributed to the browser, so license notices should be preserved somewhere.
- This does not necessarily require a public-facing "credits" table.
- A third-party notices file, preserved file headers, vendor license files, or similar accessible notice mechanism may be sufficient, depending on license and distribution method.
- If assets are loaded from CDN rather than bundled, notice obligations may differ, but the app should still track what is served and what is bundled.

Relevant license mechanics:

- MIT and BSD-style licenses generally require copyright/license notices to remain in copies or distributions.
- Apache-2.0 generally requires license/notice preservation in distributions, including NOTICE handling where applicable.
- MPL-2.0 can require access to source code for covered software if distributed in executable form.
- OFL fonts allow use, but bundled font files should retain copyright/license metadata or accompanying notices.

## Dictionary and Lexical Sources

This is the primary public attribution area because users see dictionary content.

Sources currently listed on the page:

- Wiktionary / Kaikki
- CC-CEDICT
- JMDict / EDICT
- KRDict / Korean Learners' Dictionary
- Chinese Notes
- DCS Sanskrit
- Bosworth-Toller
- Perseus LSJ lexica

Current conclusion:

- Public attribution is likely required or strongly prudent for dictionary/lexical sources because the app displays adapted dictionary content to users.
- A dropdown name alone is probably not enough for CC-style attribution.
- A minimal public attribution page should include source name, source link, license, and an indication that the data was adapted/processed where applicable.
- The current "Dictionary Sources" section is the part of the info page most likely to be legally meaningful.

Open dictionary questions for review:

- What exact license applies to the imported Wiktionary/Kaikki exports used in the SQLite dictionaries?
- Are CC BY-SA dictionary sources compatible with the app's paid access model, provided attribution/license links are given and downstream restrictions are not imposed on the content itself?
- What exact license applies to Chinese Notes data as used here?
- What exact license applies to DCS Sanskrit data as used here?
- What exact digital source and license applies to Bosworth-Toller data as used here?
- Does the app need attribution at the individual entry level, or is a centralized source page sufficient?
- Is the current transformation into SQLite/index/hydration format an "adaptation" under the applicable licenses, and if so what exact notice language is needed?

## Model Training Data

The current page lists per-language model/training data sources, including Universal Dependencies treebanks and NER corpora. Many are CC BY or CC BY-SA.

Important app-specific fact:

- `language_registry.py` is not reliable as a complete provenance source because some runtime model artifacts have reportedly been swapped/retrained and renamed under older Trankit names. A separate private model provenance manifest is needed.

Current conclusion:

- If the app only uses trained models server-side and does not distribute the model weights or datasets, public attribution for training datasets is not clearly triggered merely by hosted inference.
- Creative Commons attribution is clearly triggered when licensed material or adapted material is publicly shared. Hosted model inference is not obviously the same as sharing the source treebank or NER corpus.
- Creative Commons FAQ language on text/data mining says that if publicly sharing the results of mining activity or the mined data, attribution should be given. Whether server-side model outputs count as such "results" for each dataset should be reviewed, but the conservative operational conclusion is that public attribution for training data is not strictly required if no data/model is distributed and outputs do not expose substantial copied dataset content.
- A private provenance manifest is still important for risk management, reproducibility, and later distribution decisions.

Recommended private model provenance manifest fields:

- App language code
- Runtime model artifact path/hash
- Whether tokenizer/tagger/parser/NER are stock or custom
- Original training dataset(s)
- Dataset version/commit/download date
- Dataset license
- Whether model weights are distributed or server-only
- Whether outputs can reproduce training examples
- Notes on any Gemini-generated or hand-corrected training data

Open model questions for review:

- Does using a model trained on CC BY-SA Universal Dependencies data behind a hosted service require public attribution?
- Does a trained model weight file count as adapted material or an output of text/data mining under relevant jurisdictions?
- If model weights are ever downloadable, shipped, or embedded in a client, what attribution/license obligations attach?
- Are any NER datasets under GPL/AGPL/noncommercial/sharealike terms incompatible with commercial hosted use or later model distribution?
- Are local Gemini-corrected datasets copyrightable/adapted from third-party datasets, and if so what source obligations remain?

## AGPL / Copyleft Risk Areas

The active reader path currently does not rely on PyMuPDF/fitz or ebooklib. However, legacy server routes in `document_handling.py` appear to reference server-side document-processing packages.

Potential issue:

- If any AGPL-licensed package is actually used in production in a way users interact with over the network, it may trigger source-code offer obligations, especially if the covered program is modified.
- If these routes are dead, unused, and not product functionality, the cleaner compliance action is to remove or disable them rather than credit them publicly.

Current conclusion:

- Do not list PyMuPDF/ebooklib as active reader dependencies on the public info page unless those routes remain supported.
- Treat old document routes as a cleanup/legal-risk item.

Open AGPL questions for review:

- Are PyMuPDF/fitz, ebooklib, or any other AGPL packages installed and reachable through public server routes?
- Are they modified?
- Are users interacting with them remotely through the web app?
- Does the app need to remove these routes or provide source-code offers?

## Chrome Extension and Web Snapshots

The app supports frozen HTML snapshots created by a sister Chrome extension.

Current conclusion:

- The extension itself did not appear to have obvious third-party bundled libraries requiring source attribution, but this should be checked before store distribution.
- The bigger issue is privacy/data-flow disclosure: the extension captures page DOM/assets into a frozen HTML snapshot. Users should understand what is saved locally, uploaded, or sent to the server.
- Captured pages may contain third-party copyrighted content. That is user-provided content, but terms/privacy should cover user responsibility and storage/processing.

Open extension questions for review:

- Does the extension upload snapshots automatically or only save local files?
- What permissions does the extension request?
- Does the extension need Chrome Web Store privacy disclosures?
- Should terms state that users are responsible for rights in uploaded/captured documents and web pages?

## Marketing Screenshots and Videos

The public landing page uses screenshots and videos showing app behavior with sample PDFs, websites, and texts.

Current conclusion:

- This is not a dependency-license issue.
- It is a public copyright/provenance issue.
- If screenshots/videos include third-party books, articles, PDFs, websites, scans, or substantial text excerpts, those examples need clearance, replacement with owned/public-domain material, or fair-use review.

Open marketing questions for review:

- What exact texts/sites/documents appear in the public screenshots/videos?
- Are they public domain, licensed, owned, or fair-use defensible?
- Are any website screenshots covered by site terms restricting reproduction?

## Recommended Public Page Structure

If the goal is strict legal necessity rather than transparency, the public info page can be reduced substantially.

Recommended public-facing legal/provenance content:

1. Dictionary and lexical source attribution.
2. Privacy/service disclosures for Google OAuth, Gemini, Stripe, SMTP/email, and document processing, likely in privacy/terms rather than the info page.
3. Optional third-party notices link for client-side bundled software.

Recommended removals from public info page:

- Dependency Map as a legal/credits section
- NLP Pipeline table
- Specific Model Training Data table, unless kept for transparency
- General App Infrastructure table
- Review Before Public Release section

Keep privately:

- Full software dependency inventory
- Model/data provenance manifest
- Dictionary import provenance
- Marketing asset provenance
- Third-party notices bundle for distributed JS/assets

## Current Practical Conclusions

1. The only major public attribution category that appears strictly necessary is dictionary/lexical content shown to users.
2. The model training data table is probably not legally required on the public page if models stay server-side and datasets/model weights are not distributed.
3. Server-side runtime/software libraries do not need public attribution on the info page for a hosted service.
4. Client-side libraries need notice preservation somewhere, but not necessarily prominent public attribution.
5. Legacy AGPL-ish document-processing routes should be removed/disabled if unused.
6. Marketing media and user-uploaded/captured content need separate terms/privacy/provenance review.

## External Sources Consulted

- Creative Commons BY-SA 4.0 legal code: https://creativecommons.org/licenses/by-sa/4.0/legalcode.en
- Creative Commons BY 4.0 legal code: https://creativecommons.org/licenses/by/4.0/legalcode.en
- Creative Commons FAQ on data and text/data mining: https://creativecommons.org/faq/
- Universal Dependencies licensing page: https://universaldependencies.org/contributing/licensing.html
- MIT License text, Open Source Initiative: https://opensource.org/license/mit
- BSD 3-Clause License text, Open Source Initiative: https://opensource.org/license/BSD-3-clause
- Apache Software Foundation guidance on Apache-2.0 notices: https://www.apache.org/legal/apply-license
- Mozilla Public License 2.0 text: https://www.mozilla.org/en-US/MPL/2.0/
- GNU Affero GPL v3 text: https://www.gnu.org/licenses/agpl-3.0.en.html
- SIL Open Font License text/FAQ: https://openfontlicense.org/open-font-license-official-text/

