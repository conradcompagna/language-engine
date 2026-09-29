# Third-party software and data

This repository contains original application code alongside integrations with third-party software. Dependency manifests and upstream notices remain authoritative for those components. Inclusion here does not relicense upstream software or datasets.

Large datasets, model weights, generated results, and private account data are not distributed. Obtain external resources under their respective terms. This publication adds no license grant beyond existing component license declarations. Proprietary datasets are not licensed or distributed here.

The vendored [Foliate.js](https://github.com/johnfactotum/foliate-js) files contain the browser renderer and the dependencies used by this application. Upstream demo pages, unused modules, tests, and build tooling are omitted. Its [MIT license](static/foliate-js/LICENSE) and package attribution are retained.

## Vendored inventory

The [SHA-256 inventory](docs/vendor-manifest.json) identifies the included bytes;
an upstream commit cannot be recovered reliably from a minified file alone.
No dependency binaries were silently upgraded during modularization.

| Location | Upstream / retained attribution |
|---|---|
| `static/vendor/pdfjs/` | [Mozilla PDF.js](https://github.com/mozilla/pdf.js), Apache-2.0 notices in the files |
| `static/vendor/dompurify/` | [DOMPurify](https://github.com/cure53/DOMPurify), header identifies 3.2.4 and Apache-2.0/MPL-2.0 |
| `static/vendor/mammoth/` | [Mammoth.js](https://github.com/mwilliamson/mammoth.js), retain bundled notices and consult upstream terms |
| `static/marked.min.js` | [Marked](https://github.com/markedjs/marked), retain bundled copyright/license header |
| `static/foliate-js/` | [Foliate.js](https://github.com/johnfactotum/foliate-js), retained MIT license and package metadata |
| `research/pipeline/models/upstream_patches/trankit/` | Local Trankit patch snapshot; compare with [Trankit](https://github.com/nlp-uoregon/trankit) before applying to a different version |

Python and browser build dependencies are recorded in the requirements files and
`package-lock.json`; model and dataset terms remain separate from software licenses.
