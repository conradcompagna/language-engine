import { buildEngineDebugEntryRefs } from './entry-filters.mjs';
import { DictionaryEngine } from './model.mjs';
import {
  buildGraphemeSpanTable,
  getLemmaHintTexts,
  isKoreanLanguageCode,
  lookupKey,
  lookupKeys
} from './normalization.mjs';
export function normalizePreferredPosList(rawList) {
  var src = Array.isArray(rawList) ? rawList : rawList ? [rawList] : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < src.length; i++) {
    var pos = String(src[i] || '')
      .trim()
      .toLowerCase();
    if (!pos || seen[pos]) continue;
    seen[pos] = true;
    out.push(pos);
  }
  return out;
}
export function selectEntriesByPreferredPosRaw(entries, preferredPosRaws) {
  var src = Array.isArray(entries) ? entries.slice() : [];
  var preferred = normalizePreferredPosList(preferredPosRaws);
  if (!preferred.length || !src.length) {
    return {
      primary: src,
      other: [],
      matched_pos_raw: ''
    };
  }
  for (var pi = 0; pi < preferred.length; pi++) {
    var wanted = preferred[pi];
    var primary = [];
    var other = [];
    for (var ei = 0; ei < src.length; ei++) {
      var entry = src[ei] || {};
      var posRaw = String(entry.pos_raw || entry.pos || '')
        .trim()
        .toLowerCase();
      if (posRaw === wanted) primary.push(entry);
      else other.push(entry);
    }
    if (primary.length) {
      return {
        primary: primary,
        other: other,
        matched_pos_raw: wanted
      };
    }
  }
  return {
    primary: [],
    other: src,
    matched_pos_raw: ''
  };
}
export function initializeSelection() {
  DictionaryEngine.prototype._greedy_fill_simple = function (
    word,
    excludeWhole,
    boundaries,
    _koreanGroups,
    debug,
    lemmaHints
  ) {
    if (!word) {
      return {
        mode: 'greedy',
        fills: [],
        has_known: false,
        has_unknown: false
      };
    }
    var engineLang = String(this._lang_code || '')
      .trim()
      .toLowerCase();
    var hintList = Array.isArray(lemmaHints) ? lemmaHints : [];
    var self = this;
    function dedupeExactEntryObjects(entries) {
      var src = Array.isArray(entries) ? entries : [];
      if (src.length <= 1) return src.slice();
      var dedupTag = '_exact_' + Math.random().toString(36).slice(2, 8);
      var seenCompact = Object.create(null);
      var tagged = [];
      var out = [];
      for (var i = 0; i < src.length; i++) {
        var entry = src[i];
        if (!entry || typeof entry !== 'object') continue;
        if (entry._winner_ref) {
          var compactKey =
            String(entry.storage_kind || 'sqlite')
              .trim()
              .toLowerCase() +
            '|' +
            String(entry.db_alias || '').trim() +
            '|' +
            (parseInt(entry.entry_row_id, 10) || 0) +
            '|' +
            (parseInt(entry.form_row_id, 10) || 0);
          if (seenCompact[compactKey]) continue;
          seenCompact[compactKey] = true;
          out.push(entry);
          continue;
        }
        if (entry[dedupTag]) continue;
        entry[dedupTag] = true;
        tagged.push(entry);
        out.push(entry);
      }
      for (var ti = 0; ti < tagged.length; ti++) {
        delete tagged[ti][dedupTag];
      }
      return out;
    }
    function collectWholeTokenLemmaExactEntries() {
      if (!hintList.length) return [];
      if (isKoreanLanguageCode(engineLang) && hintList.length > 1) return [];
      if (hintList.length !== 1) return [];
      var out = [];
      var wordKey = lookupKey(word, engineLang);
      var hintTexts = getLemmaHintTexts(hintList[0], engineLang);
      for (var hi = 0; hi < hintTexts.length; hi++) {
        var hintText = hintTexts[hi];
        if (!hintText) continue;
        var hintKeys = lookupKeys(hintText, engineLang);
        for (var hki = 0; hki < hintKeys.length; hki++) {
          var hintKey = String(hintKeys[hki] || '').trim();
          if (!hintKey || hintKey === wordKey) continue;
          if (self._compact_mode && self._hw_index) {
            var hwHits = self._hw_index[hintKey] || [];
            for (var hwi = 0; hwi < hwHits.length; hwi++) {
              var alias = hwHits[hwi][0];
              var eid = hwHits[hwi][1];
              out.push({
                _winner_ref: true,
                storage_kind:
                  self._db_alias_map[alias] === 'custom' || alias === 'customdb' ? 'custom' : 'sqlite',
                db_alias: alias,
                entry_row_id: eid,
                match_kind: 'headword',
                match_key: hintKey,
                headword: hintText
              });
            }
            continue;
          }
          var hintEntries = self._by_word[hintKey] || [];
          for (var ei = 0; ei < hintEntries.length; ei++) out.push(hintEntries[ei]);
        }
      }
      return dedupeExactEntryObjects(out);
    }

    // If the whole surface has an exact dictionary match and we're not
    // excluding whole-surface results, accept it immediately — no DP needed.
    // If lemma hints exist, check whether any hint matches and flag accordingly.
    if (!excludeWhole) {
      var exactEntries = dedupeExactEntryObjects(
        (this.lookup_all(word) || []).concat(collectWholeTokenLemmaExactEntries())
      );
      if (exactEntries.length) {
        var exactFill = this._entry_to_fill(exactEntries[0], word);
        exactFill.entries = exactEntries;
        var promotedLemma = null;
        var promotedMeta = null;
        for (var ehi = 0; ehi < hintList.length; ehi++) {
          var ehRaw = hintList[ehi];
          var hintTexts = getLemmaHintTexts(ehRaw, engineLang);
          for (var ehti = 0; ehti < hintTexts.length; ehti++) {
            var ehText = hintTexts[ehti];
            if (!ehText) continue;
            var ehKey = lookupKey(ehText, engineLang);
            if (ehKey === lookupKey(word, engineLang)) {
              promotedLemma = ehText;
              promotedMeta =
                ehRaw && typeof ehRaw === 'object'
                  ? {
                      upos: String(ehRaw.upos || ''),
                      xpos: String(ehRaw.xpos || '')
                    }
                  : null;
              break;
            }
            for (var eei = 0; eei < exactEntries.length; eei++) {
              var ehw = lookupKey(exactEntries[eei].headword || '', engineLang);
              if (ehw && ehw === ehKey) {
                promotedLemma = ehText;
                promotedMeta =
                  ehRaw && typeof ehRaw === 'object'
                    ? {
                        upos: String(ehRaw.upos || ''),
                        xpos: String(ehRaw.xpos || '')
                      }
                    : null;
                break;
              }
            }
            if (promotedLemma) break;
          }
          if (promotedLemma) break;
        }
        if (promotedLemma) {
          exactFill._lemma_promoted = promotedLemma;
          exactFill._lemma_promoted_headword = String(exactEntries[0].headword || '');
          var ehMeta = promotedMeta;
          if (ehMeta && ehMeta.upos) exactFill._lemma_upos_hint = ehMeta.upos;
          if (ehMeta && ehMeta.xpos) exactFill._lemma_xpos_hint = ehMeta.xpos;
        }
        return {
          mode: 'greedy',
          fills: [exactFill],
          has_known: true,
          has_unknown: false,
          has_lemma_promotion: !!promotedLemma
        };
      }
    }

    // Global segmentation:
    // 1) If lemma hints are provided, candidates whose entries match a lemma
    //    hint get an unconditional promotion (hard override — they always win).
    // 2) Among non-promoted candidates: minimize unknown characters,
    //    then minimize total pieces, then maximize the longest span anywhere
    //    in the chosen path.
    var graphemeTable = buildGraphemeSpanTable(word);
    var graphemeSpans = graphemeTable.spans;
    var boundaryIndexByOffset = graphemeTable.boundary_to_index;
    var n = graphemeSpans.length;
    var wordCodeUnitLength = word.length;
    var inf = 1e9;
    var prefixStateCount = 1;
    var dpUnknown = new Array(prefixStateCount);
    var dpPieces = new Array(prefixStateCount);
    var dpPromoted = new Array(prefixStateCount);
    var dpMaxSpan = new Array(prefixStateCount);
    var dpUsedLemmaKeys = new Array(prefixStateCount);
    var choice = new Array(prefixStateCount);
    for (var ps = 0; ps < prefixStateCount; ps++) {
      dpUnknown[ps] = new Array(n + 1);
      dpPieces[ps] = new Array(n + 1);
      dpPromoted[ps] = new Array(n + 1);
      dpMaxSpan[ps] = new Array(n + 1);
      dpUsedLemmaKeys[ps] = new Array(n + 1);
      choice[ps] = new Array(n + 1);
    }
    var cache = Object.create(null);
    var boundarySet = null;
    var boundaryList = null;
    var traceEnabled = !!debug;
    var traceSteps = traceEnabled ? new Array(n) : null;
    function graphemeBoundaryOffset(index) {
      var idx = parseInt(index, 10);
      if (!isFinite(idx) || idx <= 0) return 0;
      if (idx >= n) return wordCodeUnitLength;
      return graphemeSpans[idx].start;
    }
    function sliceByGraphemeRange(start, end) {
      if (start < 0 || end <= start || end > n) return '';
      return word.slice(graphemeBoundaryOffset(start), graphemeBoundaryOffset(end));
    }

    // --- Lemma promotion setup ---
    // For each lemma hint, find the original entry objects it resolves to
    // (via direct headword lookup AND form index), and tag those original
    // objects. A candidate is promoted only if the actual object in the DP
    // was tagged — entries in different forms buckets that happen to share
    // headwords or identity keys are never cross-contaminated.
    var lemmaHintList = hintList;
    var lemmaHintMeta = Object.create(null);
    var lemmaHintLabels = Object.create(null);
    var hasLemmaPromotion = false;
    var lpTag = '_lp_' + Math.random().toString(36).slice(2, 10);
    var lpTaggedObjects = [];
    function tagPromotedObject(entry, lemmaKey) {
      if (!entry || !lemmaKey) return;
      var tags = entry[lpTag];
      if (!tags) {
        entry[lpTag] = [lemmaKey];
        lpTaggedObjects.push(entry);
        return;
      }
      for (var ti = 0; ti < tags.length; ti++) {
        if (tags[ti] === lemmaKey) return;
      }
      tags.push(lemmaKey);
    }
    for (var lhi = 0; lhi < lemmaHintList.length; lhi++) {
      var rawHint = lemmaHintList[lhi];
      var hint, hintUpos, hintXpos;
      if (rawHint && typeof rawHint === 'object' && !Array.isArray(rawHint)) {
        hint = String(rawHint.text || '').trim();
        hintUpos = String(rawHint.upos || '').trim();
        hintXpos = String(rawHint.xpos || '').trim();
      } else {
        hint = String(rawHint || '').trim();
        hintUpos = '';
        hintXpos = '';
      }
      if (!hint) continue;
      var hintTexts = getLemmaHintTexts(rawHint, engineLang);
      if (!hintTexts.length) continue;
      var lemmaKey = lookupKey(hint, engineLang) || lookupKey(hintTexts[0], engineLang) || hintTexts[0];
      if (!lemmaKey) continue;
      hasLemmaPromotion = true;
      if (!lemmaHintLabels[lemmaKey]) lemmaHintLabels[lemmaKey] = hint;
      if (hintUpos || hintXpos) {
        if (!lemmaHintMeta[lemmaKey]) {
          lemmaHintMeta[lemmaKey] = {
            upos: hintUpos,
            xpos: hintXpos
          };
        } else {
          if (hintUpos && !lemmaHintMeta[lemmaKey].upos) lemmaHintMeta[lemmaKey].upos = hintUpos;
          if (hintXpos && !lemmaHintMeta[lemmaKey].xpos) lemmaHintMeta[lemmaKey].xpos = hintXpos;
        }
      }
      for (var hti = 0; hti < hintTexts.length; hti++) {
        var hintText = hintTexts[hti];
        if (!hintText) continue;
        // Tag original entry objects reachable via direct headword lookup
        var hintKey = lookupKey(hintText, engineLang);
        var directBucket = hintKey ? this._by_word[hintKey] || [] : [];
        for (var dbi = 0; dbi < directBucket.length; dbi++) {
          tagPromotedObject(directBucket[dbi], lemmaKey);
        }
        // Tag original entry objects reachable via forms index
        var formHits = hintKey ? this._form_index[hintKey] || [] : [];
        for (var fhi = 0; fhi < formHits.length; fhi++) {
          if (formHits[fhi].entry_ref) {
            tagPromotedObject(formHits[fhi].entry_ref, lemmaKey);
          }
        }
      }
    }
    function getLemmaHintMeta(lemmaKey) {
      if (!lemmaKey) return null;
      return lemmaHintMeta[lemmaKey] || null;
    }
    function getPromotedLemmaKeys(entry) {
      if (!hasLemmaPromotion) return null;
      var hintVals = entry[lpTag];
      if (!hintVals || !hintVals.length) return null;
      return hintVals;
    }
    function cleanupLpTags() {
      for (var ci = 0; ci < lpTaggedObjects.length; ci++) {
        delete lpTaggedObjects[ci][lpTag];
      }
    }
    function filterEntriesForLemmaReuse(entries, usedLemmaKeys) {
      if (!entries || !entries.length) return [];
      if (!usedLemmaKeys) return entries.slice();
      var out = [];
      for (var ei = 0; ei < entries.length; ei++) {
        var entry = entries[ei];
        var lemmaKeys = getPromotedLemmaKeys(entry);
        if (!lemmaKeys || !lemmaKeys.length) {
          out.push(entry);
          continue;
        }
        for (var li = 0; li < lemmaKeys.length; li++) {
          if (!usedLemmaKeys[lemmaKeys[li]]) {
            out.push(entry);
            break;
          }
        }
      }
      return out;
    }
    function checkCandidatesForPromotion(entries, usedLemmaKeys) {
      if (!hasLemmaPromotion || !entries || !entries.length) return null;
      for (var ci = 0; ci < entries.length; ci++) {
        var matches = getPromotedLemmaKeys(entries[ci]);
        if (!matches || !matches.length) continue;
        for (var mi = 0; mi < matches.length; mi++) {
          var match = matches[mi];
          if (usedLemmaKeys && usedLemmaKeys[match]) continue;
          var meta = getLemmaHintMeta(match);
          return {
            index: ci,
            lemma: lemmaHintLabels[match] || match,
            lemma_key: match,
            entry: entries[ci],
            upos: meta ? meta.upos : '',
            xpos: meta ? meta.xpos : ''
          };
        }
      }
      return null;
    }
    function buildBoundaryData(rawBoundaries, forceWholeToken) {
      var src = Array.isArray(rawBoundaries) ? rawBoundaries : null;
      if (!src) return null;
      if (!src.length && !forceWholeToken) return null;
      var seen = Object.create(null);
      var list = [0, n];
      for (var bi = 0; bi < src.length; bi++) {
        var offset = parseInt(src[bi], 10);
        if (!isFinite(offset) || offset <= 0 || offset >= wordCodeUnitLength) continue;
        var boundaryIndex = boundaryIndexByOffset[offset];
        if (!isFinite(boundaryIndex) || boundaryIndex <= 0 || boundaryIndex >= n) continue;
        list.push(boundaryIndex);
      }
      list.sort(function (a, b) {
        return a - b;
      });
      var unique = [];
      for (var ui = 0; ui < list.length; ui++) {
        var value = list[ui];
        if (seen[value]) continue;
        seen[value] = true;
        unique.push(value);
      }
      if (unique.length < 2) return null;
      var set = Object.create(null);
      for (var si = 0; si < unique.length; si++) {
        set[unique[si]] = true;
      }
      return {
        list: unique,
        set: set
      };
    }

    // Auto-inject whitespace positions as boundaries so the DP cannot
    // fragment words across spaces.  A span that fully covers whole words
    // (start AND end both on boundaries) is still allowed — this handles
    // Vietnamese multi-syllable tokens like "hôm nay" where the dictionary
    // entry itself contains the space.
    var spaceBoundaries = [];
    for (var si = 0; si < n; si++) {
      var spaceSpan = graphemeSpans[si];
      if (!spaceSpan) continue;
      if (spaceSpan.text === ' ' || spaceSpan.text === '\t') {
        spaceBoundaries.push(spaceSpan.start);
        spaceBoundaries.push(spaceSpan.end);
      }
    }
    var mergedBoundaries = Array.isArray(boundaries) ? boundaries.slice() : [];
    for (var sbi = 0; sbi < spaceBoundaries.length; sbi++) {
      mergedBoundaries.push(spaceBoundaries[sbi]);
    }
    var boundaryData = buildBoundaryData(mergedBoundaries.length ? mergedBoundaries : null, false);
    if (boundaryData) {
      boundaryList = boundaryData.list;
      boundarySet = boundaryData.set;
    }
    function buildDpDebugPayload() {
      if (!traceEnabled) return null;
      var steps = [];
      for (var si = 0; si < (traceSteps || []).length; si++) {
        if (traceSteps[si]) steps.push(traceSteps[si]);
      }
      var boundaryOffsets = [];
      if (boundaryList) {
        for (var bi = 0; bi < boundaryList.length; bi++) {
          boundaryOffsets.push(graphemeBoundaryOffset(boundaryList[bi]));
        }
      }
      return {
        word: word,
        exclude_whole: !!excludeWhole,
        boundaries: boundaryOffsets,
        steps: steps
      };
    }
    for (var psInit = 0; psInit < prefixStateCount; psInit++) {
      for (var di = 0; di <= n; di++) {
        dpUnknown[psInit][di] = inf;
        dpPieces[psInit][di] = inf;
        dpPromoted[psInit][di] = 0;
        dpMaxSpan[psInit][di] = 0;
        dpUsedLemmaKeys[psInit][di] = null;
      }
      dpUnknown[psInit][n] = 0;
      dpPieces[psInit][n] = 0;
      dpPromoted[psInit][n] = 0;
      dpMaxSpan[psInit][n] = 0;
      dpUsedLemmaKeys[psInit][n] = null;
      choice[psInit][n] = null;
    }

    // Scoring: current promoted span > non-promoted span; when both current
    // spans are promoted, prefer the longer current span. Then prefer fewer
    // unknowns, fewer pieces, the largest span anywhere in the path, and
    // finally the longer current span as a deterministic last tie-break.
    function isBetter(
      cPromotedHere,
      cPromoted,
      cUnknown,
      cPieces,
      cMaxSpan,
      cSpanLen,
      bPromotedHere,
      bPromoted,
      bUnknown,
      bPieces,
      bMaxSpan,
      bSpanLen
    ) {
      if (!!cPromotedHere !== !!bPromotedHere) return !!cPromotedHere;
      if (cPromotedHere && bPromotedHere && cSpanLen !== bSpanLen) return cSpanLen > bSpanLen;
      if (cUnknown !== bUnknown) return cUnknown < bUnknown;
      if (cPromoted !== bPromoted) return cPromoted > bPromoted;
      if (cPieces !== bPieces) return cPieces < bPieces;
      if (cMaxSpan !== bMaxSpan) return cMaxSpan > bMaxSpan;
      return cSpanLen > bSpanLen;
    }
    function crossesRestrictedBoundary(start, end) {
      if (!boundaryList || boundaryList.length <= 2) return false;
      if (start >= end) return false;
      if (boundarySet[start] && boundarySet[end]) return false;
      for (var bi = 0; bi < boundaryList.length; bi++) {
        var b = boundaryList[bi];
        if (b <= start) continue;
        if (b >= end) break;
        return true;
      }
      return false;
      // Disallow partial cross-boundary spans (e.g., 위+시).
    }
    function evaluateCandidate(self, start, end, prefixStage, bestState, stepTrace) {
      var piece = sliceByGraphemeRange(start, end);
      if (!piece) return bestState;
      if (excludeWhole && wordCodeUnitLength > 1 && start === 0 && end === n) return bestState;
      var startOffset = graphemeBoundaryOffset(start);
      var endOffset = graphemeBoundaryOffset(end);
      if (crossesRestrictedBoundary(start, end)) {
        if (stepTrace) {
          stepTrace.rejected.push({
            kind: 'known',
            start: startOffset,
            end: endOffset,
            piece: piece,
            reason: 'crosses_lemma_boundary',
            detail: 'boundary_cross'
          });
        }
        return bestState;
      }
      var cacheKey = piece;
      var cached = cache[cacheKey];
      if (cached === undefined) {
        var candidateEntries = self._filter_entries_for_greedy(self.lookup_all(piece));
        cached = {
          entries: candidateEntries,
          xpos_hint: '',
          candidate_refs: traceEnabled ? buildEngineDebugEntryRefs(candidateEntries, 8) : [],
          rejected_pos_detail: null
        };
        cache[cacheKey] = cached;
      }
      if (!cached.entries || !cached.entries.length) return bestState;
      if (dpUnknown[0][end] >= inf) return bestState;
      var usedLemmaKeys = dpUsedLemmaKeys[0][end];
      var availableEntries = filterEntriesForLemmaReuse(cached.entries, usedLemmaKeys);
      if (!availableEntries.length) {
        if (stepTrace) {
          stepTrace.rejected.push({
            kind: 'known',
            start: startOffset,
            end: endOffset,
            piece: piece,
            reason: 'lemma_already_consumed',
            lemma_keys: Object.keys(usedLemmaKeys || {}),
            entry_refs: traceEnabled ? buildEngineDebugEntryRefs(cached.entries, 8) : []
          });
        }
        return bestState;
      }
      var cUnknown = dpUnknown[0][end];
      var cPieces = 1 + dpPieces[0][end];
      var spanLen = end - start;
      var cMaxSpan = Math.max(spanLen, dpMaxSpan[0][end] || 0);

      // --- Lemma promotion check ---
      var promotion = checkCandidatesForPromotion(availableEntries, usedLemmaKeys);
      var promotedHere = promotion ? 1 : 0;
      var cPromoted = dpPromoted[0][end] + promotedHere;
      var nextUsedLemmaKeys = usedLemmaKeys;
      if (promotion && promotion.lemma_key) {
        nextUsedLemmaKeys = Object.assign({}, usedLemmaKeys || {});
        nextUsedLemmaKeys[promotion.lemma_key] = true;
      }
      var acceptedTrace = null;
      if (stepTrace) {
        acceptedTrace = {
          kind: 'known',
          start: startOffset,
          end: endOffset,
          piece: piece,
          xpos_tags: [],
          entry_count: availableEntries.length,
          entry_refs: traceEnabled ? buildEngineDebugEntryRefs(availableEntries, 8) : [],
          score_promoted_here: promotedHere,
          score_unknown: cUnknown,
          score_pieces: cPieces,
          score_max_span: cMaxSpan,
          score_promoted: cPromoted,
          lemma_promoted: promotion ? promotion.lemma : null,
          lemma_promoted_headword: promotion ? String(promotion.entry.headword || '') : null,
          lemma_promoted_upos: promotion ? promotion.upos || '' : null,
          lemma_promoted_xpos: promotion ? promotion.xpos || '' : null
        };
        stepTrace.accepted.push(acceptedTrace);
      }
      if (
        isBetter(
          promotedHere,
          cPromoted,
          cUnknown,
          cPieces,
          cMaxSpan,
          spanLen,
          bestState.promoted_here,
          bestState.promoted,
          bestState.unknown,
          bestState.pieces,
          bestState.max_span_len,
          bestState.span_len
        )
      ) {
        bestState.promoted_here = promotedHere;
        bestState.promoted = cPromoted;
        bestState.unknown = cUnknown;
        bestState.pieces = cPieces;
        bestState.max_span_len = cMaxSpan;
        bestState.end = end;
        bestState.entries = availableEntries;
        bestState.kind = 'known';
        bestState.span_len = spanLen;
        bestState.xpos_hint = cached.xpos_hint || '';
        bestState.trace = acceptedTrace;
        bestState.lemma_promotion = promotion;
        bestState.used_lemma_keys = nextUsedLemmaKeys;
      }
      return bestState;
    }
    for (var i = n - 1; i >= 0; i--) {
      for (var prefixStage = 0; prefixStage < prefixStateCount; prefixStage++) {
        var bestState = {
          promoted_here: 0,
          promoted: 0,
          unknown: inf,
          pieces: inf,
          max_span_len: 0,
          end: -1,
          entries: null,
          kind: '',
          span_len: 0,
          xpos_hint: '',
          trace: null,
          lemma_promotion: null,
          used_lemma_keys: null
        };
        var stepTrace =
          traceEnabled && prefixStage === 0
            ? {
                index: graphemeBoundaryOffset(i),
                accepted: [],
                rejected: [],
                unknown_fallback: null,
                selected: null
              }
            : null;
        for (var end2 = i + 1; end2 <= n; end2++) {
          bestState = evaluateCandidate(this, i, end2, prefixStage, bestState, stepTrace);
        }
        var unknownEnd = i + 1;
        if (unknownEnd > i && unknownEnd <= n && dpUnknown[0][unknownEnd] < inf) {
          var unknownSpan = unknownEnd - i;
          var uUnknown = unknownSpan + dpUnknown[0][unknownEnd];
          var uPieces = 1 + dpPieces[0][unknownEnd];
          var uPromoted = dpPromoted[0][unknownEnd];
          var uMaxSpan = Math.max(unknownSpan, dpMaxSpan[0][unknownEnd] || 0);
          var unknownTrace = stepTrace
            ? {
                kind: 'unknown',
                start: graphemeBoundaryOffset(i),
                end: graphemeBoundaryOffset(unknownEnd),
                piece: sliceByGraphemeRange(i, unknownEnd),
                score_promoted_here: 0,
                score_unknown: uUnknown,
                score_pieces: uPieces,
                score_max_span: uMaxSpan,
                score_promoted: uPromoted
              }
            : null;
          if (stepTrace) stepTrace.unknown_fallback = unknownTrace;
          if (
            isBetter(
              0,
              uPromoted,
              uUnknown,
              uPieces,
              uMaxSpan,
              unknownSpan,
              bestState.promoted_here,
              bestState.promoted,
              bestState.unknown,
              bestState.pieces,
              bestState.max_span_len,
              bestState.span_len
            )
          ) {
            bestState.promoted_here = 0;
            bestState.promoted = uPromoted;
            bestState.unknown = uUnknown;
            bestState.pieces = uPieces;
            bestState.max_span_len = uMaxSpan;
            bestState.end = unknownEnd;
            bestState.entries = null;
            bestState.kind = 'unknown';
            bestState.span_len = unknownSpan;
            bestState.xpos_hint = '';
            bestState.trace = unknownTrace;
            bestState.lemma_promotion = null;
            bestState.used_lemma_keys = dpUsedLemmaKeys[0][unknownEnd];
          }
        }
        if (bestState.end >= 0 && bestState.kind) {
          dpUnknown[prefixStage][i] = bestState.unknown;
          dpPieces[prefixStage][i] = bestState.pieces;
          dpPromoted[prefixStage][i] = bestState.promoted;
          dpMaxSpan[prefixStage][i] = bestState.max_span_len;
          dpUsedLemmaKeys[prefixStage][i] = bestState.used_lemma_keys || null;
          choice[prefixStage][i] = {
            end: bestState.end,
            entries: bestState.entries,
            kind: bestState.kind,
            xpos_hint: bestState.xpos_hint,
            lemma_promotion: bestState.lemma_promotion || null
          };
          if (stepTrace) {
            var selectedTrace = {
              kind: bestState.kind,
              start: graphemeBoundaryOffset(i),
              end: graphemeBoundaryOffset(bestState.end),
              piece: sliceByGraphemeRange(i, bestState.end),
              score_promoted_here: bestState.promoted_here,
              score_unknown: bestState.unknown,
              score_pieces: bestState.pieces,
              score_max_span: bestState.max_span_len,
              score_promoted: bestState.promoted
            };
            if (bestState.kind === 'known') {
              selectedTrace.entry_refs =
                bestState.trace && Array.isArray(bestState.trace.entry_refs)
                  ? bestState.trace.entry_refs.slice()
                  : buildEngineDebugEntryRefs(bestState.entries, 8);
              selectedTrace.xpos_tags =
                bestState.trace && Array.isArray(bestState.trace.xpos_tags)
                  ? bestState.trace.xpos_tags.slice()
                  : [];
              selectedTrace.xpos_hint = bestState.xpos_hint || '';
              if (bestState.lemma_promotion) {
                selectedTrace.lemma_promoted = bestState.lemma_promotion.lemma;
                selectedTrace.lemma_promoted_headword = String(
                  bestState.lemma_promotion.entry.headword || ''
                );
              }
            }
            stepTrace.selected = selectedTrace;
            traceSteps[i] = stepTrace;
          }
        }
      }
    }
    var fills = [];
    var hasAnyPromotion = false;
    var idx = 0;
    while (idx < n) {
      var step = choice[0][idx];
      if (!step || step.end <= idx) {
        var fallbackEnd = idx + 1;
        var fallbackText = sliceByGraphemeRange(idx, fallbackEnd);
        if (!fallbackText) break;
        fills.push({
          text: fallbackText,
          head: fallbackText,
          roman: '',
          senses: [],
          pos: '',
          source: 'UNKNOWN'
        });
        idx = fallbackEnd;
        continue;
      }
      var segText = sliceByGraphemeRange(idx, step.end);
      if (step.kind === 'known' && step.entries && step.entries.length) {
        var fill = this._entry_to_fill(step.entries[0], segText);
        fill.entries = step.entries;
        if (step.xpos_hint) fill._xpos_hint = step.xpos_hint;
        if (step.lemma_promotion) {
          hasAnyPromotion = true;
          fill._lemma_promoted = step.lemma_promotion.lemma;
          fill._lemma_promoted_headword = String(step.lemma_promotion.entry.headword || '');
          fill._lemma_promoted_pos = String(step.lemma_promotion.entry.pos_raw || '');
          if (step.lemma_promotion.upos) fill._lemma_upos_hint = String(step.lemma_promotion.upos);
          if (step.lemma_promotion.xpos) fill._lemma_xpos_hint = String(step.lemma_promotion.xpos);
        }
        fills.push(fill);
      } else {
        fills.push({
          text: segText,
          head: segText,
          roman: '',
          senses: [],
          pos: '',
          source: 'UNKNOWN'
        });
      }
      idx = step.end;
    }
    var hasKnown = false;
    var hasUnknown = false;
    for (var mi = 0; mi < fills.length; mi++) {
      if ((fills[mi] || {}).source === 'UNKNOWN') hasUnknown = true;
      else hasKnown = true;
    }
    var result = {
      mode: 'greedy',
      fills: fills,
      has_known: hasKnown,
      has_unknown: hasUnknown,
      has_lemma_promotion: hasAnyPromotion
    };
    if (hasLemmaPromotion) result.lemma_hints = lemmaHintList.slice();
    var dpDebug = buildDpDebugPayload();
    if (dpDebug) result.dp_debug = dpDebug;
    cleanupLpTags();
    return result;
  };
  return true;
}
