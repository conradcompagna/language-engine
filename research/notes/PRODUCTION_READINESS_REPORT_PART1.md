# Production Readiness Report - Part 1

Date: 2026-05-14  
App: Language Engine  
Scope: marketing site, account/auth/billing/email, the reader product, Trankit backend, dictionary runtime, Gemini integration, document handling, and initial Hetzner deployment readiness.

## Development context

This May 14, 2026 review records the transition from an integrated application to a
deployable service. The core work already connected multilingual NLP, hybrid
dictionary lookup, document reading, account management, OAuth, subscription
billing, and usage-budgeted language assistance. The review translated that system
into concrete deployment tasks: runtime packaging, secret and session configuration,
worker memory budgeting, cache ownership, and service integration checks.

The findings below describe that development snapshot. Use the maintained
[architecture guide](../../docs/ARCHITECTURE.md), [setup instructions](../../docs/SETUP.md),
and current source for the published application; this historical checklist is a
record of the launch work, not a current deployment audit.

## Readiness snapshot at the time of review

| Area | Current Readiness | Verdict |
| --- | --- | --- |
| Marketing landing page | Good functional base with pricing, product framing, media, signup flow | Needs polish/performance check and CDN removal |
| Account handling | Real signup/login/password reset/change email/delete account flows | Needs production security hardening |
| Stripe billing | Real Checkout, webhooks, subscription sync, portal, invoices | Needs live dashboard verification |
| Email/SMTP | Resend SMTP values are configured locally | Needs domain verification and live send test |
| Google OAuth | Client ID/secret appear configured locally | Needs exact production callback verification |
| Reader/product UI | Active hybrid reader stack is wired | Needs production smoke testing |
| Trankit backend | Real multilingual NLP path exists | Needs server memory/worker strategy |
| Dictionary runtime | SQLite hydration plus JS compact indexes exist | Needs packaging manifest and cache strategy |
| Gemini integration | Real API wrapper, budget enforcement, logging | Needs secret cleanup and live quota test |
| Deployment packaging | Not ready | Needs `wsgi.py`, `requirements.txt`, manifest, cleanup |
| Security posture | Not ready | Disable debug, set secrets, restrict CORS, cookie/rate-limit hardening |
| Multi-worker Hetzner plan | Not ready as-is | Memory and worker-local caches need design choice |

## What Was Checked

This report is based on a local code sweep of the active application paths documented in the project instructions, plus direct inspection of deployment-related files and runtime footprint. The active Flask entrypoint is `router.py`. The active authentication blueprint is `auth.py`. The active Stripe integration is `payments.py`. The core database models are in `db.py`. The active dictionary server path is `dict_lookup_sqlite.py`, with client orchestration in `static/dictionary_client_hybrid.js` and `static/dictionary_engine_hybrid.js`. The active reader template is `templates/reader_jshybrid.html`. The active marketing and account surfaces are `templates/landing.html`, `static/landing.js`, `static/landing.css`, and `templates/account.html`.

Syntax checks passed for the main Python files: `router.py`, `auth.py`, `payments.py`, `config.py`, `db.py`, `language_registry.py`, `dict_lookup_sqlite.py`, `pipeline_common.py`, `document_handling.py`, `api_services.py`, `gemini_dict.py`, `gemini_log.py`, `universal_normalization.py`, `trankit_mwt_expansion.py`, `ud_overlay.py`, `debug_panel.py`, `debug_store.py`, `debug_trace_runtime.py`, and `xpos_definitions.py`. JavaScript syntax checks also passed for `static/landing.js`, `static/dictionary_client_hybrid.js`, and `static/reader.js`.

Those checks are useful, but they are not a substitute for a full deployment smoke test. I did not verify live Stripe webhook delivery, live Google OAuth callback behavior, live Resend message delivery, a real production browser session, or concurrency under Gunicorn. Those should be part of Part 2.

## Marketing And Lander Readiness

