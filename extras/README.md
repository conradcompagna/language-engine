# Document capture and rendering

I developed these components around two parts of the reading workflow: capturing
web pages with their visual context, and connecting rendered document text to
stable annotation offsets.

| Component | Engineering focus |
|---|---|
| [Chrome capture extension](chrome-extension/README.md) | DOM serialization, asset capture, frame handling and static HTML export |
| [Document-rendering study](document-renderer-test-app/README.md) | Format adapters, a canonical text model, pagination and character geometry |

The extension produces a captured HTML document. The rendering study records the
document-model and layout work in a separate development application. The
[reader architecture](../docs/BUILD_PROCESS.md#runtime-architecture) maps the
integrated application's document and annotation services.
