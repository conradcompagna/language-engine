import { applyFreshSegmentResult } from './custom-entry-state.mjs';
import { decompositionEditorState } from './decomposition-editor.state.mjs';
import { getSentenceSpansFromSegments } from './dependency-geometry.mjs';
import { normalizeUdSentenceSpans } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getLookupEntryFills } from './entry-editing.mjs';
import { flushCachedEntriesByStorageId } from './hover-interaction.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { hasSameVisibleComparisonText } from './presentation.mjs';
import {
  _entryReferencesStorageId,
  flushLookupCachesForToken,
  normalizeLookupKey
} from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { sidePanelState } from './side-panel.state.mjs';
export // alias|rowId -> decomp text (latest)

function _ensureDecompFloat() {
  if (sidePanelState._decompFloat) return sidePanelState._decompFloat;
  sidePanelState._decompFloat = document.createElement('div');
  sidePanelState._decompFloat.className = 'decomp-float';
  sidePanelState._decompFloat.style.cssText =
    'position:fixed;z-index:10000;background:#fff;' +
    'border:1px solid #334155;border-radius:6px;padding:6px 8px;' +
    'box-shadow:0 4px 12px rgba(0,0,0,0.12);font-size:11px;color:#1e293b;' +
    'line-height:1.5;max-width:340px;display:none;pointer-events:auto;';
  document.body.appendChild(sidePanelState._decompFloat);
  // Persistent (edit/view) state must not close on outside hover; only
  // explicit cancel/save/click-outside-of-headword closes it.
  sidePanelState._decompFloat.addEventListener('mousedown', function (ev) {
    ev.stopPropagation();
  });
  return sidePanelState._decompFloat;
}
export function _hideDecompFloat() {
  if (!sidePanelState._decompFloat) return;
  sidePanelState._decompFloat.style.display = 'none';
  sidePanelState._decompFloat.innerHTML = '';
  sidePanelState._decompFloatState = 'hidden';
  sidePanelState._decompFloatBlock = null;
}
export function _positionDecompFloat(targetEl) {
  if (!sidePanelState._decompFloat || !targetEl) return;
  var r = targetEl.getBoundingClientRect();
  var fr = sidePanelState._decompFloat.getBoundingClientRect();
  var vw = window.innerWidth,
    vh = window.innerHeight;
  var x = r.left;
  var y = r.bottom + 4;
  if (y + fr.height > vh - 8) y = Math.max(8, r.top - fr.height - 4);
  if (x + fr.width > vw - 8) x = Math.max(8, vw - fr.width - 8);
  sidePanelState._decompFloat.style.left = x + 'px';
  sidePanelState._decompFloat.style.top = y + 'px';
}
export function _parseDecompText(raw) {
  var s = String(raw || '').trim();
  if (!s)
    return {
      d: '',
      a: '',
      b: ''
    };
  // Try JSON first (server stores as JSON in some flows)
  if (s.charAt(0) === '{') {
    try {
      var obj = JSON.parse(s);
      return {
        d: String(obj.decomposition || obj.d || '').trim(),
        a: String(obj.analysis || obj.a || '').trim(),
        b: String(obj.breakdown || obj.b || '').trim()
      };
    } catch (_e) {}
  }
  var d = '',
    a = '',
    b = '';
  var lines = s.split(/\r?\n/);
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].replace(/^[*\-•\s]+/, '').trim();
    if (!line) continue;
    var low = line.toLowerCase();
    if (low.indexOf('decomposition') === 0) {
      var ix = line.indexOf(':');
      d = (ix >= 0 ? line.slice(ix + 1) : line).trim();
    } else if (low.indexOf('analysis') === 0) {
      var ix2 = line.indexOf(':');
      a = (ix2 >= 0 ? line.slice(ix2 + 1) : line).trim();
    } else if (low.indexOf('breakdown') === 0) {
      var ix3 = line.indexOf(':');
      b = (ix3 >= 0 ? line.slice(ix3 + 1) : line).trim();
    } else if (!d) {
      d = line;
    } else if (!a) {
      a = line;
    } else if (!b) {
      b = line;
    }
  }
  return {
    d: d,
    a: a,
    b: b
  };
}
export function _decompEsc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
export function _decompPaidGate() {
  if (window.__LE_SUBSCRIBED) return true;
  window.location.href = '/account';
  return false;
}
export function _decompCacheKey(block) {
  if (!block) return '';
  // Decomps are keyed solely by (language, surface_form).
  var lang = String(block.getAttribute('data-decomp-lang') || '').trim();
  var surface = String(block.getAttribute('data-decomp-surface-form') || '').trim();
  if (!surface) return '';
  return lang + '|sf:' + surface;
}
export function _getDecompCached(block) {
  if (block && block.getAttribute) {
    var inlineVal = String(block.getAttribute('data-decomp-value') || '');
    if (inlineVal) return inlineVal;
  }
  var k = _decompCacheKey(block);
  return k && sidePanelState._decompCache[k] !== undefined ? sidePanelState._decompCache[k] : null;
}
export function _setDecompForBlock(block, text) {
  var raw = String(text || '');
  var k = _decompCacheKey(block);
  if (k) sidePanelState._decompCache[k] = raw;
  if (block && block.setAttribute) {
    if (raw) block.setAttribute('data-decomp-value', raw);
    else block.removeAttribute('data-decomp-value');
  }
}

