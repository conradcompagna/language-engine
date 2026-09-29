import { getUdInfoForSegment } from './dependency-hover.mjs';
import { ensureLmWeightsInitialized } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { syncInlineDepTree } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { refreshSeparateGrammarPopup } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getOrderedCompoundLemmaTexts } from './entry-editing.mjs';
import { _surfaceHasGlossableChar } from './gloss-entries.mjs';
import { loadDisplaySettings, saveDisplaySettings } from './gloss-requests.mjs';
import { getDependencyHoverText, normalizeDepLabel } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { orthographyState } from './orthography.state.mjs';
import {
  escapeHtml,
  getManualSentenceSegmentationForLanguage,
  isManualSentenceSegmentationSupportedLanguage
} from './presentation.mjs';
import { renderSegments } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { hidePopup } from './side-panel.mjs';
import { tokenBannerMenuState } from './token-banner-menu.state.mjs';
import { renderTokenBanner } from './token-banner.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export // -- Orth breakdown request helper --

// Build HTML for the ORTH row: grapheme clusters with codepoint decomp in brackets.
// Returns the inner HTML for one sub-unit (no "+" joining).  Compact styling.
function _isOrthInvisibleCodePoint(ch) {
  if (!ch) return false;
  var cp = ch.codePointAt(0);
  if (!isFinite(cp)) return false;
  return (
    cp === 0x00ad || // soft hyphen
    cp === 0x034f || // combining grapheme joiner
    cp === 0x061c || // arabic letter mark
    cp === 0x180e || // mongolian vowel separator
    cp === 0x200b || // zero width space
    cp === 0x200c || // zero width non-joiner
    cp === 0x200d || // zero width joiner
    cp === 0x2060 || // word joiner
    cp === 0xfeff || // zero width no-break space
    (cp >= 0xfe00 && cp <= 0xfe0f) || // variation selectors
    (cp >= 0xe0100 && cp <= 0xe01ef)
  ); // variation selectors supplementary
}
export function _isOrthCombiningCodePoint(ch) {
  if (!ch) return false;
  return /\p{Mark}/u.test(String(ch));
}
export function _formatOrthCodePointLabel(ch) {
  if (!ch) return '';
  var cp = ch.codePointAt(0);
  if (!isFinite(cp)) return '';
  return 'U+' + cp.toString(16).toUpperCase();
}
export function _buildOrthCodePointHtml(ch) {
  if (!ch) return '';
  var label = _formatOrthCodePointLabel(ch);
  if (_isOrthInvisibleCodePoint(ch)) {
    return (
      '<span class="orth-cp-unit orth-cp-unit-zero" title="' +
      escapeHtml(label) +
      '">' +
      escapeHtml(label) +
      '</span>'
    );
  }
  if (_isOrthCombiningCodePoint(ch)) {
    // ◌ (U+25CC) is the conventional dotted-circle anchor for combining marks.
    // The outer border/box is removed from .orth-cp-unit-mark CSS so only the
    // dotted circle itself shows, not a second enclosing rectangle.
    return (
      '<span class="orth-cp-unit orth-cp-unit-mark" title="' +
      escapeHtml(label) +
      '">&#9676;' +
      escapeHtml(ch) +
      '</span>'
    );
  }
  return '<span class="orth-cp-unit">' + escapeHtml(ch) + '</span>';
}
export function _buildOrthSurfaceClusterHtml(gc) {
  if (!gc) return '';
  var cps = Array.from(gc);
  if (cps.length === 1 && (_isOrthInvisibleCodePoint(cps[0]) || _isOrthCombiningCodePoint(cps[0]))) {
    return _buildOrthCodePointHtml(cps[0]);
  }
  return escapeHtml(gc);
}
export function _getOrthDecompositionCodePoints(text) {
  var raw = Array.from(String(text || ''));
  if (!raw.length) return raw;
  try {
    var decomposed = Array.from(String(text || '').normalize('NFD'));
    if (decomposed.length > raw.length) return decomposed;
    if (decomposed.join('') !== raw.join('')) return decomposed;
  } catch (e) {}
  return raw;
}
export function _buildOrthHtmlForUnit(text) {
  if (!text) return '';
  var clusters = _graphemeClusters(text);
  if (!clusters.length) return '';
  var parts = [];
  for (var i = 0; i < clusters.length; i++) {
    var gc = clusters[i];
    // Show surface cluster only — decomp brackets suppressed for readability.
    // (Decomp logic above is preserved for future hover popups.)
    parts.push(_buildOrthSurfaceClusterHtml(gc));
  }
  return parts.join(' ');
}
export function _getGraphemePronunciationApi() {
  var api = null;
  if (typeof window !== 'undefined') {
    api = window.GraphemePronunciationProfiles || window.grapheme_pronunciation_profiles || null;
  }
  return api && typeof api.analyzeCluster === 'function' ? api : null;
}
export function _getLocalBreakdownSubTexts(surface, udTok) {
  if (!surface) return [];
  var subTexts = [];
  var mwtParts = udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length ? udTok.mwt_parts : null;
  var lemmaRaw = udTok && udTok.lemma ? String(udTok.lemma) : '';
  if (mwtParts && mwtParts.length > 1) {
    for (var i = 0; i < mwtParts.length; i++) {
      var part =
        typeof mwtParts[i] === 'string'
          ? mwtParts[i]
          : (mwtParts[i] && (mwtParts[i].text || mwtParts[i].form)) || '';
      if (part) subTexts.push(part);
    }
  } else if (lemmaRaw && lemmaRaw.indexOf('+') !== -1) {
    var lparts = lemmaRaw.split('+');
    for (var j = 0; j < lparts.length; j++) {
      var lp = lparts[j].trim();
      if (lp) subTexts.push(lp);
    }
  }
  if (!subTexts.length) subTexts = [surface];
  return subTexts;
}
export function _formatPhonSoundValue(rawSound) {
  var text = String(rawSound || '').trim();
  return text || 'UNK';
}
export function _isPhonCombiningOnlyText(text) {
  var value = String(text || '');
  return !!value && /^\p{Mark}+$/u.test(value);
}

