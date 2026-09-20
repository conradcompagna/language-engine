import { parseTxtFile, parseTxtString } from "./adapters/txt.js";
import { parseHtmlFile, parseHtmlString } from "./adapters/html.js";
import { parseUrl } from "./adapters/url.js";
import { parseMarkdownFile } from "./adapters/markdown.js";
import { parseEpubFile } from "./adapters/epub.js";
import { parseDocxFile } from "./adapters/docx.js";
import { parsePdfFile } from "./adapters/pdf.js";
import { tokenizeForDemo } from "./align.js";
import { getDocumentStats } from "./canonical.js";
import { DEFAULT_RENDER_OPTIONS, renderReflowableSection, renderFixedLayoutDocument, collectCharacterBoxesForPage } from "./renderer.js";

const els = {
  file: document.querySelector("#fileInput"),
  loadSample: document.querySelector("#loadSample"),
  urlInput: document.querySelector("#urlInput"),
  loadUrl: document.querySelector("#loadUrl"),
  status: document.querySelector("#status"),
  pageHost: document.querySelector("#pageHost"),
  pageLabel: document.querySelector("#pageLabel"),
  prev: document.querySelector("#prevPage"),
  next: document.querySelector("#nextPage"),
  sectionSelect: document.querySelector("#sectionSelect"),
  meta: document.querySelector("#metadata"),
  pageText: document.querySelector("#pageText"),
  tokens: document.querySelector("#tokens"),
  charBoxes: document.querySelector("#charBoxes"),
  inspectChars: document.querySelector("#inspectChars"),
  fontSize: document.querySelector("#fontSize"),
  lineHeight: document.querySelector("#lineHeight"),
  pageSize: document.querySelector("#pageSize")
};

let state = {
  doc: null,
  tokens: [],
  rendered: null,
  pageIndex: 0,
  sectionIndex: 0,
  options: { ...DEFAULT_RENDER_OPTIONS }
};

function setStatus(message, kind = "") {
  els.status.textContent = message;
  els.status.dataset.kind = kind;
}

function extension(fileName) {
  return fileName.toLowerCase().split(".").pop();
}

function applyPageSize(value) {
  if (value === "book") {
    Object.assign(state.options, { pageWidth: 760, pageHeight: 980, marginTop: 58, marginRight: 66, marginBottom: 66, marginLeft: 66 });
  } else if (value === "tablet") {
    Object.assign(state.options, { pageWidth: 820, pageHeight: 1080, marginTop: 62, marginRight: 72, marginBottom: 72, marginLeft: 72 });
  } else {
    Object.assign(state.options, { pageWidth: 650, pageHeight: 850, marginTop: 48, marginRight: 48, marginBottom: 54, marginLeft: 48 });
  }
}

async function parseFile(file) {
  const ext = extension(file.name);
  if (["txt", "text"].includes(ext)) return parseTxtFile(file);
  if (["html", "htm", "xhtml"].includes(ext)) return parseHtmlFile(file);
  if (["md", "markdown"].includes(ext)) return parseMarkdownFile(file);
  if (ext === "epub") return parseEpubFile(file);
  if (ext === "docx") return parseDocxFile(file);
  if (ext === "pdf") return parsePdfFile(file);
  throw new Error(`Unsupported test format: .${ext}. Add an adapter or convert to TXT/HTML/EPUB/DOCX/PDF.`);
}

