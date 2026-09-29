/* canonical_annotator.js
 *
 * Merges backend /lookup payloads into CanonicalPage.tokens.
 * It replaces old DOM offset decoration with pure model enrichment.
 *
 * Browser global:
 *   window.CanonicalAnnotator
 */
(function(global) {
  'use strict';

  function requireDeps() {
    if (!global.CanonicalModel) throw new Error('CanonicalModel must be loaded before CanonicalAnnotator');
  }

  function str(v) { return v == null ? '' : String(v); }
  function num(v, fallback) { var n = Number(v); return isFinite(n) ? n : (fallback || 0); }

  function normalizeOffset(raw, fallbackStart, fallbackText) {
    if (raw && typeof raw === 'object') {
      var s = num(raw.start != null ? raw.start : raw[0], fallbackStart);
      var e = num(raw.end != null ? raw.end : raw[1], s + str(fallbackText).length);
      return { start: s, end: Math.max(s, e) };
    }
    return { start: fallbackStart, end: fallbackStart + str(fallbackText).length };
  }

  function findUdForToken(payload, idx, segText) {
    var ud = payload && payload.ud_overlay;
    if (!ud) return null;
    if (Array.isArray(ud.tokens) && ud.tokens[idx]) return ud.tokens[idx];
    if (Array.isArray(ud.nodes) && ud.nodes[idx]) return ud.nodes[idx];
    if (Array.isArray(ud.words) && ud.words[idx]) return ud.words[idx];
    if (ud.token_map && ud.token_map[idx]) return ud.token_map[idx];
    if (ud.by_index && ud.by_index[idx]) return ud.by_index[idx];
    if (segText && ud.by_text && ud.by_text[segText]) return ud.by_text[segText];
    return null;
  }

  function findNerForToken(payload, idx, start, end) {
    var ner = payload && (payload.ner_overlay || payload.ner);
    if (!ner) return null;
    if (Array.isArray(ner.tokens) && ner.tokens[idx]) return ner.tokens[idx];
    var ents = Array.isArray(ner.entities) ? ner.entities : (Array.isArray(ner) ? ner : []);
    var hits = [];
    for (var i = 0; i < ents.length; i++) {
      var e = ents[i] || {};
      var s = num(e.start != null ? e.start : e.char_start, -1);
      var n = num(e.end != null ? e.end : e.char_end, -1);
      if (s < end && n > start) hits.push(e);
    }
    return hits.length ? hits : null;
  }

  function extractLemma(result, grammar, ud) {
    return str(
      (result && (result.lemma || result.lemma_form || result.morph_base)) ||
      (grammar && (grammar.lemma || grammar.lemma_form)) ||
      (ud && (ud.lemma || ud.lemma_form)) ||
      ''
    );
  }

  function extractPosField(name, result, grammar, ud) {
    return str(
      (grammar && grammar[name]) ||
      (ud && ud[name]) ||
      (result && result[name]) ||
      ''
    );
  }

  function dictEntriesForResult(result) {
    if (!result) return [];
    if (Array.isArray(result.entries)) return result.entries;
    if (Array.isArray(result.entry_groups)) return result.entry_groups;
    if (Array.isArray(result.atomic_entries_all)) return result.atomic_entries_all;
    if (Array.isArray(result.results)) return result.results;
    return result ? [result] : [];
  }

  function fillHitsForResult(result) {
    if (!result) return [];
    if (Array.isArray(result.dict_fill_surface_slices)) return result.dict_fill_surface_slices;
    if (Array.isArray(result.fillHits)) return result.fillHits;
    if (Array.isArray(result.dict_fill)) return result.dict_fill.map(function(entry, i) {
      return { fillIndex: i, entry: entry, start: null, end: null };
    });
    return [];
  }

  function annotatePage(page, payload, opts) {
    requireDeps();
    opts = opts || {};
    if (!page) throw new Error('annotatePage requires a CanonicalPage');
    payload = payload || {};
    var segments = Array.isArray(payload.segments) ? payload.segments : [];
    var offsets = Array.isArray(payload.segment_offsets) ? payload.segment_offsets : [];
    var results = Array.isArray(payload.results_by_seg) ? payload.results_by_seg : [];
    var grammarTokens = payload.grammar_overlay && Array.isArray(payload.grammar_overlay.tokens) ? payload.grammar_overlay.tokens : [];
    var tokens = [];
    var cursor = 0;
    for (var i = 0; i < segments.length; i++) {
      var segText = str(segments[i]);
      var off = normalizeOffset(offsets[i], cursor, segText);
      off.start = Math.max(0, Math.min(page.text.length, off.start));
      off.end = Math.max(off.start, Math.min(page.text.length, off.end));
      if (!offsets[i] && segText) {
        var found = page.text.indexOf(segText, cursor);
        if (found >= 0) off = { start: found, end: found + segText.length };
      }
      var surface = page.text.slice(off.start, off.end) || segText;
      cursor = off.end;
      var result = results[i] || null;
      var grammar = grammarTokens[i] || null;
      var ud = findUdForToken(payload, i, segText);
      var ner = findNerForToken(payload, i, off.start, off.end);
      tokens.push(global.CanonicalModel.makeToken({
        id: page.id + '-tok-' + i,
        index: i,
        start: off.start,
        end: off.end,
        text: surface,
        segment: segText || surface,
        lemma: extractLemma(result, grammar, ud),
        upos: extractPosField('upos', result, grammar, ud),
        xpos: extractPosField('xpos', result, grammar, ud),
        feats: (grammar && grammar.feats) || (ud && ud.feats) || (result && result.feats) || null,
        dep: (ud && (ud.dep || ud.deprel || ud.relation)) || null,
        ner: ner,
        dictEntry: result,
        dictEntries: dictEntriesForResult(result),
        fillHits: fillHitsForResult(result),
        grammar: grammar,
        ud: ud,
        raw: { result: result, grammar: grammar, ud: ud }
      }));
    }
    page.tokens = tokens;
    page.lookupPayload = opts.keepPayload === false ? null : payload;
    return page;
  }

  function buildFillsDict(page) {
    var out = {};
    var tokens = Array.isArray(page && page.tokens) ? page.tokens : [];
    tokens.forEach(function(tok) {
      var result = tok && tok.dictEntry;
      if (result && Array.isArray(result.dict_fill) && result.dict_fill.length) {
        out[tok.index] = result.dict_fill;
      }
    });
    return out;
  }

  global.CanonicalAnnotator = {
    annotatePage: annotatePage,
    buildFillsDict: buildFillsDict,
    dictEntriesForResult: dictEntriesForResult,
    fillHitsForResult: fillHitsForResult
  };
})(window);