// isSilent=true means the empty sound is intentional (known silent diacritic).
// isSilent=false/undefined means truly unknown.
export function _buildPhonSoundHtml(rawSound, isSilent) {
  var text = String(rawSound == null ? '' : rawSound).trim();
  var className = 'phon-cp-unit';
  var innerHtml;
  if (text === '') {
    if (isSilent) {
      className += ' phon-cp-unit-silent';
      innerHtml = '\u2205'; // ∅
    } else {
      className += ' phon-cp-unit-unk';
      innerHtml = 'UNK';
    }
  } else if (_isPhonCombiningOnlyText(text)) {
    className += ' phon-cp-unit-mark';
    innerHtml = '&#9676;' + escapeHtml(text);
  } else {
    innerHtml = escapeHtml(text);
  }
  return '<span class="' + className + '">' + innerHtml + '</span>';
}

// Log truly unknown phoneme marks to the server for later engine improvement.
// Deduped in-memory so repeat marks in one session don't spam the endpoint.
export function _logUnknownPhonMark(ch, lang) {
  if (!ch) return;
  var key = lang + '|' + ch;
  if (orthographyState._unknownPhonMarksSeen[key]) return;
  orthographyState._unknownPhonMarksSeen[key] = true;
  try {
    fetch('/api/log_unknown_phon_mark', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        char: ch,
        lang: lang || documentShellState.currentLanguage || ''
      })
    }).catch(function () {});
  } catch (e) {}
}
export function _buildPhonHtmlForUnit(text, rawLang) {
  if (!text) return '';
  var api = _getGraphemePronunciationApi();
  if (!api) return '';
  var lang = String(rawLang || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  if (typeof api.getLanguageProfile === 'function' && !api.getLanguageProfile(lang)) return '';
  var clusters = _graphemeClusters(text);
  if (!clusters.length) return '';
  var parts = [];
  for (var i = 0; i < clusters.length; i++) {
    var gc = clusters[i];
    var analysis = null;
    try {
      analysis = api.analyzeCluster(lang, gc, {
        normalize: true,
        decompose: true,
        compatibility: true,
        preserveUnknown: false
      });
    } catch (e) {
      analysis = null;
    }
    if (!analysis) {
      // analysis=null means the engine had no data at all — truly unknown
      parts.push(_buildPhonSoundHtml('', false));
      _logUnknownPhonMark(gc, lang);
      continue;
    }
    var clusterSound = String(analysis.sound == null ? '' : analysis.sound).trim();
    // If the engine returned a result (analysis != null) with sound="", it's a known
    // silent character (e.g. sukun diacritic, tatweel). Only flag as UNK when the
    // engine had no data (analysis === null, handled above).
    // Skip silent clusters (tatweel, standalone diacritics etc) — nothing to show.
    // Part decomp brackets suppressed for readability; logic preserved for future hover.
    if (clusterSound === '') continue;
    parts.push(_buildPhonSoundHtml(clusterSound, false));
  }
  if (!parts.length) return '';
  return parts.join(' ');
}

// Build full ORTH row HTML for a token, splitting MWT / compound lemmas.
// Sub-units are joined with " + " (matching the LLM gloss / ROM format).
export function _buildOrthRowContent(surface, udTok) {
  if (!surface) return '';
  var subTexts = _getLocalBreakdownSubTexts(surface, udTok);
  if (!subTexts.length) return '';
  var htmlParts = [];
  for (var m = 0; m < subTexts.length; m++) {
    htmlParts.push(_buildOrthHtmlForUnit(subTexts[m]));
  }
  return htmlParts.join('<span style="margin:0 4px;color:#b45309;">+</span>');
}
export function _buildPhonRowContent(surface, udTok, rawLang) {
  if (!surface) return '';
  var subTexts = _getLocalBreakdownSubTexts(surface, udTok);
  if (!subTexts.length) return '';
  var htmlParts = [];
  for (var i = 0; i < subTexts.length; i++) {
    var partHtml = _buildPhonHtmlForUnit(subTexts[i], rawLang);
    if (partHtml) htmlParts.push(partHtml);
  }
  if (!htmlParts.length) return '';
  return htmlParts.join('<span style="margin:0 4px;color:#0f766e;">+</span>');
}
export function _wrapOrthDisplayHtml(innerHtml, className, direction) {
  var html = String(innerHtml || '').trim();
  if (!html) return '';
  var dir = String(direction || 'auto').trim() || 'auto';
  return (
    '<span class="' +
    escapeHtml(String(className || '').trim()) +
    '" dir="' +
    escapeHtml(dir) +
    '">' +
    html +
    '</span>'
  );
}

// Segment text into Unicode grapheme clusters
export function _graphemeClusters(text) {
  var clusters = [];
  if (typeof Intl !== 'undefined' && Intl.Segmenter) {
    var segmenter = new Intl.Segmenter(undefined, {
      granularity: 'grapheme'
    });
    var iter = segmenter.segment(text);
    for (var s of iter) {
      clusters.push(s.segment);
    }
  } else {
    var arr = Array.from(text);
    for (var i = 0; i < arr.length; i++) clusters.push(arr[i]);
  }
  return clusters;
}
export function _buildOrthBreakdownChunks(data) {
  var segments = data.segments || [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udOverlay = data.ud_overlay || {};
  var udTokens = udOverlay.tokens && Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  var CHUNK_SIZE = 100;

  // Build token list, splitting MWT and Korean compound lemmas into sub-parts
  var allTokens = [];
  for (var ti = 0; ti < segments.length; ti++) {
    var seg = segments[ti];
    if (!_surfaceHasGlossableChar(seg)) {
      allTokens.push({
        texts: null,
        idx: ti
      }); // skip marker
      continue;
    }
    var udTok = null;
    for (var ui = 0; ui < udTokens.length; ui++) {
      if (udTokens[ui] && udTokens[ui].i === ti) {
        udTok = udTokens[ui];
        break;
      }
    }
    var resultEntry = ti >= 0 && ti < resultsBySeg.length ? resultsBySeg[ti] || null : null;
    var mwtParts = udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length ? udTok.mwt_parts : null;
    var subTexts = [];
    if (mwtParts && mwtParts.length > 1) {
      // MWT token: feed each surface slice separately
      for (var mi = 0; mi < mwtParts.length; mi++) {
        var part =
          typeof mwtParts[mi] === 'string'
            ? mwtParts[mi]
            : mwtParts[mi].text || mwtParts[mi].form || String(mwtParts[mi]);
        if (part && _surfaceHasGlossableChar(part)) subTexts.push(part);
      }
    } else {
      // Korean-style compound lemma: feed lemma parts
      var lemmaParts = getOrderedCompoundLemmaTexts(seg, {
        entry: resultEntry,
        udTok: udTok
      });
      for (var li = 0; li < lemmaParts.length; li++) {
        var lp = String(lemmaParts[li] || '').trim();
        if (lp && _surfaceHasGlossableChar(lp)) subTexts.push(lp);
      }
    }
    if (!subTexts.length) subTexts = [seg];
    allTokens.push({
      texts: subTexts,
      idx: ti
    });
  }
  var result = [];
  for (var start = 0; start < allTokens.length; start += CHUNK_SIZE) {
    var end = Math.min(start + CHUNK_SIZE, allTokens.length);
    var chunkTokens = [];
    var chunkIndices = [];
    var chunkSlotCounts = []; // how many sub-parts per token (for server-side + joining)
    for (var j = start; j < end; j++) {
      if (!allTokens[j].texts) continue; // skip non-glossable
      var texts = allTokens[j].texts;
      for (var si = 0; si < texts.length; si++) {
        chunkTokens.push({
          text: texts[si],
          graphemes: _graphemeClusters(texts[si])
        });
      }
      chunkIndices.push(allTokens[j].idx);
      chunkSlotCounts.push(texts.length);
    }
    if (chunkTokens.length) {
      result.push({
        tokens: chunkTokens,
        indices: chunkIndices,
        slot_counts: chunkSlotCounts
      });
    }
  }
  return result;
}
export function _fireOrthBreakdownRequest(data) {
  if (!dependencyPopupState.displaySettings.orthBreakdown) return;
  var segments = data.segments || [];
  if (!segments.length) return;
  var chunks = _buildOrthBreakdownChunks(data);
  if (!chunks.length) return;
  var lang = documentShellState.currentLanguage || '';
  var seq = ++hoverLayoutState.latestOrthBreakdownSeq;
  hoverLayoutState.latestOrthBreakdowns = new Array(segments.length).fill(null);
  _refreshOrthBreakdownUI();
  fetch('/api/orth_breakdowns', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      chunks: chunks,
      lang: lang
    })
  })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      function pump() {
        return reader.read().then(function (chunk) {
          if (seq !== hoverLayoutState.latestOrthBreakdownSeq) {
            reader.cancel();
            return;
          }
          if (chunk.done) return;
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
              if (msg.done) return;
              if (msg.error) {
                console.warn('Orth rom error:', msg.error);
                return;
              }
              if (Array.isArray(msg.indices) && Array.isArray(msg.roms)) {
                for (var mi = 0; mi < msg.indices.length; mi++) {
                  hoverLayoutState.latestOrthBreakdowns[msg.indices[mi]] = msg.roms[mi];
                }
                _refreshOrthBreakdownUI();
              }
            } catch (e) {}
          }
          return pump();
        });
      }
      return pump();
    })
    .catch(function (err) {
      console.warn('Orth rom request failed:', err);
    });
}
export function _refreshOrthBreakdownUI() {
  if (hoverLayoutState.tokenMapData && document.getElementById('token-banner')) {
    renderTokenBanner(tokenBannerMenuState._bannerActiveFillKey);
  }
}
export function _refreshLlmGlossUI(reason) {
  // If a token banner is currently displayed, re-render it
  if (hoverLayoutState.tokenMapData && document.getElementById('token-banner')) {
    renderTokenBanner(tokenBannerMenuState._bannerActiveFillKey);
  }
  refreshSeparateGrammarPopup();
  syncInlineDepTree('llm-gloss-refresh');
}
export function _refreshLlmDecompUI() {
  if (hoverLayoutState.tokenMapData && document.getElementById('token-banner')) {
    renderTokenBanner(tokenBannerMenuState._bannerActiveFillKey);
  }
  if (
    hoverLayoutState.grammarPopup &&
    hoverLayoutState.grammarPopup.style.display !== 'none' &&
    hoverLayoutState.grammarPopup.innerHTML
  ) {
    // Grammar popup follows the same refresh behavior as LLM gloss rows.
  }
}