The marketing side is in decent shape as a first public face for an indie SaaS. The app has an actual landing page rather than a placeholder, and it includes the important basics: product positioning, language reading context, pricing, signup/login entry points, and a path from pricing into account creation and checkout. The `landing.js` flow is wired so that a prospective customer can choose billing, authenticate, and be carried toward the account/checkout flow. Google OAuth also participates in that flow through the `next` parameter, which matters because a marketing click should not get lost during auth.

The pricing page currently presents Free and Pro. Free is framed around limited daily use. Pro is priced at $10/month or $100/year in the visible landing page, which matches the Stripe price IDs that were recently supplied. That is coherent enough to launch, but it should be reviewed against all product copy. The project overview still mentions Basic and Pro tiers, but the app currently behaves like a Free plus Pro product. For launch, that is fine if intentional. If Basic is not being sold, remove Basic from deployment docs and any old copy. If Basic is still part of the business plan, it is not currently implemented as a first-class tier and should not be advertised.

The visual marketing page appears to have real product media in `static/marketing`, which is good because a language reader is easier to sell when users can see PDF reading, hover lookup, translation, and multilingual examples. The tradeoff is size. The marketing folder is hundreds of megabytes, mostly video. That is acceptable only if Nginx is configured to serve static files efficiently and the videos are compressed enough for public traffic. For a first indie launch, the marketing assets should be reviewed for file size, poster images, mobile behavior, and lazy loading. Large media can make the site feel slow even when the backend is healthy.

The biggest marketing-side deployment problem is external asset loading. The active reader template and CSS still pull from third-party CDNs for Google Fonts, JSZip, DOMPurify, Mammoth, and PDF.js. The repo also has local PDF.js vendor files, but the active template still references CDN resources. This conflicts with the stated deployment goal: the tarball should capture the whole runtime infrastructure. Before production packaging, those assets should be vendored locally and loaded from `static/vendor` or an equivalent local directory. That also improves reliability on a Hetzner deployment because the app does not become dependent on third-party CDN availability, browser blocking, or network policy.

Marketing verdict: the landing page is functionally ready enough to support launch after asset and copy cleanup. It is not the primary blocker. The main remaining marketing work is to verify the page in a real browser at desktop and mobile sizes, confirm that pricing language exactly matches the billing implementation, remove CDN dependencies, and compress or selectively ship only the marketing media that is actually used.

## Account, Auth, Payments, And Email

The account system has the major pieces that a paid SaaS needs. Users can sign up, log in, log out, request password resets, change password, change email, delete their account, and log in with Google OAuth. The account page can show subscription state and usage, start checkout, open the billing portal, and display invoice history. This is a real account system, not a stub.

Stripe integration is also real. `payments.py` creates Checkout Sessions in subscription mode, attaches or creates Stripe customers, supports monthly and yearly price selection, handles webhooks, updates local subscription state, opens the Customer Portal, and lists invoices. The app has routes for `/payments/create-checkout`, `/payments/webhook`, `/payments/portal`, `/payments/invoices`, and `/payments/status`. That is the right shape for an MVP paid SaaS.

The local environment has Stripe live values set, including live secret key, webhook secret, monthly price ID, yearly price ID, and the app base URL. I am intentionally not repeating those values here. The app also has Resend SMTP configured locally with `smtp.resend.com`, port 587, the `resend` username, and a from address on `noreply@language-engine.ai`. The contact destination email can be your personal address without exposing it to users, because it lives server-side. Users see the sender/display address and whatever reply-to behavior is configured, not the hidden destination mailbox.

The remaining account and payment work is operational verification. Stripe still needs the production dashboard side to be correct: the live product and prices must match the app, the Customer Portal must be enabled, the webhook endpoint must point at `https://language-engine.ai/payments/webhook`, and the endpoint must subscribe to the events the app handles. The important events are subscription created, updated, deleted, checkout session completed, invoice payment failed, and invoice payment action required. The webhook secret in the server environment must match that live endpoint, not a different test endpoint.