// Fetch decomp from server. Cached after first fetch per cache key.
export function _fetchDecompForBlock(block, cb) {
  var cached = _getDecompCached(block);
  if (cached !== null) {
    cb(cached);
    return;
  }
  var k = _decompCacheKey(block);
  if (!k) {
    cb('');
    return;
  }
  var lang = block.getAttribute('data-decomp-lang') || '';
  var surface = (block.getAttribute('data-decomp-surface-form') || '').trim();
  if (!surface) {
    _setDecompForBlock(block, '');
    cb('');
    return;
  }
  var url =
    '/api/entry_decomp/get?lang=' + encodeURIComponent(lang) + '&surface_form=' + encodeURIComponent(surface);
  fetch(url)
    .then(function (r) {
      return r.json();
    })
    .then(function (d) {
      var t = d && d.ok ? String(d.decomp || '') : '';
      _setDecompForBlock(block, t);
      cb(t);
    })
    .catch(function () {
      cb('');
    });
}
export function _flushDecompSurfaceCaches(surface, langOverride) {
  var text = String(surface || '').trim();
  if (!text) return;
  flushLookupCachesForToken(text, langOverride);
  var base = normalizeLookupKey(text, langOverride);
  if (!base) return;
  var prefix = base + '||';
  var sidePanelKeysToDelete = [];
  segmentRenderingState.sidePanelLookupCache.forEach(function (_entry, key) {
    var skey = String(key || '');
    if (skey === base || skey.indexOf(prefix) === 0) sidePanelKeysToDelete.push(skey);
  });
  for (var i = 0; i < sidePanelKeysToDelete.length; i++) {
    segmentRenderingState.sidePanelLookupCache.delete(sidePanelKeysToDelete[i]);
  }
  var promiseKeysToDelete = [];
  segmentRenderingState.sidePanelLookupPromiseCache.forEach(function (_promise, key) {
    var pkey = String(key || '');
    if (pkey === base || pkey.indexOf(prefix) === 0) promiseKeysToDelete.push(pkey);
  });
  for (var j = 0; j < promiseKeysToDelete.length; j++) {
    segmentRenderingState.sidePanelLookupPromiseCache.delete(promiseKeysToDelete[j]);
  }
}
export function _entryTouchesDecompSurface(entry, surfaceForm, langOverride) {
  var targetKey = normalizeLookupKey(surfaceForm, langOverride);
  if (!targetKey || !entry || typeof entry !== 'object') return false;
  var stack = [entry];
  while (stack.length) {
    var current = stack.pop();
    if (!current || typeof current !== 'object') continue;
    var candidates = [
      current._decomp_surface_form,
      current.display_headword,
      current.surface_form,
      current.headword,
      current.head,
      current.text
    ];
    for (var i = 0; i < candidates.length; i++) {
      var candidateKey = normalizeLookupKey(candidates[i], langOverride);
      if (candidateKey && candidateKey === targetKey) return true;
    }
    var currentFills = getLookupEntryFills(current);
    for (var fi = 0; fi < currentFills.length; fi++) {
      stack.push(currentFills[fi]);
    }
    var nestedEntries = Array.isArray(current.entries) ? current.entries : [];
    for (var ei = 0; ei < nestedEntries.length; ei++) {
      stack.push(nestedEntries[ei]);
    }
  }
  return false;
}
export function _findDecompAffectedLiveSegmentIndexes(surfaceForm, dbAlias, rowId, langOverride) {
  var out = [];
  var seen = Object.create(null);
  var targetSurface = String(surfaceForm || '').trim();
  var alias = String(dbAlias || '').trim();
  var id = parseInt(rowId || 0, 10) || 0;
  var results =
    hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)
      ? hoverLayoutState.latestData.results_by_seg
      : [];
  var segments = Array.isArray(hoverLayoutState.latestSegments) ? hoverLayoutState.latestSegments : [];
  function addIndex(idx) {
    var n = parseInt(idx, 10);
    if (!isFinite(n) || n < 0 || seen[n]) return;
    seen[n] = true;
    out.push(n);
  }
  for (var i = 0; i < segments.length; i++) {
    var segText = String(segments[i] || '').trim();
    if (targetSurface && hasSameVisibleComparisonText(segText, targetSurface)) {
      addIndex(i);
      continue;
    }
    var result = results[i] || null;
    if (targetSurface && result && _entryTouchesDecompSurface(result, targetSurface, langOverride)) {
      addIndex(i);
      continue;
    }
    if (alias && id && result && _entryReferencesStorageId(result, alias, id)) {
      addIndex(i);
      continue;
    }
    var mwtTok = dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[i];
    var mwtParts = mwtTok && Array.isArray(mwtTok.mwt_parts) ? mwtTok.mwt_parts : [];
    for (var mi = 0; mi < mwtParts.length; mi++) {
      var mwtPartText = String((mwtParts[mi] && mwtParts[mi].text) || '').trim();
      if (targetSurface && hasSameVisibleComparisonText(mwtPartText, targetSurface)) {
        addIndex(i);
        break;
      }
    }
  }
  return out;
}

