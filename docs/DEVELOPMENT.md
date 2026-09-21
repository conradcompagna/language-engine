# Development commands

Use Python 3.12 and Node.js 22 or newer; activate a virtual environment first.
Commands run from the repository root and use public synthetic fixtures.

```sh
python -m pip install -r requirements-dev.txt
npm ci
npm run build
python tools/check_repository.py
node tools/check_javascript.mjs
python -m pytest
npm test
npx playwright install chromium
npm run test:browser
```

Linux CI installs browser system dependencies with `npx playwright install --with-deps chromium`.
The browser sources and generated URLs are described in [frontend/README.md](../frontend/README.md).
Build outputs are ignored and must be generated before serving the reader.
For a local interactive fixture, follow [setup](SETUP.md); full inference requires
separately provisioned assets and credentials. The public checks do not assert neural
quality, GPU performance or behavior of the live website.

See [research evidence](../research/EVIDENCE.md), [reproduction commands](../research/REPRODUCIBILITY.md),
[contributing](../CONTRIBUTING.md) and [security](../SECURITY.md).
