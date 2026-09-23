# Browser source

Run `npm ci --ignore-scripts && npm run build` before starting Flask. Node 22 or
newer is used in CI. The build produces readable bundles and source maps at the
existing `static/*.js` URLs, so templates and classic `importScripts` workers
retain their loading contract. Generated bundles are ignored by Git; edit these
ES modules instead. Vendored PDF.js, Mammoth, DOMPurify and Foliate remain separate.

| Directory                    | Responsibility                                                                                 |
| ---------------------------- | ---------------------------------------------------------------------------------------------- |
| `reader/`                    | Reader presentation, entry editing, popups, overlays, document navigation and settings         |
| `dictionary/engine/`         | Entry parsing, index loading, identity, selection, segmentation, fuzzy search and hydration    |
| `dictionary/client/`         | Cache and workers, winner references, result assembly, language lifecycle and request adapters |
| `documents/snapshot/`        | Snapshot frame lifecycle, selection, layout, pagination and inert interaction                  |
| `linguistics/tags/`          | Language tag tables and lookup API                                                             |
| `linguistics/pronunciation/` | Grapheme analysis, script-specific algorithms, profiles and tables                             |

Each entrypoint imports feature modules explicitly. Feature state lives in the
adjacent `*.state.mjs` module; `index.mjs` initializes each entrypoint in dependency
order. Browser and worker APIs are synchronous where their callers require it.
Modules import cross-feature functions directly; state modules have no DOM or
network effects on import.

## Checks and fixture demo

```sh
npm run build
npm test
npx playwright install chromium
npm run test:browser
node tests/browser/fixture-server.mjs
```

The last command serves the real reader template at `http://127.0.0.1:8791`
with synthetic authentication/configuration responses, without importing the
production server, loading a model, or calling an external service.

Regression fixtures cover dictionary/form lookup, compact row
identity, fuzzy tiers, custom-key updates, lemma alignment, every published tag
label, and pronunciation results for all profile table keys and spans. Browser
tests exercise rendering, snapshot selection/isolation, classic worker imports,
and PDF loading/search using a synthetic local PDF. Stylesheets use explicit
imports to define cascade order. Model-backed evaluation is documented separately
in the [research evidence index](../research/EVIDENCE.md).
