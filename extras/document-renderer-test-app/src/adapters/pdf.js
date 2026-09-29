import { createBlock, createSection, finalizeCanonicalDocument, escapeHtml } from "../canonical.js";

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function safeTransform(item) {
  const tx = item?.transform;
  if (!Array.isArray(tx) || tx.length < 6) return null;
  if (!tx.every(isFiniteNumber)) return null;
  return tx;
}

function isRealTextItem(item) {
  return typeof item?.str === "string" && safeTransform(item);
}

export function normalizePdfTextItems(rawItems = []) {
  // pdf.js can return marked-content sentinels when includeMarkedContent is true;
  // some PDFs also produce malformed/no-transform text items. Those are not renderable.
  return rawItems
    .filter(isRealTextItem)
    .map((item, index) => {
      const tx = safeTransform(item);
      const str = item.str || "";
      return {
        ...item,
        str,
        transform: tx,
        originalIndex: index,
        x: tx[4],
        y: tx[5],
        fontSize: Math.max(6, Math.hypot(tx[0], tx[1]) || Math.abs(tx[3]) || Number(item.height) || 10),
        width: isFiniteNumber(item.width) ? item.width : Math.max(1, str.length * 6),
        height: isFiniteNumber(item.height) ? item.height : Math.max(8, Math.hypot(tx[0], tx[1]) || 10)
      };
    });
}

function makePdfTextHtml(items, viewport) {
  const width = Math.max(1, Math.floor(viewport?.width || 800));
  const height = Math.max(1, Math.floor(viewport?.height || 1000));
  const normalized = normalizePdfTextItems(items);
  const spans = normalized.map(item => {
    const x = item.x;
    const y = height - item.y;
    const fontSize = item.fontSize;
    const text = escapeHtml(item.str || "");
    if (!text) return "";
    return `<span class="pdf-text-item" data-pdf-item="${item.originalIndex}" style="left:${x.toFixed(2)}px;top:${Math.max(0, y - fontSize).toFixed(2)}px;font-size:${fontSize.toFixed(2)}px">${text}</span>`;
  }).join("");
  const empty = spans ? "" : `<div class="pdf-empty-page">No extractable text was found on this page.</div>`;
  return `<div class="pdf-fixed-page" style="width:${width}px;height:${height}px">${spans}${empty}</div>`;
}

function joinPdfItems(items) {
  const normalized = normalizePdfTextItems(items);
  let out = "";
  let lastY = null;
  let lastX = null;
  for (const item of normalized) {
    const y = Math.round(item.y);
    const x = item.x;
    const value = item.str || "";
    if (!value) continue;
    if (lastY !== null) {
      if (item.hasEOL || Math.abs(y - lastY) > 5) out += "\n";
      else if (out && !/\s$/.test(out) && (lastX === null || x > lastX)) out += " ";
    }
    out += value;
    lastY = y;
    lastX = x + (item.width || 0);
  }
  return out.trim();
}

async function getPageTextContentSafely(page) {
  try {
    // includeMarkedContent=false avoids marked-content pseudo-items that do not have transforms.
    return await page.getTextContent({ includeMarkedContent: false, disableNormalization: false });
  } catch (firstError) {
    console.warn("PDF text extraction failed; retrying with default options.", firstError);
    try {
      return await page.getTextContent();
    } catch (secondError) {
      console.warn("PDF text extraction failed for page.", secondError);
      return { items: [] };
    }
  }
}

export async function parsePdfFile(file) {
  if (!globalThis.pdfjsLib) throw new Error("PDF support needs pdf.js loaded from index.html.");
  const arrayBuffer = await file.arrayBuffer();
  const loadingTask = globalThis.pdfjsLib.getDocument({
    data: arrayBuffer,
    useSystemFonts: true,
    disableFontFace: false
  });
  const pdf = await loadingTask.promise;
  const sections = [];
  const fixedLayoutPages = [];
  const metadata = { format: "PDF", parser: "pdf.js textContent adapter", pages: pdf.numPages };
  try {
    const meta = await pdf.getMetadata();
    Object.assign(metadata, meta.info || {});
    if (meta.metadata?.getAll) metadata.xmp = meta.metadata.getAll();
  } catch {}

  const warnings = [];
  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
    try {
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1.35 });
      const textContent = await getPageTextContentSafely(page);
      const items = normalizePdfTextItems(textContent.items || []);
      const text = joinPdfItems(items);
      const html = makePdfTextHtml(items, viewport);
      if (!items.length) warnings.push(`Page ${pageNumber}: no extractable text items.`);
      const block = createBlock({
        type: "pre",
        text,
        html,
        style: { whiteSpace: "pre-wrap" },
        sourcePath: `${file.name}#page=${pageNumber}`,
        metadata: { pageNumber, width: viewport.width, height: viewport.height, textItems: items.length }
      });
      const section = createSection({ title: `Page ${pageNumber}`, sourcePath: `${file.name}#page=${pageNumber}`, blocks: [block], metadata: { pageNumber } });
      sections.push(section);
      fixedLayoutPages.push({
        pageIndex: fixedLayoutPages.length,
        sectionId: section.id,
        sourcePage: pageNumber,
        width: viewport.width,
        height: viewport.height,
        html,
        text,
        canonicalStart: -1,
        canonicalEnd: -1,
        metadata: { textItems: items.length }
      });
    } catch (err) {
      console.warn(`Skipping PDF page ${pageNumber}.`, err);
      warnings.push(`Page ${pageNumber}: ${err?.message || String(err)}`);
      const text = `[PDF page ${pageNumber} could not be parsed: ${err?.message || String(err)}]`;
      const html = `<div class="pdf-fixed-page" style="width:800px;height:1000px"><div class="pdf-empty-page">${escapeHtml(text)}</div></div>`;
      const block = createBlock({ type: "pre", text, html, style: { whiteSpace: "pre-wrap" }, sourcePath: `${file.name}#page=${pageNumber}`, metadata: { pageNumber, error: true } });
      const section = createSection({ title: `Page ${pageNumber}`, sourcePath: `${file.name}#page=${pageNumber}`, blocks: [block], metadata: { pageNumber, error: true } });
      sections.push(section);
      fixedLayoutPages.push({ pageIndex: fixedLayoutPages.length, sectionId: section.id, sourcePage: pageNumber, width: 800, height: 1000, html, text, canonicalStart: -1, canonicalEnd: -1, metadata: { error: true } });
    }
  }
  if (warnings.length) metadata.warnings = warnings.slice(0, 50);

  const doc = finalizeCanonicalDocument({
    title: metadata.Title || metadata.title || file.name,
    sourceType: "pdf",
    fileName: file.name,
    metadata,
    sections,
    fixedLayoutPages
  });

  // Fill PDF page canonical ranges after finalization.
  for (let i = 0; i < doc.fixedLayoutPages.length; i++) {
    const page = doc.fixedLayoutPages[i];
    const section = doc.sections[i];
    page.sectionId = section.id;
    page.canonicalStart = section.canonicalStart;
    page.canonicalEnd = section.canonicalEnd;
  }
  return doc;
}
