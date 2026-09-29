// panel_segment_renderer.js
//
// Standalone panel segment renderer for the side panel.
//
// Touches exactly five things outside this file:
//   1. DictionaryClient.lookupSingle(...) for canonical side-panel token lookups
//   2. opts.showPopup(target) — one callback from reader.js (= showDictPopupSimple)
//   3. opts.hidePopup() — clears the shared side-panel popup
//   4. opts.positionPopup(x, y) — repositions the shared side-panel popup
//   5. opts.setHoveredElement(el) — keeps popup anchoring tied to the hovered span
//
// Reader.js calls:
//   PanelSegmentRenderer.init({ showPopup: showDictPopupSimple });  // once per panel render
//   PanelSegmentRenderer.processPanel(panelContentEl, langCode);    // after each innerHTML set

(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  var _showPopup = null;
  var _hidePopup = null;
  var _positionPopup = null;
  var _setHoveredElement = null;

  // Fill cache: "lang|surface" → { surface, lang, lookupResult, fills, slices, anchorSlices }
  var _cache = Object.create(null);
  var _pending = Object.create(null);

  // Current hover key — prevents re-firing on same target
  var _currentHoverKey = null;
  var _cacheVersions = Object.create(null);

  function getCacheKey(surface, langCode) {
    var surfaceText = String(surface || '').trim();
    var lang = String(langCode || '').toLowerCase();
    if (!surfaceText || !lang) return '';
    return lang + '|' + surfaceText;
  }

  function bumpCacheKey(key) {
    if (!key) return;
    _cacheVersions[key] = (_cacheVersions[key] || 0) + 1;
    delete _cache[key];
    delete _pending[key];
    if (_currentHoverKey && _currentHoverKey.indexOf(key) >= 0) clearLookupHover();
  }

  function invalidateLookup(surface, langCode) {
    bumpCacheKey(getCacheKey(surface, langCode));
  }

  function entryReferencesStorageId(entry, dbAlias, rowId) {
    var alias = String(dbAlias || '').trim();
    var id = parseInt(rowId || 0, 10) || 0;
    if (!entry || typeof entry !== 'object' || !alias || !id) return false;
    var stack = [entry];
    while (stack.length) {
      var current = stack.pop();
      if (!current || typeof current !== 'object') continue;
      var currentAlias = String(current._storage_db_alias || '').trim();
      var currentRowId = parseInt(current._storage_row_id || 0, 10) || 0;
      if (currentAlias === alias && currentRowId === id) return true;
      var fills = Array.isArray(current.dict_fill) ? current.dict_fill : [];
      for (var fi = 0; fi < fills.length; fi++) {
        var fill = fills[fi];
        if (!fill || typeof fill !== 'object') continue;
        stack.push(fill);
        var nestedEntries = Array.isArray(fill.entries) ? fill.entries : [];
        for (var ei = 0; ei < nestedEntries.length; ei++) stack.push(nestedEntries[ei]);
        var refKeys = Array.isArray(fill.entry_refs) ? fill.entry_refs : [];
        for (var ri = 0; ri < refKeys.length; ri++) {
          var parts = String(refKeys[ri] || '').split('|');
          if (parts.length >= 3 && parts[1] === alias && (parseInt(parts[2], 10) || 0) === id) return true;
        }
      }
      var koChildren = Array.isArray(current.ko_compound_lemma_children) ? current.ko_compound_lemma_children : [];
      for (var ki = 0; ki < koChildren.length; ki++) {
        if (koChildren[ki] && koChildren[ki].lookup) stack.push(koChildren[ki].lookup);
      }
    }
    return false;
  }

  function invalidateByStorageId(dbAlias, rowId) {
    var keys = [];
    for (var key in _cache) {
      if (!Object.prototype.hasOwnProperty.call(_cache, key)) continue;
      var cached = _cache[key];
      if (cached && entryReferencesStorageId(cached.lookupResult, dbAlias, rowId)) keys.push(key);
    }
    for (var i = 0; i < keys.length; i++) bumpCacheKey(keys[i]);
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function init(opts) {
    opts = opts || {};
    if (typeof opts.showPopup === 'function') _showPopup = opts.showPopup;
    if (typeof opts.hidePopup === 'function') _hidePopup = opts.hidePopup;
    if (typeof opts.positionPopup === 'function') _positionPopup = opts.positionPopup;
    if (typeof opts.setHoveredElement === 'function') _setHoveredElement = opts.setHoveredElement;
  }

  function processPanel(containerEl, langCode) {
    if (!containerEl) return;
    var lang = String(langCode || '').toLowerCase();
    var spans = containerEl.querySelectorAll('.headword-component[data-seg], [data-seg][data-hover-mode="lookup"]');
    var hasLookupTargets = spans.length > 0 || containerEl.querySelectorAll('.reader-token-fill-hit').length > 0;

    if (lang) {
      for (var i = 0; i < spans.length; i++) {
        if (!isLookupSpan(spans[i])) continue;
        processSpan(spans[i], lang);
      }
    }

    if (hasLookupTargets) attachHoverListener(containerEl);
  }

  function isLookupSpan(spanEl) {
    if (!spanEl || !spanEl.dataset) return false;
    if (!spanEl.dataset.seg) return false;
    if (spanEl.classList && spanEl.classList.contains('headword-meta-component')) return false;
    var hoverMode = String(spanEl.dataset.hoverMode || 'lookup').trim().toLowerCase();
    // Exclude headwords/surface slices from fill anchors
    if (hoverMode === 'disabled') return false;
    return !hoverMode || hoverMode === 'lookup';
  }

  function hasLookupTarget(target) {
    if (!target || !target.closest) return false;
    var fillHit = target.closest('.reader-token-fill-hit');
    if (fillHit) return true;
    var segSpan = target.closest('.headword-component[data-seg], [data-seg][data-hover-mode="lookup"]');
    return !!isLookupSpan(segSpan);
  }

  // ---------------------------------------------------------------------------
  // Per-span segmentation
  // ---------------------------------------------------------------------------

  function processSpan(spanEl, lang) {
    var surface = String(spanEl.dataset.seg || '').trim();
    if (!surface) return;

    var key = getCacheKey(surface, lang);
    var cached = _cache[key];
    if (cached) {
      applyFillToSpan(spanEl, cached);
      return;
    }
    if (_pending[key]) {
      _pending[key].push(spanEl);
      spanEl.dataset.psrPending = '1';
      spanEl.dataset.psrLookupKey = key;
      return;
    }
    _pending[key] = [spanEl];
    spanEl.dataset.psrPending = '1';
    spanEl.dataset.psrLookupKey = key;
    var cacheVersion = _cacheVersions[key] || 0;

    var dictApi = window.DictionaryClient || {};
    var lookupPromise = (typeof dictApi.lookupSingle === 'function')
      ? dictApi.lookupSingle(surface, lang, { exact: true })
      : fetch('/lookup_dp_only?q=' + encodeURIComponent(surface) + '&lang=' + encodeURIComponent(lang) + '&exact=1')
          .then(function (resp) { return resp.json(); });
    lookupPromise
      .then(function (data) {
        if ((_cacheVersions[key] || 0) !== cacheVersion) return;
        var resolved = resolveLookupPayload(surface, lang, data, dictApi);
        _cache[key] = resolved;
        var waiters = _pending[key] || [];
        delete _pending[key];
        for (var wi = 0; wi < waiters.length; wi++) {
          applyFillToSpan(waiters[wi], resolved);
        }
      })
      .catch(function () {
        if ((_cacheVersions[key] || 0) !== cacheVersion) return;
        var fallback = resolveLookupPayload(surface, lang, null, dictApi);
        _cache[key] = fallback;
        var waiters = _pending[key] || [];
        delete _pending[key];
        for (var wi = 0; wi < waiters.length; wi++) {
          applyFillToSpan(waiters[wi], fallback);
        }
      });
  }

  // ---------------------------------------------------------------------------
  // DOM: inject .psr-fill-hit sub-spans for multi-piece fills
  // ---------------------------------------------------------------------------

  function applyFillToSpan(spanEl, result) {
    if (!spanEl || !result || typeof result !== 'object') return;
    spanEl.dataset.psrLookupKey = String(result.cacheKey || '');
    delete spanEl.dataset.psrPending;
    delete spanEl.dataset.psrHasFillHits;
    delete spanEl.dataset.hasFillHits;
    var fills = Array.isArray(result.fills) ? result.fills : [];
    if (fills.length <= 1) return;
    applyResolvedFillAnchors(spanEl, result);
  }

  // ---------------------------------------------------------------------------
  // Shared fill-hit construction
  // ---------------------------------------------------------------------------

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function stripZeroWidthJoiners(text) {
    return String(text || '').replace(/[\u200C\u200D]/g, '');
  }

  function normalizeClassList(baseClasses, extraClasses) {
    var out = Array.isArray(baseClasses) ? baseClasses.slice() : [];
    var extra = Array.isArray(extraClasses) ? extraClasses : (extraClasses ? [extraClasses] : []);
    for (var i = 0; i < extra.length; i++) {
      var className = String(extra[i] || '').trim();
      if (!className) continue;
      if (out.indexOf(className) >= 0) continue;
      out.push(className);
    }
    return out;
  }

  function buildDataAttrs(extraData) {
    var attrs = '';
    var data = (extraData && typeof extraData === 'object') ? extraData : null;
    if (!data) return attrs;
    for (var key in data) {
      if (!Object.prototype.hasOwnProperty.call(data, key)) continue;
      var value = data[key];
      if (value == null || value === '') continue;
      attrs += ' data-' + escapeHtml(String(key).replace(/_/g, '-')) + '="' + escapeHtml(String(value)) + '"';
    }
    return attrs;
  }

  function renderLookupSpanHtml(segText, options) {
    var rawText = String(segText || '');
    var opts = options || {};
    var displayText = String(opts.displayText != null ? opts.displayText : stripZeroWidthJoiners(rawText));
    if (!rawText || !displayText.trim()) return '';
    var classList = ['headword-component'];
    if (opts.panelToken) classList = normalizeClassList(classList, ['panel-token', 'panel-headword-token']);
    classList = normalizeClassList(classList, opts.extraClasses);
    // Add subtle blue underline only to dict entry headwords (panel-generic-headword-token)
    var styleAttr = classList.indexOf('panel-generic-headword-token') >= 0
      ? ' style="border-bottom:1px solid rgba(14,165,233,0.25);"'
      : '';
    var attrs = 'class="' + escapeHtml(classList.join(' ')) + '"' +
      styleAttr +
      ' data-seg="' + escapeHtml(rawText) + '"' +
      ' data-hover-mode="' + escapeHtml(String(opts.hoverMode || 'lookup')) + '"' +
      buildDataAttrs(opts.extraData);
    return '<span ' + attrs + '>' + escapeHtml(displayText) + '</span>';
  }

  function renderLookupSequenceHtml(rawText, options) {
    var opts = options || {};
    var decomp = Array.isArray(opts.decomp) ? opts.decomp : null;
    var html = '';
    if (decomp && decomp.length) {
      for (var i = 0; i < decomp.length; i++) {
        var comp = decomp[i];
        var compText = '';
        var compDisplay = '';
        if (comp && typeof comp === 'object') {
          compText = String(comp.head || comp.raw || '');
          compDisplay = String(comp.display != null ? comp.display : stripZeroWidthJoiners(compText));
        } else {
          compText = String(comp || '');
          compDisplay = stripZeroWidthJoiners(compText);
        }
        if (!compText || !compDisplay.trim()) continue;
        if (compText === '+' || compText === '\uFF0B') {
          html += '<span aria-hidden="true" style="opacity:0.65;pointer-events:none;">' + escapeHtml(compText) + '</span>';
          continue;
        }
        html += renderLookupSpanHtml(compText, {
          displayText: compDisplay,
          panelToken: !!opts.panelToken,
          extraClasses: opts.extraClasses
        });
      }
      return html;
    }
    var parts = String(rawText || '').split(/(\s+|[+\uFF0B])/);
    for (var pi = 0; pi < parts.length; pi++) {
      var part = String(parts[pi] || '');
      if (!part) continue;
      if (/^\s+$/.test(part)) {
        html += '<span aria-hidden="true" style="white-space:pre;">' + escapeHtml(part) + '</span>';
        continue;
      }
      if (part === '+' || part === '\uFF0B') {
        html += '<span aria-hidden="true" style="opacity:0.65;pointer-events:none;">' + escapeHtml(part) + '</span>';
        continue;
      }
      var partDisplay = stripZeroWidthJoiners(part);
      if (!partDisplay.trim()) continue;
      html += renderLookupSpanHtml(part, {
        displayText: partDisplay,
        panelToken: !!opts.panelToken,
        extraClasses: opts.extraClasses
      });
    }
    return html;
  }

  function getDictFillSurfaceText(fillEntry) {
    if (!fillEntry || typeof fillEntry !== 'object') return '';
    if (fillEntry.text != null) return String(fillEntry.text);
    if (fillEntry.head != null) return String(fillEntry.head);
    return '';
  }

  function getPrimaryLookupResult(data) {
    if (!data || typeof data !== 'object') return null;
    if (Array.isArray(data.results_by_seg) && data.results_by_seg.length) return data.results_by_seg[0] || null;
    if (Array.isArray(data.results) && data.results.length) return data.results[0] || null;
    return data;
  }

  function getLookupResultFills(result) {
    if (!result || typeof result !== 'object') return [];
    if (Array.isArray(result.dict_fill)) return result.dict_fill.slice();
    if (Array.isArray(result.fills)) return result.fills.slice();
    return [];
  }

  function getLookupResultFillSlices(result) {
    if (!result || typeof result !== 'object') return [];
    return Array.isArray(result.dict_fill_surface_slices) ? result.dict_fill_surface_slices.slice() : [];
  }

  function getTextCharOffsets(text) {
    var src = Array.from(String(text || ''));
    var out = [];
    var cursor = 0;
    for (var i = 0; i < src.length; i++) {
      var ch = src[i];
      var next = cursor + ch.length;
      out.push({ start: cursor, end: next, char: ch });
      cursor = next;
    }
    return out;
  }

  function fillVisibleWeight(fillEntry) {
    var visible = stripZeroWidthJoiners(getDictFillSurfaceText(fillEntry));
    var chars = Array.from(String(visible || ''));
    return chars.length > 0 ? chars.length : 1;
  }

  function clampSliceBounds(surfaceText, start, end) {
    var max = String(surfaceText || '').length;
    var s = parseInt(start, 10);
    var e = parseInt(end, 10);
    if (!isFinite(s) || s < 0) s = 0;
    if (!isFinite(e) || e > max) e = max;
    if (e < s) e = s;
    return { start: s, end: e };
  }

  function attachIndexesToNearestAnchor(slices, fillIndexes) {
    var anchors = Array.isArray(slices) ? slices : [];
    var ids = Array.isArray(fillIndexes) ? fillIndexes : [];
    if (!anchors.length || !ids.length) return;
    for (var i = 0; i < ids.length; i++) {
      var idx = ids[i];
      var bestAnchor = 0;
      var bestDist = Infinity;
      for (var ai = 0; ai < anchors.length; ai++) {
        var present = Array.isArray(anchors[ai].fillIndexes) ? anchors[ai].fillIndexes : [];
        for (var pi = 0; pi < present.length; pi++) {
          var dist = Math.abs(present[pi] - idx);
          if (dist < bestDist) {
            bestDist = dist;
            bestAnchor = ai;
          }
        }
      }
      appendUniqueFillIndexes(anchors[bestAnchor].fillIndexes, [idx]);
    }
  }

  function splitGroupedSliceByVisibleChars(surfaceText, start, end, fillIndexes, fills) {
    var bounds = clampSliceBounds(surfaceText, start, end);
    var sliceText = String(surfaceText || '').slice(bounds.start, bounds.end);
    var charOffsets = getTextCharOffsets(sliceText);
    var nonMarkIds = Array.isArray(fillIndexes) ? fillIndexes.slice() : [];
    if (!charOffsets.length || !nonMarkIds.length) return [];
    if (nonMarkIds.length === 1) {
      return [{ start: bounds.start, end: bounds.end, fillIndexes: nonMarkIds.slice() }];
    }
    if (charOffsets.length === 1) {
      return [{ start: bounds.start, end: bounds.end, fillIndexes: nonMarkIds.slice() }];
    }

    var out = [];

    if (charOffsets.length >= nonMarkIds.length) {
      var weights = [];
      var totalWeight = 0;
      for (var wi = 0; wi < nonMarkIds.length; wi++) {
        var weight = fillVisibleWeight(fills[nonMarkIds[wi]]);
        if (!(weight > 0)) weight = 1;
        weights.push(weight);
        totalWeight += weight;
      }
      var remainingChars = charOffsets.length;
      var remainingWeight = totalWeight;
      var charCursor = 0;
      for (var fi = 0; fi < nonMarkIds.length; fi++) {
        var remainingBuckets = nonMarkIds.length - fi;
        var take = 1;
        if (fi === nonMarkIds.length - 1) {
          take = remainingChars;
        } else {
          var expected = Math.round((weights[fi] / remainingWeight) * remainingChars);
          var minTake = 1;
          var maxTake = remainingChars - (remainingBuckets - 1);
          if (!isFinite(expected)) expected = minTake;
          take = expected;
          if (take < minTake) take = minTake;
          if (take > maxTake) take = maxTake;
        }
        var startOffset = charOffsets[charCursor].start;
        var endOffset = charOffsets[charCursor + take - 1].end;
        out.push({
          start: bounds.start + startOffset,
          end: bounds.start + endOffset,
          fillIndexes: [nonMarkIds[fi]]
        });
        charCursor += take;
        remainingChars = charOffsets.length - charCursor;
        remainingWeight -= weights[fi];
        if (remainingWeight < 1) remainingWeight = 1;
      }
      return out;
    }

    var fillCursor = 0;
    var remainingFills = nonMarkIds.length;
    for (var ci = 0; ci < charOffsets.length; ci++) {
      var remainingBuckets2 = charOffsets.length - ci;
      var take2 = 1;
      if (ci === charOffsets.length - 1) {
        take2 = remainingFills;
      } else {
        take2 = Math.max(1, Math.round(remainingFills / remainingBuckets2));
      }
      var group = nonMarkIds.slice(fillCursor, fillCursor + take2);
      if (!group.length) break;
      out.push({
        start: bounds.start + charOffsets[ci].start,
        end: bounds.start + charOffsets[ci].end,
        fillIndexes: group
      });
      fillCursor += take2;
      remainingFills = nonMarkIds.length - fillCursor;
    }
    return out;
  }

  function buildAnchorSlices(surfaceText, fills, rawSlices) {
    var surface = String(surfaceText || '');
    var rows = Array.isArray(fills) ? fills : [];
    if (!surface || rows.length < 2) return [];

    var normalized = normalizeProvidedSlices(rawSlices, rows.length);
    if (!normalized.length) return [];

    normalized.sort(function(a, b) {
      if (a.start !== b.start) return a.start - b.start;
      return a.end - b.end;
    });

    var out = [];
    var pendingMarkOnly = [];

    for (var i = 0; i < normalized.length; i++) {
      var rawSlice = normalized[i] || {};
      var bounds = clampSliceBounds(surface, rawSlice.start, rawSlice.end);
      if (bounds.end <= bounds.start) continue;
      var sliceIndexes = Array.isArray(rawSlice.fillIndexes) ? rawSlice.fillIndexes.slice() : [];
      if (!sliceIndexes.length) continue;

      var nonMarkIds = [];
      var markOnlyIds = [];
      for (var ii = 0; ii < sliceIndexes.length; ii++) {
        var fillIndex = sliceIndexes[ii];
        if (isMarkOnlySliceText(getDictFillSurfaceText(rows[fillIndex]))) markOnlyIds.push(fillIndex);
        else nonMarkIds.push(fillIndex);
      }

      if (!nonMarkIds.length) {
        pendingMarkOnly = appendUniqueFillIndexes(pendingMarkOnly, markOnlyIds);
        continue;
      }

      var exactSlice = {
        start: bounds.start,
        end: bounds.end,
        fillIndexes: nonMarkIds.slice()
      };
      if (pendingMarkOnly.length) {
        appendUniqueFillIndexes(exactSlice.fillIndexes, pendingMarkOnly);
        pendingMarkOnly = [];
      }
      if (markOnlyIds.length) appendUniqueFillIndexes(exactSlice.fillIndexes, markOnlyIds);
      out.push(exactSlice);
    }

    if (pendingMarkOnly.length) {
      if (out.length) attachIndexesToNearestAnchor(out, pendingMarkOnly);
      else {
        out.push({
          start: 0,
          end: surface.length,
          fillIndexes: pendingMarkOnly.slice()
        });
      }
    }

    return out;
  }

  function resolveLookupPayload(surface, lang, data, dictApi) {
    var primaryResult = (data && data.ok) ? getPrimaryLookupResult(data) : null;
    var fills = getLookupResultFills(primaryResult);
    var rawSlices = [];
    if (primaryResult) {
      rawSlices = getLookupResultFillSlices(primaryResult);
    }
    if ((!rawSlices || !rawSlices.length) && fills.length >= 2 && dictApi && typeof dictApi.buildFillSurfaceSlices === 'function') {
      try {
        rawSlices = dictApi.buildFillSurfaceSlices(surface, fills, lang) || [];
      } catch (_e) {
        rawSlices = [];
      }
    }
    if ((!rawSlices || !rawSlices.length) && fills.length >= 2) {
      rawSlices = buildInteractiveFillSlices(surface, fills, []);
    }
    return {
      cacheKey: lang + '|' + surface,
      surface: String(surface || ''),
      lang: String(lang || ''),
      lookupResult: primaryResult,
      fills: fills,
      slices: Array.isArray(rawSlices) ? rawSlices.slice() : [],
      anchorSlices: buildAnchorSlices(surface, fills, rawSlices)
    };
  }

  function applyResolvedFillAnchors(spanEl, result) {
    if (!spanEl || !result || typeof result !== 'object') return false;
    var surface = String(result.surface || spanEl.dataset.seg || '');
    var slices = Array.isArray(result.anchorSlices) ? result.anchorSlices : [];
    if (!surface || !slices.length) return false;

    var frag = document.createDocumentFragment();
    var cursor = 0;
    for (var i = 0; i < slices.length; i++) {
      var slice = slices[i] || {};
      var bounds = clampSliceBounds(surface, slice.start, slice.end);
      if (bounds.end <= bounds.start) continue;
      if (bounds.start > cursor) {
        frag.appendChild(document.createTextNode(surface.slice(cursor, bounds.start)));
      }
      var hit = document.createElement('span');
      var indexes = Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : [];
      hit.className = 'reader-token-fill-hit';
      hit.dataset.fillIndexes = indexes.join(',');
      if (indexes.length === 1) hit.dataset.fillIndex = String(indexes[0]);
      hit.dataset.psrLookupKey = String(result.cacheKey || '');
      hit.textContent = surface.slice(bounds.start, bounds.end);
      frag.appendChild(hit);
      cursor = bounds.end;
    }
    if (cursor < surface.length) {
      frag.appendChild(document.createTextNode(surface.slice(cursor)));
    }
    while (spanEl.firstChild) spanEl.removeChild(spanEl.firstChild);
    spanEl.appendChild(frag);
    spanEl.dataset.hasFillHits = '1';
    spanEl.dataset.psrHasFillHits = '1';
    return true;
  }

  var combiningMarkOnlyRe = (function() {
    try {
      return new RegExp('^[\\p{M}\\u200C\\u200D\\uFE00-\\uFE0F]+$', 'u');
    } catch (_e) {
      return null;
    }
  })();

  function isCombiningMarkChar(ch) {
    var text = String(ch || '');
    if (!text) return false;
    var cp = text.codePointAt(0);
    return (
      (cp >= 0x0300 && cp <= 0x036F) ||
      (cp >= 0x1AB0 && cp <= 0x1AFF) ||
      (cp >= 0x1DC0 && cp <= 0x1DFF) ||
      (cp >= 0x20D0 && cp <= 0x20FF) ||
      (cp >= 0xFE20 && cp <= 0xFE2F) ||
      (cp >= 0xFE00 && cp <= 0xFE0F)
    );
  }

  function isMarkOnlySliceText(text) {
    var value = String(text || '');
    if (!value) return false;
    if (combiningMarkOnlyRe) return combiningMarkOnlyRe.test(value);
    var chars = Array.from(value);
    if (!chars.length) return false;
    for (var i = 0; i < chars.length; i++) {
      if (chars[i] !== '\u200C' && chars[i] !== '\u200D' && !isCombiningMarkChar(chars[i])) return false;
    }
    return true;
  }

  function appendUniqueFillIndexes(target, source) {
    var out = Array.isArray(target) ? target : [];
    var seen = Object.create(null);
    for (var i = 0; i < out.length; i++) seen[out[i]] = true;
    var src = Array.isArray(source) ? source : [];
    for (var j = 0; j < src.length; j++) {
      var idx = src[j];
      if (seen[idx]) continue;
      seen[idx] = true;
      out.push(idx);
    }
    return out;
  }

  function coalesceMarkOnlyFillSlices(seg, slices) {
    if (!seg || !Array.isArray(slices) || slices.length < 2) return slices;
    var out = [];
    var pendingLeading = null;
    for (var i = 0; i < slices.length; i++) {
      var slice = slices[i] || {};
      var current = {
        start: parseInt(slice.start, 10) || 0,
        end: parseInt(slice.end, 10) || 0,
        fillIndexes: Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : []
      };
      var sliceText = seg.slice(current.start, current.end);
      if (isMarkOnlySliceText(sliceText)) {
        if (out.length) {
          out[out.length - 1].end = current.end;
          appendUniqueFillIndexes(out[out.length - 1].fillIndexes, current.fillIndexes);
        } else if (pendingLeading) {
          pendingLeading.end = current.end;
          appendUniqueFillIndexes(pendingLeading.fillIndexes, current.fillIndexes);
        } else {
          pendingLeading = current;
        }
        continue;
      }
      if (pendingLeading) {
        current.start = pendingLeading.start;
        current.fillIndexes = appendUniqueFillIndexes(pendingLeading.fillIndexes.slice(), current.fillIndexes);
        pendingLeading = null;
      }
      out.push(current);
    }
    if (pendingLeading) {
      if (out.length) {
        out[out.length - 1].end = pendingLeading.end;
        appendUniqueFillIndexes(out[out.length - 1].fillIndexes, pendingLeading.fillIndexes);
      } else {
        out.push(pendingLeading);
      }
    }
    return out;
  }

  function parseFillIndexes(fillHit, fillCount) {
    var max = parseInt(fillCount, 10);
    var out = [];
    var seen = Object.create(null);
    if (!fillHit || !fillHit.dataset) return out;
    var rawList = String(fillHit.dataset.fillIndexes || '').trim();
    if (!rawList && fillHit.dataset.fillIndex != null) rawList = String(fillHit.dataset.fillIndex);
    if (!rawList) return out;
    var parts = rawList.split(',');
    for (var i = 0; i < parts.length; i++) {
      var idx = parseInt(String(parts[i] || '').trim(), 10);
      if (!isFinite(idx) || idx < 0 || seen[idx]) continue;
      if (isFinite(max) && max >= 0 && idx >= max) continue;
      seen[idx] = true;
      out.push(idx);
    }
    return out;
  }

  function normalizeProvidedSlices(providedSlices, fillCount) {
    var rawSlices = Array.isArray(providedSlices) ? providedSlices : [];
    var out = [];
    for (var i = 0; i < rawSlices.length; i++) {
      var raw = rawSlices[i] || {};
      var start = parseInt(raw.start, 10);
      var end = parseInt(raw.end, 10);
      if (!isFinite(start) || !isFinite(end)) continue;
      var indexes = [];
      if (Array.isArray(raw.fillIndexes)) {
        indexes = raw.fillIndexes.slice();
      } else if (Array.isArray(raw.fill_indexes)) {
        indexes = raw.fill_indexes.slice();
      } else if (raw.fillIndex != null) {
        indexes = [raw.fillIndex];
      } else if (raw.fill_index != null) {
        indexes = [raw.fill_index];
      }
      indexes = parseFillIndexes({
        dataset: {
          fillIndexes: Array.isArray(indexes) ? indexes.join(',') : '',
          fillIndex: !Array.isArray(indexes) ? String(indexes) : ''
        }
      }, fillCount);
      out.push({
        start: start,
        end: end,
        fillIndexes: indexes
      });
    }
    return out;
  }

  function buildSlices(surface, fills, providedSlices) {
    return buildInteractiveFillSlices(surface, fills, providedSlices);
  }

  function buildSequentialSlices(surface, surfaces) {
    if (!surface || !Array.isArray(surfaces) || surfaces.length < 2) return null;
    var lower = String(surface || '').toLowerCase();
    var cursor = 0;
    var out = [];
    for (var i = 0; i < surfaces.length; i++) {
      var piece = String(surfaces[i] || '');
      if (!piece) return null;
      var idx = lower.indexOf(piece.toLowerCase(), cursor);
      if (idx < 0) return null;
      out.push({ start: idx, end: idx + piece.length, fillIndexes: [i] });
      cursor = idx + piece.length;
    }
    return out;
  }

  function buildProportionalSlices(surface, surfaces) {
    if (!surface || !Array.isArray(surfaces) || surfaces.length < 2) return null;
    var totalChars = 0;
    var charCounts = [];
    for (var i = 0; i < surfaces.length; i++) {
      var c = String(surfaces[i] || '').length || 1;
      charCounts.push(c);
      totalChars += c;
    }
    var out = [];
    var cursor = 0;
    for (var j = 0; j < surfaces.length; j++) {
      var isLast = (j === surfaces.length - 1);
      var end = isLast
        ? surface.length
        : Math.round(cursor + (charCounts[j] / totalChars) * surface.length);
      if (end <= cursor) end = cursor + 1;
      if (end > surface.length) end = surface.length;
      out.push({ start: cursor, end: end, fillIndexes: [j] });
      cursor = end;
    }
    return out;
  }

  function collectDictFillSurfaces(entries) {
    if (!Array.isArray(entries) || !entries.length) return null;
    var out = [];
    for (var i = 0; i < entries.length; i++) {
      var surface = getDictFillSurfaceText(entries[i]);
      if (!surface) return null;
      out.push(surface);
    }
    return out.length ? out : null;
  }

  function buildForcedProjectedDictFillSlices(seg, dictFill) {
    var token = String(seg || '');
    if (!token || !Array.isArray(dictFill) || dictFill.length < 2) return null;
    var segLen = token.length;
    if (segLen < 1) return null;
    var nonMarkFillIndexes = [];
    var nonMarkSurfaces = [];
    var markOnlyFillIndexes = [];
    for (var i = 0; i < dictFill.length; i++) {
      var rawText = getDictFillSurfaceText(dictFill[i]);
      if (isMarkOnlySliceText(rawText)) {
        markOnlyFillIndexes.push(i);
      } else {
        nonMarkFillIndexes.push(i);
        nonMarkSurfaces.push(String(rawText || 'x'));
      }
    }
    if (!nonMarkFillIndexes.length) {
      return [{
        start: 0,
        end: segLen,
        fillIndexes: dictFill.map(function(_entry, idx) { return idx; })
      }];
    }
    var rawSlices = null;
    if (segLen >= nonMarkFillIndexes.length) {
      rawSlices = buildProportionalSlices(token, nonMarkSurfaces);
    }
    if (!rawSlices || !rawSlices.length) {
      rawSlices = [];
      for (var ri = 0; ri < nonMarkFillIndexes.length; ri++) {
        var start = Math.floor((ri * segLen) / nonMarkFillIndexes.length);
        if (start >= segLen) start = segLen - 1;
        if (start < 0) start = 0;
        var end = Math.floor(((ri + 1) * segLen) / nonMarkFillIndexes.length);
        if (end <= start) end = Math.min(segLen, start + 1);
        if (end <= start) end = segLen;
        rawSlices.push({
          start: start,
          end: end,
          fillIndexes: [ri]
        });
      }
    }
    var out = [];
    for (var si = 0; si < rawSlices.length; si++) {
      var rawSlice = rawSlices[si] || {};
      var ordinal = parseInt((rawSlice.fillIndexes || [si])[0], 10);
      if (!isFinite(ordinal)) ordinal = si;
      var actualFillIndex = nonMarkFillIndexes[ordinal];
      if (!isFinite(actualFillIndex)) continue;
      var sliceStart = Number(rawSlice.start || 0);
      var sliceEnd = Number(rawSlice.end || 0);
      if (sliceStart < 0) sliceStart = 0;
      if (sliceEnd > segLen) sliceEnd = segLen;
      if (sliceEnd <= sliceStart) sliceEnd = Math.min(segLen, sliceStart + 1);
      if (sliceEnd <= sliceStart) {
        sliceStart = Math.max(0, segLen - 1);
        sliceEnd = segLen;
      }
      out.push({
        start: sliceStart,
        end: sliceEnd,
        fillIndexes: [actualFillIndex]
      });
    }
    for (var mi = 0; mi < markOnlyFillIndexes.length; mi++) {
      var markFillIndex = markOnlyFillIndexes[mi];
      var attachAt = 0;
      for (var oi = 0; oi < out.length; oi++) {
        var existingFillIndex = out[oi].fillIndexes[0];
        if (existingFillIndex <= markFillIndex) attachAt = oi;
        else break;
      }
      appendUniqueFillIndexes(out[attachAt].fillIndexes, [markFillIndex]);
    }
    return out.length ? out : null;
  }

  function buildDictFillSlicesForToken(seg, dictFill, providedSlices) {
    if (!seg || !Array.isArray(dictFill) || dictFill.length < 2) return null;
    var segLen = seg.length;
    if (segLen < 1) return null;
    var hintWidthByFill = Object.create(null);
    var rawSlices = normalizeProvidedSlices(providedSlices, dictFill.length);
    for (var hi = 0; hi < rawSlices.length; hi++) {
      var raw = rawSlices[hi] || {};
      var start = parseInt(raw.start, 10);
      var end = parseInt(raw.end, 10);
      if (!isFinite(start) || !isFinite(end) || end <= start) continue;
      if (start < 0) start = 0;
      if (end > segLen) end = segLen;
      if (end <= start) continue;
      var width = end - start;
      var indexes = Array.isArray(raw.fillIndexes) ? raw.fillIndexes.slice() : [];
      for (var ii = 0; ii < indexes.length; ii++) {
        var idx = indexes[ii];
        if (!(width > 0)) continue;
        if (!(hintWidthByFill[idx] > 0) || width > hintWidthByFill[idx]) {
          hintWidthByFill[idx] = width;
        }
      }
    }
    var nonMark = [];
    var markOnlyFillIndexes = [];
    for (var i = 0; i < dictFill.length; i++) {
      var fillSurface = getDictFillSurfaceText(dictFill[i]);
      if (isMarkOnlySliceText(fillSurface)) {
        markOnlyFillIndexes.push(i);
        continue;
      }
      var weight = Number(hintWidthByFill[i] || 0);
      if (!(weight > 0)) {
        var visibleSurface = stripZeroWidthJoiners(fillSurface);
        weight = String(visibleSurface || fillSurface || '').length;
      }
      if (!(weight > 0)) weight = 1;
      nonMark.push({
        fillIndex: i,
        weight: weight
      });
    }
    if (!nonMark.length) {
      return [{
        start: 0,
        end: segLen,
        fillIndexes: dictFill.map(function(_entry, idx) { return idx; })
      }];
    }
    var slices = [];
    if (segLen >= nonMark.length) {
      var cursor = 0;
      var remainingChars = segLen;
      var remainingWeight = 0;
      for (var wi = 0; wi < nonMark.length; wi++) remainingWeight += nonMark[wi].weight;
      for (var ni = 0; ni < nonMark.length; ni++) {
        var start = cursor;
        var take = 0;
        var remainingBuckets = nonMark.length - ni;
        if (ni === nonMark.length - 1) {
          take = remainingChars;
        } else {
          var expected = Math.round((nonMark[ni].weight / remainingWeight) * remainingChars);
          var minTake = 1;
          var maxTake = remainingChars - (remainingBuckets - 1);
          if (!isFinite(expected)) expected = minTake;
          take = expected;
          if (take < minTake) take = minTake;
          if (take > maxTake) take = maxTake;
        }
        var end = start + take;
        if (end <= start) end = Math.min(segLen, start + 1);
        if (end <= start) end = segLen;
        slices.push({
          start: start,
          end: end,
          fillIndexes: [nonMark[ni].fillIndex]
        });
        cursor = end;
        remainingChars = segLen - cursor;
        remainingWeight -= nonMark[ni].weight;
        if (remainingWeight < 1) remainingWeight = 1;
      }
    } else {
      for (var pi = 0; pi < nonMark.length; pi++) {
        var pStart = Math.floor((pi * segLen) / nonMark.length);
        if (pStart >= segLen) pStart = segLen - 1;
        if (pStart < 0) pStart = 0;
        var pEnd = Math.floor(((pi + 1) * segLen) / nonMark.length);
        if (pEnd <= pStart) pEnd = Math.min(segLen, pStart + 1);
        if (pEnd <= pStart) pEnd = segLen;
        slices.push({
          start: pStart,
          end: pEnd,
          fillIndexes: [nonMark[pi].fillIndex]
        });
      }
    }
    for (var mi = 0; mi < markOnlyFillIndexes.length; mi++) {
      var markFillIndex = markOnlyFillIndexes[mi];
      var attachAt = 0;
      for (var si = 0; si < slices.length; si++) {
        var existingFillIndex = slices[si].fillIndexes[0];
        if (existingFillIndex <= markFillIndex) attachAt = si;
        else break;
      }
      appendUniqueFillIndexes(slices[attachAt].fillIndexes, [markFillIndex]);
    }
    return slices.length ? slices : null;
  }

  function buildInteractiveFillSlices(seg, dictFill, providedSlices) {
    var slices = buildDictFillSlicesForToken(seg, dictFill, providedSlices);
    if (slices && slices.length) return coalesceMarkOnlyFillSlices(seg, slices);
    var surfaces = collectDictFillSurfaces(dictFill);
    if (surfaces && surfaces.length) {
      var seq = buildSequentialSlices(seg, surfaces);
      if (seq && seq.length) return coalesceMarkOnlyFillSlices(seg, seq);
    }
    if (Array.isArray(dictFill) && dictFill.length >= 2) {
      var forced = buildForcedProjectedDictFillSlices(seg, dictFill);
      if (forced && forced.length) return coalesceMarkOnlyFillSlices(seg, forced);
    }
    return null;
  }

  function buildExactDictFillSlicesForToken(seg, dictFill, providedSlices) {
    if (!seg || !Array.isArray(dictFill) || dictFill.length < 2) return null;
    var slices = [];
    var lastEnd = 0;
    if (Array.isArray(providedSlices) && providedSlices.length) {
      for (var i = 0; i < providedSlices.length; i++) {
        var raw = providedSlices[i] || {};
        var start = parseInt(raw.start, 10);
        var end = parseInt(raw.end, 10);
        if (!isFinite(start) || !isFinite(end) || start < 0 || end > seg.length || end <= start) return null;
        if (start < lastEnd) return null;
        var indexes = [];
        if (Array.isArray(raw.fillIndexes)) indexes = raw.fillIndexes.slice();
        else if (Array.isArray(raw.fill_indexes)) indexes = raw.fill_indexes.slice();
        else if (raw.fillIndex != null) indexes = [raw.fillIndex];
        else if (raw.fill_index != null) indexes = [raw.fill_index];
        indexes = parseFillIndexes({
          dataset: {
            fillIndexes: indexes.join(','),
            fillIndex: indexes.length === 1 ? String(indexes[0]) : ''
          }
        }, dictFill.length);
        if (!indexes.length) return null;
        slices.push({
          start: start,
          end: end,
          fillIndexes: indexes
        });
        lastEnd = end;
      }
      return coalesceMarkOnlyFillSlices(seg, slices);
    }
    var pendingLeading = [];
    var exactSlices = [];
    var cursor = 0;
    var segLower = seg.toLowerCase();
    for (var fi = 0; fi < dictFill.length; fi++) {
      var fillText = getDictFillSurfaceText(dictFill[fi]);
      if (!fillText) continue;
      if (isMarkOnlySliceText(fillText)) {
        pendingLeading.push(fi);
        continue;
      }
      var idx = segLower.indexOf(fillText.toLowerCase(), cursor);
      if (idx < 0) return null;
      var nextSlice = {
        start: idx,
        end: idx + fillText.length,
        fillIndexes: [fi]
      };
      if (pendingLeading.length) {
        nextSlice.fillIndexes = appendUniqueFillIndexes(pendingLeading.slice(), nextSlice.fillIndexes);
        pendingLeading = [];
      }
      exactSlices.push(nextSlice);
      cursor = nextSlice.end;
    }
    if (pendingLeading.length) {
      if (!exactSlices.length) return null;
      appendUniqueFillIndexes(exactSlices[exactSlices.length - 1].fillIndexes, pendingLeading);
    }
    return exactSlices.length ? exactSlices : null;
  }

  function buildFillHitModel(surface, dictFill, providedSlices) {
    var token = String(surface || '');
    var fills = Array.isArray(dictFill) ? dictFill : [];
    if (!token || fills.length < 2) return null;
    var slices = buildExactDictFillSlicesForToken(token, fills, providedSlices);
    if (!slices || !slices.length) {
      slices = buildInteractiveFillSlices(token, fills, providedSlices);
    }
    if (!slices || !slices.length) return null;
    return {
      surface: token,
      fills: fills,
      slices: slices
    };
  }

  function applyFillHitTargets(spanEl, surface, dictFill, providedSlices, options) {
    if (!spanEl) return false;
    var model = buildFillHitModel(surface, dictFill, providedSlices);
    if (!model) return false;
    var opts = options || {};
    var frag = document.createDocumentFragment();
    var cursor = 0;
    for (var i = 0; i < model.slices.length; i++) {
      var slice = model.slices[i];
      if (slice.start > cursor) {
        frag.appendChild(document.createTextNode(model.surface.slice(cursor, slice.start)));
      }
      var partText = model.surface.slice(slice.start, slice.end);
      var fillIndexes = Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : [];
      var fillEntry = fillIndexes.length ? (model.fills[fillIndexes[0]] || {}) : {};
      var hit = document.createElement('span');
      hit.className = 'reader-token-fill-hit';
      hit.dataset.fillIndexes = fillIndexes.join(',');
      if (fillIndexes.length === 1) hit.dataset.fillIndex = String(fillIndexes[0]);
      hit.dataset.fillText = partText;
      if (fillEntry.head != null) {
        hit.dataset.fillHead = String(fillEntry.head);
      } else if (fillEntry.text != null) {
        hit.dataset.fillHead = String(fillEntry.text);
      }
      hit.textContent = partText;
      frag.appendChild(hit);
      cursor = slice.end;
    }
    if (cursor < model.surface.length) {
      frag.appendChild(document.createTextNode(model.surface.slice(cursor)));
    }
    while (spanEl.firstChild) spanEl.removeChild(spanEl.firstChild);
    spanEl.appendChild(frag);
    spanEl.dataset.hasFillHits = '1';
    var hostFlagName = String(opts.hostFlagName || '').trim();
    if (hostFlagName) {
      spanEl.dataset[hostFlagName] = '1';
    }
    return true;
  }

  function buildFillHitHtml(surface, dictFill, providedSlices) {
    var model = buildFillHitModel(surface, dictFill, providedSlices);
    if (!model) {
      return {
        html: escapeHtml(surface || ''),
        hasFillHits: false,
        slices: []
      };
    }
    var parts = [];
    var cursor = 0;
    for (var i = 0; i < model.slices.length; i++) {
      var slice = model.slices[i];
      if (slice.start > cursor) parts.push(escapeHtml(model.surface.slice(cursor, slice.start)));
      var fillIndexes = Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : [];
      var fillEntry = fillIndexes.length ? (model.fills[fillIndexes[0]] || {}) : {};
      var partText = model.surface.slice(slice.start, slice.end);
      var attrs = ' class="reader-token-fill-hit" data-fill-indexes="' + escapeHtml(fillIndexes.join(',')) + '"';
      if (fillIndexes.length === 1) attrs += ' data-fill-index="' + escapeHtml(String(fillIndexes[0])) + '"';
      attrs += ' data-fill-text="' + escapeHtml(partText) + '"';
      if (fillEntry.head != null) attrs += ' data-fill-head="' + escapeHtml(String(fillEntry.head)) + '"';
      else if (fillEntry.text != null) attrs += ' data-fill-head="' + escapeHtml(String(fillEntry.text)) + '"';
      parts.push('<span' + attrs + '>' + escapeHtml(partText) + '</span>');
      cursor = slice.end;
    }
    if (cursor < model.surface.length) parts.push(escapeHtml(model.surface.slice(cursor)));
    return {
      html: parts.join(''),
      hasFillHits: true,
      slices: model.slices.slice()
    };
  }

  function renderLookupTokenHtml(tokenText, role, dictFill, providedSlices, options) {
    void dictFill;
    void providedSlices;
    var tokenValue = String(tokenText || '');
    var opts = options || {};
    if (!tokenValue) return '';
    var extraClasses = ['panel-token'];
    var roleName = String(role || '').trim();
    if (roleName) extraClasses.push('panel-' + roleName + '-token');
    return renderLookupSpanHtml(tokenValue, {
      displayText: String(opts.tokenDisplay != null ? opts.tokenDisplay : stripZeroWidthJoiners(tokenValue)),
      panelToken: true,
      extraClasses: extraClasses,
      extraData: {
        panel_head_role: roleName || 'surface',
        token_map_lookup: roleName || 'surface',
        token_map_lookup_key: String(opts.lookupKey != null ? opts.lookupKey : tokenValue),
        token_map_part_index: isFinite(opts.tokenMapPartIndex) ? parseInt(opts.tokenMapPartIndex, 10) : ''
      }
    });
  }

  function buildHoverTargetPayload(cacheKey, fillIndexes) {
    var key = String(cacheKey || '').trim();
    var cached = key ? _cache[key] : null;
    if (!cached || !cached.lookupResult) return null;
    var payload = {
      seg: String(cached.surface || ''),
      lookupResult: cached.lookupResult
    };
    if (Array.isArray(fillIndexes) && fillIndexes.length) payload.fillIndexes = fillIndexes.slice();
    return payload;
  }

  function clearLookupHover() {
    _currentHoverKey = null;
    if (typeof _setHoveredElement === 'function') _setHoveredElement(null);
    if (typeof _hidePopup === 'function') _hidePopup();
  }

  function applyLookupHover(target, key, anchorEl, clientX, clientY) {
    if (!target || !_showPopup) {
      clearLookupHover();
      return;
    }
    if (typeof _setHoveredElement === 'function') _setHoveredElement(anchorEl || null);
    if (typeof _positionPopup === 'function' && isFinite(clientX) && isFinite(clientY)) {
      _positionPopup(clientX, clientY);
    }
    if (key === _currentHoverKey) return;
    _currentHoverKey = key;
    _showPopup(target);
  }

  // ---------------------------------------------------------------------------
  // Hover listener
  // ---------------------------------------------------------------------------

  function attachHoverListener(containerEl) {
    if (containerEl._psrCleanup) containerEl._psrCleanup();

    function onMouseMove(ev) {
      if (!_showPopup) return;

      var hit = ev.target && ev.target.closest ? ev.target.closest('.reader-token-fill-hit') : null;
      if (hit && hit.closest && hit.closest('.dict-entries-container')) {
        // Allow fill-hits that are children of a base-form token.
        var hitParentSpan = hit.parentNode && hit.parentNode.classList ? hit.parentNode : null;
        if (!hitParentSpan || !hitParentSpan.classList.contains('panel-base-form-token')) {
          clearLookupHover();
          return;
        }
      }
      if (hit && containerEl.contains(hit)) {
        var hitLookupKey = String(hit.dataset.psrLookupKey || (hit.parentNode && hit.parentNode.dataset ? hit.parentNode.dataset.psrLookupKey : '') || '').trim();
        var hitCached = hitLookupKey ? _cache[hitLookupKey] : null;
        var hitFillCount = hitCached && Array.isArray(hitCached.fills) ? hitCached.fills.length : -1;
        var activeFillIndexes = parseFillIndexes(hit, hitFillCount);
        var hitPayload = buildHoverTargetPayload(hitLookupKey, activeFillIndexes);
        if (!hitPayload) {
          clearLookupHover();
          return;
        }
        applyLookupHover(hitPayload, 'psr-fill|' + hitLookupKey + '|' + activeFillIndexes.join(','), hit, ev.clientX, ev.clientY);
        return;
      }

      var segSpan = ev.target && ev.target.closest
        ? ev.target.closest('.headword-component[data-seg], [data-seg][data-hover-mode="lookup"]')
        : null;
      // Dictionary entry text (surface slice, headwords, base forms,
      // mwt-child tokens rendered inside .dict-entries-container) is fully
      // non-interactive — no segmentation, no hover lookup. The token
      // banner lives outside this container and stays fully live.
      // The decomp hover popup in reader.js owns headword interactions now.
      if (segSpan && segSpan.closest && segSpan.closest('.dict-entries-container')) {
        // Base-form tokens are the one exception: they sit inside dict-entries-container
        // but should still be hoverable/inspectable.
        if (!segSpan.classList.contains('panel-base-form-token')) {
          clearLookupHover();
          return;
        }
      }
      if (segSpan && containerEl.contains(segSpan) && isLookupSpan(segSpan)) {
        if (String(segSpan.dataset.psrPending || '') === '1') {
          clearLookupHover();
          return;
        }
        if (String(segSpan.dataset.psrHasFillHits || segSpan.dataset.hasFillHits || '') === '1') {
          clearLookupHover();
          return;
        }
        var seg2 = String(segSpan.dataset.seg || '');
        var segLookupKey = String(segSpan.dataset.psrLookupKey || '').trim();
        var segPayload = buildHoverTargetPayload(segLookupKey, []);
        if (!segPayload && seg2) segPayload = seg2;
        applyLookupHover(segPayload, 'psr-single|' + (segLookupKey || seg2), segSpan, ev.clientX, ev.clientY);
        return;
      }

      clearLookupHover();
    }

    function onMouseLeave() {
      clearLookupHover();
    }

    containerEl.addEventListener('mousemove', onMouseMove);
    containerEl.addEventListener('mouseleave', onMouseLeave);
    containerEl._psrCleanup = function () {
      containerEl.removeEventListener('mousemove', onMouseMove);
      containerEl.removeEventListener('mouseleave', onMouseLeave);
      delete containerEl._psrCleanup;
    };
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  window.PanelSegmentRenderer = {
    init: init,
    processPanel: processPanel,
    hasLookupTarget: hasLookupTarget,
    buildSlicesForSurface: buildSlices,
    renderLookupSpanHtml: renderLookupSpanHtml,
    renderLookupSequenceHtml: renderLookupSequenceHtml,
    buildFillHitHtml: buildFillHitHtml,
    renderLookupTokenHtml: renderLookupTokenHtml,
    applyFillHitTargets: applyFillHitTargets,
    parseFillIndexes: parseFillIndexes,
    invalidateLookup: invalidateLookup,
    invalidateByStorageId: invalidateByStorageId
  };

})();