// Load settings on startup
export function applyViewMode() {
  var showDep = !!dependencyPopupState.displaySettings.depTreeView;
  if (hoverLayoutState.renderedText) hoverLayoutState.renderedText.style.display = showDep ? 'none' : 'block';
  if (hoverLayoutState.depTreeViewEl)
    hoverLayoutState.depTreeViewEl.style.display = showDep ? 'block' : 'none';
  if (window.DepTreeView && typeof window.DepTreeView.setVisible === 'function') {
    window.DepTreeView.setVisible(showDep);
  }
  if (showDep) {
    if (window.DepTreeView && typeof window.DepTreeView.refitView === 'function') {
      window.DepTreeView.refitView();
    }
    hidePopup();
  }
}
export function initDepTreeView() {
  if (!hoverLayoutState.depTreeViewEl || !window.DepTreeView || typeof window.DepTreeView.init !== 'function')
    return;
  lookupProgressState.depTreeController = window.DepTreeView;
  lookupProgressState.depTreeController.init({
    container: hoverLayoutState.depTreeViewEl,
    chunkHighlight: dependencyPopupState.displaySettings.chunkHighlight,
    dictPopup: dependencyPopupState.displaySettings.dictPopup,
    linearClauseSplit: dependencyPopupState.displaySettings.linearClauseSplit,
    branchDepthMin: dependencyPopupState.displaySettings.branchDepthMin,
    clauseDepthDrop: dependencyPopupState.displaySettings.clauseDepthDrop,
    bottomUpChunkThreshold: dependencyPopupState.displaySettings.bottomUpChunkThreshold
  });
  if (typeof lookupProgressState.depTreeController.setSourceToggleState === 'function') {
    lookupProgressState.depTreeController.setSourceToggleState(lookupProgressState.depTreeUseConllu);
  }
  if (
    lookupProgressState.depTreeUseConllu &&
    lookupProgressState.depTreeConlluMetaUrl &&
    lookupProgressState.depTreeConlluUrl &&
    typeof lookupProgressState.depTreeController.loadConlluSentenceSource === 'function'
  ) {
    lookupProgressState.depTreeController.loadConlluSentenceSource(
      lookupProgressState.depTreeConlluMetaUrl,
      lookupProgressState.depTreeConlluUrl
    );
  } else if (
    lookupProgressState.depTreeUseConllu &&
    lookupProgressState.depTreeConlluUrl &&
    typeof lookupProgressState.depTreeController.loadConlluFromUrl === 'function'
  ) {
    lookupProgressState.depTreeController.loadConlluFromUrl(lookupProgressState.depTreeConlluUrl);
  }
  lookupProgressState.depTreeController.setVisible(dependencyPopupState.displaySettings.depTreeView);
}
export function updateDepTreeFromLatestData() {
  if (
    !lookupProgressState.depTreeController ||
    typeof lookupProgressState.depTreeController.setData !== 'function'
  )
    return;
  if (!hoverLayoutState.latestSegments || !dependencyState.latestUdOverlay) {
    lookupProgressState.depTreeController.setData({
      segments: [],
      udOverlay: null
    });
    return;
  }
  lookupProgressState.depTreeController.debugMode = false;
  lookupProgressState.depTreeController.changedTokens = null;
  lookupProgressState.depTreeController.changeDetails = null;
  lookupProgressState.depTreeController.fills = lookupProgressState.latestFillsDict || {};
  lookupProgressState.depTreeController.setData({
    segments: hoverLayoutState.latestSegments,
    udOverlay: dependencyState.latestUdOverlay,
    originalText: lookupProgressState.latestOriginalText
  });
}
export function setDepTreeSourceMode(useConllu) {
  lookupProgressState.depTreeUseConllu = !!useConllu;
  if (
    lookupProgressState.depTreeController &&
    typeof lookupProgressState.depTreeController.setSourceToggleState === 'function'
  ) {
    lookupProgressState.depTreeController.setSourceToggleState(lookupProgressState.depTreeUseConllu);
  }
  if (lookupProgressState.depTreeUseConllu) {
    if (
      lookupProgressState.depTreeController &&
      typeof lookupProgressState.depTreeController.loadConlluSentenceSource === 'function'
    ) {
      lookupProgressState.depTreeController.loadConlluSentenceSource(
        lookupProgressState.depTreeConlluMetaUrl,
        lookupProgressState.depTreeConlluUrl
      );
    }
  } else {
    if (
      lookupProgressState.depTreeController &&
      typeof lookupProgressState.depTreeController.clearSentenceSource === 'function'
    ) {
      lookupProgressState.depTreeController.clearSentenceSource();
    }
    updateDepTreeFromLatestData();
  }
}
export function getCurrentHoverSegIdx() {
  if (!segmentRenderingState.currentSpan) return -1;
  var base = segmentRenderingState.currentSpan;
  if (!base || !base.dataset) return -1;
  return parseInt(base.dataset.index || '-1', 10);
}
export function appendDepDescriptionForParentArrow(svg, segIdx, item, xTip, yTip, controlY) {
  if (!item) return;
  // Parent line for the hovered token: parent -> hovered child.
  if (item.hoverRelation) {
    if (item.hoverRelation !== 'incoming') return;
  } else if (!(item.toIdx === segIdx && item.isChildLine === false)) {
    return;
  }
  if (tokenFragmentsState.udGrammarAnchor) return;
  var udTok = getUdInfoForSegment(item.toIdx);
  var depLabel = normalizeDepLabel(String(item.dep || (udTok && (udTok.dep_label || udTok.dep)) || ''));
  if (!depLabel) return;
  var depDesc = getDependencyHoverText(depLabel);
  if (!depDesc) depDesc = '';
  tokenFragmentsState.udGrammarAnchor = {
    x: Number(xTip),
    y: Number(yTip),
    controlY: Number(controlY),
    depLabel: depLabel,
    depDesc: depDesc
  };
}
export function appendLmWeightsToUrl(url) {
  if (dependencyPopupState.displaySettings.lmWeights) {
    dependencyPopupState.LM_WEIGHT_FIELDS.forEach(function (field) {
      var val = dependencyPopupState.displaySettings.lmWeights[field.key];
      if (typeof val === 'number' && isFinite(val)) {
        url += '&' + field.param + '=' + encodeURIComponent(val);
      }
    });
  }
  return url;
}
export function getSelectedLanguageCode() {
  if (hoverLayoutState.languageSelect)
    return String(hoverLayoutState.languageSelect.value || '')
      .trim()
      .toLowerCase();
  return String(documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
}
export function getSelectedDictSource() {
  var dictSourceSelect = document.getElementById('dictSourceSelect');
  if (dictSourceSelect) return String(dictSourceSelect.value || '').trim();
  var dc = window.DictionaryClient;
  if (dc && typeof dc.getDictSource === 'function') return String(dc.getDictSource() || '').trim();
  return '';
}
export function hasSelectedLanguage() {
  return !!getSelectedLanguageCode();
}
export function syncLookupSelectionStatus() {
  var selectedLanguage = getSelectedLanguageCode();
  if (!selectedLanguage) {
    if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Select a language.';
    return;
  }
  if (!getSelectedDictSource()) {
    if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Select a dictionary.';
    return;
  }
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
}
export function clearLookupOutputForMissingLanguage() {
  if (hoverLayoutState.renderedText) hoverLayoutState.renderedText.innerHTML = '';
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Select a language.';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  if (
    !lookupProgressState.depTreeUseConllu &&
    lookupProgressState.depTreeController &&
    typeof lookupProgressState.depTreeController.setData === 'function'
  ) {
    lookupProgressState.depTreeController.setData({
      segments: [],
      udOverlay: null
    });
  }
}
export function buildLookupUrl(q) {
  var url = '/lookup?q=' + encodeURIComponent(q || '');
  url += '&merge_greedy=' + (dependencyPopupState.displaySettings.mergeGreedy ? '1' : '0');
  url += '&split_fill=' + (dependencyPopupState.displaySettings.splitDictFill ? '1' : '0');
  url += '&pos_override=' + (dependencyPopupState.displaySettings.posOverride ? '1' : '0');
  url += '&stanza_ner=' + (dependencyPopupState.displaySettings.stanzaNer ? '1' : '0');
  url += '&collapse_ner_spans=' + (dependencyPopupState.displaySettings.collapseNerUd ? '1' : '0');
  url += '&gemini_ner=0';
  url += '&dp_resegment=' + (dependencyPopupState.displaySettings.dpResegment ? '1' : '0');
  url += '&strip_punctuation=0';
  url +=
    '&manual_sentence_segmentation=' +
    (getManualSentenceSegmentationForLanguage(documentShellState.currentLanguage) ? '1' : '0');
  url += '&lang=' + encodeURIComponent(documentShellState.currentLanguage);
  if (documentShellState.currentTrankitOverride)
    url += '&trankit=' + encodeURIComponent(documentShellState.currentTrankitOverride);
  return appendLmWeightsToUrl(url);
}
export function buildLookupUrlLite(q) {
  var url = '/lookup?q=' + encodeURIComponent(q || '');
  url += '&merge_greedy=' + (dependencyPopupState.displaySettings.mergeGreedy ? '1' : '0');
  url += '&split_fill=' + (dependencyPopupState.displaySettings.splitDictFill ? '1' : '0');
  url += '&collapse_ner_spans=' + (dependencyPopupState.displaySettings.collapseNerUd ? '1' : '0');
  url += '&gemini_ner=0';
  url += '&strip_punctuation=0';
  url +=
    '&manual_sentence_segmentation=' +
    (getManualSentenceSegmentationForLanguage(documentShellState.currentLanguage) ? '1' : '0');
  url += '&lite=1';
  url += '&lang=' + encodeURIComponent(documentShellState.currentLanguage);
  if (documentShellState.currentTrankitOverride)
    url += '&trankit=' + encodeURIComponent(documentShellState.currentTrankitOverride);
  return appendLmWeightsToUrl(url);
}
export function syncStripPunctuationControl() {
  if (!orthographyState.toggleStripPunctuation) return;
  orthographyState.toggleStripPunctuation.checked = false;
  orthographyState.toggleStripPunctuation.disabled = true;
  var label = orthographyState.toggleStripPunctuation.parentElement;
  if (label && label.style) {
    label.style.opacity = '';
    label.title = 'Strip punctuation before parsing is disabled.';
  }
}
export function syncManualSentenceSegmentationControl() {
  if (!orthographyState.toggleManualSentenceSegmentation) return;
  var supported = isManualSentenceSegmentationSupportedLanguage(documentShellState.currentLanguage);
  orthographyState.toggleManualSentenceSegmentation.checked =
    !!dependencyPopupState.displaySettings.manualSentenceSegmentation;
  orthographyState.toggleManualSentenceSegmentation.disabled = !supported;
  var label = orthographyState.toggleManualSentenceSegmentation.parentElement;
  if (label && label.style) {
    label.style.display = '';
    label.style.opacity = supported ? '' : '0.6';
    label.setAttribute('data-native-tooltip', '');
    label.title = 'Recommended setting';
  }
}
// Display controls dropdown
export function ensureGrammarTypesInitialized() {
  dependencyPopupState.GRAMMAR_TYPES.forEach(function (t) {
    if (dependencyPopupState.displaySettings.grammarTypes[t] === undefined) {
      dependencyPopupState.displaySettings.grammarTypes[t] = false;
    }
  });
}
export function ensureFuzzySettingsInitialized() {
  if (
    typeof dependencyPopupState.displaySettings.fuzzyMaxEditDistance !== 'number' ||
    !isFinite(dependencyPopupState.displaySettings.fuzzyMaxEditDistance)
  ) {
    dependencyPopupState.displaySettings.fuzzyMaxEditDistance = 3;
  }
  if (dependencyPopupState.displaySettings.fuzzyMaxEditDistance < 0) {
    dependencyPopupState.displaySettings.fuzzyMaxEditDistance = 0;
  }
  if (dependencyPopupState.displaySettings.fuzzyMaxEditDistance > 6) {
    dependencyPopupState.displaySettings.fuzzyMaxEditDistance = 6;
  }
}
export function syncMasterGrammarToggle() {
  if (!orthographyState.toggleGrammarOverlayAll) return;
  var allOn = dependencyPopupState.GRAMMAR_TYPES.length
    ? dependencyPopupState.GRAMMAR_TYPES.every(function (t) {
        return dependencyPopupState.displaySettings.grammarTypes[t];
      })
    : false;
  orthographyState.toggleGrammarOverlayAll.checked = allOn;
}
export function renderGrammarTypeCheckboxes() {
  if (!orthographyState.grammarOverlayPanel) return;
  orthographyState.grammarOverlayPanel.innerHTML = '';
  var header = document.createElement('h4');
  header.textContent = 'Grammar categories';
  orthographyState.grammarOverlayPanel.appendChild(header);
  var list = document.createElement('div');
  list.className = 'toggle-grid';
  orthographyState.grammarOverlayPanel.appendChild(list);
  dependencyPopupState.GRAMMAR_TYPES.forEach(function (t) {
    var label = document.createElement('label');
    label.className = 'toggle-label';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !!dependencyPopupState.displaySettings.grammarTypes[t];
    cb.dataset.grammarType = t;
    cb.addEventListener('change', function () {
      var gt = this.dataset.grammarType;
      dependencyPopupState.displaySettings.grammarTypes[gt] = this.checked;
      syncMasterGrammarToggle();
      saveDisplaySettings();
      if (hoverLayoutState.latestData) {
        renderSegments(hoverLayoutState.latestData, hoverLayoutState.sourceText.value);
      }
    });
    var span = document.createElement('span');
    span.textContent = t;
    label.appendChild(cb);
    label.appendChild(span);
    list.appendChild(label);
  });
}

