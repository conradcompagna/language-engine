# Browser source

Source for the reader's browser code, as ES modules. `npm run build` compiles the
entry points listed in `entries.json` into the `static/*.js` files loaded by the
templates; those build outputs are not tracked. PDF.js, Mammoth, DOMPurify and Foliate
provide document rendering.

| Folder | Contents |
|---|---|
| `reader/` | Reader interface: popups, overlays, entry editing, document navigation, settings |
| `dictionary/engine/` | Dictionary index loading, word matching, segmentation and fuzzy search |
| `dictionary/client/` | Caching, workers and requests to the server for full entries |
| `documents/pdf/` | PDF display |
| `documents/snapshot/` | Display of saved web pages |
| `linguistics/tags/` | Grammatical tag tables |
| `linguistics/pronunciation/` | Grapheme analysis and pronunciation tables by script |
| `styles/` | Stylesheets |

Each feature module keeps its state in an adjacent `*.state.mjs` file, and each entry
point's `index.mjs` initializes its modules.
