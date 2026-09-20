import { normalizeWhitespaceForAlignment } from "./canonical.js";

export function findAlignedRange(pageText, canonicalText, approximateStart = 0) {
  const needle = normalizeWhitespaceForAlignment(pageText);
  const haystack = normalizeWhitespaceForAlignment(canonicalText);
  if (!needle) return { start: approximateStart, end: approximateStart, score: 0 };
  const prefix = needle.slice(0, Math.min(240, needle.length));
  const idx = haystack.indexOf(prefix, Math.max(0, approximateStart - 1000));
  if (idx >= 0) return { start: idx, end: idx + needle.length, score: prefix.length };
  const loose = prefix.slice(0, Math.min(80, prefix.length));
  const looseIdx = haystack.indexOf(loose);
  return looseIdx >= 0
    ? { start: looseIdx, end: looseIdx + needle.length, score: loose.length }
    : { start: approximateStart, end: approximateStart + needle.length, score: 0 };
}

export function tokenizeForDemo(canonicalText) {
  const tokens = [];
  const re = /\p{L}[\p{L}\p{M}\p{N}'’\-]*|\p{N}+|[^\s]/gu;
  let m;
  let i = 0;
  while ((m = re.exec(canonicalText))) {
    tokens.push({
      id: `tok_${i++}`,
      text: m[0],
      canonicalStart: m.index,
      canonicalEnd: m.index + m[0].length,
      lemma: m[0].toLowerCase(),
      dictionaryEntries: [{ gloss: `demo gloss for “${m[0]}”` }]
    });
  }
  return tokens;
}
