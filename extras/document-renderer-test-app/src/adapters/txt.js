import { createBlock, createSection, finalizeCanonicalDocument, escapeHtml } from "../canonical.js";

function looksCentered(line) {
  const leading = line.match(/^\s*/)?.[0].length || 0;
  const trimmed = line.trim();
  return leading >= 4 && trimmed.length > 0 && trimmed.length <= 80;
}

function looksHeading(line, previousBlank, nextBlank) {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (/^(chapter|book|part|section|canto|act)\b/i.test(trimmed)) return true;
  if (/^[IVXLCDM]+\.?\s+/.test(trimmed)) return true;
  if (previousBlank && nextBlank && trimmed.length <= 72 && !/[.!?;:]$/.test(trimmed)) return true;
  if (trimmed === trimmed.toUpperCase() && /[A-Z]/.test(trimmed) && trimmed.length <= 80) return true;
  return false;
}

function paragraphize(text) {
  const lines = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let para = [];

  function flushPara() {
    if (!para.length) return;
    const text = para.join("\n");
    const first = para[0] || "";
    blocks.push(createBlock({
      type: para.length > 1 && para.every(l => l.length < 85) ? "pre" : "paragraph",
      text,
      html: escapeHtml(text),
      style: {
        whiteSpace: "pre-wrap",
        textIndent: /^\s{2,}/.test(first) ? Math.min(48, first.match(/^\s*/)[0].length * 4) : undefined
      }
    }));
    para = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const previousBlank = i === 0 || !lines[i - 1].trim();
    const nextBlank = i === lines.length - 1 || !lines[i + 1].trim();

    if (!line.trim()) {
      flushPara();
      continue;
    }

    if (looksHeading(line, previousBlank, nextBlank) || looksCentered(line)) {
      flushPara();
      const trimmed = line.trim();
      blocks.push(createBlock({
        type: "heading",
        text: trimmed,
        html: escapeHtml(trimmed),
        style: { textAlign: looksCentered(line) ? "center" : undefined, fontWeight: "700" }
      }));
      continue;
    }

    para.push(line);
  }
  flushPara();
  return blocks;
}

export async function parseTxtFile(file) {
  const text = await file.text();
  return parseTxtString(text, { fileName: file.name });
}

export function parseTxtString(text, { fileName = "raw-text.txt", title = fileName } = {}) {
  const blocks = paragraphize(text);
  const section = createSection({ id: "section_1", title, blocks });
  return finalizeCanonicalDocument({
    title,
    sourceType: "txt",
    fileName,
    metadata: { format: "Plain text", parser: "built-in txt adapter" },
    sections: [section]
  });
}