function summarizeObject(obj) {
  return Object.entries(obj || {})
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .slice(0, 40)
    .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(typeof v === "object" ? JSON.stringify(v).slice(0, 280) : String(v))}</dd>`)
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));
}

function renderMetadata() {
  if (!state.doc) return;
  const stats = getDocumentStats(state.doc);
  els.meta.innerHTML = `
    <h3>${escapeHtml(state.doc.title)}</h3>
    <dl>
      <dt>Source type</dt><dd>${escapeHtml(state.doc.sourceType)}</dd>
      <dt>Sections</dt><dd>${stats.sections}</dd>
      <dt>Blocks</dt><dd>${stats.blocks}</dd>
      <dt>Characters</dt><dd>${stats.characters.toLocaleString()}</dd>
      <dt>Words</dt><dd>${stats.words.toLocaleString()}</dd>
      ${summarizeObject(state.doc.metadata)}
    </dl>`;
  els.sectionSelect.innerHTML = state.doc.sections.map((s, i) => `<option value="${i}">${escapeHtml(s.title || `Section ${i + 1}`)}</option>`).join("");
  els.sectionSelect.value = String(state.sectionIndex);
  els.sectionSelect.disabled = !!state.doc.fixedLayoutPages;
}

function updatePagePanels() {
  const rendered = state.rendered;
  if (!rendered) return;
  const page = rendered.pages[state.pageIndex];
  els.pageLabel.textContent = `Page ${state.pageIndex + 1} / ${rendered.pageCount}`;
  els.prev.disabled = state.pageIndex <= 0;
  els.next.disabled = state.pageIndex >= rendered.pageCount - 1;
  els.pageText.textContent = page?.text || "";
  els.tokens.innerHTML = (page?.tokens || []).slice(0, 200).map(t => `
    <span class="token-chip" title="${escapeHtml(t.dictionaryEntries?.[0]?.gloss || "")}">
      <b>${escapeHtml(t.text)}</b><small>${t.canonicalStart}-${t.canonicalEnd}</small>
    </span>`).join("");

  if (rendered.flow && !state.doc?.fixedLayoutPages && page) {
    const chars = collectCharacterBoxesForPage(rendered.flow, page, state.options, 120);
    els.charBoxes.textContent = JSON.stringify({
      page: state.pageIndex + 1,
      pageRange: [page.canonicalStart, page.canonicalEnd],
      sampledCharacters: chars.length,
      characters: chars.slice(0, 80)
    }, null, 2);
  } else {
    els.charBoxes.textContent = "Character coordinate sample is available for reflowable DOM pages.";
  }
}

async function rerender() {
  if (!state.doc) return;
  state.options.fontSize = Number(els.fontSize.value);
  state.options.lineHeight = Number(els.lineHeight.value);
  applyPageSize(els.pageSize.value);
  state.pageIndex = 0;
  if (state.doc.fixedLayoutPages) {
    state.rendered = renderFixedLayoutDocument({ container: els.pageHost, doc: state.doc, tokens: state.tokens });
  } else {
    state.rendered = await renderReflowableSection({
      container: els.pageHost,
      doc: state.doc,
      sectionIndex: state.sectionIndex,
      tokens: state.tokens,
      options: state.options
    });
  }
  state.rendered.showPage(state.pageIndex);
  updatePagePanels();
}

async function loadDocument(doc, elapsedMs = 0) {
  state.doc = doc;
  state.tokens = tokenizeForDemo(doc.canonicalText);
  state.sectionIndex = 0;
  renderMetadata();
  const renderStart = performance.now();
  await rerender();
  const renderMs = performance.now() - renderStart;
  const stats = getDocumentStats(doc);
  setStatus(`Loaded ${stats.characters.toLocaleString()} chars, ${stats.blocks} blocks. Parse ${elapsedMs.toFixed(1)} ms; first render ${renderMs.toFixed(1)} ms.`, "ok");
}

async function handleFile(file) {
  setStatus(`Parsing ${file.name}…`);
  const t0 = performance.now();
  try {
    const doc = await parseFile(file);
    await loadDocument(doc, performance.now() - t0);
  } catch (err) {
    console.error(err);
    setStatus(err.message || String(err), "error");
  }
}

async function handleUrl() {
  const url = els.urlInput.value.trim();
  if (!url) {
    setStatus("Paste a URL first.", "error");
    return;
  }
  setStatus(`Fetching ${url}…`);
  const t0 = performance.now();
  try {
    const doc = await parseUrl(url);
    await loadDocument(doc, performance.now() - t0);
  } catch (err) {
    console.error(err);
    setStatus(err.message || String(err), "error");
  }
}

function changePage(delta) {
  if (!state.rendered) return;
  state.pageIndex = Math.max(0, Math.min(state.rendered.pageCount - 1, state.pageIndex + delta));
  state.rendered.showPage(state.pageIndex);
  updatePagePanels();
}

async function inspectChars() {
  if (!state.rendered || state.doc?.fixedLayoutPages) {
    els.charBoxes.textContent = "Character box inspection is implemented for reflowable DOM pages in this prototype.";
    return;
  }
  const page = state.rendered.pages[state.pageIndex];
  const chars = collectCharacterBoxesForPage(state.rendered.flow, page, state.options, 300);
  els.charBoxes.textContent = JSON.stringify(chars.slice(0, 80), null, 2);
}

function sampleText() {
  return `        THE GOLDEN BIRD\n\nOnce upon a time there was a king who had a garden, and in the garden stood a tree which bore golden apples.\n\nEvery morning the king counted the apples. One morning one was missing. He ordered that the tree should be watched every night.\n\n    This indented paragraph is deliberately preserved. It lets the renderer prove that raw spacing can survive canonicalization.\n\nCHAPTER II\n\nThe youngest son sat beneath the tree. At midnight a bird came flying through the air, and its feathers shone like fire.\n\nShort verse-like lines\nfall into the page\nwithout being crushed\ninto one paragraph.`;
}

els.file.addEventListener("change", () => {
  const file = els.file.files?.[0];
  if (file) handleFile(file);
});
els.loadUrl.addEventListener("click", handleUrl);
els.urlInput.addEventListener("keydown", event => { if (event.key === "Enter") handleUrl(); });

els.loadSample.addEventListener("click", async () => {
  const t0 = performance.now();
  await loadDocument(parseTxtString(sampleText(), { title: "Sample structured text", fileName: "sample.txt" }), performance.now() - t0);
});
els.prev.addEventListener("click", () => changePage(-1));
els.next.addEventListener("click", () => changePage(1));
els.sectionSelect.addEventListener("change", async () => { state.sectionIndex = Number(els.sectionSelect.value); await rerender(); });
els.fontSize.addEventListener("input", rerender);
els.lineHeight.addEventListener("input", rerender);
els.pageSize.addEventListener("change", rerender);
els.inspectChars.addEventListener("click", inspectChars);

if (globalThis.pdfjsLib) {
  globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
}

els.loadSample.click();
