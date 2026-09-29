# Browser source


ES modules compile into the `static/*.js` assets consumed by templates and classic
workers. Entrypoints preserve those loading contracts; PDF.js, Mammoth, DOMPurify
and Foliate provide the document-rendering dependencies.

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
