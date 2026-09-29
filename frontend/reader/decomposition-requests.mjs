import { decompositionRequestsState } from './decomposition-requests.state.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getMwtPartSurfaceSliceText } from './entry-editing.mjs';
import {
  _surfaceHasGlossableChar,
  _tokenHasEligibleLlmDecompFeats,
  getRenderableLlmDecompRows,
  mergeLlmDecompEntries
} from './gloss-entries.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _assistantSliceMwtValue } from './lookup-progress.mjs';
import { _refreshLlmDecompUI } from './orthography.mjs';
export // -- LLM inflectional decomposition request helper --

function _buildLlmDecompCandidates(data) {
  var segments = data.segments || [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udOverlay = data.ud_overlay || {};
  var udTokens = udOverlay.tokens && Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  var udTokMap = {};
  for (var ui = 0; ui < udTokens.length; ui++) {
    if (udTokens[ui] && udTokens[ui].i != null) udTokMap[udTokens[ui].i] = udTokens[ui];
  }
  var candidates = [];
  function pushCandidate(segIdx, partIdx, surface, lemma, upos, xpos, feats) {
    var cleanSurface = String(surface || '').trim();
    var cleanFeats = String(feats || '').trim();
    if (
      !cleanSurface ||
      !_surfaceHasGlossableChar(cleanSurface) ||
      !_tokenHasEligibleLlmDecompFeats(cleanFeats)
    )
      return;
    candidates.push({
      candidateIdx: candidates.length,
      segIdx: segIdx,
      partIdx: isFinite(Number(partIdx)) ? Number(partIdx) : -1,
      surface: cleanSurface,
      lemma: String(lemma || '').trim(),
      upos: String(upos || '').trim(),
      xpos: String(xpos || '').trim(),
      feats: cleanFeats
    });
  }
  for (var ti = 0; ti < segments.length; ti++) {
    var segText = String(segments[ti] || '');
    var resultEntry = ti >= 0 && ti < resultsBySeg.length ? resultsBySeg[ti] || null : null;
    var udTok = udTokMap[ti] || null;
    var mwtParts =
      udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length > 1 ? udTok.mwt_parts : null;
    if (mwtParts) {
      for (var pi = 0; pi < mwtParts.length; pi++) {
        var part = mwtParts[pi] || {};
        var partSurface = getMwtPartSurfaceSliceText(
          segText,
          udTok,
          pi,
          String(part.text || part.form || '').trim()
        );
        if (!partSurface) partSurface = String(part.text || part.form || '').trim();
        pushCandidate(
          ti,
          pi,
          partSurface,
          String(
            part.lemma ||
              _assistantSliceMwtValue(
                (resultEntry && (resultEntry.lemma_raw || resultEntry.lemma)) ||
                  (udTok && (udTok.lemma_raw || udTok.lemma)) ||
                  '',
                pi
              ) ||
              ''
          ).trim(),
          String(
            part.upos ||
              _assistantSliceMwtValue((resultEntry && resultEntry.upos) || (udTok && udTok.upos) || '', pi) ||
              ''
          ).trim(),
          String(
            part.tag ||
              part.xpos ||
              _assistantSliceMwtValue(
                (resultEntry && (resultEntry.tag || resultEntry.xpos)) ||
                  (udTok && (udTok.tag || udTok.xpos)) ||
                  '',
                pi
              ) ||
              ''
          ).trim(),
          String(
            part.feats ||
              _assistantSliceMwtValue(
                (resultEntry && resultEntry.feats) || (udTok && udTok.feats) || '',
                pi
              ) ||
              ''
          ).trim()
        );
      }
      continue;
    }
    pushCandidate(
      ti,
      -1,
      segText,
      String(
        (udTok && (udTok.lemma_raw || udTok.lemma)) ||
          (resultEntry && (resultEntry.lemma_raw || resultEntry.lemma)) ||
          ''
      ).trim(),
      String((udTok && udTok.upos) || (resultEntry && resultEntry.upos) || '').trim(),
      String(
        (udTok && (udTok.tag || udTok.xpos)) || (resultEntry && (resultEntry.tag || resultEntry.xpos)) || ''
      ).trim(),
      String((udTok && udTok.feats) || (resultEntry && resultEntry.feats) || '').trim()
    );
  }
  return candidates;
}
export function _llmDecompTokenKey(lang, candidate) {
  try {
    return (
      lang +
      '\u0001' +
      JSON.stringify([
        String(candidate.surface || ''),
        String(candidate.lemma || ''),
        String(candidate.upos || ''),
        String(candidate.xpos || ''),
        String(candidate.feats || '')
      ])
    );
  } catch (e) {
    return null;
  }
}
export function _ingestLlmDecompCandidateResult(candidate, incoming) {
  if (!candidate || !hoverLayoutState.latestLlmDecomps) return;
  var segIdx = Number(candidate.segIdx);
  if (!isFinite(segIdx) || segIdx < 0 || segIdx >= hoverLayoutState.latestLlmDecomps.length) return;
  var decompText = '';
  if (typeof incoming === 'string') decompText = incoming;
  else if (incoming && typeof incoming === 'object')
    decompText = String(incoming.decomp || incoming.text || '');
  decompText = String(decompText || '').trim();
  if (!decompText) return;
  hoverLayoutState.latestLlmDecomps[segIdx] = mergeLlmDecompEntries(
    hoverLayoutState.latestLlmDecomps[segIdx],
    {
      rows: [
        {
          partIdx: candidate.partIdx,
          surface: candidate.surface,
          lemma: candidate.lemma,
          decomp: decompText
        }
      ]
    }
  );
}
export function _getLlmDecompRowForCandidate(candidate) {
  if (!candidate || !hoverLayoutState.latestLlmDecomps) return null;
  var segIdx = Number(candidate.segIdx);
  if (!isFinite(segIdx) || segIdx < 0 || segIdx >= hoverLayoutState.latestLlmDecomps.length) return null;
  var rows = getRenderableLlmDecompRows(hoverLayoutState.latestLlmDecomps[segIdx], {
    isMwtChild: isFinite(Number(candidate.partIdx)) && Number(candidate.partIdx) >= 0,
    partIndex: candidate.partIdx,
    childLemma: candidate.lemma
  });
  return rows.length ? rows[0] : null;
}
export // Sentence-scoped override for DECOMP:
// send one full sentence token stream at a time, target only eligible slots,
// and cache aligned sentence results including null skips.
function _buildLlmDecompSentences(data) {
  var segments = data.segments || [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udOverlay = data.ud_overlay || {};
  var udTokens = udOverlay.tokens && Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  var sents = udOverlay.sentences && Array.isArray(udOverlay.sentences) ? udOverlay.sentences : null;
  var doc2seg = udOverlay.doc2seg && Array.isArray(udOverlay.doc2seg) ? udOverlay.doc2seg : null;
  var udTokMap = {};
  for (var ui = 0; ui < udTokens.length; ui++) {
    if (udTokens[ui] && udTokens[ui].i != null) udTokMap[udTokens[ui].i] = udTokens[ui];
  }
  function expandSeg(idx) {
    var segText = String(segments[idx] || '').trim();
    if (!segText) return null;
    var resultEntry = idx >= 0 && idx < resultsBySeg.length ? resultsBySeg[idx] || null : null;
    var udTok = udTokMap[idx] || null;
    var mwtParts =
      udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length > 1 ? udTok.mwt_parts : null;
    var out = [];
    if (mwtParts) {
      for (var pi = 0; pi < mwtParts.length; pi++) {
        var part = mwtParts[pi] || {};
        var partText = getMwtPartSurfaceSliceText(
          segText,
          udTok,
          pi,
          String(part.text || part.form || '').trim()
        );
        if (!partText) partText = String(part.text || part.form || '').trim();
        partText = String(partText || '').trim();
        if (!partText) continue;
        var partLemma = String(
          part.lemma ||
            _assistantSliceMwtValue(
              (resultEntry && (resultEntry.lemma_raw || resultEntry.lemma)) ||
                (udTok && (udTok.lemma_raw || udTok.lemma)) ||
                '',
              pi
            ) ||
            ''
        ).trim();
        var partFeats = String(
          part.feats ||
            _assistantSliceMwtValue((resultEntry && resultEntry.feats) || (udTok && udTok.feats) || '', pi) ||
            ''
        ).trim();
        out.push({
          text: partText,
          segIdx: idx,
          partIdx: pi,
          lemma: partLemma,
          eligible: _tokenHasEligibleLlmDecompFeats(partFeats)
        });
      }
      return out.length ? out : null;
    }
    out.push({
      text: segText,
      segIdx: idx,
      partIdx: -1,
      lemma: String(
        (udTok && (udTok.lemma_raw || udTok.lemma)) ||
          (resultEntry && (resultEntry.lemma_raw || resultEntry.lemma)) ||
          ''
      ).trim(),
      eligible: _tokenHasEligibleLlmDecompFeats(
        String((udTok && udTok.feats) || (resultEntry && resultEntry.feats) || '').trim()
      )
    });
    return out;
  }
  var out = [];
  if (sents && sents.length && doc2seg) {
    for (var si = 0; si < sents.length; si++) {
      var rng = sents[si];
      if (!Array.isArray(rng) || rng.length < 2) continue;
      var docStart = rng[0] | 0;
      var docEnd = rng[1] | 0;
      var segSet = {};
      for (var j = docStart; j < docEnd && j < udTokens.length; j++) {
        var seg = j < doc2seg.length ? doc2seg[j] | 0 : -1;
        if (seg >= 0) segSet[seg] = true;
      }
      var segIdxs = Object.keys(segSet)
        .map(function (k) {
          return parseInt(k, 10);
        })
        .sort(function (a, b) {
          return a - b;
        });
      var sentTokens = [];
      for (var k = 0; k < segIdxs.length; k++) {
        var expanded = expandSeg(segIdxs[k]);
        if (!expanded || !expanded.length) continue;
        for (var ei = 0; ei < expanded.length; ei++) sentTokens.push(expanded[ei]);
      }
      if (sentTokens.length)
        out.push({
          tokens: sentTokens
        });
    }
    return out;
  }
  var whole = [];
  for (var ti = 0; ti < segments.length; ti++) {
    var expandedFallback = expandSeg(ti);
    if (!expandedFallback || !expandedFallback.length) continue;
    for (var fi = 0; fi < expandedFallback.length; fi++) whole.push(expandedFallback[fi]);
  }
  if (whole.length)
    out.push({
      tokens: whole
    });
  return out;
}
export function _buildLlmDecompChunks(data) {
  var sentences = _buildLlmDecompSentences(data);
  var candidates = [];
  var chunks = [];
  for (var si = 0; si < sentences.length; si++) {
    var sent = sentences[si] || {};
    var sentTokens = Array.isArray(sent.tokens) ? sent.tokens : [];
    if (!sentTokens.length) continue;
    var chunkTokens = [];
    var indices = [];
    var targetPositions = [];
    var targetTokens = [];
    for (var ti = 0; ti < sentTokens.length; ti++) {
      var tok = sentTokens[ti] || {};
      var tokText = String(tok.text || '').trim();
      if (!tokText) continue;
      chunkTokens.push(tokText);
      if (!tok.eligible) continue;
      var candidate = {
        candidateIdx: candidates.length,
        segIdx: tok.segIdx,
        partIdx: isFinite(Number(tok.partIdx)) ? Number(tok.partIdx) : -1,
        surface: tokText,
        lemma: String(tok.lemma || '').trim(),
        sentenceIndex: ti
      };
      candidates.push(candidate);
      indices.push(candidate.candidateIdx);
      targetPositions.push(ti);
      targetTokens.push(tokText);
    }
    if (indices.length) {
      chunks.push({
        chunk_id: 'decomp_' + String(si),
        tokens: chunkTokens,
        indices: indices,
        target_positions: targetPositions,
        target_tokens: targetTokens
      });
    }
  }
  return {
    candidates: candidates,
    chunks: chunks
  };
}
export function _llmDecompLoadCache() {
  try {
    var raw = sessionStorage.getItem(decompositionRequestsState._LLM_DECOMP_SS_KEY);
    if (!raw) return Object.create(null);
    var obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : Object.create(null);
  } catch (e) {
    return Object.create(null);
  }
}
export function _llmDecompSaveCache(cache) {
  try {
    sessionStorage.setItem(decompositionRequestsState._LLM_DECOMP_SS_KEY, JSON.stringify(cache));
  } catch (e) {
    try {
      var keys = Object.keys(cache);
      var drop = Math.max(1, Math.floor(keys.length * 0.2));
      for (var i = 0; i < drop; i++) delete cache[keys[i]];
      sessionStorage.setItem(decompositionRequestsState._LLM_DECOMP_SS_KEY, JSON.stringify(cache));
    } catch (e2) {}
  }
}
export function _llmDecompSentKey(lang, sentenceTokens, targetPositions) {
  try {
    return lang + '\u0001' + JSON.stringify(sentenceTokens) + '\u0001' + JSON.stringify(targetPositions);
  } catch (e) {
    return null;
  }
}
export function _fireLlmDecompRequest(data) {
  if (!dependencyPopupState.displaySettings.llmDecomp) return;
  var segments = data.segments || [];
  if (!segments.length) return;
  var built = _buildLlmDecompChunks(data);
  var candidates = built.candidates || [];
  var allChunks = built.chunks || [];
  if (!candidates.length || !allChunks.length) {
    hoverLayoutState.latestLlmDecomps = new Array(segments.length).fill(null);
    _refreshLlmDecompUI();
    return;
  }
  var lang = documentShellState.currentLanguage || '';
  var seq = ++hoverLayoutState.latestLlmDecompSeq;
  hoverLayoutState.latestLlmDecomps = new Array(segments.length).fill(null);
  var cache = _llmDecompLoadCache();
  var chunksToSend = [];
  var pendingById = Object.create(null);
  var cacheHits = [];
  for (var ci = 0; ci < allChunks.length; ci++) {
    var chunk = allChunks[ci];
    chunk.cache_key = _llmDecompSentKey(lang, chunk.tokens, chunk.target_positions);
    var cached = chunk.cache_key ? cache[chunk.cache_key] : null;
    if (cached && Array.isArray(cached) && cached.length === chunk.indices.length) {
      for (var ti = 0; ti < chunk.indices.length; ti++) {
        var cachedVal = cached[ti];
        var cachedCandidate = candidates[chunk.indices[ti]];
        if (!cachedCandidate || cachedVal == null) continue;
        _ingestLlmDecompCandidateResult(cachedCandidate, cachedVal);
      }
      cacheHits.push({
        tokens: chunk.tokens.slice()
      });
    } else {
      chunk._resultComplete = false;
      chunk._resultArray = null;
      chunksToSend.push(chunk);
      pendingById[chunk.chunk_id] = chunk;
    }
  }
  _refreshLlmDecompUI();
  if (!chunksToSend.length) return;
  fetch('/api/llm_decomps', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      chunks: chunksToSend,
      lang: lang
    })
  })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      function persistOnce() {
        var cur = _llmDecompLoadCache();
        var changed = false;
        for (var ck = 0; ck < chunksToSend.length; ck++) {
          var sentChunk = chunksToSend[ck];
          if (
            !sentChunk.cache_key ||
            !sentChunk._resultComplete ||
            !Array.isArray(sentChunk._resultArray) ||
            sentChunk._resultArray.length !== sentChunk.indices.length
          )
            continue;
          var arr = [];
          for (var ai = 0; ai < sentChunk._resultArray.length; ai++) {
            var raw = sentChunk._resultArray[ai];
            if (raw == null) {
              arr.push(null);
              continue;
            }
            var textVal = '';
            if (typeof raw === 'string') textVal = raw;
            else if (raw && typeof raw === 'object') textVal = String(raw.decomp || raw.text || '');
            textVal = String(textVal || '').trim();
            arr.push(
              textVal
                ? {
                    decomp: textVal
                  }
                : null
            );
          }
          cur[sentChunk.cache_key] = arr;
          changed = true;
        }
        if (changed) _llmDecompSaveCache(cur);
      }
      function pump() {
        return reader.read().then(function (chunk) {
          if (seq !== hoverLayoutState.latestLlmDecompSeq) {
            try {
              persistOnce();
            } catch (e) {}
            reader.cancel();
            return;
          }
          if (chunk.done) {
            try {
              persistOnce();
            } catch (e) {}
            return;
          }
          buf += decoder.decode(chunk.value, {
            stream: true
          });
          var lines = buf.split('\n');
          buf = lines.pop();
          for (var li = 0; li < lines.length; li++) {
            var line = lines[li].trim();
            if (!line || line.indexOf('data: ') !== 0) continue;
            try {
              var msg = JSON.parse(line.slice(6));
              if (msg.done) {
                try {
                  persistOnce();
                } catch (e) {}
                return;
              }
              if (msg.error) {
                console.warn('LLM decomp error:', msg.error);
                return;
              }
              if (Array.isArray(msg.indices) && Array.isArray(msg.decomps)) {
                var sentRef = msg.chunk_id && pendingById[msg.chunk_id] ? pendingById[msg.chunk_id] : null;
                if (sentRef && msg.decomps.length === sentRef.indices.length) {
                  sentRef._resultArray = msg.decomps.slice();
                  sentRef._resultComplete = true;
                }
                for (var mi = 0; mi < msg.indices.length; mi++) {
                  var globalIdx = msg.indices[mi];
                  var candidate = candidates[globalIdx];
                  var decompVal = msg.decomps[mi];
                  if (!candidate || decompVal == null) continue;
                  _ingestLlmDecompCandidateResult(candidate, decompVal);
                }
                _refreshLlmDecompUI();
              }
            } catch (e) {}
          }
          return pump();
        });
      }
      return pump();
    })
    .catch(function (err) {
      console.warn('LLM decomp request failed:', err);
    });
}
export function initializeDecompositionRequests() {
  decompositionRequestsState._LLM_DECOMP_SS_KEY = 'llmDecompTokenCache:v1';
  window._fireLlmDecompRequest = _fireLlmDecompRequest;
  decompositionRequestsState._LLM_DECOMP_SS_KEY = 'llmDecompSentCache:v2';
  window._fireLlmDecompRequest = _fireLlmDecompRequest;

  // -- Orth breakdown request helper --

  // Build HTML for the ORTH row: grapheme clusters with codepoint decomp in brackets.
  // Returns the inner HTML for one sub-unit (no "+" joining).  Compact styling.
  return true;
}