Google OAuth needs one precise production check. In Google Cloud Console, the OAuth client should include the production JavaScript origin `https://language-engine.ai` and the production redirect URI `https://language-engine.ai/auth/google/callback`. If `www.language-engine.ai` will also be used, it should either redirect to the apex domain consistently or be added explicitly. The app can already handle Google login, but OAuth is exact-string sensitive; one slash or host mismatch can make it fail only after deployment.

Email is close, but not complete until Resend domain verification passes and a live message is sent from the server. Password resets and account email-change confirmations depend on SMTP. Contact form delivery also depends on SMTP. If email is not working, the app can still sign users up, but it should not be considered ready for public paid traffic because users need recovery and support paths. Resend with `noreply@language-engine.ai` for transactional messages and `support@language-engine.ai` for support identity is a normal setup. If replies need to reach your personal inbox, route or forward `support@language-engine.ai` at the mail provider level rather than exposing the personal address in the app.

The account security posture needs hardening before launch. The largest item is `LE_SECRET_KEY`. The local `.env` does not currently set it, so Flask can fall back to the insecure default in `config.py`. That must be fixed before any live deployment. A long random secret should be generated and placed only in the production `.env`. The source default should also be made non-production-safe so the app fails loudly if the secret is missing.

There is also no obvious rate limiting on signup, login, forgot password, reset password, or contact form. For a small launch, this does not require a large system, but some basic protection is important. Flask-Limiter or Nginx-level rate limits would be enough for the first pass. CSRF protection is also not obvious on state-changing authenticated JSON routes. Same-site cookies reduce some risk, but they are not a full replacement for explicit CSRF tokens on account and billing-adjacent actions. Session cookie settings should be hardened in production: secure cookies on HTTPS, HTTP-only, and a sane SameSite policy.

Account verdict: the feature set is basically present. It is not production-ready until the secret key, email verification, OAuth callback, Stripe dashboard, cookie settings, rate limiting, and CSRF posture are handled.

## Product Engine Readiness

The product itself is the strongest part of the app, but also the heaviest operationally. The active architecture is the hybrid lookup chain: the server runs Trankit NLP and returns linguistic overlays, while the browser runs client-side DP segmentation against compact dictionary indexes and then asks the server to hydrate selected SQLite rows. This is the right architecture for this app because it keeps the server from doing expensive full dictionary segmentation on every lookup and lets the browser carry more of the lookup workload.

The active flow is coherent. `reader.js` requests `/lookup`. `dictionary_client_hybrid.js` intercepts and orchestrates the hybrid flow. `router.py` runs `/lookup` through the NLP-only path. The client then segments and calls `/js/hydrate`. `dict_lookup_sqlite.py` reads the full entries from the SQLite dictionary files. `reader_wikt.js` renders the shared dictionary popup. The side panel path similarly intercepts `/lookup_dp_only` and avoids server-side Trankit when only a dictionary-style lookup is needed.

This is a real language engine. It has Trankit-backed tokenization, POS, lemma, dependency and NER overlays where available, a shared renderer for dictionary entries, custom/Gemini entry injection, and a paid feature gate. The syntax checks passing on the active Python and JavaScript files are a good sign. The active language registry currently exposes 27 languages in the UI and registry: Chinese, Japanese, Korean, Vietnamese, Classical Chinese, Turkish, Persian, Indonesian, Hindi, Arabic, Thai, Sanskrit, Old English, French, Italian, Russian, Spanish, German, Dutch, Portuguese, Latin, Greek, Armenian, Ancient Greek, Hebrew, Tagalog, and Swahili. There are additional dictionary SQLite files for other languages, but they are not all active in the UI/registry. The public claim should match the active product. If the marketing says 30+ languages, either activate and test the missing languages or adjust the claim.

