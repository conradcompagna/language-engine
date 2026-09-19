/**
 * normalize_keys.js — Node.js shim for dictionary_normalization_layer.js.
 *
 * Loads the browser normalization layer by shimming `window`, then reads
 * newline-delimited JSON from stdin and writes normalized keys to stdout.
 *
 * Input lines:  {"text": "...", "lang": "..."}
 * Output lines: {"text": "...", "lang": "...", "key": "..."}
 *
 * Called by dict_lookup_sqlite.py and convert_tsv_to_sqlite.py as a subprocess.
 */

"use strict";

const path = require("path");

// Shim window so the browser IIFE can assign to window.DictionaryNormalizationLayer
global.window = {};
require(path.join(__dirname, "../static/dictionary_normalization_layer.js"));
const layer = global.window.DictionaryNormalizationLayer;

if (!layer || typeof layer.normalizeLookupKeyText !== "function") {
  process.stderr.write("normalize_keys.js: failed to load DictionaryNormalizationLayer\n");
  process.exit(1);
}

let buf = "";

process.stdin.setEncoding("utf8");

process.stdin.on("data", function(chunk) {
  buf += chunk;
  const lines = buf.split("\n");
  buf = lines.pop(); // keep incomplete last line
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      const obj = JSON.parse(line);
      const text = String(obj.text || "");
      const lang = String(obj.lang || "");
      const key = layer.normalizeLookupKeyText(text, { langCode: lang });
      process.stdout.write(JSON.stringify({ text: text, lang: lang, key: String(key || "") }) + "\n");
    } catch (e) {
      try {
        const obj = JSON.parse(line);
        process.stdout.write(JSON.stringify({ text: String(obj.text || ""), lang: String(obj.lang || ""), key: "", error: String(e) }) + "\n");
      } catch (_) {
        process.stdout.write(JSON.stringify({ text: "", lang: "", key: "", error: String(e) }) + "\n");
      }
    }
  }
});

process.stdin.on("end", function() {
  if (buf.trim()) {
    try {
      const obj = JSON.parse(buf.trim());
      const text = String(obj.text || "");
      const lang = String(obj.lang || "");
      const key = layer.normalizeLookupKeyText(text, { langCode: lang });
      process.stdout.write(JSON.stringify({ text: text, lang: lang, key: String(key || "") }) + "\n");
    } catch (e) {
      process.stdout.write(JSON.stringify({ text: "", lang: "", key: "", error: String(e) }) + "\n");
    }
  }
});
