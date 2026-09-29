export const CANONICAL_VERSION = "0.1.0";

let idCounter = 0;
export function makeId(prefix = "id") {
  idCounter += 1;
  return `${prefix}_${idCounter.toString(36)}`;
}

export function normalizeWhitespaceForAlignment(value) {
  return String(value ?? "")
    .normalize("NFKC")
    .replace(/\u00AD/g, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/[ \t\f\v\r\n]+/g, " ")
    .trim();
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function styleObjectToCss(style = {}) {
  const pairs = [];
  const map = {
    textAlign: "text-align",
    fontSize: "font-size",
    fontWeight: "font-weight",
    fontStyle: "font-style",
    fontFamily: "font-family",
    marginTop: "margin-top",
    marginBottom: "margin-bottom",
    marginLeft: "margin-left",
    marginRight: "margin-right",
    textIndent: "text-indent",
    lineHeight: "line-height",
    whiteSpace: "white-space"
  };
  for (const [key, value] of Object.entries(style)) {
    if (value === undefined || value === null || value === "") continue;
    const prop = map[key] || key.replace(/[A-Z]/g, m => `-${m.toLowerCase()}`);
    const cssValue = typeof value === "number" && /fontSize|margin|textIndent|lineHeight/.test(key)
      ? `${value}px`
      : String(value);
    pairs.push(`${prop}:${cssValue}`);
  }
  return pairs.join(";");
}

export function createBlock({
  id = makeId("block"),
  type = "paragraph",
  text = "",
  html = null,
  runs = [],
  style = {},
  attrs = {},
  sourcePath = null,
  metadata = {}
} = {}) {
  return {
    id,
    type,
    text: String(text ?? ""),
    html,
    runs,
    style,
    attrs,
    sourcePath,
    metadata,
    canonicalStart: -1,
    canonicalEnd: -1
  };
}

export function createSection({ id = makeId("section"), title = "", sourcePath = null, blocks = [], metadata = {} } = {}) {
  return { id, title, sourcePath, blocks, metadata, canonicalStart: -1, canonicalEnd: -1 };
}

export function finalizeCanonicalDocument({
  title = "Untitled document",
  sourceType = "unknown",
  fileName = "",
  metadata = {},
  sections = [],
  fixedLayoutPages = null
} = {}) {
  let canonicalText = "";
  const sourceMap = [];
  const blockIndex = new Map();
  const sectionIndex = new Map();

  for (const section of sections) {
    section.canonicalStart = canonicalText.length;
    sectionIndex.set(section.id, section);
    for (const block of section.blocks) {
      const prefix = canonicalText.length > 0 ? "\n\n" : "";
      if (prefix) canonicalText += prefix;
      block.canonicalStart = canonicalText.length;
      canonicalText += block.text ?? "";
      block.canonicalEnd = canonicalText.length;
      block.sectionId = section.id;
      blockIndex.set(block.id, block);
      sourceMap.push({
        sectionId: section.id,
        blockId: block.id,
        sourcePath: block.sourcePath || section.sourcePath || null,
        canonicalStart: block.canonicalStart,
        canonicalEnd: block.canonicalEnd,
        type: block.type
      });
    }
    section.canonicalEnd = canonicalText.length;
  }

  const doc = {
    version: CANONICAL_VERSION,
    id: makeId("doc"),
    title,
    sourceType,
    fileName,
    metadata,
    sections,
    canonicalText,
    sourceMap,
    fixedLayoutPages,
    createdAt: new Date().toISOString()
  };

  Object.defineProperties(doc, {
    blockIndex: { value: blockIndex, enumerable: false },
    sectionIndex: { value: sectionIndex, enumerable: false }
  });
  return doc;
}

export function blockToHtml(block) {
  const css = styleObjectToCss(block.style);
  const attr = `data-block-id="${escapeHtml(block.id)}" data-canonical-start="${block.canonicalStart}" data-canonical-end="${block.canonicalEnd}"`;
  const styleAttr = css ? ` style="${escapeHtml(css)}"` : "";
  const content = block.html ?? escapeHtml(block.text);
  switch (block.type) {
    case "heading": return `<h2 ${attr}${styleAttr}>${content}</h2>`;
    case "blockquote": return `<blockquote ${attr}${styleAttr}>${content}</blockquote>`;
    case "pre": return `<pre ${attr}${styleAttr}>${content}</pre>`;
    case "list_item": return `<li ${attr}${styleAttr}>${content}</li>`;
    case "table": return `<div class="canonical-table" ${attr}${styleAttr}>${content}</div>`;
    case "image": return `<figure ${attr}${styleAttr}>${content}</figure>`;
    default: return `<p ${attr}${styleAttr}>${content}</p>`;
  }
}

export function sectionToHtml(section) {
  const chunks = [];
  let inList = false;
  for (const block of section.blocks) {
    if (block.type === "list_item") {
      if (!inList) { chunks.push("<ul>"); inList = true; }
      chunks.push(blockToHtml(block));
    } else {
      if (inList) { chunks.push("</ul>"); inList = false; }
      chunks.push(blockToHtml(block));
    }
  }
  if (inList) chunks.push("</ul>");
  return chunks.join("\n");
}

export function getDocumentStats(doc) {
  const blockCount = doc.sections.reduce((sum, s) => sum + s.blocks.length, 0);
  return {
    sections: doc.sections.length,
    blocks: blockCount,
    characters: doc.canonicalText.length,
    words: (doc.canonicalText.match(/\S+/g) || []).length,
    fixedPages: doc.fixedLayoutPages?.length || 0
  };
}