The dictionary layer is substantial. The `dict_sqlite` folder is about 6.6 GB and contains 46 SQLite files. The runtime cache is close to 1 GB and contains built compact index artifacts. The compressed Trankit runtime is about 2.7 GB. The `training` folder is over 12 GB. This means deployment is not just "copy a Flask app." It is a data-heavy runtime with models, dictionaries, indexes, static assets, and generated caches. A production manifest is required so that the tarball includes everything the app needs and excludes everything it does not.

The product risk is not mainly correctness at the code level. The risk is runtime behavior under deployment. `router.py` preloads startup resources at import time, including Trankit initialization and JS dictionary index cache building. That may be fine if the cache is already warm, but on a fresh server it can make first boot slow and memory intensive. With Gunicorn, every worker imports the app. If every worker loads its own Trankit pipeline and compressed runtime state, memory usage scales with worker count. This is the central Hetzner sizing issue.

On a 16 GB RAM CPU server, I would be cautious about multiple full Gunicorn workers unless memory is measured after import and after real lookups. On a 32 GB server, two workers may be realistic, but it still needs testing. The app uses a shared Trankit pipeline with a lock inside each process, so threads inside one worker may serialize around Trankit work. Multiple workers can improve concurrency, but each worker costs memory. The right production shape may be two workers on 32 GB, or one worker plus threads on 16 GB, depending on measured resident memory and lookup latency.

There is a second multi-worker issue: worker-local state. Document cache IDs, some runtime caches, debug storage, and in-memory state can live inside one process. If Nginx or Gunicorn sends follow-up requests to a different worker, a cache ID created by worker A may not exist in worker B. PDF serving and document processing routes need to be checked for this. For a single-worker deployment this is not a problem. For multiple workers, either cache state must move to a shared filesystem/database layer, requests must be sticky where necessary, or the flow must be changed so worker-local cache IDs are not required across requests.

Document handling has one specific Linux concern. PDF handling through PyMuPDF is suitable for Hetzner. EPUB and plain text extraction paths look deployable. DOCX conversion is different. The app uses `docx2pdf` for DOCX-to-PDF conversion, and that package is generally not a good Linux server dependency because it relies on Microsoft Word or platform-specific automation. A LibreOffice fallback appears to have been considered but is disabled. If original-layout DOCX viewing is part of the sold product, this is a production blocker for Hetzner. If DOCX text extraction is enough for launch, then disable or clearly avoid the DOCX-to-PDF path until a Linux-compatible converter is implemented.

Product verdict: the core language engine is real and close, but production readiness depends on measured memory, worker design, local asset packaging, Linux document behavior, and a live smoke-test matrix across the top languages.

## Gemini Integration

Gemini integration is present through `api_services.py`, `gemini_dict.py`, `gemini_log.py`, and account-tier budget enforcement. The app has paid feature gating and tracks API usage. It also has custom synthetic dictionary entry paths. This is enough for a paid product feature, assuming the live API key and quotas are configured.

The issue is secret handling and logging. The local `.env` does not appear to set `GEMINI_API_KEY`, while `config.py` contains a hardcoded fallback key. That should be removed before production. API keys should be supplied only through environment variables on the server. The app should fail clearly if the key is missing and a Gemini feature is requested. Source-controlled hardcoded keys are a liability, and they make it harder to know which key production is actually using.

Gemini logs also need production treatment. `logs/gemini_comms.jsonl` is already sizeable and should not be included in a clean deployment tarball. Logs may contain user text and model responses, so they should be treated as private operational data. For production, log retention should be deliberate: either log only the metadata needed for cost/debugging, or rotate and restrict the full communication logs. A paid reading app will process user documents and selected text; privacy expectations matter even for an indie SaaS.

Gemini verdict: functionally present, but production should use env-only keys, clean logging, and a live budget/quota smoke test.

## Deployment And Packaging Readiness

This is the least ready area. The current repo root does not have the basic production files that the old Hetzner project had: no active root `wsgi.py`, no active root `requirements.txt`, and no current runtime manifest. There are deployment notes in the repo, but the app is not yet in a clean "tar this and deploy" state.

