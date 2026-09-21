import { documentShellState } from './document-shell.state.mjs';
import {
  getLookupEntryFills,
  getLookupEntryResolution,
  getLookupEntryResolvedVia,
  getMwtPartSurfaceSliceText,
  getRenderableLlmGlossRows
} from './entry-editing.mjs';
import { buildGrammarPopupPronunciationRows } from './flashcards.mjs';
import {
  buildLlmGlossUpgradeMessageHtml,
  cloneLookupEntryForScopedPart,
  getLlmGlossEntryForSeg,
  shouldShowLlmGlossUpgradeMessage,
  tokenShouldShowSynthHint
} from './gloss-entries.mjs';
import { uposColorForTag } from './gloss-requests.mjs';
import { grammarPopupState } from './grammar-popup.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { koreanCompoundSynthGroupHasGreedy } from './mwt-anchors.mjs';
import { _filterDictFillForMwtPart } from './mwt-context.mjs';
import {
  buildHoverableAnnotatedLemmaHtml,
  buildPlainAnnotatedLemmaHtml,
  buildPlainLemmaDisplayHtml,
  escapeHtml,
  getHeadwordForms,
  getLanguageAdapter,
  getLemmaDisplayMeta,
  getTrimmedDisplayText,
  hasPersianVariantLemma,
  hasSameVisibleComparisonText,
  normalizeVisibleComparisonText,
  stripZeroWidthJoiners
} from './presentation.mjs';
import { getG2PMiniGroupTextSets } from './pronunciation-panel.mjs';
import { getExactSidePanelLookupEntry } from './segment-rendering.mjs';
import { isUnknownDictEntry } from './side-panel.mjs';
import { buildGrammarPopupTokenMapState, buildTokenMapLookupRequestOptions } from './token-banner.mjs';
import {
  buildTokenMapLookupHtml,
  buildTokenResolutionHtml,
  getRenderableTokenMapDisplaySliceItems,
  getTokenMapDictFill,
  getTokenMapResolvedVia,
  getTokenResolutionInfo
} from './token-map.mjs';
export function buildPopupHeadwordHtml(entry, fallbackHead) {
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.formatPopupHeadwordHtml === 'function') {
    var adaptedHtml = adapter.formatPopupHeadwordHtml(
      entry,
      fallbackHead,
      documentShellState.currentLanguage,
      escapeHtml
    );
    if (typeof adaptedHtml === 'string' && adaptedHtml) return adaptedHtml;
  }
  var forms = [];
  if (adapter && typeof adapter.getPopupHeadwordForms === 'function') {
    var popupForms = adapter.getPopupHeadwordForms(entry, fallbackHead, documentShellState.currentLanguage);
    if (Array.isArray(popupForms)) {
      forms = popupForms
        .map(function (f) {
          return String(f || '');
        })
        .filter(function (f) {
          return !!f;
        });
    }
  }
  if (!forms.length) {
    var info = getHeadwordForms(entry, fallbackHead);
    forms = Array.isArray(info.forms) ? info.forms : [];
  }
  var displayForms = [];
  var seenDisplay = Object.create(null);
  for (var i = 0; i < forms.length; i++) {
    var displayForm = stripZeroWidthJoiners(forms[i]);
    if (!displayForm.trim() || seenDisplay[displayForm]) continue;
    seenDisplay[displayForm] = true;
    displayForms.push(displayForm);
  }
  if (!displayForms.length) {
    var fallbackDisplay = stripZeroWidthJoiners(String(fallbackHead || ''));
    return escapeHtml(fallbackDisplay || String(fallbackHead || ''));
  }
  if (displayForms.length === 1) return escapeHtml(displayForms[0]);
  return (
    escapeHtml(displayForms[0]) +
    '<span class="popup-headword-alt">' +
    escapeHtml(displayForms[1]) +
    '</span>'
  );
}
export function getHeadlineLemmaCueSurfaceText(entry, fallbackSurface) {
  var text = getTrimmedDisplayText(fallbackSurface || '');
  if (text) return text;
  if (entry && typeof entry === 'object') {
    text = getTrimmedDisplayText(entry.text || entry.surface_form || entry.head || '');
    if (text) return text;
  }
  return '';
}
export function getHeadlineLemmaCueFillText(fillEntry) {
  if (!fillEntry || typeof fillEntry !== 'object') return '';
  return getTrimmedDisplayText(fillEntry._lemma_override || fillEntry.lemma_override || '');
}
export function collectHeadlineLemmaCueTexts(entry, fallbackSurface) {
  var e = entry && typeof entry === 'object' ? entry : null;
  var surfaceText = getHeadlineLemmaCueSurfaceText(e, fallbackSurface);
  var resolvedVia = e ? getLookupEntryResolvedVia(e) : '';
  var out = [];
  var seen = Object.create(null);
  function addText(rawText) {
    var text = getTrimmedDisplayText(rawText || '');
    if (!text) return;
    var key = normalizeVisibleComparisonText(text);
    if (!key || seen[key]) return;
    seen[key] = true;
    out.push(text);
  }
  var fillEntries = e && Array.isArray(e.dict_fill) ? e.dict_fill : [];
  if (fillEntries.length) {
    var fillTexts = [];
    var hasKnownFill = false;
    var allKnownOverride = true;
    for (var i = 0; i < fillEntries.length; i++) {
      var fillEntry = fillEntries[i] || {};
      if (isUnknownDictEntry(fillEntry)) continue;
      hasKnownFill = true;
      var fillResolutionSource = String(fillEntry.resolution_source || '')
        .trim()
        .toLowerCase();
      var isOverrideFill = !!(
        fillEntry._lemma_override ||
        fillEntry.lemma_override ||
        fillResolutionSource === 'lemma_override'
      );
      if (!isOverrideFill) {
        allKnownOverride = false;
        break;
      }
      var fillLemmaText = getHeadlineLemmaCueFillText(fillEntry);
      if (fillLemmaText) fillTexts.push(fillLemmaText);
    }
    if (hasKnownFill && allKnownOverride && fillTexts.length) {
      for (var fi = 0; fi < fillTexts.length; fi++) addText(fillTexts[fi]);
      if (out.length) {
        if (out.length === 1 && surfaceText && hasSameVisibleComparisonText(out[0], surfaceText)) return [];
        return out;
      }
    }
  }
  if (resolvedVia !== 'lemma_override') return [];
  var overrideParts = e && Array.isArray(e.lemma_override_parts) ? e.lemma_override_parts : [];
  for (var pi = 0; pi < overrideParts.length; pi++) {
    var part = overrideParts[pi] || {};
    if (part.matched === false) continue;
    addText(part.text || part.source_text || '');
  }
  if (out.length) {
    if (out.length === 1 && surfaceText && hasSameVisibleComparisonText(out[0], surfaceText)) return [];
    return out;
  }
  addText(getHeadlineLemmaCueFillText(e));
  if (!out.length) addText((e && (e.lemma_raw || e.lemma_form || e.lemma || '')) || '');
  if (out.length === 1 && surfaceText && hasSameVisibleComparisonText(out[0], surfaceText)) return [];
  return out;
}
export function buildHeadlineLemmaCueHtml(entry, fallbackSurface) {
  var lemmaTexts = collectHeadlineLemmaCueTexts(entry, fallbackSurface);
  if (!lemmaTexts.length) return '';
  var parts = [];
  for (var i = 0; i < lemmaTexts.length; i++) {
    parts.push(
      '<span class="popup-headline-lemma-part">' +
        buildPlainLemmaDisplayHtml(lemmaTexts[i], documentShellState.currentLanguage || '') +
        '</span>'
    );
  }
  return (
    '<span class="popup-headline-lemma-cue"><span class="popup-headline-lemma-arrow" aria-hidden="true">\u2192</span><span class="popup-headline-lemma-body">(' +
    parts.join('<span class="popup-headline-lemma-join" aria-hidden="true"> + </span>') +
    ')</span></span>'
  );
}
export function appendHeadlineLemmaCueHtml(mainHtml, entry, fallbackSurface) {
  var html = String(mainHtml || '');
  if (!html) return html;
  var cueHtml = buildHeadlineLemmaCueHtml(entry, fallbackSurface);
  return cueHtml ? html + cueHtml : html;
}
export function buildPopupSurfaceHeadlineHtml(entry, fallbackHead) {
  return buildPopupHeadwordHtml(entry, fallbackHead);
}
export function buildPopupHeadlineClass(contentHtml, extraClass) {
  var cls = 'popup-headline';
  var html = String(contentHtml || '');
  if (html.indexOf('panel-headword-token') >= 0 || html.indexOf('token-map-live-token') >= 0) {
    cls += ' popup-headline-inline-flow';
  }
  if (extraClass) cls += ' ' + String(extraClass || '').trim();
  return cls;
}
export function wrapPopupHeadlineHtml(contentHtml, styleAttr, extraClass) {
  var html = String(contentHtml || '');
  var attrs = String(styleAttr || '');
  var cls = buildPopupHeadlineClass(html, extraClass);
  return '<div class="' + cls + '"' + attrs + '>' + html + '</div>';
}
export function getHeadwordComponentHoverSlices(componentEl) {
  if (!componentEl || !componentEl.dataset) return [];
  if (Array.isArray(componentEl.__hoverSlicesCache)) return componentEl.__hoverSlicesCache;
  var encoded = String(componentEl.dataset.hoverSlices || '').trim();
  if (!encoded) return [];
  try {
    var parsed = JSON.parse(decodeURIComponent(encoded));
    var out = [];
    for (var i = 0; i < parsed.length; i++) {
      var row = parsed[i] || {};
      var seg = String(row.seg || '').trim();
      var start = parseInt(row.start, 10);
      var end = parseInt(row.end, 10);
      if (!seg || !isFinite(start) || !isFinite(end) || end <= start) continue;
      out.push({
        seg: seg,
        start: start,
        end: end
      });
    }
    componentEl.__hoverSlicesCache = out;
    return out;
  } catch (_e) {
    return [];
  }
}
export function getFirstTextNode(rootEl) {
  if (!rootEl || !document || typeof document.createTreeWalker !== 'function') return null;
  var walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, null);
  return walker.nextNode();
}
export function resolveHeadwordComponentHoverSeg(componentEl, clientX, clientY) {
  if (!componentEl) return '';
  var hoverMode = String(componentEl.dataset.hoverMode || 'lookup')
    .trim()
    .toLowerCase();
  var fallbackSeg = String(componentEl.dataset.seg || '').trim();
  if (hoverMode !== 'decompose-slices') return fallbackSeg;
  var slices = getHeadwordComponentHoverSlices(componentEl);
  if (!slices.length) return fallbackSeg;
  var textNode = getFirstTextNode(componentEl);
  if (!textNode) return fallbackSeg;
  for (var i = 0; i < slices.length; i++) {
    var slice = slices[i] || {};
    var start = parseInt(slice.start, 10);
    var end = parseInt(slice.end, 10);
    if (!isFinite(start) || !isFinite(end) || end <= start) continue;
    var range = document.createRange();
    try {
      range.setStart(textNode, start);
      range.setEnd(textNode, end);
    } catch (_e) {
      continue;
    }
    var rects = range.getClientRects();
    for (var ri = 0; ri < rects.length; ri++) {
      var rect = rects[ri];
      if (!rect) continue;
      if (
        clientX >= rect.left - 1 &&
        clientX <= rect.right + 1 &&
        clientY >= rect.top - 1 &&
        clientY <= rect.bottom + 1
      ) {
        return String(slice.seg || '').trim() || fallbackSeg;
      }
    }
  }
  return fallbackSeg;
}
export function mergePanelEntryLanguageFields(targetEntry, parentEntry) {
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.mergePanelEntryFields === 'function') {
    adapter.mergePanelEntryFields(targetEntry, parentEntry, documentShellState.currentLanguage);
  }
}
export function buildPanelHeadwordHoverHtml(entry, fallbackHead) {
  var info = getHeadwordForms(entry, fallbackHead);
  var forms = Array.isArray(info.forms) ? info.forms : [];
  var visibleForms = [];
  for (var i = 0; i < forms.length; i++) {
    var rawForm = String(forms[i] || '');
    var displayForm = stripZeroWidthJoiners(rawForm);
    if (!displayForm.trim()) continue;
    visibleForms.push({
      raw: rawForm,
      display: displayForm
    });
    if (visibleForms.length >= 2) break;
  }
  if (!visibleForms.length) {
    var fallbackDisplay = stripZeroWidthJoiners(String(fallbackHead || ''));
    return escapeHtml(fallbackDisplay || String(fallbackHead || ''));
  }
  var psrApi = window.PanelSegmentRenderer || null;
  if (visibleForms.length === 1) {
    return psrApi && typeof psrApi.renderLookupSpanHtml === 'function'
      ? psrApi.renderLookupSpanHtml(visibleForms[0].raw, {
          displayText: visibleForms[0].display
        })
      : escapeHtml(visibleForms[0].display);
  }
  if (psrApi && typeof psrApi.renderLookupSpanHtml === 'function') {
    return (
      psrApi.renderLookupSpanHtml(visibleForms[0].raw, {
        displayText: visibleForms[0].display
      }) +
      '<span class="popup-headword-alt">' +
      psrApi.renderLookupSpanHtml(visibleForms[1].raw, {
        displayText: visibleForms[1].display
      }) +
      '</span>'
    );
  }
  return (
    escapeHtml(visibleForms[0].display) +
    '<span class="popup-headword-alt">' +
    escapeHtml(visibleForms[1].display) +
    '</span>'
  );
}
export function getTokenResolutionDictFill(entry, fullData) {
  if (fullData && Array.isArray(fullData.tokenDictFill)) return fullData.tokenDictFill;
  if (fullData && Array.isArray(fullData.dictFill)) return fullData.dictFill;
  return getLookupEntryFills(entry);
}
export function getTokenLiveResolution(entry) {
  return getLookupEntryResolution(entry);
}
export function getPanelTokenCompareInfo(entry, fallbackHead, fullData) {
  var panelTokenEntry =
    fullData && fullData._panelTokenEntry && typeof fullData._panelTokenEntry === 'object'
      ? fullData._panelTokenEntry
      : null;
  var tokenSurface = '';
  if (fullData && fullData._panelTokenSurface != null)
    tokenSurface = String(fullData._panelTokenSurface || '');
  if (!tokenSurface && panelTokenEntry && panelTokenEntry.surface_form != null)
    tokenSurface = String(panelTokenEntry.surface_form || '');
  if (!tokenSurface && entry && entry.surface_form != null) tokenSurface = String(entry.surface_form || '');
  if (!tokenSurface) tokenSurface = String(fallbackHead || '');
  var tokenLemma = '';
  if (fullData && fullData._panelTokenLemma != null) tokenLemma = String(fullData._panelTokenLemma || '');
  if (!tokenLemma && panelTokenEntry && panelTokenEntry.lemma_form != null)
    tokenLemma = String(panelTokenEntry.lemma_form || '');
  if (!tokenLemma && panelTokenEntry && panelTokenEntry.lemma != null)
    tokenLemma = String(panelTokenEntry.lemma || '');
  if (!tokenLemma && entry && entry.lemma_form != null) tokenLemma = String(entry.lemma_form || '');
  if (!tokenLemma && entry && entry.lemma != null) tokenLemma = String(entry.lemma || '');
  var tokenLemmaRaw = '';
  if (fullData && fullData._panelTokenLemmaRaw != null)
    tokenLemmaRaw = String(fullData._panelTokenLemmaRaw || '');
  if (!tokenLemmaRaw && panelTokenEntry && panelTokenEntry.lemma_raw != null)
    tokenLemmaRaw = String(panelTokenEntry.lemma_raw || '');
  if (!tokenLemmaRaw && entry && entry.lemma_raw != null) tokenLemmaRaw = String(entry.lemma_raw || '');
  if (!tokenLemmaRaw) tokenLemmaRaw = tokenLemma;
  tokenSurface = tokenSurface.trim();
  tokenLemma = tokenLemma.trim();
  tokenLemmaRaw = tokenLemmaRaw.trim();
  var lemmaMeta = getLemmaDisplayMeta(tokenLemma, tokenLemmaRaw);
  if (!tokenLemma) return null;
  if (!lemmaMeta.hasRawSuffix && hasSameVisibleComparisonText(tokenLemma, tokenSurface)) return null;
  var liveResolution = getTokenLiveResolution(panelTokenEntry || entry);
  if (!liveResolution) return null;
  if (liveResolution.compare_kind === 'surface') {
    return {
      kind: 'surface',
      text: tokenSurface
    };
  }
  if (liveResolution.compare_kind !== 'lemma') return null;
  return {
    kind: 'lemma',
    text: tokenLemma,
    rawText: tokenLemmaRaw
  };
}
export function buildAlwaysHoverableLemmaHtml(rawText, headDecompByForm, langOverride) {
  var text = String(rawText || '');
  if (!text) return '';
  if (hasPersianVariantLemma(text, langOverride)) {
    return buildPlainLemmaDisplayHtml(text, langOverride);
  }
  var psrApi = window.PanelSegmentRenderer || null;
  if (psrApi && typeof psrApi.renderLookupSequenceHtml === 'function') {
    var psrDecomp = headDecompByForm && Array.isArray(headDecompByForm[text]) ? headDecompByForm[text] : null;
    return psrApi.renderLookupSequenceHtml(text, {
      decomp: psrDecomp || null
    });
  }
  return buildPlainLemmaDisplayHtml(text, langOverride);
}
export function buildPanelLemmaCompareHtml(entry, fallbackHead, fullData, headDecompByForm) {
  if (fullData && fullData._panelManualSearch) return '';
  var compareInfo = getPanelTokenCompareInfo(entry, fallbackHead, fullData);
  if (!compareInfo || !compareInfo.text) return '';
  var requestLang =
    fullData && fullData._lookupLang
      ? String(fullData._lookupLang)
      : String(documentShellState.currentLanguage || '');
  var label = compareInfo.kind === 'surface' ? 'Surface String' : 'Lemma';
  var tone =
    compareInfo.kind === 'surface'
      ? {
          border: '#bfdbfe',
          bg: 'linear-gradient(180deg, #f8fbff 0%, #eff6ff 100%)',
          text: '#1d4ed8',
          value: '#1e3a8a',
          shadow: 'rgba(59, 130, 246, 0.08)'
        }
      : {
          border: '#cbd5e1',
          bg: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
          text: '#64748b',
          value: '#334155',
          shadow: 'rgba(15, 23, 42, 0.06)'
        };
  var valueHtml = '';
  if (compareInfo.kind === 'lemma') {
    valueHtml = buildHoverableAnnotatedLemmaHtml(
      compareInfo.text,
      compareInfo.rawText,
      headDecompByForm,
      requestLang
    );
  } else {
    // Surface compare: use buildTokenMapLookupHtml so fill-hit sub-spans
    // get rendered for individual hover, same as the token banner.
    var surfaceLookupEntry =
      (hoverLayoutState.tokenMapData && hoverLayoutState.tokenMapData.surfaceLookup) ||
      getExactSidePanelLookupEntry(
        compareInfo.text,
        requestLang,
        buildTokenMapLookupRequestOptions('surface', hoverLayoutState.tokenMapData, null)
      ) ||
      null;
    if (surfaceLookupEntry) {
      valueHtml = buildTokenMapLookupHtml(surfaceLookupEntry, compareInfo.text, 'surface', {});
    } else {
      valueHtml = buildAlwaysHoverableLemmaHtml(compareInfo.text, headDecompByForm, requestLang);
    }
  }
  if (!valueHtml) return '';
  return (
    '' +
    '<div class="panel-lemma-compare" style="margin-left:auto;max-width:48%;min-width:0;text-align:right;display:flex;align-items:baseline;justify-content:flex-end;">' +
    '<div style="padding:4px 10px 5px 10px;border:1px solid ' +
    tone.border +
    ';border-radius:10px;background:' +
    tone.bg +
    ';color:' +
    tone.value +
    ';font-size:18px;line-height:1.1;display:inline-flex;align-items:baseline;justify-content:flex-end;gap:7px;box-shadow:0 1px 2px ' +
    tone.shadow +
    ';white-space:nowrap;flex-wrap:nowrap;max-width:100%;overflow:hidden;">' +
    '<span style="color:' +
    tone.text +
    ';font-size:12px;font-weight:700;letter-spacing:0.02em;">' +
    escapeHtml(label) +
    ':</span>' +
    '<span style="font-weight:500;letter-spacing:0.005em;white-space:nowrap;display:inline-flex;align-items:baseline;gap:0;flex-wrap:nowrap;">' +
    valueHtml +
    '</span>' +
    '</div>' +
    '</div>'
  );
}
export function formatGrammarGlossText(rawText) {
  var text = String(rawText || '').trim();
  if (!text) return '';
  var firstLetterIdx = text.search(/[A-Za-z]/);
  if (firstLetterIdx < 0) return text;
  var wordEndIdx = firstLetterIdx;
  while (wordEndIdx < text.length && /[A-Za-z]/.test(text.charAt(wordEndIdx))) {
    wordEndIdx++;
  }
  var prefix = text.slice(0, firstLetterIdx);
  var firstWord = text.slice(firstLetterIdx, wordEndIdx);
  var suffix = text.slice(wordEndIdx);
  if (!firstWord) return text;
  if (/^[A-Z]+$/.test(firstWord)) {
    return prefix + firstWord + suffix;
  }
  return prefix + firstWord.charAt(0).toUpperCase() + firstWord.slice(1).toLowerCase() + suffix;
}
export function getDependencyHoverText(depLabel) {
  var key = String(depLabel || '')
    .trim()
    .toLowerCase();
  if (!key) return '';
  if (Object.prototype.hasOwnProperty.call(grammarPopupState.UD_DEP_HOVER_TEXT, key)) {
    return formatGrammarGlossText(grammarPopupState.UD_DEP_HOVER_TEXT[key]);
  }
  var base = key.split(':')[0];
  if (base && Object.prototype.hasOwnProperty.call(grammarPopupState.UD_DEP_HOVER_TEXT, base)) {
    return formatGrammarGlossText(grammarPopupState.UD_DEP_HOVER_TEXT[base]);
  }
  return '';
}
export function normalizeDepLabel(rawDepLabel) {
  var depLabel = String(rawDepLabel || '');
  if (!depLabel) return '';
  return depLabel.toLowerCase() === 'root' ? 'ROOT' : depLabel;
}
export function buildPopupPosBadgeHtml(posData, options) {
  if (!posData) return '';
  var uposLabelText = String(posData.upos_label || posData.upos || '');
  if (!uposLabelText) return '';
  var opts = options || {};
  var withMargin = !!opts.withMargin;
  var uposStyle = 'display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:600;';
  if (withMargin) uposStyle += 'margin-left:6px;';
  if (posData.upos_color) {
    uposStyle += 'background-color:' + String(posData.upos_color) + ';color:#000;';
  }
  return (
    '<span class="pos-badge" title="Coarse POS (UPOS)" style="' +
    uposStyle +
    '">' +
    escapeHtml(uposLabelText) +
    '</span>'
  );
}
export function loadXposDescriptionsForLanguage(langOverride) {
  var lang = String(langOverride || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  if (lang === 'ancient-greek' || lang === 'ancientgreek' || lang === 'ancient greek') {
    lang = 'grc';
  } else if (lang === 'modern-greek' || lang === 'moderngreek' || lang === 'modern greek') {
    lang = 'el';
  } else {
    var dash = lang.indexOf('-');
    if (dash > 0) lang = lang.slice(0, dash);
  }
  if (lang === 'chinese') lang = 'zh';
  if (lang === 'japanese') lang = 'ja';
  grammarPopupState._activeXposLang = lang;
  return Promise.resolve(!!window.TRANKIT_TAGS.getXposMap(lang));
}
export function getXposDescription(xposLabel) {
  var raw = String(xposLabel || '').trim();
  if (!raw) return '';
  var desc = window.TRANKIT_TAGS.getXpos(grammarPopupState._activeXposLang, raw);
  return desc ? formatGrammarGlossText(desc) : '';
}
export function buildPopupXposBadgeHtml(posData) {
  if (!posData) return '';
  var xposLabel = String(posData.tag || posData.xpos || '').trim();
  if (!xposLabel) return '';
  var parts = xposLabel.indexOf('+') !== -1 ? xposLabel.split('+') : [xposLabel];
  var html = '';
  for (var i = 0; i < parts.length; i++) {
    var tag = parts[i].trim();
    if (!tag) continue;
    var desc = getXposDescription(tag);
    html += '<div style="line-height:1.4;">';
    html += '<span class="pos-badge xpos-badge" title="Fine POS (XPOS)">' + escapeHtml(tag) + '</span>';
    if (desc) {
      html += '<span class="headword-grammar-xpos-text">' + escapeHtml(desc) + '</span>';
    }
    html += '</div>';
  }
  return html;
}
export function normalizeGrammarMetaValue(rawValue) {
  if (rawValue == null) return '';
  if (typeof rawValue === 'string') return rawValue.trim();
  if (Array.isArray(rawValue)) {
    var arrParts = [];
    for (var i = 0; i < rawValue.length; i++) {
      var item = String(rawValue[i] == null ? '' : rawValue[i]).trim();
      if (item) arrParts.push(item);
    }
    return arrParts.join('|');
  }
  if (typeof rawValue === 'object') {
    var objParts = [];
    for (var key in rawValue) {
      if (!Object.prototype.hasOwnProperty.call(rawValue, key)) continue;
      var k = String(key || '').trim();
      var v = String(rawValue[key] == null ? '' : rawValue[key]).trim();
      if (!k && !v) continue;
      objParts.push(k ? k + '=' + v : v);
    }
    return objParts.join('|');
  }
  return String(rawValue).trim();
}
export function filterFeatsForLang(featsStr, lang) {
  var l = String(lang || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  if (l !== 'ang') return featsStr;
  // Old English: strip Uninflected=Yes — it applies to almost every token and adds no value
  var parts = featsStr.split('|');
  var filtered = [];
  for (var i = 0; i < parts.length; i++) {
    if (parts[i].trim() !== 'Uninflected=Yes') filtered.push(parts[i]);
  }
  return filtered.join('|');
}
export function getFeatDescription(feat) {
  var key = String(feat || '').trim();
  if (!key) return '';
  if (Object.prototype.hasOwnProperty.call(grammarPopupState.FEATS_DESCRIPTIONS, key)) {
    return formatGrammarGlossText(grammarPopupState.FEATS_DESCRIPTIONS[key]);
  }
  return '';
}
export function buildPopupFeatsRowsHtml(rawValue) {
  var value = normalizeGrammarMetaValue(rawValue);
  if (!value) return '';
  var feats = value.split('|');
  var rows = [];
  for (var i = 0; i < feats.length; i++) {
    var f = feats[i].trim();
    if (!f) continue;
    var desc = getFeatDescription(f);
    var html =
      '<div class="popup-headword-grammar-row popup-headword-meta-row popup-headword-feats-row">' +
      '<span class="headword-grammar-meta-pill">' +
      escapeHtml(f) +
      '</span>';
    if (desc) {
      html += '<span class="headword-grammar-meta-text">' + escapeHtml(desc) + '</span>';
    }
    html += '</div>';
    rows.push(html);
  }
  return rows.join('');
}
export function buildPopupGrammarMetaRowHtml(label, rawValue, rowClass) {
  var value = normalizeGrammarMetaValue(rawValue);
  if (!value) return '';
  var extraClass = rowClass ? ' ' + String(rowClass) : '';
  return (
    '<div class="popup-headword-grammar-row popup-headword-meta-row' +
    extraClass +
    '">' +
    '<span class="headword-grammar-meta-pill">' +
    escapeHtml(label) +
    '</span>' +
    '<span class="headword-grammar-meta-text">' +
    escapeHtml(value) +
    '</span>' +
    '</div>'
  );
}
export function uniqueStringList(raw) {
  var src = Array.isArray(raw) ? raw : raw ? [raw] : [];
  var out = [];
  var seen = Object.create(null);
  for (var i = 0; i < src.length; i++) {
    var text = String(src[i] == null ? '' : src[i]).trim();
    if (!text || seen[text]) continue;
    seen[text] = true;
    out.push(text);
  }
  return out;
}
export function extractMorphMetaFromPosData(posData) {
  var out = {
    morphInfo: [],
    morphBase: '',
    grammar: ''
  };
  if (!posData || typeof posData !== 'object') return out;
  out.morphInfo = uniqueStringList(posData.morph_info);
  out.morphBase = String(posData.morph_base || '').trim();
  out.grammar = String(posData.grammar || '').trim();
  if (out.morphInfo.length || out.morphBase || out.grammar) return out;
  var fill = Array.isArray(posData.dict_fill) ? posData.dict_fill : [];
  for (var i = 0; i < fill.length; i++) {
    var f = fill[i] || {};
    var morphInfo = uniqueStringList(f.morph_info);
    var morphBase = String(f.morph_base || '').trim();
    var grammar = String(f.grammar || '').trim();
    if (!morphInfo.length && !morphBase && !grammar) continue;
    out.morphInfo = morphInfo;
    out.morphBase = morphBase;
    out.grammar = grammar;
    return out;
  }
  return out;
}
export function buildGrammarPopupHtml(posData, udTok, tokenText, tokenEntry, options) {
  var tokenMapState = buildGrammarPopupTokenMapState(posData, udTok, tokenText, tokenEntry, options);
  var _gpPartIdxInit = options && isFinite(Number(options.mwtPartIndex)) ? Number(options.mwtPartIndex) : -1;
  var _gpMwtPartsInit = udTok && Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
  var _gpChild =
    _gpPartIdxInit >= 0 && _gpMwtPartsInit[_gpPartIdxInit] ? _gpMwtPartsInit[_gpPartIdxInit] : null;
  var _gpIsMwtChild = _gpPartIdxInit >= 0;
  function _gpSliceByIdx(val) {
    if (_gpPartIdxInit < 0 || !val || val.indexOf('+') === -1) return val;
    var parts = String(val).split('+');
    return _gpPartIdxInit < parts.length ? parts[_gpPartIdxInit].trim() : val;
  }
  var depLabel = (posData && (posData.dep_label || posData.dep)) || '';
  if (!depLabel && udTok && udTok.dep) depLabel = udTok.dep;
  depLabel = normalizeDepLabel(depLabel);
  depLabel = _gpSliceByIdx(depLabel);
  if (_gpChild && _gpChild.dep) depLabel = normalizeDepLabel(String(_gpChild.dep));
  var uposLabel = (posData && (posData.upos_label || posData.upos)) || '';
  uposLabel = _gpSliceByIdx(uposLabel);
  if (_gpChild && _gpChild.upos) uposLabel = String(_gpChild.upos);
  var uposColor = (posData && posData.upos_color) || '';
  var xposLabel = String((posData && (posData.tag || posData.xpos)) || '').trim();
  var _gpLang = String(documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  var _gpKeepTokenXpos = _gpLang === 'ko' || _gpLang === 'korean' || _gpLang.indexOf('ko-') === 0;
  if (!_gpKeepTokenXpos) xposLabel = _gpSliceByIdx(xposLabel);
  if (_gpChild && (_gpChild.tag || _gpChild.xpos)) xposLabel = String(_gpChild.tag || _gpChild.xpos);
  var lemmaValue = getTrimmedDisplayText(
    (tokenMapState && tokenMapState.lemma) ||
      (posData && (posData.lemma || '')) ||
      (udTok && (udTok.lemma || '')) ||
      ''
  );
  var lemmaRawValue = getTrimmedDisplayText(
    (tokenMapState && tokenMapState.lemma_raw) ||
      (posData && (posData.lemma_raw || '')) ||
      (udTok && (udTok.lemma_raw || '')) ||
      lemmaValue
  );
  if (_gpChild && _gpChild.lemma) {
    lemmaValue = String(_gpChild.lemma);
    lemmaRawValue = lemmaValue;
  }
  var lemmaMeta = getLemmaDisplayMeta(lemmaValue, lemmaRawValue);
  var featsValue = (posData && (posData.feats || '')) || (udTok && (udTok.feats || '')) || '';
  featsValue = _gpSliceByIdx(featsValue);
  var conjugationData = !_gpIsMwtChild && posData && posData.conjugation ? posData.conjugation : null;
  var _gpParentSurfaceForSlice = String(
    (tokenMapState && tokenMapState.surface) || tokenText || (tokenEntry && tokenEntry.surface_form) || ''
  );
  var _gpLookupText = String(
    (options && (options.lookupText || options.mwtChildText)) ||
      (tokenMapState && (tokenMapState.lookupText || tokenMapState.mwtChildText)) ||
      ''
  ).trim();
  var _gpChildSliceText = '';
  if (_gpPartIdxInit >= 0) {
    _gpChildSliceText = String(
      (options && (options.anchorText || options.mwtSurfaceSlice)) ||
        (tokenMapState && (tokenMapState.anchorText || tokenMapState.mwtSurfaceSlice)) ||
        ''
    ).trim();
    if (!_gpChildSliceText) {
      _gpChildSliceText = getMwtPartSurfaceSliceText(_gpParentSurfaceForSlice, udTok, _gpPartIdxInit, '');
    }
  }
  var surfaceRaw = _gpChildSliceText || _gpParentSurfaceForSlice;
  var surfaceValue = getTrimmedDisplayText(surfaceRaw);
  var dictFill = getTokenMapDictFill(tokenMapState);
  var resolvedVia = getTokenMapResolvedVia(tokenMapState);
  var entrySliceItems = getRenderableTokenMapDisplaySliceItems(tokenMapState);
  if (_gpPartIdxInit >= 0) {
    var _gpFiltered = _filterDictFillForMwtPart(dictFill, _gpPartIdxInit);
    if (_gpFiltered && Array.isArray(_gpFiltered.rows) && _gpFiltered.rows.length) {
      dictFill = _gpFiltered.rows;
      var _gpKeepIdx = {};
      for (var _gpki = 0; _gpki < _gpFiltered.origIndexes.length; _gpki++) {
        _gpKeepIdx[String(_gpFiltered.origIndexes[_gpki])] = true;
      }
      var _gpFilteredItems = [];
      for (var _gpii = 0; _gpii < entrySliceItems.length; _gpii++) {
        var _gpIt = entrySliceItems[_gpii] || {};
        var _gpFi = Array.isArray(_gpIt.fillIndexes) ? _gpIt.fillIndexes : [];
        var _gpAny = false;
        for (var _gpfj = 0; _gpfj < _gpFi.length; _gpfj++) {
          if (_gpKeepIdx[String(_gpFi[_gpfj])]) {
            _gpAny = true;
            break;
          }
        }
        if (_gpAny) _gpFilteredItems.push(_gpIt);
      }
      entrySliceItems = _gpFilteredItems;
    }
  }
  featsValue = filterFeatsForLang(normalizeGrammarMetaValue(featsValue));
  var rows = [];
  var tailRows = [];
  var glossRows = [];
  if (surfaceValue) {
    rows.push(
      '<tr><td class="gp-label">Surface</td><td class="gp-lemma-val">' +
        buildPlainLemmaDisplayHtml(surfaceValue, documentShellState.currentLanguage || '') +
        '</td></tr>'
    );
  }

  // Per-child MWT display: when rendering a single MWT child, show the
  // unsandhied child text as a separate "MWT" row when it differs from the
  // orthographic surface slice (e.g. Sanskrit sandhi).
  if (_gpIsMwtChild) {
    var _gpChildText = _gpLookupText;
    var _gpSliceText = String(
      (options && (options.anchorText || options.mwtSurfaceSlice)) || surfaceValue || ''
    ).trim();
    if (_gpChildText && _gpSliceText && !hasSameVisibleComparisonText(_gpChildText, _gpSliceText)) {
      rows.push(
        '<tr><td class="gp-label">MWT</td><td class="gp-lemma-val">' +
          buildPlainLemmaDisplayHtml(_gpChildText, documentShellState.currentLanguage || '') +
          '</td></tr>'
      );
    }
  } else {
    var _gpMwtParts = udTok && Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
    if (_gpMwtParts.length >= 2) {
      var _gpMwtTexts = [];
      for (var _mi = 0; _mi < _gpMwtParts.length; _mi++) {
        var _mp = _gpMwtParts[_mi] || {};
        var _mt = String(_mp.text || '').trim();
        if (!_mt || _mt === '_') _mt = String(_mp.lemma || '').trim();
        if (_mt) _gpMwtTexts.push(_mt);
      }
      var _gpMwtJoined = _gpMwtTexts.join('');
      if (_gpMwtJoined && !hasSameVisibleComparisonText(_gpMwtJoined, surfaceValue)) {
        var _gpMwtDisplay = _gpMwtTexts.join(' + ');
        rows.push(
          '<tr><td class="gp-label">MWT</td><td class="gp-lemma-val">' +
            buildPlainLemmaDisplayHtml(_gpMwtDisplay, documentShellState.currentLanguage || '') +
            '</td></tr>'
        );
      }
    }
  }
  var g2pRows = buildGrammarPopupPronunciationRows(
    _gpIsMwtChild ? surfaceValue : tokenText || surfaceValue,
    String(documentShellState.currentLanguage || ''),
    tokenEntry && tokenEntry.g2p,
    {
      groupTextSets: getG2PMiniGroupTextSets(
        _gpIsMwtChild ? surfaceValue : tokenText || surfaceValue,
        udTok,
        tokenEntry
      )
    }
  );
  if (g2pRows.length) {
    rows = rows.concat(g2pRows);
  }
  var resolutionTokenEntry =
    (tokenMapState && (tokenMapState.tokenEntry || tokenMapState.entry)) || tokenEntry;
  resolutionTokenEntry = cloneLookupEntryForScopedPart(resolutionTokenEntry, dictFill, _gpPartIdxInit);
  resolvedVia = getLookupEntryResolvedVia(resolutionTokenEntry) || resolvedVia;
  var resolutionInfo = getTokenResolutionInfo(
    surfaceValue,
    lemmaValue,
    resolutionTokenEntry,
    dictFill,
    resolvedVia
  );
  var resolvedHtml = buildTokenResolutionHtml(
    resolutionInfo,
    function (text, kind) {
      var cls = kind === 'secondary' ? 'gp-pill gp-feat-pill' : 'gp-pill gp-dep-pill';
      return '<span class="' + cls + '">' + escapeHtml(text) + '</span>';
    },
    function (text) {
      return '<span class="gp-desc">' + escapeHtml(text) + '</span>';
    }
  );
  /*
  if (resolvedHtml) {
    tailRows.push('<tr><td class="gp-label">Resolved</td><td>' + resolvedHtml + '</td></tr>');
  }
   if (entrySliceItems.length) {
    var entryCells = [];
    for (var esi = 0; esi < entrySliceItems.length; esi++) {
      var item = entrySliceItems[esi] || {};
      var itemText = String(item.text || '');
      if (!itemText) continue;
      var itemUnknown = !!item.isUnknown;
      var itemLemmaDerived = !!item.isLemmaDerived;
      var itemBorder = itemUnknown ? '#d1d5db' : (itemLemmaDerived ? '#f59e0b' : '#bfdbfe');
      var itemBackground = itemUnknown ? '#f8fafc' : (itemLemmaDerived ? '#fffbeb' : '#eff6ff');
      var itemColor = itemUnknown ? '#111827' : (itemLemmaDerived ? '#92400e' : '#2563eb');
      entryCells.push(
        '<span class="gp-pill" style="margin-right:4px;margin-bottom:4px;display:inline-block;border:1px solid ' +
        itemBorder + ';background:' + itemBackground + ';color:' + itemColor + ';">' +
        escapeHtml(itemText) + '</span>'
      );
    }
    if (entryCells.length) {
      tailRows.push('<tr><td class="gp-label">Entries</td><td>' + entryCells.join('') + '</td></tr>');
    }
  }
  */

  // LLM gloss row(s) sit at the bottom of the grammar popup.
  var _glossSegIdx = options && typeof options.segIdx === 'number' ? options.segIdx : -1;
  var _gEntry = getLlmGlossEntryForSeg(_glossSegIdx);
  var _gpGlossRowsAdded = false;
  if (_gEntry) {
    var _gpPartIdx = _gpIsMwtChild ? Number(options.mwtPartIndex) : -1;
    var _gpGlossRenderRows = getRenderableLlmGlossRows(
      _gEntry,
      surfaceValue || tokenText || '',
      {
        entry: tokenEntry,
        udTok: udTok,
        posData: posData,
        lemma: lemmaValue,
        lemma_raw: lemmaRawValue
      },
      {
        isMwtChild: _gpIsMwtChild,
        partIndex: _gpPartIdx,
        childLemma: (posData && posData.lemma) || ''
      }
    );
    for (var _lgi = 0; _lgi < _gpGlossRenderRows.length; _lgi++) {
      var _gpRow = _gpGlossRenderRows[_lgi] || {};
      var _lgLabel = _lgi === 0 ? 'Gloss' : '';
      var _lgLemma = String(_gpRow.lemma || '').trim();
      var _lgVal = String(_gpRow.gloss || '').trim();
      if (!_lgVal) continue;
      if (_lgLemma) {
        glossRows.push(
          '<tr><td class="gp-label">' +
            escapeHtml(_lgLabel) +
            '</td><td><span class="gp-pill gp-feat-pill" style="background:#e0f2fe;border-color:#7dd3fc;color:#0369a1;">' +
            escapeHtml(_lgLemma) +
            '</span> <span class="gp-desc">' +
            escapeHtml(_lgVal) +
            '</span></td></tr>'
        );
      } else {
        glossRows.push(
          '<tr><td class="gp-label">' +
            escapeHtml(_lgLabel || 'Gloss') +
            '</td><td><span class="gp-desc" style="color:#0369a1;">' +
            escapeHtml(_lgVal) +
            '</span></td></tr>'
        );
      }
      _gpGlossRowsAdded = true;
    }
  }
  if (!_gpGlossRowsAdded && shouldShowLlmGlossUpgradeMessage()) {
    glossRows.push(
      '<tr><td class="gp-label">Gloss</td><td>' + buildLlmGlossUpgradeMessageHtml() + '</td></tr>'
    );
  }
  // Dep relation row \u2014 split MWT compound deps (e.g. "cc+nmod+nmod:poss") into side-by-side pills
  if (depLabel) {
    var depParts = depLabel.indexOf('+') !== -1 ? depLabel.split('+') : [depLabel];
    var depPills = '';
    for (var di = 0; di < depParts.length; di++) {
      var dTag = depParts[di].trim();
      if (!dTag) continue;
      var _gpDepGloss = getDependencyHoverText(dTag);
      if (depPills) depPills += ' ';
      depPills += _gpDepGloss
        ? '<span class="gp-pill gp-dep-pill">' + escapeHtml(_gpDepGloss) + '</span>'
        : '<span class="gp-pill gp-dep-pill" style="color:#dc2626;border-color:#ef4444;">' +
          escapeHtml(dTag) +
          '</span>';
    }
    if (depPills) rows.push('<tr><td class="gp-label">Dep</td><td>' + depPills + '</td></tr>');
  }

  // UPOS row � split MWT compound tags (e.g. "CCONJ+NOUN+PRON") into side-by-side pills
  if (uposLabel) {
    var uposParts = uposLabel.indexOf('+') !== -1 ? uposLabel.split('+') : [uposLabel];
    var uposPills = '';
    for (var ui = 0; ui < uposParts.length; ui++) {
      var uTag = uposParts[ui].trim();
      if (!uTag) continue;
      var uColor = uposColorForTag(uTag);
      var uStyle = uColor ? ' style="background-color:' + escapeHtml(String(uColor)) + ';color:#000;"' : '';
      if (uposPills) uposPills += ' ';
      uposPills += '<span class="gp-pill gp-upos-pill"' + uStyle + '>' + escapeHtml(uTag) + '</span>';
    }
    if (uposPills) rows.push('<tr><td class="gp-label">UPoS</td><td>' + uposPills + '</td></tr>');
  }

  // XPOS row � split compound tags (e.g. "E+RD") into side-by-side pills
  if (xposLabel) {
    var xposParts = /[+\uFF0B]/.test(xposLabel) ? xposLabel.split(/[+\uFF0B]/) : [xposLabel];
    var xposPills = '';
    for (var xi = 0; xi < xposParts.length; xi++) {
      var xtag = xposParts[xi].trim();
      if (!xtag) continue;
      var _gpXDesc = getXposDescription(xtag);
      xposPills += '<div class="gp-xpos-stack-item">';
      xposPills += _gpXDesc
        ? '<span class="gp-pill gp-xpos-pill">' + escapeHtml(_gpXDesc) + '</span>'
        : '<span class="gp-pill gp-xpos-pill" style="color:#dc2626;border-color:#ef4444;">' +
          escapeHtml(xtag) +
          '</span>';
      xposPills += '</div>';
    }
    if (xposPills) rows.push('<tr><td class="gp-label">XPoS</td><td>' + xposPills + '</td></tr>');
  }

  // Feats rows � vertical layout; MWT tokens get tab-separated columns
  if (featsValue) {
    var featBundles = featsValue.indexOf('+') !== -1 ? featsValue.split('+') : [featsValue];
    var isMwtFeats = featBundles.length > 1;
    if (isMwtFeats) {
      // Parse each bundle into an array of pill HTML strings
      var columns = [];
      var maxRows = 0;
      for (var bi = 0; bi < featBundles.length; bi++) {
        var bundle = featBundles[bi].trim();
        var col = [];
        if (bundle) {
          var feats = bundle.split('|');
          for (var fi = 0; fi < feats.length; fi++) {
            var f = feats[fi].trim();
            if (!f) continue;
            var _gpFDesc = getFeatDescription(f);
            col.push(
              _gpFDesc
                ? '<span class="gp-pill gp-feat-pill">' + escapeHtml(_gpFDesc) + '</span>'
                : '<span class="gp-pill gp-feat-pill" style="color:#dc2626;border-color:#ef4444;">' +
                    escapeHtml(f) +
                    '</span>'
            );
          }
        }
        if (col.length === 0) col.push('<span class="gp-pill gp-feat-pill gp-feat-empty">\u2014</span>');
        columns.push(col);
        if (col.length > maxRows) maxRows = col.length;
      }
      // Build a mini inner flex container with columns side by side, wrapping when needed
      var inner = '<div style="display:flex;flex-wrap:wrap;gap:2px 0;">';
      for (var ci = 0; ci < columns.length; ci++) {
        inner +=
          '<div style="padding-right:8px;display:flex;flex-direction:column;align-items:flex-start;gap:2px;">';
        for (var ri = 0; ri < columns[ci].length; ri++) {
          inner += columns[ci][ri];
        }
        inner += '</div>';
      }
      inner += '</div>';
      rows.push('<tr><td class="gp-label">Feats</td><td>' + inner + '</td></tr>');
    } else {
      var feats = featBundles[0].trim().split('|');
      var hasFeat = false;
      for (var fi = 0; fi < feats.length; fi++) {
        var f = feats[fi].trim();
        if (!f) continue;
        var _gpFDesc = getFeatDescription(f);
        var pill = _gpFDesc
          ? '<span class="gp-pill gp-feat-pill">' + escapeHtml(_gpFDesc) + '</span>'
          : '<span class="gp-pill gp-feat-pill" style="color:#dc2626;border-color:#ef4444;">' +
            escapeHtml(f) +
            '</span>';
        rows.push(
          '<tr><td class="gp-label">' + (!hasFeat ? 'Feats' : '') + '</td><td>' + pill + '</td></tr>'
        );
        hasFeat = true;
      }
    }
  }

  // Lemma row — omit when identical to the surface form
  if (lemmaValue) {
    var tok = _gpIsMwtChild && _gpLookupText ? _gpLookupText : surfaceValue;
    var lem = lemmaMeta.lemma || getTrimmedDisplayText(lemmaValue);
    var lemmaIsSame = !lemmaMeta.hasRawSuffix && hasSameVisibleComparisonText(lem, tok);
    if (!lemmaIsSame) {
      var lemmaDisplayHtml = buildPlainAnnotatedLemmaHtml(lem, lemmaMeta.raw || lemmaRawValue);
      rows.push(
        '<tr><td class="gp-label">Lemma</td><td class="gp-lemma-val">' + lemmaDisplayHtml + '</td></tr>'
      );
    }
  }

  // Dictionary morphology rows (Yomitan non-lemma mapping / grammar field)
  var morphMeta = _gpIsMwtChild
    ? {
        morphInfo: [],
        morphBase: '',
        grammar: ''
      }
    : extractMorphMetaFromPosData(posData);
  var morphBaseDisplay = getTrimmedDisplayText(morphMeta.morphBase);
  if (morphBaseDisplay) {
    rows.push(
      '<tr><td class="gp-label">Base</td><td class="gp-lemma-val">' +
        escapeHtml(morphBaseDisplay) +
        '</td></tr>'
    );
  }
  if (morphMeta.morphInfo.length) {
    var maxMorph = Math.min(morphMeta.morphInfo.length, 8);
    for (var mi = 0; mi < maxMorph; mi++) {
      var mlabel = getTrimmedDisplayText(morphMeta.morphInfo[mi]);
      if (!mlabel) continue;
      rows.push(
        '<tr><td class="gp-label">' +
          escapeHtml(mi === 0 ? 'Morph' : '') +
          '</td><td><span class="gp-pill gp-feat-pill">' +
          escapeHtml(mlabel) +
          '</span></td></tr>'
      );
    }
    if (morphMeta.morphInfo.length > maxMorph) {
      rows.push('<tr><td class="gp-label"></td><td><span class="gp-desc">�</span></td></tr>');
    }
  }
  if (morphMeta.grammar) {
    var grammarText =
      morphMeta.grammar.length > 220 ? morphMeta.grammar.slice(0, 217) + '...' : morphMeta.grammar;
    rows.push(
      '<tr><td class="gp-label">Wikt</td><td><span class="gp-desc">' +
        escapeHtml(grammarText) +
        '</span></td></tr>'
    );
  }

  // Conjugation row (language hook payload)
  if (conjugationData && typeof conjugationData === 'object') {
    var analyses = [];
    if (Array.isArray(conjugationData.analyses) && conjugationData.analyses.length) {
      analyses = conjugationData.analyses;
    } else {
      analyses = [conjugationData];
    }
    var count = Number(conjugationData.analysis_count || analyses.length || 0);
    var isAmbiguous = !!conjugationData.ambiguous || count > 1 || analyses.length > 1;
    var rendered = [];
    for (var ci = 0; ci < analyses.length; ci++) {
      var cand = analyses[ci] || {};
      var analysisCategory = String(cand.category || '').trim();
      var analysisVariant = String(cand.analysis_variant || '').trim();
      var conjName = String(cand.conjugation || '').trim();
      var conjDesc = String(cand.conjugation_desc || '').trim();
      var conjAux = Array.isArray(cand.auxiliaries) ? cand.auxiliaries : [];
      var auxInfo = Array.isArray(cand.auxiliary_info) ? cand.auxiliary_info : [];
      var conjPieces = [];
      if (conjName) {
        conjPieces.push('<span class="gp-pill gp-feat-pill">' + escapeHtml(conjName) + '</span>');
      }
      for (var ai = 0; ai < conjAux.length; ai++) {
        var auxLabel = String(conjAux[ai] || '').trim();
        if (!auxLabel) continue;
        conjPieces.push('<span class="gp-pill gp-feat-pill">' + escapeHtml(auxLabel) + '</span>');
      }
      var detailLines = [];
      if (analysisCategory && analysisVariant) {
        detailLines.push(analysisCategory + ' (' + analysisVariant + ')');
      } else if (analysisCategory) {
        detailLines.push(analysisCategory);
      }
      if (conjName && conjDesc) {
        detailLines.push(conjDesc);
      }
      for (var di = 0; di < auxInfo.length; di++) {
        var info = auxInfo[di] || {};
        var auxName = String(info.name || '').trim();
        var auxDesc = String(info.description || '').trim();
        if (auxName && auxDesc) {
          detailLines.push(auxDesc);
        }
      }
      var detailHtml = detailLines.length
        ? '<span class="gp-desc">' + escapeHtml(detailLines.join('; ')) + '</span>'
        : '';
      if (!conjPieces.length && !detailHtml) continue;
      var listPrefix =
        isAmbiguous && count > 1
          ? '<span class="gp-desc">' + escapeHtml(String(ci + 1) + '. ') + '</span>'
          : '';
      rendered.push(
        '<div style="margin-top:4px;">' + listPrefix + conjPieces.join(' ') + detailHtml + '</div>'
      );
    }
    var ambiguityNote = '';
    if (isAmbiguous && count > 1) {
      ambiguityNote =
        '<div><span class="gp-desc">Ambiguous: ' + escapeHtml(String(count)) + ' options</span></div>';
    }
    if (ambiguityNote || rendered.length) {
      rows.push(
        '<tr><td class="gp-label" style="vertical-align:top;">Conj</td><td>' +
          ambiguityNote +
          rendered.join('') +
          '</td></tr>'
      );
    }
  }
  if (tailRows.length) rows = rows.concat(tailRows);
  if (glossRows.length) rows = rows.concat(glossRows);
  if (!rows.length) return '';
  var synthHintForced = !!(options && options.forceSynthHint);
  if (!synthHintForced && options && options.koreanCompoundSynthGroup) {
    synthHintForced = koreanCompoundSynthGroupHasGreedy(options.koreanCompoundSynthGroup);
  }
  var synthHintRow =
    synthHintForced || tokenShouldShowSynthHint(resolutionTokenEntry || tokenEntry, surfaceValue)
      ? '<tr class="gp-synth-hint-row"><td colspan="2">create synthetic entry \u2192</td></tr>'
      : '';
  return (
    '<div class="grammar-popup-inner"><table class="gp-table">' +
    rows.join('') +
    synthHintRow +
    '</table></div>'
  );
}
export function initializeGrammarPopup() {
  grammarPopupState.UD_DEP_HOVER_TEXT = window.TRANKIT_TAGS.DEP;
  grammarPopupState._activeXposLang = '';
  grammarPopupState.FEATS_DESCRIPTIONS = window.TRANKIT_TAGS.FEATS;
  return true;
}
