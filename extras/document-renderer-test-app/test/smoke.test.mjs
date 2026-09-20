import assert from "node:assert/strict";
import { parseTxtString } from "../src/adapters/txt.js";
import { tokenizeForDemo, findAlignedRange } from "../src/align.js";
import { getDocumentStats, sectionToHtml } from "../src/canonical.js";

const input = `        CENTERED TITLE\n\nCHAPTER I\n\n  This paragraph has indentation. It should preserve text and offsets.\n\nSecond paragraph with difficult-language tokens: θεός, राजा, 漢字.`;
const doc = parseTxtString(input, { title: "Smoke" });
const stats = getDocumentStats(doc);
assert.equal(doc.sourceType, "txt");
assert.equal(stats.sections, 1);
assert.ok(stats.blocks >= 3);
assert.ok(doc.canonicalText.includes("CENTERED TITLE"));
assert.ok(doc.canonicalText.includes("θεός"));

for (const section of doc.sections) {
  for (const block of section.blocks) {
    assert.ok(block.canonicalStart >= 0);
    assert.ok(block.canonicalEnd >= block.canonicalStart);
    assert.equal(doc.canonicalText.slice(block.canonicalStart, block.canonicalEnd), block.text);
  }
}

const tokens = tokenizeForDemo(doc.canonicalText);
assert.ok(tokens.find(t => t.text === "θεός"));
assert.ok(tokens.find(t => t.text === "राजा"));
assert.ok(tokens.find(t => t.text === "漢字"));

const html = sectionToHtml(doc.sections[0]);
assert.ok(html.includes("data-canonical-start"));
assert.ok(html.includes("CENTERED TITLE"));

const range = findAlignedRange("paragraph has indentation", doc.canonicalText, 0);
assert.ok(range.score > 0);

console.log("Smoke tests passed:", { stats, tokenCount: tokens.length });

import { normalizePdfTextItems } from "../src/adapters/pdf.js";
const pdfItems = normalizePdfTextItems([
  { type: "beginMarkedContent", id: "bad" },
  { str: "Hello", transform: [10, 0, 0, 10, 20, 700], width: 25, height: 10 },
  { str: "broken", transform: undefined },
  { str: "World", transform: [10, 0, 0, 10, 52, 700], width: 28, height: 10 }
]);
assert.equal(pdfItems.length, 2);
assert.equal(pdfItems[0].str, "Hello");
assert.equal(pdfItems[1].x, 52);