The desired deployment flow is sensible: copy the full workspace, delete unnecessary files, make sure all runtime infrastructure is local, include requirements, include settings templates, then deploy to Hetzner. But that cleanup should be scripted or at least driven by a manifest. Manual deletion from a giant workspace is risky because the app depends on large data directories, model directories, local vendor assets, language configs, static files, templates, and caches. A missing file may only show up when a user tries a specific language.

The production tarball should include at least:

- Active Python runtime files.
- Active templates.
- Active static files and local vendor JavaScript/CSS assets.
- `dict_sqlite` for all shipped languages.
- `wiktionary_general/lang_config_*.json`.
- The compressed Trankit runtime directories actually used by `NEWPIPELINE=1`.
- The dependency bundle or normal installed packages needed for ONNX runtime.
- Required Trankit model/cache files.
- Runtime cache artifacts if the goal is fast first boot.
- A production `wsgi.py`.
- A pinned `requirements.txt`.
- A `.env.example` matching the current config names.
- A deployment manifest listing every included runtime path.
- Nginx and systemd templates.

It should exclude:

- `.env` and all real secrets.
- Logs.
- Debug dumps.
- Backup and copy files.
- Old defunct architecture folders.
- Training data not needed at runtime.
- Local database contents unless intentionally seeding production.
- Browser cache or temporary files.
- Any old SQLite WAL/SHM files from local development.

The lack of `requirements.txt` is a concrete blocker. The local environment has many packages installed, including a CUDA/dev build of PyTorch that is not suitable for a Hetzner CPU server. The production requirements should be pinned to CPU-compatible packages. If the compressed ONNX path is the intended default, the requirements and runtime manifest need to say exactly whether production installs `onnxruntime` normally or ships the existing bundled dependency directory. The current app can work locally because the sandbox dependency directory is present, but production should not depend on an undocumented path.

The old project's `wsgi.py` is a useful template: it imports the Flask app and performs startup loading before Gunicorn serves traffic. For this app, a simple `wsgi.py` can probably import `app` from `router.py`, because `router.py` already preloads startup resources at import. However, Part 2 should decide whether import-time preloading remains acceptable or whether production startup should be made more explicit. The service command will likely be something like `gunicorn wsgi:app --bind 127.0.0.1:5000 --workers 1 or 2 --threads 1 --timeout 180`, with Nginx proxying public HTTPS traffic and serving static files directly.

Deployment verdict: not ready. The app needs production files, pinned dependencies, local vendored browser assets, a runtime manifest, a cleanup list, and a measured Gunicorn worker plan.

## Security, Privacy, And Operations

Several production hardening items need attention before public launch. The largest is debug exposure. `router.py` registers the debug blueprint, and `debug_store.py` has debug collection enabled. That is useful locally, but it should not be public. Debug routes can expose lookup internals, user text, system behavior, and operational data. Production should either not register `debug_bp` at all or guard it behind explicit admin authentication and a production env flag that defaults to off.

CORS is also too open for production. `CORS(app)` with default behavior is convenient during development, but a deployed SaaS should restrict allowed origins to `https://language-engine.ai` and any intentional alternate host. This is especially relevant because the app uses cookie-based login sessions.

The Flask secret key must be set. Cookie/session security should be explicit. HTTPS should be mandatory through Nginx and Certbot. Upload limits and Nginx proxy timeouts should match the Flask 500 MB max upload setting if large PDFs are genuinely supported. Logs should be rotated. The SQLite app database should have a backup plan. Stripe webhook failures should be visible in logs or monitoring. A `/healthz` endpoint would be useful for uptime checks, even if it only verifies the process is alive and can reach the database.

SQLite is acceptable for a small first launch if traffic is modest and writes are low. It is not a scaling plan. For an indie launch, the minimum is to put the database in a known persistent path, back it up regularly, ensure WAL behavior is understood, and avoid shipping dev data. If real paid traffic grows, Postgres should become the account/subscription/user-data store. Dictionary SQLite files are separate read-heavy assets and are fine as SQLite.

