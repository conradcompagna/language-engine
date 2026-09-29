import { dependencyPopupState } from './dependency-popup.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getLookupEntryResolution, getTokenBannerSurfaceText } from './entry-editing.mjs';
import { getTokenBannerLemmaInfo } from './gloss-entries.mjs';
import { buildAlwaysHoverableLemmaHtml } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { presentationState } from './presentation.state.mjs';
import {
  buildTokenMapCompoundLookupHtml,
  buildTokenMapLookupHtml,
  resolveTokenMapLookupEntry
} from './token-map.mjs';
export function getGrammarColor(type) {
  return presentationState.GRAMMAR_TYPE_COLORS[type] || '#6b7280';
}
export function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
// ---- Shared upgrade prompt (floating dismissible box) ----
export function showUpgradePrompt() {
  var existing = document.getElementById('le-upgrade-prompt');
  if (existing) existing.remove();
  var box = document.createElement('div');
  box.id = 'le-upgrade-prompt';
  box.className = 'le-upgrade-prompt';
  box.innerHTML =
    '<span>This feature requires a paid subscription. <a href="/account">Upgrade</a></span>' +
    '<button type="button" class="le-upgrade-prompt-close">\u00d7</button>';
  document.body.appendChild(box);
  box.querySelector('.le-upgrade-prompt-close').addEventListener('click', function () {
    box.remove();
  });
}
// Check an API response for upgrade_required and show prompt instead of alert
export function handlePaidFeatureError(data, fallbackMsg) {
  if (data && data.upgrade_required) {
    showUpgradePrompt();
    return true;
  }
  alert((data && data.error) || fallbackMsg || 'Request failed.');
  return false;
}
export function stripZeroWidthJoiners(raw) {
  return String(raw == null ? '' : raw).replace(presentationState.ZERO_WIDTH_JOINER_RE, '');
}
export function getTrimmedDisplayText(raw) {
  return stripZeroWidthJoiners(raw).trim();
}
export function normalizeVisibleComparisonText(raw) {
  var text = String(raw == null ? '' : raw);
  var layer = window.DictionaryNormalizationLayer;
  if (layer && typeof layer.normalizeVisibleComparisonText === 'function') {
    try {
      return String(layer.normalizeVisibleComparisonText(text) || '');
    } catch (_e) {}
  }
  if (text.normalize) text = text.normalize('NFKC');
  if (layer && typeof layer.stripInvisibleComparisonChars === 'function') {
    try {
      text = String(layer.stripInvisibleComparisonChars(text) || '');
    } catch (_e2) {}
  }
  return text.trim();
}
export function hasSameVisibleComparisonText(left, right) {
  return normalizeVisibleComparisonText(left) === normalizeVisibleComparisonText(right);
}
export function hasDisplayText(raw) {
  return !!getTrimmedDisplayText(raw);
}
export function getEntryDisplayHead(entry, fallbackText) {
  if (entry && typeof entry === 'object') {
    if (entry.display_headword != null && hasDisplayText(entry.display_headword)) {
      return String(entry.display_headword);
    }
    if (entry.headword != null && hasDisplayText(entry.headword)) {
      return String(entry.headword);
    }
    if (entry.head != null && hasDisplayText(entry.head)) {
      return String(entry.head);
    }
    if (entry.text != null && hasDisplayText(entry.text)) {
      return String(entry.text);
    }
    if (entry.surface_form != null && hasDisplayText(entry.surface_form)) {
      return String(entry.surface_form);
    }
  }
  return hasDisplayText(fallbackText) ? String(fallbackText) : '';
}
export function getRenderableFillLabel(fillEntry, fallbackText) {
  return getEntryDisplayHead(fillEntry, fallbackText);
}
export function filterRenderableFillEntries(fillEntries) {
  var src = Array.isArray(fillEntries) ? fillEntries : [];
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var fillEntry = src[i];
    if (!fillEntry || typeof fillEntry !== 'object') continue;
    if (!hasDisplayText(getEntryDisplayHead(fillEntry, ''))) continue;
    out.push(fillEntry);
  }
  return out;
}
export function getRenderableFillState(fillEntries, isUnknownFn) {
  var entries = filterRenderableFillEntries(fillEntries);
  var hasKnown = false;
  var hasUnknown = false;
  for (var i = 0; i < entries.length; i++) {
    if (isUnknownFn && isUnknownFn(entries[i])) hasUnknown = true;
    else hasKnown = true;
  }
  return {
    entries: entries,
    hasKnown: hasKnown,
    hasUnknown: hasUnknown
  };
}
// Generic language adapter registry. Language-specific logic is loaded from separate static files.
export function getLanguageAdapter(langOverride) {
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  if (!lang) return null;
  if (presentationState.ReaderLanguageAdapters[lang]) return presentationState.ReaderLanguageAdapters[lang];
  var dash = lang.indexOf('-');
  if (dash > 0) {
    var base = lang.slice(0, dash);
    if (presentationState.ReaderLanguageAdapters[base]) return presentationState.ReaderLanguageAdapters[base];
  }
  return null;
}
// Compatibility wrappers: language adapters own any script-specific normalization.
export function normalizePinyinSyllable(rawSyllable) {
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.normalizePinyinSyllable === 'function') {
    return adapter.normalizePinyinSyllable(rawSyllable, documentShellState.currentLanguage);
  }
  return String(rawSyllable || '');
}
export function normalizePinyinToneMarks(rawText) {
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.normalizePinyinToneMarks === 'function') {
    return adapter.normalizePinyinToneMarks(rawText, documentShellState.currentLanguage);
  }
  return String(rawText || '');
}
export function formatPopupRoman(rawText) {
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.formatPopupRoman === 'function') {
    return adapter.formatPopupRoman(rawText, documentShellState.currentLanguage);
  }
  return normalizePinyinToneMarks(rawText);
}
export function collectPopupRomanFromG2P(g2pData) {
  if (!g2pData || !Array.isArray(g2pData.syllables) || !g2pData.syllables.length) return '';
  var parts = [];
  for (var i = 0; i < g2pData.syllables.length; i++) {
    var syll = g2pData.syllables[i];
    if (!syll || !syll.roman) continue;
    var normalized = formatPopupRoman(syll.roman);
    if (normalized) parts.push(normalized);
  }
  return parts.join(' ');
}
export function renderPopupRomanLine(g2pData) {
  var romanLine = collectPopupRomanFromG2P(g2pData);
  if (!romanLine) return '';
  return '<div style="font-size:0.85em;color:#666;">' + escapeHtml(romanLine) + '</div>';
}
export function getHeadwordForms(entry, fallbackHead) {
  var fallback = String(fallbackHead || '');
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.getHeadwordForms === 'function') {
    var adapted = adapter.getHeadwordForms(entry, fallback, documentShellState.currentLanguage);
    if (adapted && typeof adapted === 'object' && Array.isArray(adapted.forms)) return adapted;
  }
  var forms = [];
  var seen = Object.create(null);
  function pushForm(raw) {
    var f = String(raw || '');
    if (!f || seen[f]) return;
    seen[f] = true;
    forms.push(f);
  }
  pushForm(entry && entry.text ? entry.text : '');
  pushForm(fallback);
  pushForm(entry && entry.surface_form ? entry.surface_form : '');
  pushForm(entry && entry.head ? entry.head : '');
  pushForm(getEntryDisplayHead(entry, ''));
  if (!forms.length) forms.push('');
  return {
    forms: forms
  };
}
export function isChineseLanguage() {
  // Kept for backward-compatible call sites; resolved by adapters.
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.isChineseLanguage === 'function') {
    return !!adapter.isChineseLanguage(documentShellState.currentLanguage);
  }
  return false;
}
export function isJapaneseLanguage(langOverride) {
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  if (!lang) return false;
  return lang === 'ja' || lang === 'japanese' || lang.indexOf('ja-') === 0;
}
export function isPersianLanguage(langOverride) {
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  if (!lang) return false;
  return lang === 'fa' || lang === 'persian' || lang.indexOf('fa-') === 0;
}
export function isManualSentenceSegmentationSupportedLanguage(langOverride) {
  var lang = String(langOverride || documentShellState.currentLanguage || '').toLowerCase();
  if (!lang) return false;
  return (
    lang === 'sa' ||
    lang === 'sanskrit' ||
    lang.indexOf('sa-') === 0 ||
    lang === 'lzh' ||
    lang === 'classical' ||
    lang === 'classical-chinese' ||
    lang.indexOf('lzh-') === 0
  );
}
export function getManualSentenceSegmentationForLanguage(langOverride) {
  return (
    isManualSentenceSegmentationSupportedLanguage(langOverride) &&
    !!dependencyPopupState.displaySettings.manualSentenceSegmentation
  );
}
export function getStripPunctuationForLanguage(langOverride) {
  void langOverride;
  return false;
}
export function hasPersianVariantLemma(rawText, langOverride) {
  return isPersianLanguage(langOverride) && String(rawText || '').indexOf('#') !== -1;
}
export function formatPersianVariantLemma(rawText) {
  var raw = String(rawText || '').trim();
  if (!raw) return '';
  var parts = raw
    .split('#')
    .map(function (part) {
      return String(part || '').trim();
    })
    .filter(Boolean);
  if (parts.length > 1) return parts.join(' / ');
  return raw.replace(/#/g, ' / ');
}
export function buildPlainLemmaDisplayHtml(rawText, langOverride) {
  var text = String(rawText || '');
  if (!text) return '';
  var displayText = hasPersianVariantLemma(text, langOverride)
    ? formatPersianVariantLemma(text)
    : stripZeroWidthJoiners(text);
  displayText = String(displayText || '');
  if (!displayText.trim()) return '';
  return '<span dir="auto" style="white-space:pre-wrap;">' + escapeHtml(displayText) + '</span>';
}
export function getLemmaDisplayMeta(lemmaValue, lemmaRawValue) {
  var lemma = getTrimmedDisplayText(lemmaValue);
  var raw = getTrimmedDisplayText(lemmaRawValue);
  if (!raw) raw = lemma;
  var suffix = '';
  if (lemma && raw && raw !== lemma && raw.indexOf(lemma) === 0) {
    suffix = raw.slice(lemma.length);
  }
  return {
    lemma: lemma,
    raw: raw,
    suffix: suffix,
    hasRawSuffix: !!suffix
  };
}
export function buildLemmaSuffixHtml(rawSuffix) {
  var suffix = String(rawSuffix || '');
  if (!suffix) return '';
  return (
    '<span dir="auto" aria-hidden="true" data-no-inspect="1" style="white-space:pre-wrap;pointer-events:auto;cursor:default;opacity:0.72;">' +
    escapeHtml(suffix) +
    '</span>'
  );
}
export function buildPlainAnnotatedLemmaHtml(lemmaValue, lemmaRawValue, langOverride) {
  var meta = getLemmaDisplayMeta(lemmaValue, lemmaRawValue);
  if (!meta.lemma && meta.raw) return buildPlainLemmaDisplayHtml(meta.raw, langOverride);
  if (!meta.lemma) return '';
  return buildPlainLemmaDisplayHtml(meta.lemma, langOverride) + buildLemmaSuffixHtml(meta.suffix);
}
export function buildHoverableAnnotatedLemmaHtml(lemmaValue, lemmaRawValue, headDecompByForm, langOverride) {
  var meta = getLemmaDisplayMeta(lemmaValue, lemmaRawValue);
  if (!meta.lemma && meta.raw) return buildPlainLemmaDisplayHtml(meta.raw, langOverride);
  if (!meta.lemma) return '';
  return (
    buildAlwaysHoverableLemmaHtml(meta.lemma, headDecompByForm, langOverride) +
    buildLemmaSuffixHtml(meta.suffix)
  );
}
export function buildTokenMapAnnotatedLemmaHtml(lemmaValue, lemmaRawValue, lemmaLookup, data) {
  var meta = getLemmaDisplayMeta(lemmaValue, lemmaRawValue);
  var lemmaText = meta.lemma;
  var effectiveLemmaLookup = resolveTokenMapLookupEntry('lemma', data, lemmaText) || lemmaLookup || null;
  var uiRenderDebugEnabled = isUiRenderDebugEnabled();
  var traceBase = uiRenderDebugEnabled
    ? {
        lemma: lemmaText,
        raw: meta.raw,
        suffix: meta.suffix,
        provided_lookup: summarizeUiRenderDebugLookupEntry(lemmaLookup),
        effective_lookup: summarizeUiRenderDebugLookupEntry(effectiveLemmaLookup)
      }
    : null;
  if (!lemmaText && meta.raw) {
    if (uiRenderDebugEnabled) {
      traceUiRenderEvent(
        'banner_lemma_render',
        Object.assign({}, traceBase, {
          path: 'raw_only_lookup'
        }),
        {
          scope: 'banner-lemma'
        }
      );
    }
    return buildTokenMapLookupHtml(effectiveLemmaLookup, meta.raw, 'lemma', {
      tokenMapData: data,
      forceTokenMapFallback: true
    });
  }
  if (!lemmaText) return '';
  var prefixHtml = '';
  if (hasPersianVariantLemma(lemmaText)) {
    if (uiRenderDebugEnabled) {
      traceUiRenderEvent(
        'banner_lemma_render',
        Object.assign({}, traceBase, {
          path: 'persian_plain_display'
        }),
        {
          scope: 'banner-lemma'
        }
      );
    }
    prefixHtml = buildPlainLemmaDisplayHtml(lemmaText);
  } else {
    var isCompound = /[+\uFF0B]/.test(lemmaText);
    if (uiRenderDebugEnabled) {
      traceUiRenderEvent(
        'banner_lemma_render',
        Object.assign({}, traceBase, {
          path: isCompound ? 'compound_lookup' : 'single_lookup'
        }),
        {
          scope: 'banner-lemma'
        }
      );
    }
    prefixHtml = /[+\uFF0B]/.test(lemmaText)
      ? buildTokenMapCompoundLookupHtml(lemmaText, 'lemma', data)
      : buildTokenMapLookupHtml(effectiveLemmaLookup, lemmaText, 'lemma', {
          tokenMapData: data,
          forceTokenMapFallback: true
        });
  }
  return prefixHtml + buildLemmaSuffixHtml(meta.suffix);
}
export function getPanelHeadwordRows(entry, fallbackHead) {
  var fallback = String(fallbackHead || '');
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.getPanelHeadwordRows === 'function') {
    var rows = adapter.getPanelHeadwordRows(entry, fallback, documentShellState.currentLanguage);
    if (Array.isArray(rows) && rows.length) {
      return rows.map(function (r) {
        return String(r || '');
      });
    }
  }
  var info = getHeadwordForms(entry, fallback);
  var rows = Array.isArray(info.forms) ? info.forms.slice() : [];
  if (!rows.length && fallback) rows.push(fallback);
  if (!rows.length) rows.push('');
  return rows;
}
export function isUiRenderDebugEnabled() {
  return presentationState._uiRenderDebugCollectionEnabled;
}
export function getUiRenderDebugCaptureId() {
  return String((hoverLayoutState.latestData && hoverLayoutState.latestData.debug_capture_id) || '').trim();
}
export function clipUiRenderDebugText(raw, maxChars) {
  var text = String(raw == null ? '' : raw);
  var limit = parseInt(maxChars, 10);
  if (!isFinite(limit) || limit < 32) limit = 320;
  if (text.length <= limit) return text;
  return text.slice(0, limit) + '...';
}
export function sanitizeUiRenderDebugValue(value, depth) {
  if (!isUiRenderDebugEnabled()) return null;
  var level = isFinite(depth) ? depth : 0;
  if (level > 5) return '[max-depth]';
  if (value == null) return value;
  var kind = typeof value;
  if (kind === 'string') return clipUiRenderDebugText(value, 1200);
  if (kind === 'number' || kind === 'boolean') return value;
  if (kind === 'function') return '[function]';
  if (value && value.nodeType) return '[dom-node]';
  if (Array.isArray(value)) {
    var outArr = [];
    var maxItems = Math.min(value.length, 80);
    for (var i = 0; i < maxItems; i++) {
      outArr.push(sanitizeUiRenderDebugValue(value[i], level + 1));
    }
    if (value.length > maxItems) outArr.push('[+' + String(value.length - maxItems) + ' more]');
    return outArr;
  }
  if (kind === 'object') {
    var outObj = {};
    var keys = Object.keys(value);
    var maxKeys = Math.min(keys.length, 80);
    for (var ki = 0; ki < maxKeys; ki++) {
      var key = keys[ki];
      outObj[key] = sanitizeUiRenderDebugValue(value[key], level + 1);
    }
    if (keys.length > maxKeys) outObj.__truncated_keys = keys.length - maxKeys;
    return outObj;
  }
  try {
    return String(value);
  } catch (_e) {
    return '[unserializable]';
  }
}
export function summarizeUiRenderDebugLookupEntry(entry) {
  if (!isUiRenderDebugEnabled()) return null;
  if (!entry || typeof entry !== 'object') return null;
  var resolution = getLookupEntryResolution(entry) || {};
  return {
    head: String(entry.head || entry.headword || ''),
    text: String(entry.text || ''),
    surface_form: String(entry.surface_form || ''),
    lemma_form: String(entry.lemma_form || entry.lemma || ''),
    resolved_via: String((resolution && resolution.resolved_via) || entry.resolved_via || ''),
    source: String(entry.source || ''),
    dict_source: String(entry._dict_source || entry._source || ''),
    pos: String(entry.pos || ''),
    dict_fill_count: Array.isArray(entry.dict_fill) ? entry.dict_fill.length : 0,
    dict_fill_surface_slice_count: Array.isArray(entry.dict_fill_surface_slices)
      ? entry.dict_fill_surface_slices.length
      : 0,
    inspect_fill_count:
      entry.inspect_fill_count || (Array.isArray(entry.inspect_fill) ? entry.inspect_fill.length : 0)
  };
}
export function summarizeUiRenderDebugSliceList(slices, tokenDisplay, dictFill) {
  if (!isUiRenderDebugEnabled()) return [];
  var src = Array.isArray(slices) ? slices : [];
  var out = [];
  for (var i = 0; i < src.length; i++) {
    var sl = src[i] || {};
    var fillIndexes = Array.isArray(sl.fillIndexes) ? sl.fillIndexes.slice() : [];
    var fillEntry = fillIndexes.length ? (dictFill && dictFill[fillIndexes[0]]) || {} : {};
    out.push({
      start: Number(sl.start || 0),
      end: Number(sl.end || 0),
      text: clipUiRenderDebugText(
        String(tokenDisplay || '').slice(Number(sl.start || 0), Number(sl.end || 0)),
        160
      ),
      fill_indexes: fillIndexes,
      fill_head: String(fillEntry.head || fillEntry.text || '')
    });
  }
  return out;
}
export function summarizeUiRenderDebugFillHitEl(el) {
  if (!isUiRenderDebugEnabled()) return null;
  if (!el || !el.dataset) return null;
  return {
    text: String(el.textContent || ''),
    fill_indexes: String(el.dataset.fillIndexes || el.dataset.fillIndex || ''),
    fill_text: String(el.dataset.fillText || ''),
    fill_head: String(el.dataset.fillHead || '')
  };
}
export function summarizeUiRenderDebugTokenEl(el) {
  if (!isUiRenderDebugEnabled()) return null;
  if (!el || !el.dataset) return null;
  var fillHits = [];
  var hitEls = el.querySelectorAll ? el.querySelectorAll('.reader-token-fill-hit') : [];
  for (var i = 0; i < hitEls.length; i++) {
    var hitInfo = summarizeUiRenderDebugFillHitEl(hitEls[i]);
    if (hitInfo) fillHits.push(hitInfo);
  }
  return {
    text: clipUiRenderDebugText(el.textContent || '', 240),
    class_name: String(el.className || ''),
    seg: String(el.dataset.seg || ''),
    lookup_role: String(el.dataset.tokenMapLookup || ''),
    lookup_key: String(el.dataset.tokenMapLookupKey || ''),
    hover_mode: String(el.dataset.hoverMode || ''),
    has_fill_hits: String(el.dataset.hasFillHits || '') === '1',
    fill_hit_count: fillHits.length,
    fill_hits: fillHits
  };
}
export function summarizeUiRenderDebugHeadlineEl(el) {
  if (!isUiRenderDebugEnabled()) return null;
  if (!el) return null;
  var tokenEls = el.querySelectorAll
    ? el.querySelectorAll('.token-map-live-token, .headword-component, [data-panel-surface-seg]')
    : [];
  var tokens = [];
  for (var i = 0; i < tokenEls.length; i++) {
    var tokenInfo = summarizeUiRenderDebugTokenEl(tokenEls[i]);
    if (tokenInfo) tokens.push(tokenInfo);
  }
  return {
    text: clipUiRenderDebugText(el.textContent || '', 320),
    class_name: String(el.className || ''),
    html: clipUiRenderDebugText(el.outerHTML || '', 1600),
    token_count: tokens.length,
    tokens: tokens
  };
}
export function ensureUiRenderDebugState() {
  if (!isUiRenderDebugEnabled()) return null;
  var captureId = getUiRenderDebugCaptureId();
  if (
    !presentationState._uiRenderDebugState ||
    String(presentationState._uiRenderDebugState.debug_capture_id || '') !== captureId
  ) {
    presentationState._uiRenderDebugState = {
      version: 1,
      debug_capture_id: captureId,
      current_language: String(documentShellState.currentLanguage || ''),
      updated_at: Date.now(),
      current_panel_session_id: '',
      panel_sessions: [],
      general_events: [],
      banner_snapshots: []
    };
  } else {
    presentationState._uiRenderDebugState.current_language = String(documentShellState.currentLanguage || '');
    presentationState._uiRenderDebugState.updated_at = Date.now();
  }
  return presentationState._uiRenderDebugState;
}
export function trimUiRenderDebugCollection(arr, maxItems) {
  if (!Array.isArray(arr)) return;
  var limit = parseInt(maxItems, 10);
  if (!isFinite(limit) || limit < 1) limit = 1;
  while (arr.length > limit) arr.shift();
}
export function getUiRenderDebugCurrentPanelSession(state) {
  var debugState = state || ensureUiRenderDebugState();
  if (!debugState) return null;
  var currentId = String(debugState.current_panel_session_id || '');
  if (!currentId) return null;
  for (var i = debugState.panel_sessions.length - 1; i >= 0; i--) {
    var session = debugState.panel_sessions[i];
    if (session && String(session.id || '') === currentId) return session;
  }
  return null;
}
export function traceUiRenderEvent(type, details, options) {
  var debugState = ensureUiRenderDebugState();
  if (!debugState) return null;
  var opts = options || {};
  var scope = String(opts.scope || 'general').trim() || 'general';
  var event = {
    seq: ++presentationState._uiRenderDebugEventSeq,
    ts: Date.now(),
    type: String(type || '').trim() || 'event',
    scope: scope,
    details: sanitizeUiRenderDebugValue(details || {}, 0)
  };
  var targetSession = null;
  if (opts.sessionId) {
    var wantedId = String(opts.sessionId || '');
    for (var i = debugState.panel_sessions.length - 1; i >= 0; i--) {
      if (String((debugState.panel_sessions[i] || {}).id || '') === wantedId) {
        targetSession = debugState.panel_sessions[i];
        break;
      }
    }
  }
  if (!targetSession && scope.indexOf('panel') === 0) {
    targetSession = getUiRenderDebugCurrentPanelSession(debugState);
  }
  if (targetSession) {
    if (!Array.isArray(targetSession.events)) targetSession.events = [];
    targetSession.events.push(event);
    trimUiRenderDebugCollection(targetSession.events, 500);
  } else {
    debugState.general_events.push(event);
    trimUiRenderDebugCollection(debugState.general_events, 500);
  }
  return event;
}
export function startUiRenderPanelSession(meta) {
  var debugState = ensureUiRenderDebugState();
  if (!debugState) return null;
  var session = {
    id: 'panel-' + String(++presentationState._uiRenderDebugPanelSeq),
    started_at: Date.now(),
    meta: sanitizeUiRenderDebugValue(meta || {}, 0),
    events: [],
    snapshots: []
  };
  debugState.current_panel_session_id = session.id;
  debugState.panel_sessions.push(session);
  trimUiRenderDebugCollection(debugState.panel_sessions, 8);
  traceUiRenderEvent('panel_session_started', session.meta, {
    scope: 'panel-session',
    sessionId: session.id
  });
  return session;
}
export function captureUiRenderPanelSnapshot(reason) {
  var debugState = ensureUiRenderDebugState();
  var session = getUiRenderDebugCurrentPanelSession(debugState);
  if (!debugState || !session || !hoverLayoutState.panelContent) return null;
  var headlineEls = hoverLayoutState.panelContent.querySelectorAll(
    '.popup-headline, .popup-headline-inline-flow'
  );
  var headlines = [];
  for (var i = 0; i < headlineEls.length; i++) {
    var headlineInfo = summarizeUiRenderDebugHeadlineEl(headlineEls[i]);
    if (headlineInfo) headlines.push(headlineInfo);
  }
  var interactiveEls = hoverLayoutState.panelContent.querySelectorAll('[data-seg], .reader-token-fill-hit');
  var interactive = [];
  for (var ii = 0; ii < interactiveEls.length; ii++) {
    var tokenInfo = summarizeUiRenderDebugTokenEl(interactiveEls[ii]);
    if (!tokenInfo) {
      tokenInfo = summarizeUiRenderDebugFillHitEl(interactiveEls[ii]);
    }
    if (tokenInfo) interactive.push(tokenInfo);
  }
  var snapshot = {
    reason: String(reason || '').trim() || 'panel_snapshot',
    ts: Date.now(),
    headline_count: headlines.length,
    token_map_token_count: hoverLayoutState.panelContent.querySelectorAll('.token-map-live-token').length,
    fill_hit_count: hoverLayoutState.panelContent.querySelectorAll('.reader-token-fill-hit').length,
    pending_surface_count: hoverLayoutState.panelContent.querySelectorAll('[data-panel-surface-seg]').length,
    interactive_count: interactive.length,
    headlines: sanitizeUiRenderDebugValue(headlines, 0),
    interactive_tokens: sanitizeUiRenderDebugValue(interactive, 0)
  };
  session.snapshots.push(snapshot);
  trimUiRenderDebugCollection(session.snapshots, 24);
  return snapshot;
}
export function captureUiRenderBannerSnapshot(reason, data) {
  var debugState = ensureUiRenderDebugState();
  var banner = document.getElementById('token-banner');
  if (!debugState || !banner || !banner.innerHTML) return null;
  var surfaceWrap = banner.querySelector('.tb-surface-wrap');
  var lemmaWrap = banner.querySelector('.tb-lemma-wrap');
  var snapshot = {
    reason: String(reason || '').trim() || 'banner_snapshot',
    ts: Date.now(),
    token_surface: String((data && getTokenBannerSurfaceText(data)) || ''),
    token_lemma: String((data && getTokenBannerLemmaInfo(data).lemma) || ''),
    surface: surfaceWrap ? summarizeUiRenderDebugHeadlineEl(surfaceWrap) : null,
    lemma: lemmaWrap ? summarizeUiRenderDebugHeadlineEl(lemmaWrap) : null,
    fill_button_count: banner.querySelectorAll('.tb-fill-btn').length
  };
  debugState.banner_snapshots.push(sanitizeUiRenderDebugValue(snapshot, 0));
  trimUiRenderDebugCollection(debugState.banner_snapshots, 16);
  return snapshot;
}
export function isAggregateDictEntryContainer(entry) {
  if (!entry || typeof entry !== 'object') return false;
  return !!(
    Array.isArray(entry.dict_fill) ||
    Array.isArray(entry.fills) ||
    Array.isArray(entry.entries) ||
    Array.isArray(entry.entry_groups) ||
    Array.isArray(entry.entry_groups_hover) ||
    Array.isArray(entry.entry_groups_other) ||
    Array.isArray(entry.atomic_entries_all) ||
    Array.isArray(entry.atomic_entries_hover) ||
    Array.isArray(entry.atomic_entries_other) ||
    Array.isArray(entry.atomic_entry_refs_all) ||
    Array.isArray(entry.atomic_entry_refs_hover) ||
    Array.isArray(entry.atomic_entry_refs_other)
  );
}
// DEBUG MAP: provenance starts here on the reader side.
// This resolves the entry's source tag into UI badge metadata.
// If badges/edit disappear, inspect the entry object reaching this function.
export function getDictSourceBadgeInfo(entry) {
  var dictSrc = '';
  if (entry && typeof entry === 'object') {
    if (isAggregateDictEntryContainer(entry)) return null;
    if (entry._source) dictSrc = String(entry._source);
    else if (entry.source) dictSrc = String(entry.source);
  }
  dictSrc = String(dictSrc || '')
    .trim()
    .toLowerCase();
  if (dictSrc === 'gemini') {
    return {
      label: 'Synthetic',
      className: 'dict-source-badge-synth',
      source: 'gemini'
    };
  }
  if (dictSrc === 'user_created') {
    return {
      label: 'User Created',
      className: 'dict-source-badge-user',
      source: 'user_created'
    };
  }
  return null;
}
// DEBUG MAP: turns provenance metadata into the rendered badge HTML.
// Popup and side-panel provenance both flow through this helper.
export function buildDictSourceBadgeHtml(entry) {
  var badgeInfo = getDictSourceBadgeInfo(entry);
  if (!badgeInfo) return '';
  return (
    '<span class="popup-headline-meta"><span class="dict-source-badge dict-source-badge-inline ' +
    badgeInfo.className +
    '">' +
    badgeInfo.label +
    '</span></span>'
  );
}
// DEBUG MAP: packs provenance badge + edit button into the inline bundle
// that is later injected next to a sense-level headword row.
export function buildEntrySenseMetaHtml(badgeHtml, editHtml) {
  var badge = String(badgeHtml || '');
  var edit = String(editHtml || '');
  if (!badge && !edit) return '';
  return (
    '<span class="sense-entry-meta">' +
    (badge ? '<span class="sense-entry-badge-slot">' + badge + '</span>' : '') +
    (edit ? '<span class="sense-entry-action-slot">' + edit + '</span>' : '') +
    '</span>'
  );
}
export function buildPopupEntryMetaHtmlForEntry(entryObj) {
  return buildEntrySenseMetaHtml(buildDictSourceBadgeHtml(entryObj), '');
}
export function normalizePanelEditGlossList(glosses) {
  var src = Array.isArray(glosses) ? glosses : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < src.length; i++) {
    var text = String(src[i] || '').trim();
    if (!text || seen[text]) continue;
    seen[text] = true;
    out.push(text);
  }
  if (out.length >= 3) {
    var allSingleChar = true;
    for (var j = 0; j < out.length; j++) {
      if (out[j].length !== 1) {
        allSingleChar = false;
        break;
      }
    }
    if (allSingleChar) {
      var merged = out.join('').trim();
      return merged ? [merged] : [];
    }
  }
  return out;
}
export function extractPanelEditGlosses(entry) {
  var glosses = [];
  if (!entry || typeof entry !== 'object') return glosses;
  if (entry._glosses_raw) {
    try {
      var parsed = JSON.parse(entry._glosses_raw);
      if (Array.isArray(parsed)) {
        for (var i = 0; i < parsed.length; i++) {
          var sense = parsed[i];
          if (!sense || !Array.isArray(sense.glosses)) continue;
          for (var g = 0; g < sense.glosses.length; g++) {
            var gloss = String(sense.glosses[g] || '').trim();
            if (gloss) glosses.push(gloss);
          }
        }
      }
    } catch (_e) {}
  } else if (Array.isArray(entry.senses_full)) {
    for (var sf = 0; sf < entry.senses_full.length; sf++) {
      var fullSense = entry.senses_full[sf];
      if (!fullSense || !Array.isArray(fullSense.glosses)) continue;
      for (var sg = 0; sg < fullSense.glosses.length; sg++) {
        var fullGloss = String(fullSense.glosses[sg] || '').trim();
        if (fullGloss) glosses.push(fullGloss);
      }
    }
  } else if (Array.isArray(entry.senses)) {
    for (var si = 0; si < entry.senses.length; si++) {
      var senseText = String(entry.senses[si] || '').trim();
      if (senseText) glosses.push(senseText);
    }
  }
  return normalizePanelEditGlossList(glosses);
}
export function initializePresentation() {
  // Force a clean reload when navigating back/forward to this page.
  // Uses navigation timing (always set, unaffected by bfcache eligibility).
  (function () {
    var nav = performance.getEntriesByType('navigation')[0];
    if (nav && nav.type === 'back_forward') window.location.reload();
  })();

  // Dictionary lookup decoration/runtime now lives in dictionary_client_hybrid.js.
  presentationState._origFetch = window.fetch;
  if (window.DictionaryClient && typeof window.DictionaryClient.wrapFetch === 'function') {
    window.fetch = window.DictionaryClient.wrapFetch(presentationState._origFetch);
  }
  presentationState.GRAMMAR_TYPE_COLORS = {
    CLAUSE_ATTR: '#f59e0b',
    COMPOUND_NOUN_ELEM: '#16a34a',
    COMPOUND_VERB_ELEM: '#22c55e',
    CLASSIFIER: '#15803d',
    PREVERB: '#f97316',
    COORDINATOR: '#0ea5e9',
    LOCATION_NOUN: '#0891b2',
    MISC_FUNC: '#6b7280',
    NOUN_ATTR_MARKER: '#38bdf8',
    NOUN_MARKER: '#2563eb',
    NOUN_MODIFIER: '#1d4ed8',
    NEGATION_MARKER: '#dc2626',
    SELECTIVE: '#0d9488',
    SENTENCE_MARKER: '#4b5563',
    SENTENCE_MEDIAL_PART: '#6366f1',
    SENTENCE_FINAL_PART: '#a855f7',
    HEAD_NOUN: '#65a30d',
    SUBORDINATE_CLAUSE_MARKER: '#7c3aed',
    SUBORDINATE_SENTENCE_MARKER: '#7c3aed',
    VERB_ATTR_MARKER: '#84cc16',
    VERB_MODIFIER: '#d97706'
  };
  presentationState.ZERO_WIDTH_JOINER_RE = /[\u200C\u200D]/g;
  presentationState.ReaderLanguageAdapters =
    window.ReaderLanguageAdapters || (window.ReaderLanguageAdapters = {});
  presentationState._uiRenderDebugState = null;
  presentationState._uiRenderDebugPanelSeq = 0;
  presentationState._uiRenderDebugEventSeq = 0;
  presentationState._uiRenderDebugCollectionEnabled = false;
  window.ReaderUiDebug = window.ReaderUiDebug || {};
  window.ReaderUiDebug.trace = traceUiRenderEvent;
  window.ReaderUiDebug.startPanelSession = startUiRenderPanelSession;
  window.ReaderUiDebug.capturePanelSnapshot = captureUiRenderPanelSnapshot;
  window.ReaderUiDebug.captureBannerSnapshot = captureUiRenderBannerSnapshot;
  window.ReaderUiDebug.getState = function () {
    var debugState = ensureUiRenderDebugState();
    return debugState ? sanitizeUiRenderDebugValue(debugState, 0) : null;
  };
  return true;
}