// Sync checkboxes with loaded settings
export function openGrammarOverlayPanelUI() {
  if (!orthographyState.displayDropdown) return;
  if (!orthographyState.grammarOverlayPanel) {
    orthographyState.grammarOverlayPanel = document.createElement('div');
    orthographyState.grammarOverlayPanel.id = 'grammarOverlayPanel';
    orthographyState.grammarOverlayPanel.className = 'grammar-overlay-panel';
    orthographyState.displayDropdown.appendChild(orthographyState.grammarOverlayPanel);
  }
  renderGrammarTypeCheckboxes();
  orthographyState.grammarOverlayPanel.style.display = 'block';
}
export function closeGrammarOverlayPanel() {
  if (orthographyState.grammarOverlayPanel) orthographyState.grammarOverlayPanel.style.display = 'none';
}
export function initializeOrthography() {
  orthographyState._unknownPhonMarksSeen = Object.create(null);
  window._fireOrthBreakdownRequest = _fireOrthBreakdownRequest;
  loadDisplaySettings();
  orthographyState.displayToggleBtn = document.getElementById('displayToggleBtn');
  orthographyState.displayDropdown = document.getElementById('displayDropdown');
  orthographyState.toggleDepTreeView = document.getElementById('toggleDepTreeView');
  orthographyState.toggleGrammarOverlayAll = document.getElementById('toggleGrammarOverlayAll');
  orthographyState.openGrammarOverlayPanel = document.getElementById('openGrammarOverlayPanel');
  orthographyState.grammarOverlayPanel = null;
  orthographyState.openLmWeightsPanel = document.getElementById('openLmWeightsPanel');
  orthographyState.lmWeightsPanel = null;
  // OBSOLETE: greedy/split post-passes replaced by DP resegmentation
  // var toggleMergeGreedy = document.getElementById('toggleMergeGreedy');
  // var toggleSplitDictFill = document.getElementById('toggleSplitDictFill');
  // posOverride, stanzaNer, collapseNerUd, dpResegment toggles removed - now hardcoded
  orthographyState.toggleUdOverlay = document.getElementById('toggleUdOverlay');
  orthographyState.toggleChunkHighlight = document.getElementById('toggleChunkHighlight');
  orthographyState.toggleNerOverlay = document.getElementById('toggleNerOverlay');
  orthographyState.toggleGeminiNer = document.getElementById('toggleGeminiNer');
  orthographyState.toggleIslandDepTree = document.getElementById('toggleIslandDepTree');
  orthographyState.toggleConnectedIslands = document.getElementById('toggleConnectedIslands');
  orthographyState.toggleConnectedIslandsAclGate = document.getElementById('toggleConnectedIslandsAclGate');
  orthographyState.toggleContextWindow = document.getElementById('toggleContextWindow');
  orthographyState.contextWindowSizeInput = document.getElementById('contextWindowSize');
  orthographyState.toggleBottomUpChunk = document.getElementById('toggleBottomUpChunk');
  orthographyState.toggleBottomUpCascade = document.getElementById('toggleBottomUpCascade');
  orthographyState.bottomUpChunkThresholdInput = document.getElementById('bottomUpChunkThreshold');
  orthographyState.branchDepthMinInput = document.getElementById('branchDepthMin');
  orthographyState.clauseDepthDropInput = document.getElementById('clauseDepthDrop');
  orthographyState.togglePronunciation = document.getElementById('togglePronunciation');
  orthographyState.toggleLlmGloss = document.getElementById('toggleLlmGloss');
  orthographyState.toggleLlmDecomp = document.getElementById('toggleLlmDecomp');
  orthographyState.toggleOrthBreakdown = document.getElementById('toggleOrthBreakdown');
  orthographyState.toggleGrammarPopup = document.getElementById('toggleGrammarPopup');
  orthographyState.toggleDictPopup = document.getElementById('toggleDictPopup');
  orthographyState.debugCaptureMode = document.getElementById('debugCaptureMode');
  orthographyState.openLegacyDepTreeToolBtn = document.getElementById('openLegacyDepTreeToolBtn');
  orthographyState.depTreeInlineToggleBtn = document.getElementById('depTreeInlineToggle');
  orthographyState.depTreeInlinePanelEl = document.getElementById('depTreeInlinePanel');
  orthographyState.depTreeInlineHostEl = document.getElementById('depTreeInlineHost');
  // sqliteDictMode removed � SQLite is always on
  orthographyState.togglePdfOcrCleanup = document.getElementById('togglePdfOcrCleanup');
  orthographyState.pdfTextSourceGroup = document.getElementById('pdfTextSourceGroup');
  orthographyState.fuzzyMaxEditDistanceInput = document.getElementById('fuzzyMaxEditDistance');
  orthographyState.toggleComments = document.getElementById('toggleComments');
  orthographyState.toggleSubsegmentPopups = document.getElementById('toggleSubsegmentPopups');
  orthographyState.toggleStripPunctuation = document.getElementById('toggleStripPunctuation');
  orthographyState.toggleManualSentenceSegmentation = document.getElementById(
    'toggleManualSentenceSegmentation'
  );
  ensureGrammarTypesInitialized();
  ensureLmWeightsInitialized();
  ensureFuzzySettingsInitialized();
  syncMasterGrammarToggle();
  if (orthographyState.toggleDepTreeView)
    orthographyState.toggleDepTreeView.checked = dependencyPopupState.displaySettings.depTreeView;
  // OBSOLETE: greedy/split post-passes replaced by DP resegmentation
  // if (toggleMergeGreedy) toggleMergeGreedy.checked = displaySettings.mergeGreedy;
  // if (toggleSplitDictFill) toggleSplitDictFill.checked = displaySettings.splitDictFill;
  if (orthographyState.toggleIslandDepTree)
    orthographyState.toggleIslandDepTree.checked = dependencyPopupState.displaySettings.islandDepTree;
  if (orthographyState.toggleConnectedIslands)
    orthographyState.toggleConnectedIslands.checked = dependencyPopupState.displaySettings.connectedIslands;
  if (orthographyState.toggleConnectedIslandsAclGate)
    orthographyState.toggleConnectedIslandsAclGate.checked =
      dependencyPopupState.displaySettings.connectedIslandsAclGate;
  if (orthographyState.toggleContextWindow)
    orthographyState.toggleContextWindow.checked = dependencyPopupState.displaySettings.contextWindow;
  if (orthographyState.contextWindowSizeInput)
    orthographyState.contextWindowSizeInput.value = dependencyPopupState.displaySettings.contextWindowSize;
  if (orthographyState.toggleBottomUpChunk)
    orthographyState.toggleBottomUpChunk.checked = dependencyPopupState.displaySettings.bottomUpChunk;
  if (orthographyState.toggleBottomUpCascade)
    orthographyState.toggleBottomUpCascade.checked = dependencyPopupState.displaySettings.bottomUpCascade;
  if (orthographyState.bottomUpChunkThresholdInput)
    orthographyState.bottomUpChunkThresholdInput.value =
      dependencyPopupState.displaySettings.bottomUpChunkThreshold;
  // posOverride, stanzaNer, collapseNerUd, dpResegment checkboxes removed - now hardcoded
  if (orthographyState.branchDepthMinInput)
    orthographyState.branchDepthMinInput.value = dependencyPopupState.displaySettings.branchDepthMin;
  if (orthographyState.clauseDepthDropInput)
    orthographyState.clauseDepthDropInput.value = dependencyPopupState.displaySettings.clauseDepthDrop;
  if (orthographyState.toggleUdOverlay)
    orthographyState.toggleUdOverlay.checked = dependencyPopupState.displaySettings.udOverlay;
  if (orthographyState.toggleChunkHighlight)
    orthographyState.toggleChunkHighlight.checked = dependencyPopupState.displaySettings.chunkHighlight;
  if (orthographyState.toggleNerOverlay)
    orthographyState.toggleNerOverlay.checked = dependencyPopupState.displaySettings.nerOverlay;
  if (orthographyState.toggleGeminiNer)
    orthographyState.toggleGeminiNer.checked = dependencyPopupState.displaySettings.geminiNer;
  if (orthographyState.togglePronunciation)
    orthographyState.togglePronunciation.checked = dependencyPopupState.displaySettings.pronunciation;
  if (orthographyState.toggleLlmGloss)
    orthographyState.toggleLlmGloss.checked = dependencyPopupState.displaySettings.llmGloss;
  if (orthographyState.toggleLlmDecomp)
    orthographyState.toggleLlmDecomp.checked = dependencyPopupState.displaySettings.llmDecomp;
  if (orthographyState.toggleOrthBreakdown)
    orthographyState.toggleOrthBreakdown.checked = dependencyPopupState.displaySettings.orthBreakdown;
  if (orthographyState.toggleGrammarPopup)
    orthographyState.toggleGrammarPopup.checked = dependencyPopupState.displaySettings.grammarPopup;
  if (orthographyState.toggleDictPopup)
    orthographyState.toggleDictPopup.checked = dependencyPopupState.displaySettings.dictPopup;
  if (orthographyState.debugCaptureMode)
    orthographyState.debugCaptureMode.value = dependencyPopupState.displaySettings.debugCapture
      ? 'on'
      : 'off';
  // sqliteDictMode removed � SQLite is always on
  if (orthographyState.fuzzyMaxEditDistanceInput)
    orthographyState.fuzzyMaxEditDistanceInput.value =
      dependencyPopupState.displaySettings.fuzzyMaxEditDistance;
  if (orthographyState.toggleComments)
    orthographyState.toggleComments.checked = dependencyPopupState.displaySettings.comments;
  if (orthographyState.toggleManualSentenceSegmentation)
    orthographyState.toggleManualSentenceSegmentation.checked =
      dependencyPopupState.displaySettings.manualSentenceSegmentation;
  syncManualSentenceSegmentationControl();
  syncStripPunctuationControl();
  return true;
}