Operations verdict: launchable after a hardening pass, but not safe to expose today because debug, secrets, CORS, cookie, dependency, and backup settings are not finished.

## P0 Requirements Before Go-Live

1. Create a production `wsgi.py` for Gunicorn.
2. Create a pinned production `requirements.txt` for a Hetzner CPU server.
3. Generate and set `LE_SECRET_KEY` in production `.env`.
4. Remove hardcoded Gemini fallback secrets from source and require env configuration.
5. Disable or auth-guard the debug panel and debug collection in production.
6. Restrict CORS to the production domain.
7. Vendor CDN JavaScript/CSS/font assets locally or intentionally document every external dependency.
8. Verify Resend domain status and send a live password-reset email from the deployed server.
9. Verify Google OAuth with `https://language-engine.ai/auth/google/callback`.
10. Verify Stripe live Checkout, webhook delivery, subscription sync, Customer Portal, and invoices.
11. Decide worker strategy after measuring memory: likely one worker for 16 GB, one or two for 32 GB.
12. Resolve worker-local document cache behavior before using multiple workers.
13. Fix or disable Linux DOCX-to-PDF conversion.
14. Build a runtime manifest and clean tarball include/exclude list.
15. Remove logs, temp files, backup files, copy files, local secrets, and dev database artifacts from the deployment package.

## P1 Requirements Before Serious Paid Traffic

1. Add rate limiting to auth, contact, password reset, and expensive lookup/API routes.
2. Add CSRF protection for authenticated state-changing routes.
3. Set secure session cookie options explicitly.
4. Add Nginx config for HTTPS, upload size, proxy timeouts, static caching, and gzip/brotli where appropriate.
5. Add systemd service config and logrotate config.
6. Add a health endpoint and uptime monitoring.
7. Add regular SQLite backup automation.
8. Confirm privacy/logging policy for document text, selected text, Gemini calls, and contact messages.
9. Run a browser smoke test for landing, signup, login, checkout, account portal, upload, lookup, Gemini, password reset, and contact form.
10. Run a language smoke matrix for the top launch languages.
11. Review public claims: active language count, pricing, usage limits, LLM limits, cancellation terms, and support path.

## Hetzner Server Recommendation

For this app, 32 GB RAM is the safer first production choice if budget allows. The app is data-heavy and model-heavy. The dictionary files are large, the Trankit runtime is large, and multiple workers can multiply memory. A 16 GB server may work for a careful single-worker launch, especially if the ONNX compressed runtime is stable and memory is measured, but it leaves less room for spikes, index generation, large PDF processing, and operational overhead.

Do not assume that "more workers" is automatically better here. For a typical small Flask app, workers improve throughput easily. For this app, each worker may carry a large NLP/model footprint, and some document/cache state may be process-local. The first production deployment should prioritize predictability: one worker if using 16 GB, measured two-worker deployment if using 32 GB, and then scale based on real memory and latency data.

If low latency is the goal, prebuilding dictionary compact indexes and shipping the runtime cache is useful. If smaller tarball size is the goal, the server can build caches on first boot, but first startup may be slow. For a paid app, I would favor shipping prebuilt cache artifacts once the manifest is clean, because predictable boot and first-user behavior matter.

## Conclusion

The review established deployment hardening as the next phase of development: the marketing page, account system, Stripe integration, email integration, Google OAuth path, reader UI, Trankit backend, dictionary hydration, and Gemini feature stack were already integrated. The checklist below records the remaining work identified on May 14, 2026.

The go-live blockers are mainly production discipline: clean packaging, pinned requirements, local assets, secure secrets, disabled debug surfaces, verified third-party dashboards, documented runtime data, and a measured Hetzner worker plan. Once those are handled, the app should be suitable for a controlled indie SaaS launch. The most practical next phase is to create the deployment files and manifest, localize browser dependencies, clean the tarball boundary, and run the app on a fresh server-like environment before deploying it publicly.