// Wider-context builder for Gemini entry_note / entry_decomp calls.
// Given (dbAlias, rowId, surface), locate the owning segment in latestData
// and assemble: sentence token stream, the full set of dict fills on the
// target token (flagging which one matches the target), and the Trankit
// morphological analysis (upos/xpos/feats/lemma). Returns a plain object
// suitable for direct JSON serialization to the backend.
export function _buildGeminiEntryContext(dbAlias, rowId, surface) {
  var out = {
    sentence_tokens: [],
    fills: [],
    trankit: null
  };
  try {
    var alias = String(dbAlias || '').trim();
    var id = parseInt(rowId || 0, 10) || 0;
    var targetSurface = String(surface || '').trim();
    var results =
      hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)
        ? hoverLayoutState.latestData.results_by_seg
        : [];
    var segments = Array.isArray(hoverLayoutState.latestSegments) ? hoverLayoutState.latestSegments : [];
    if (!results.length || !segments.length) return out;

    // Find the segment that owns this entry: prefer (alias, rowId) match,
    // else fall back to surface-text match.
    var segIdx = -1;
    if (alias && id) {
      for (var i = 0; i < results.length; i++) {
        var r = results[i] || null;
        if (r && _entryReferencesStorageId(r, alias, id)) {
          segIdx = i;
          break;
        }
      }
    }
    if (segIdx < 0 && targetSurface) {
      for (var j = 0; j < segments.length; j++) {
        if (hasSameVisibleComparisonText(segments[j] || '', targetSurface)) {
          segIdx = j;
          break;
        }
      }
    }
    if (segIdx < 0) return out;

    // Sentence tokens: use the sentence range the seg falls into.
    var ctxS = 0,
      ctxE = segments.length;
    var sentences = normalizeUdSentenceSpans(
      (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.sentences) || []
    );
    if (!sentences.length) {
      var fb = getSentenceSpansFromSegments(segments);
      for (var fi = 0; fi < fb.length; fi++) sentences.push([fb[fi].start, fb[fi].end]);
    }
    for (var si = 0; si < sentences.length; si++) {
      if (segIdx >= sentences[si][0] && segIdx < sentences[si][1]) {
        ctxS = sentences[si][0];
        ctxE = sentences[si][1];
        break;
      }
    }
    for (var k = ctxS; k < ctxE; k++) {
      var tok = String(segments[k] || '').trim();
      if (tok) out.sentence_tokens.push(tok);
    }

    // Trankit analysis for the owning token.
    var udTok = (dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[segIdx]) || null;
    if (udTok) {
      var feats = udTok.feats;
      if (feats && typeof feats === 'object' && !Array.isArray(feats)) {
        var fp = [];
        Object.keys(feats).forEach(function (fk) {
          var fv = feats[fk];
          if (fv != null && fv !== '') fp.push(fk + '=' + fv);
        });
        feats = fp.join('|');
      }
      out.trankit = {
        upos: String(udTok.upos || '').trim(),
        xpos: String(udTok.xpos || udTok.tag || '').trim(),
        feats: String(feats || '').trim(),
        lemma: String(udTok.lemma || udTok.lemma_raw || '').trim()
      };
    }

    // Fills on this token. Walk result.dict_fill and surface each sub-entry,
    // flagging the one that matches (alias, rowId) as the target.
    var seg = results[segIdx] || null;
    var fillList = [];
    function pushEntry(e, surfaceHint) {
      if (!e || typeof e !== 'object') return;
      var a = String(e._storage_db_alias || '').trim();
      var rid = parseInt(e._storage_row_id || 0, 10) || 0;
      var hw = String(e.headword || e.head || e.display_headword || '').trim();
      var glosses = [];
      var senses =
        Array.isArray(e.senses_hover) && e.senses_hover.length
          ? e.senses_hover
          : Array.isArray(e.senses_full) && e.senses_full.length
            ? e.senses_full
            : Array.isArray(e.senses)
              ? e.senses
              : [];
      for (var si2 = 0; si2 < senses.length && glosses.length < 3; si2++) {
        var s = senses[si2];
        if (typeof s === 'string' && s.trim()) glosses.push(s.trim());
        else if (s && typeof s === 'object') {
          var g = String(s.gloss || s.def || s.text || '').trim();
          if (!g && Array.isArray(s.glosses) && s.glosses.length) g = String(s.glosses[0] || '').trim();
          if (g) glosses.push(g);
        }
      }
      fillList.push({
        surface: String(surfaceHint || e.match_key || e._surface || '').trim(),
        headword: hw,
        glosses: glosses,
        is_target: !!(alias && id && a === alias && rid === id)
      });
    }
    if (seg && Array.isArray(seg.dict_fill)) {
      for (var df = 0; df < seg.dict_fill.length; df++) {
        var fill = seg.dict_fill[df] || {};
        var fillSurface = String(fill.surface || fill.match_key || fill.key || '').trim();
        if (Array.isArray(fill.entries) && fill.entries.length) {
          for (var ei = 0; ei < fill.entries.length; ei++) pushEntry(fill.entries[ei], fillSurface);
        } else {
          pushEntry(fill, fillSurface);
        }
      }
    }
    // Fallback: if no dict_fill, at least include the seg-level entry itself.
    if (!fillList.length && seg) pushEntry(seg, targetSurface || segments[segIdx]);
    out.fills = fillList;
  } catch (_e) {}
  return out;
}
export function _renderDecompTooltip(block) {
  var fl = _ensureDecompFloat();
  // Show neutral label until cached fetch resolves; refine once we know.
  var cached = _getDecompCached(block);
  fl.innerHTML =
    cached === null || cached === ''
      ? '<span style="color:#0ea5e9;font-weight:bold;">+ Decomp</span>'
      : '<span style="color:#0ea5e9;font-weight:bold;">Decomp</span>';
  fl.style.opacity = '1';
  fl.style.cursor = 'pointer';
  fl.style.display = 'block';
  sidePanelState._decompFloatState = 'tooltip';
  sidePanelState._decompFloatBlock = block;
  _positionDecompFloat(block);
  if (cached === null) {
    // Background-fetch and update label if popup still in tooltip mode
    _fetchDecompForBlock(block, function (t) {
      if (sidePanelState._decompFloatState === 'tooltip' && sidePanelState._decompFloatBlock === block) {
        fl.innerHTML = t
          ? '<span style="color:#0ea5e9;font-weight:bold;">Decomp</span>'
          : '<span style="color:#0ea5e9;font-weight:bold;">+ Decomp</span>';
        _positionDecompFloat(block);
      }
    });
  }
}
export function _renderDecompView(block, decompText) {
  var fl = _ensureDecompFloat();
  var p = _parseDecompText(decompText);
  var html = '';
  if (p.d)
    html +=
      '<div style="white-space:pre-wrap;"><span style="color:#0ea5e9;margin-right:4px;font-weight:bold;">Decomp:</span><span style="color:#000;">' +
      _decompEsc(p.d) +
      '</span></div>';
  if (p.a)
    html +=
      '<div style="white-space:pre-wrap;margin-top:2px;"><span style="color:#0ea5e9;margin-right:4px;font-weight:bold;">Analysis:</span><span style="color:#000;">' +
      _decompEsc(p.a) +
      '</span></div>';
  if (p.b)
    html +=
      '<div style="white-space:pre-wrap;margin-top:2px;"><span style="color:#0ea5e9;margin-right:4px;font-weight:bold;">Breakdown:</span><span style="color:#000;">' +
      _decompEsc(p.b) +
      '</span></div>';
  if (!html) html = '<div style="opacity:0.6;">(empty)</div>';
  fl.innerHTML = html;
  fl.style.opacity = '1';
  fl.style.cursor = 'default';
  fl.style.display = 'block';
  sidePanelState._decompFloatState = 'view';
  sidePanelState._decompFloatBlock = block;
  _positionDecompFloat(block);
}
export function _renderDecompEditor(block, decompText) {
  var fl = _ensureDecompFloat();
  var p = _parseDecompText(decompText);
  fl.innerHTML =
    '' +
    '<div style="display:flex;gap:4px;align-items:baseline;">' +
    '<span style="color:#0ea5e9;font-weight:bold;flex-shrink:0;">Decomp:</span>' +
    '<span class="decomp-edit-d" contenteditable="true" ' +
    'style="display:inline-block;outline:none;min-width:100px;white-space:pre-wrap;' +
    'border-bottom:1px dotted #334155;flex:1;color:#000;">' +
    _decompEsc(p.d) +
    '</span>' +
    '</div>' +
    '<div style="display:flex;gap:4px;align-items:baseline;margin-top:2px;">' +
    '<span style="color:#0ea5e9;font-weight:bold;flex-shrink:0;">Analysis:</span>' +
    '<span class="decomp-edit-a" contenteditable="true" ' +
    'style="display:inline-block;outline:none;min-width:100px;white-space:pre-wrap;' +
    'border-bottom:1px dotted #334155;flex:1;color:#000;">' +
    _decompEsc(p.a) +
    '</span>' +
    '</div>' +
    '<div style="display:flex;gap:4px;align-items:baseline;margin-top:2px;">' +
    '<span style="color:#0ea5e9;font-weight:bold;flex-shrink:0;">Breakdown:</span>' +
    '<span class="decomp-edit-b" contenteditable="true" ' +
    'style="display:inline-block;outline:none;min-width:100px;white-space:pre-wrap;' +
    'border-bottom:1px dotted #334155;flex:1;color:#000;">' +
    _decompEsc(p.b) +
    '</span>' +
    '</div>' +
    '<div style="margin-top:6px;display:flex;gap:8px;justify-content:flex-end;align-items:center;">' +
    '<span class="decomp-save-btn" role="button" tabindex="0" title="Save" ' +
    'style="cursor:pointer;font-size:13px;color:#1e293b;font-weight:bold;">&#10003;</span>' +
    '<span class="decomp-cancel-btn" role="button" tabindex="0" title="Cancel" ' +
    'style="cursor:pointer;font-size:13px;color:#888;">&#10007;</span>' +
    '<span class="decomp-delete-btn" role="button" tabindex="0" title="Delete" ' +
    'style="cursor:pointer;font-size:12px;color:#dc2626;">&#128465;</span>' +
    '</div>';
  fl.style.opacity = '1';
  fl.style.cursor = 'default';
  fl.style.display = 'block';
  sidePanelState._decompFloatState = 'edit';
  sidePanelState._decompFloatBlock = block;
  _positionDecompFloat(block);
  var ed = fl.querySelector('.decomp-edit-d');
  if (ed) ed.focus();
}
export function _decompRelookup(surfaceForm, alias, rowId) {
  var targetSurface = String(surfaceForm || '').trim();
  var nAlias = String(alias || '').trim();
  var nRowId = parseInt(rowId || 0, 10) || 0;
  if (
    !hoverLayoutState.latestData ||
    !Array.isArray(hoverLayoutState.latestData.results_by_seg) ||
    !hoverLayoutState.latestSegments
  )
    return;
  var dc = window.DictionaryClient;
  if (!dc || typeof dc.relookupOneSegment !== 'function') return;
  var rlang = String(documentShellState.currentLanguage || '').toLowerCase();
  var rbs = hoverLayoutState.latestData.results_by_seg;
  var refreshIndexes = _findDecompAffectedLiveSegmentIndexes(targetSurface, nAlias, nRowId, rlang);
  if (targetSurface) _flushDecompSurfaceCaches(targetSurface, rlang);
  for (var rj = 0; rj < refreshIndexes.length; rj++) {
    var refreshIdx = refreshIndexes[rj];
    var refreshSeg = rbs[refreshIdx];
    var refreshSurface = String(hoverLayoutState.latestSegments[refreshIdx] || '').trim();
    if (!refreshSurface || !refreshSeg) continue;
    (function (segIdx, segSurface, existing) {
      _flushDecompSurfaceCaches(segSurface, rlang);
      var seededExisting = existing;
      if (
        (!seededExisting.mwt_parts ||
          !Array.isArray(seededExisting.mwt_parts) ||
          !seededExisting.mwt_parts.length) &&
        dependencyState.latestUdTokenMap &&
        dependencyState.latestUdTokenMap[segIdx] &&
        Array.isArray(dependencyState.latestUdTokenMap[segIdx].mwt_parts) &&
        dependencyState.latestUdTokenMap[segIdx].mwt_parts.length
      ) {
        seededExisting = Object.assign({}, existing, {
          mwt_parts: dependencyState.latestUdTokenMap[segIdx].mwt_parts.slice()
        });
      }
      dc.relookupOneSegment(rlang, segSurface, seededExisting)
        .then(function (fresh) {
          applyFreshSegmentResult(fresh || existing, segIdx, segSurface);
        })
        .catch(function () {});
    })(refreshIdx, refreshSurface, refreshSeg);
  }
}
export function _decompInlineViewHtml(decompText) {
  var p = _parseDecompText(decompText);
  var html = '';
  if (p.d) {
    html +=
      '<div class="entry-decomp-row">' +
      '<span class="entry-decomp-label" style="' +
      decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
      '">Decomp:</span> ' +
      '<span class="entry-decomp-value entry-decomp-morphemes" role="button" tabindex="0" style="' +
      decompositionEditorState.INLINE_DECOMP_VALUE_STYLE +
      '">' +
      _decompEsc(p.d) +
      '</span>' +
      '</div>';
  }
  if (p.a) {
    html +=
      '<div class="entry-decomp-row" style="' +
      decompositionEditorState.INLINE_DECOMP_ROW_STYLE +
      '">' +
      '<span class="entry-decomp-label" style="' +
      decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
      '">Analysis:</span> ' +
      '<span class="entry-decomp-value entry-decomp-analysis" role="button" tabindex="0" style="' +
      decompositionEditorState.INLINE_DECOMP_VALUE_STYLE +
      '">' +
      _decompEsc(p.a) +
      '</span>' +
      '</div>';
  }
  if (p.b) {
    html +=
      '<div class="entry-decomp-row" style="' +
      decompositionEditorState.INLINE_DECOMP_ROW_STYLE +
      '">' +
      '<span class="entry-decomp-label" style="' +
      decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
      '">Breakdown:</span> ' +
      '<span class="entry-decomp-value entry-decomp-breakdown" role="button" tabindex="0" style="' +
      decompositionEditorState.INLINE_DECOMP_VALUE_STYLE +
      '">' +
      _decompEsc(p.b) +
      '</span>' +
      '</div>';
  }
  if (!html) {
    html =
      '<span class="entry-decomp-auto-btn" role="button" tabindex="0" style="' +
      decompositionEditorState.INLINE_DECOMP_AUTO_STYLE +
      '">+ decomp</span>';
  }
  return html;
}
export function _decompInlineEditorHtml(decompText) {
  var p = _parseDecompText(decompText);
  return (
    '' +
    '<div class="entry-decomp-row entry-decomp-editor-row">' +
    '<span class="entry-decomp-label" style="' +
    decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
    '">Decomp:</span> ' +
    '<span class="entry-decomp-editable decomp-edit-d" contenteditable="true" style="' +
    decompositionEditorState.INLINE_DECOMP_EDIT_STYLE +
    '">' +
    _decompEsc(p.d) +
    '</span>' +
    '</div>' +
    '<div class="entry-decomp-row entry-decomp-editor-row" style="' +
    decompositionEditorState.INLINE_DECOMP_ROW_STYLE +
    '">' +
    '<span class="entry-decomp-label" style="' +
    decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
    '">Analysis:</span> ' +
    '<span class="entry-decomp-editable decomp-edit-a" contenteditable="true" style="' +
    decompositionEditorState.INLINE_DECOMP_EDIT_STYLE +
    '">' +
    _decompEsc(p.a) +
    '</span>' +
    '</div>' +
    '<div class="entry-decomp-row entry-decomp-editor-row" style="' +
    decompositionEditorState.INLINE_DECOMP_ROW_STYLE +
    '">' +
    '<span class="entry-decomp-label" style="' +
    decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
    '">Breakdown:</span> ' +
    '<span class="entry-decomp-editable decomp-edit-b" contenteditable="true" style="' +
    decompositionEditorState.INLINE_DECOMP_EDIT_STYLE +
    '">' +
    _decompEsc(p.b) +
    '</span>' +
    '</div>' +
    '<div class="entry-decomp-row entry-decomp-actions-row" style="margin-top:3px;">' +
    '<span class="entry-decomp-label entry-decomp-label-spacer" aria-hidden="true" style="' +
    decompositionEditorState.INLINE_DECOMP_LABEL_STYLE +
    decompositionEditorState.INLINE_DECOMP_SPACER_STYLE +
    '">Decomp:</span>' +
    '<span class="entry-decomp-save-btn entry-decomp-inline-btn" role="button" tabindex="0" title="Save" style="' +
    decompositionEditorState.INLINE_DECOMP_BUTTON_STYLE +
    ';font-size:11px;">&#10003;</span>' +
    '<span class="entry-decomp-cancel-btn entry-decomp-inline-btn" role="button" tabindex="0" title="Cancel" style="' +
    decompositionEditorState.INLINE_DECOMP_BUTTON_STYLE +
    ';font-size:11px;color:#6b7280;">&#10007;</span>' +
    '<span class="entry-decomp-delete-btn entry-decomp-inline-btn" role="button" tabindex="0" title="Delete" style="' +
    decompositionEditorState.INLINE_DECOMP_BUTTON_STYLE +
    ';font-size:11px;color:#dc2626;">&#128465;</span>' +
    '</div>'
  );
}
export function _focusInlineDecompEditor(block) {
  if (!block) return;
  var ed = block.querySelector('.decomp-edit-d');
  if (!ed) return;
  ed.focus();
  var range = document.createRange();
  var sel = window.getSelection();
  range.selectNodeContents(ed);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
}
export function _renderInlineDecompRows(block, decompText) {
  if (!block || block.getAttribute('data-decomp-inline') !== '1') return false;
  _setDecompForBlock(block, decompText);
  block.innerHTML = _decompInlineViewHtml(decompText);
  return true;
}
export function _generateAndShowDecomp(block) {
  if (sidePanelState._decompFloatBusy) return;
  if (!_decompPaidGate()) return;
  var fl = _ensureDecompFloat();
  fl.innerHTML = '<div style="opacity:0.7;">generating…</div>';
  fl.style.display = 'block';
  sidePanelState._decompFloatBusy = true;
  var lang = block.getAttribute('data-decomp-lang') || '';
  var headword = block.getAttribute('data-decomp-headword') || '';
  var pos = block.getAttribute('data-decomp-pos') || '';
  var surface = (block.getAttribute('data-decomp-surface-form') || '').trim();
  var alias = block.getAttribute('data-decomp-alias') || '';
  var rowId = block.getAttribute('data-decomp-rowid') || '';
  if (!surface) {
    sidePanelState._decompFloatBusy = false;
    return;
  }
  // Decomps are keyed by surface_form alone. Gemini still gets headword/pos
  // as context so it analyzes the actual form the user is looking at.
  var _decompCtx = _buildGeminiEntryContext(alias, parseInt(rowId, 10), surface);
  var genBody = {
    lang: lang,
    surface_form: surface,
    headword: headword || surface,
    pos: pos,
    trankit: _decompCtx.trankit
  };
  fetch('/api/entry_decomp/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(genBody)
  })
    .then(function (r) {
      return r.json();
    })
    .then(function (d) {
      sidePanelState._decompFloatBusy = false;
      if (d.ok && d.decomp) {
        _setDecompForBlock(block, d.decomp);
        if (alias && rowId) {
          flushCachedEntriesByStorageId(alias, rowId);
        }
        _decompRelookup(surface, alias, rowId);
        if (!_renderInlineDecompRows(block, d.decomp)) {
          _renderDecompView(block, d.decomp);
        } else {
          _hideDecompFloat();
        }
      } else {
        fl.innerHTML = '<div style="color:#b91c1c;">' + _decompEsc(d.error || 'Failed.') + '</div>';
      }
    })
    .catch(function () {
      sidePanelState._decompFloatBusy = false;
      fl.innerHTML = '<div style="color:#b91c1c;">Network error.</div>';
    });
}
export function _saveDecompFromEditor(block) {
  if (!block || sidePanelState._decompFloatBusy) return;
  var fl = sidePanelState._decompFloat;
  if (!fl) return;
  var ed = fl.querySelector('.decomp-edit-d');
  var ea = fl.querySelector('.decomp-edit-a');
  var eb = fl.querySelector('.decomp-edit-b');
  var dText = ed ? (ed.textContent || '').trim() : '';
  var aText = ea ? (ea.textContent || '').trim() : '';
  var bText = eb ? (eb.textContent || '').trim() : '';
  if (!dText) return;
  // Store as JSON so all three fields round-trip cleanly through the server.
  var combined = JSON.stringify({
    decomposition: dText,
    analysis: aText,
    breakdown: bText
  });
  var alias = block.getAttribute('data-decomp-alias') || '';
  var rowId = block.getAttribute('data-decomp-rowid') || '';
  var lang = block.getAttribute('data-decomp-lang') || '';
  var surface = (block.getAttribute('data-decomp-surface-form') || '').trim();
  if (!surface) return;
  sidePanelState._decompFloatBusy = true;
  var saveBody = {
    lang: lang,
    surface_form: surface,
    decomp: combined
  };
  fetch('/api/entry_decomp/save', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(saveBody)
  })
    .then(function (r) {
      return r.json();
    })
    .then(function (d) {
      sidePanelState._decompFloatBusy = false;
      if (d.ok) {
        _setDecompForBlock(block, combined);
        if (alias && rowId) {
          flushCachedEntriesByStorageId(alias, rowId);
        }
        _decompRelookup(surface, alias, rowId);
        if (_renderInlineDecompRows(block, combined)) {
          _hideDecompFloat();
        } else {
          _renderDecompView(block, combined);
        }
      } else {
        if (d.error) alert(d.error);
      }
    })
    .catch(function () {
      sidePanelState._decompFloatBusy = false;
    });
}
export function initializeDecompositionEditor() {
  decompositionEditorState.INLINE_DECOMP_ROW_STYLE = 'margin-top:2px;';
  decompositionEditorState.INLINE_DECOMP_LABEL_STYLE = 'color:#6b7280;font-weight:600;';
  decompositionEditorState.INLINE_DECOMP_VALUE_STYLE =
    'display:inline;vertical-align:baseline;color:#2563eb;font:inherit;line-height:inherit;text-decoration:underline dotted rgba(37,99,235,0.45);text-underline-offset:2px;cursor:pointer;white-space:normal;word-break:break-word;';
  decompositionEditorState.INLINE_DECOMP_AUTO_STYLE =
    'display:inline;vertical-align:baseline;color:#2563eb;font:inherit;line-height:inherit;cursor:pointer;white-space:normal;word-break:break-word;';
  decompositionEditorState.INLINE_DECOMP_BUTTON_STYLE =
    'color:#2563eb;font-size:10px;line-height:1.2;opacity:0.8;cursor:pointer;';
  decompositionEditorState.INLINE_DECOMP_EDIT_STYLE =
    'display:inline;min-width:72px;outline:none;color:#1d4ed8;font:inherit;line-height:inherit;white-space:normal;word-break:break-word;border-bottom:1px dotted #93c5fd;';
  decompositionEditorState.INLINE_DECOMP_SPACER_STYLE = 'visibility:hidden;';
  return true;
}
