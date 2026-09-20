import { createBlock, createSection, finalizeCanonicalDocument } from "../canonical.js";

const BLOCK_TAGS = new Set(["P", "DIV", "SECTION", "ARTICLE", "HEADER", "FOOTER", "ASIDE", "MAIN"]);
const HEADING_TAGS = new Set(["H1", "H2", "H3", "H4", "H5", "H6"]);

function cleanHtml(html) {
  if (globalThis.DOMPurify) {
    return globalThis.DOMPurify.sanitize(html, {
      ADD_ATTR: ["style", "class", "data-*"],
      FORBID_TAGS: ["script", "iframe", "object", "embed"]
    });
  }
  return String(html).replace(/<script[\s\S]*?<\/script>/gi, "");
}

function pickInlineStyle(el) {
  const style = {};
  const attr = el.getAttribute?.("style") || "";
  const read = prop => {
    const m = attr.match(new RegExp(`${prop}\\s*:\\s*([^;]+)`, "i"));
    return m ? m[1].trim() : undefined;
  };
  const textAlign = read("text-align");
  const fontSize = read("font-size");
  const fontWeight = read("font-weight");
  const fontStyle = read("font-style");
  const marginLeft = read("margin-left");
  const textIndent = read("text-indent");
  if (textAlign) style.textAlign = textAlign;
  if (fontSize) style.fontSize = fontSize;
  if (fontWeight) style.fontWeight = fontWeight;
  if (fontStyle) style.fontStyle = fontStyle;
  if (marginLeft) style.marginLeft = marginLeft;
  if (textIndent) style.textIndent = textIndent;
  return style;
}

function nodeToBlock(el, sourcePath) {
  const tag = el.tagName;
  const text = (el.textContent || "").replace(/\s+\n/g, "\n").trim();
  if (!text && tag !== "IMG") return null;
  let type = "paragraph";
  if (HEADING_TAGS.has(tag)) type = "heading";
  else if (tag === "LI") type = "list_item";
  else if (tag === "BLOCKQUOTE") type = "blockquote";
  else if (tag === "PRE" || tag === "CODE") type = "pre";
  else if (tag === "TABLE") type = "table";
  else if (tag === "IMG") type = "image";
  const html = cleanHtml(el.innerHTML || text);
  return createBlock({ type, text, html, style: pickInlineStyle(el), sourcePath });
}

export function htmlStringToSections(html, { title = "HTML document", sourcePath = "inline.html" } = {}) {
  const parser = new DOMParser();
  const parsed = parser.parseFromString(cleanHtml(html), "text/html");
  const body = parsed.body;
  const blocks = [];

  function walk(node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName;
    if (HEADING_TAGS.has(tag) || BLOCK_TAGS.has(tag) || ["LI", "BLOCKQUOTE", "PRE", "TABLE"].includes(tag)) {
      const block = nodeToBlock(node, sourcePath);
      if (block) blocks.push(block);
      return;
    }
    for (const child of Array.from(node.children)) walk(child);
  }

  for (const child of Array.from(body.children)) walk(child);
  if (!blocks.length && body.textContent?.trim()) {
    blocks.push(createBlock({ type: "paragraph", text: body.textContent.trim(), html: cleanHtml(body.innerHTML), sourcePath }));
  }
  return [createSection({ title, sourcePath, blocks })];
}

export async function parseHtmlFile(file) {
  const html = await file.text();
  const sections = htmlStringToSections(html, { title: file.name, sourcePath: file.name });
  return finalizeCanonicalDocument({
    title: file.name,
    sourceType: "html",
    fileName: file.name,
    metadata: { format: "HTML", parser: "built-in HTML adapter" },
    sections
  });
}

export function parseHtmlString(html, { title = "HTML document", fileName = "inline.html" } = {}) {
  const sections = htmlStringToSections(html, { title, sourcePath: fileName });
  return finalizeCanonicalDocument({
    title,
    sourceType: "html",
    fileName,
    metadata: { format: "HTML", parser: "built-in HTML adapter" },
    sections
  });
}
