import { escapeHtml } from "./canonical.js";

export function annotatePlainTextWithTokens(text, baseOffset, tokens) {
  const local = tokens
    .filter(t => t.canonicalEnd > baseOffset && t.canonicalStart < baseOffset + text.length)
    .sort((a, b) => a.canonicalStart - b.canonicalStart);
  let out = "";
  let cursor = 0;
  for (const token of local) {
    const start = Math.max(0, token.canonicalStart - baseOffset);
    const end = Math.min(text.length, token.canonicalEnd - baseOffset);
    if (start < cursor || end <= start) continue;
    out += escapeHtml(text.slice(cursor, start));
    out += `<span class="reader-token" data-token-id="${escapeHtml(token.id)}" data-start="${token.canonicalStart}" data-end="${token.canonicalEnd}" title="${escapeHtml(token.dictionaryEntries?.[0]?.gloss || token.lemma || token.text)}">${escapeHtml(text.slice(start, end))}</span>`;
    cursor = end;
  }
  out += escapeHtml(text.slice(cursor));
  return out;
}

export function tokensForRange(tokens, start, end) {
  return tokens.filter(t => t.canonicalEnd > start && t.canonicalStart < end);
}
