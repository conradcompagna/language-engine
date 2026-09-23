import { setDocMode } from './continuous-scroll.mjs';
import { syncRawContinuousModeForSourceText } from './document-search.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { documentState } from './document-state.state.mjs';
import { loadXposDescriptionsForLanguage } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  syncLookupSelectionStatus,
  syncManualSentenceSegmentationControl,
  syncStripPunctuationControl
} from './orthography.mjs';
export function stripNativeTitleTooltips(root) {
  root = root || document;
  if (!root || !root.querySelectorAll) return;
  try {
    Array.from(root.querySelectorAll('[title]')).forEach(function (el) {
      if (el.hasAttribute && el.hasAttribute('data-native-tooltip')) return;
      el.removeAttribute('title');
    });
  } catch (_titleErr) {}
}
export function ensurePronunciationPopupStyles() {
  if (
    hoverLayoutState._pronunciationPopupStyleInjected ||
    !hoverLayoutState.g2pPopup ||
    !document ||
    !document.head
  )
    return;
  hoverLayoutState._pronunciationPopupStyleInjected = true;
  hoverLayoutState.g2pPopup.classList.add('g2p-popup-pronunciation');
  var styleEl = document.createElement('style');
  styleEl.id = 'g2p-popup-pronunciation-styles';
  styleEl.textContent = [
    '#g2pPopup.g2p-popup-pronunciation {',
    '  background: transparent;',
    '  border: 0;',
    '  box-shadow: none;',
    '  padding: 0;',
    '  width: auto;',
    '  max-width: min(640px, calc(100vw - 16px));',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-card {',
    '  position: relative;',
    '  margin: 0;',
    '  width: min(640px, calc(100vw - 16px));',
    '  max-width: 100%;',
    '  max-height: min(66vh, 560px);',
    '  overflow: auto;',
    '  box-sizing: border-box;',
    '  padding: 14px 14px 12px;',
    '  border-radius: 20px;',
    '  border: 1px solid rgba(15, 23, 42, 0.08);',
    '  background:',
    '    radial-gradient(circle at top right, rgba(16, 185, 129, 0.16), rgba(16, 185, 129, 0) 42%),',
    '    linear-gradient(180deg, rgba(255, 255, 255, 0.99) 0%, rgba(248, 250, 252, 0.98) 100%);',
    '  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);',
    '  color: var(--le-slate-900);',
    '  backdrop-filter: blur(10px);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-card::before {',
    '  content: "";',
    '  position: absolute;',
    '  left: 0;',
    '  top: 0;',
    '  bottom: 0;',
    '  width: 4px;',
    '  border-top-left-radius: 20px;',
    '  border-bottom-left-radius: 20px;',
    '  background: linear-gradient(180deg, var(--le-green-500), rgba(16, 185, 129, 0.45));',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-card > * {',
    '  position: relative;',
    '  z-index: 1;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-header {',
    '  display: flex;',
    '  flex-direction: column;',
    '  gap: 10px;',
    '  margin-bottom: 12px;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-kicker {',
    '  margin: 0;',
    '  padding: 0;',
    '  border: 0;',
    '  background: transparent;',
    '  font-size: 11px;',
    '  letter-spacing: 0.12em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-surface-wrap {',
    '  display: flex;',
    '  flex-direction: column;',
    '  gap: 2px;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-surface-label {',
    '  font-size: 10px;',
    '  font-weight: 700;',
    '  letter-spacing: 0.12em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-surface {',
    '  font-size: 20px;',
    '  line-height: 1.15;',
    '  font-weight: 700;',
    '  color: var(--le-slate-900);',
    '  word-break: break-word;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-summary {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  gap: 6px;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-chip {',
    '  display: inline-flex;',
    '  flex-direction: column;',
    '  gap: 2px;',
    '  min-width: 76px;',
    '  padding: 7px 9px;',
    '  border-radius: 14px;',
    '  border: 1px solid rgba(15, 23, 42, 0.08);',
    '  background: rgba(255, 255, 255, 0.9);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-chip-accent {',
    '  border-color: rgba(16, 185, 129, 0.28);',
    '  background: rgba(236, 253, 245, 0.95);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-chip-label {',
    '  font-size: 9px;',
    '  font-weight: 700;',
    '  letter-spacing: 0.08em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-chip-value {',
    '  font-size: 13px;',
    '  font-weight: 700;',
    '  color: var(--le-slate-900);',
    '  overflow-wrap: anywhere;',
    '  word-break: break-word;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-sound {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  align-items: baseline;',
    '  gap: 8px;',
    '  margin-bottom: 14px;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-sound-label {',
    '  font-size: 10px;',
    '  font-weight: 700;',
    '  letter-spacing: 0.12em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-sound-value {',
    '  font-size: 18px;',
    '  font-style: italic;',
    '  font-weight: 700;',
    '  color: var(--le-green-700);',
    '  overflow-wrap: anywhere;',
    '  word-break: break-word;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-sound-empty {',
    '  color: var(--le-slate-400);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-clusters {',
    '  display: grid;',
    '  gap: 10px;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-cluster {',
    '  display: flex;',
    '  flex-direction: column;',
    '  gap: 10px;',
    '  margin: 0;',
    '  padding: 12px;',
    '  border-radius: 16px;',
    '  border: 1px solid rgba(148, 163, 184, 0.18);',
    '  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.98));',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-cluster-complex {',
    '  border-color: rgba(16, 185, 129, 0.24);',
    '  box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.05);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-cluster-head {',
    '  display: flex;',
    '  align-items: baseline;',
    '  justify-content: space-between;',
    '  gap: 10px;',
    '  flex-wrap: wrap;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-cluster-orth {',
    '  font-size: 22px;',
    '  line-height: 1.1;',
    '  font-weight: 800;',
    '  color: var(--le-slate-900);',
    '  word-break: break-word;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-cluster-roman {',
    '  font-size: 14px;',
    '  font-style: italic;',
    '  color: var(--le-green-700);',
    '  font-weight: 700;',
    '  white-space: normal;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-layer {',
    '  display: flex;',
    '  flex-direction: column;',
    '  gap: 8px;',
    '  padding: 10px;',
    '  border-radius: 14px;',
    '  border: 1px solid rgba(15, 23, 42, 0.06);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-layer-label {',
    '  font-size: 9px;',
    '  font-weight: 800;',
    '  letter-spacing: 0.12em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-layer-phonology {',
    '  background: linear-gradient(180deg, rgba(236, 253, 245, 0.95), rgba(240, 253, 244, 0.72));',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-layer-segmentation {',
    '  background: linear-gradient(180deg, rgba(248, 250, 252, 0.98), rgba(241, 245, 249, 0.9));',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-components {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  gap: 8px;',
    '  justify-content: flex-start;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp {',
    '  display: inline-flex;',
    '  flex-direction: column;',
    '  align-items: flex-start;',
    '  gap: 4px;',
    '  min-width: 72px;',
    '  padding: 8px 9px;',
    '  border-radius: 12px;',
    '  border: 1px solid rgba(15, 23, 42, 0.08);',
    '  background: rgba(255, 255, 255, 0.9);',
    '  box-sizing: border-box;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-emphasis {',
    '  border-color: rgba(16, 185, 129, 0.32);',
    '  background: rgba(236, 253, 245, 0.95);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-head {',
    '  display: flex;',
    '  flex-direction: column;',
    '  align-items: flex-start;',
    '  gap: 2px;',
    '  max-width: 100%;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-ch {',
    '  font-size: 18px;',
    '  font-weight: 800;',
    '  color: var(--le-slate-900);',
    '  line-height: 1;',
    '  word-break: break-word;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-pron {',
    '  font-size: 11px;',
    '  font-style: italic;',
    '  font-weight: 700;',
    '  color: var(--le-green-700);',
    '  line-height: 1.15;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-meta {',
    '  font-size: 9px;',
    '  font-weight: 800;',
    '  letter-spacing: 0.08em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '  line-height: 1.15;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-comp-label {',
    '  font-size: 10px;',
    '  line-height: 1.25;',
    '  color: var(--le-slate-600);',
    '  overflow-wrap: anywhere;',
    '  word-break: break-word;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segline {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  align-items: center;',
    '  gap: 6px;',
    '  padding-top: 2px;',
    '  font-size: 13px;',
    '  color: var(--le-slate-700);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segbracket {',
    '  font-size: 16px;',
    '  font-weight: 700;',
    '  color: var(--le-slate-400);',
    '  line-height: 1;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segparts {',
    '  display: inline-flex;',
    '  flex-wrap: wrap;',
    '  align-items: center;',
    '  gap: 6px;',
    '  min-width: 0;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segpart {',
    '  display: inline-flex;',
    '  flex-direction: column;',
    '  align-items: center;',
    '  gap: 2px;',
    '  min-width: 56px;',
    '  padding: 6px 8px;',
    '  border-radius: 10px;',
    '  border: 1px solid rgba(148, 163, 184, 0.18);',
    '  background: rgba(255, 255, 255, 0.94);',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segchar {',
    '  font-size: 15px;',
    '  font-weight: 800;',
    '  color: var(--le-slate-900);',
    '  line-height: 1;',
    '  word-break: break-word;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segsound {',
    '  font-size: 10px;',
    '  font-style: italic;',
    '  font-weight: 700;',
    '  color: var(--le-green-700);',
    '  line-height: 1.1;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segmeta {',
    '  font-size: 9px;',
    '  font-weight: 700;',
    '  letter-spacing: 0.08em;',
    '  text-transform: uppercase;',
    '  color: var(--le-slate-500);',
    '  line-height: 1.1;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-segplus {',
    '  font-size: 13px;',
    '  font-weight: 800;',
    '  color: var(--le-slate-400);',
    '  line-height: 1;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-empty {',
    '  font-size: 12px;',
    '  color: var(--le-slate-500);',
    '  padding: 2px 0 0;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-note {',
    '  margin-top: 10px;',
    '  padding-top: 8px;',
    '  border-top: 1px dashed rgba(148, 163, 184, 0.24);',
    '  font-size: 11px;',
    '  line-height: 1.45;',
    '  color: var(--le-slate-600);',
    '  word-break: break-word;',
    '  overflow-wrap: anywhere;',
    '}',
    '#g2pPopup.g2p-popup-pronunciation .g2p-analysis-note-label {',
    '  font-weight: 800;',
    '  text-transform: uppercase;',
    '  letter-spacing: 0.08em;',
    '  color: var(--le-slate-500);',
    '}'
  ].join('\\n');
  document.head.appendChild(styleEl);
}
// -- Token Map state (grammar/fill-map chip inset at top-right of dict content area) --
export // whether the token map view is currently shown

function normalizeTextDirection(rawDirection) {
  var d = String(rawDirection || '')
    .trim()
    .toLowerCase();
  return d === 'rtl' ? 'rtl' : 'ltr';
}
export function applyLanguagePresentationToElement(el, options) {
  if (!el) return;
  var opts = {};
  if (typeof options === 'boolean') {
    opts.alignText = options;
  } else if (options && typeof options === 'object') {
    opts = options;
  }
  var hasDirectionOverride = Object.prototype.hasOwnProperty.call(opts, 'direction');
  var direction = normalizeTextDirection(
    hasDirectionOverride ? opts.direction : hoverLayoutState.currentTextDirection
  );
  var alignText = !!opts.alignText;
  var align = String(opts.textAlign || (direction === 'rtl' ? 'right' : 'left')).toLowerCase();
  el.setAttribute('dir', direction);
  el.style.direction = direction;
  if (alignText) {
    el.style.textAlign = align === 'right' ? 'right' : 'left';
  } else {
    el.style.removeProperty('text-align');
  }
  if (hoverLayoutState.currentLanguageFontFamily) {
    el.style.fontFamily = hoverLayoutState.currentLanguageFontFamily;
  } else {
    el.style.removeProperty('font-family');
  }
}
export function applyLanguagePresentation() {
  // Only the input/output panes follow language direction/alignment.
  var ioOptions = {
    direction: hoverLayoutState.currentTextDirection,
    alignText: true,
    textAlign: hoverLayoutState.currentTextAlign
  };
  applyLanguagePresentationToElement(hoverLayoutState.sourceText, ioOptions);
  applyLanguagePresentationToElement(hoverLayoutState.sourcePager, ioOptions);
  applyLanguagePresentationToElement(hoverLayoutState.renderedText, ioOptions);

  // Keep all non-IO surfaces LTR so hover/panel UI layout stays stable.
  var nonIoOptions = {
    direction: 'ltr',
    alignText: false
  };
  applyLanguagePresentationToElement(hoverLayoutState.panelContent, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.dictSearch, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.hoverPopup, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.udPopup, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.grammarPopup, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.g2pPopup, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.notePopup, nonIoOptions);
  applyLanguagePresentationToElement(hoverLayoutState.subsegmentPopupsContainer, nonIoOptions);

  // Existing dynamic popup blocks (if already rendered)
  if (hoverLayoutState.hoverPopupContainer) {
    var dynamicPopups = hoverLayoutState.hoverPopupContainer.querySelectorAll(
      '.dict-fill-popup, .subsegment-popup'
    );
    for (var i = 0; i < dynamicPopups.length; i++) {
      applyLanguagePresentationToElement(dynamicPopups[i], nonIoOptions);
    }
  }
  if (hoverLayoutState.subsegmentPopupsContainer) {
    var subPopups = hoverLayoutState.subsegmentPopupsContainer.querySelectorAll('.subsegment-popup');
    for (var j = 0; j < subPopups.length; j++) {
      applyLanguagePresentationToElement(subPopups[j], nonIoOptions);
    }
  }
}
export function setActiveLanguageConfig(config) {
  var cfg = config && typeof config === 'object' ? config : {};
  hoverLayoutState.activeLangConfig = cfg;
  hoverLayoutState.currentTextDirection = normalizeTextDirection(cfg.text_direction || cfg.direction);
  hoverLayoutState.currentTextAlign = hoverLayoutState.currentTextDirection === 'rtl' ? 'right' : 'left';
  hoverLayoutState.currentLanguageFontFamily = String(cfg.font_family || '').trim();
  applyLanguagePresentation();
}
export function fetchLangConfigAndApply(langCode) {
  var lang = String(langCode || '')
    .trim()
    .toLowerCase();
  if (!lang) {
    setActiveLanguageConfig(null);
    return Promise.resolve(false);
  }
  return fetch('/api/lang_config?lang=' + encodeURIComponent(lang))
    .then(function (resp) {
      if (!resp.ok) throw new Error('lang config unavailable');
      return resp.json();
    })
    .then(function (payload) {
      if (payload && payload.ok && payload.config && typeof payload.config === 'object') {
        setActiveLanguageConfig(payload.config);
        return true;
      }
      setActiveLanguageConfig(null);
      return false;
    })
    .catch(function () {
      setActiveLanguageConfig(null);
      return false;
    });
}
export function clearDictionaryPopupClampForElement(el) {
  if (!el) return;
  if (window.DictPopupClamp && typeof window.DictPopupClamp.clear === 'function') {
    window.DictPopupClamp.clear(el);
  } else {
    el.classList.remove('dict-popup-clamped', 'dict-popup-truncated', 'dict-popup-overflowed');
    el.style.removeProperty('--dict-popup-max-height');
    el.style.removeProperty('max-height');
    el.style.removeProperty('overflow-y');
  }
  if (el.dataset) delete el.dataset.forceTruncationCue;
  if (el.dataset) delete el.dataset.disableClamp;
}
export function hasFilteredDefsSignalInMarkup(html) {
  if (typeof html !== 'string') return false;
  return html.indexOf('popup-alt-senses-signal') >= 0 || html.indexOf('popup-alt-senses-note') >= 0;
}
export function setDictionaryPopupSignalFromMarkup(el, html, options) {
  if (!el) return;
  var opts = options || {};
  var shouldForceCue = hasFilteredDefsSignalInMarkup(html);
  if (!shouldForceCue && el.querySelector) {
    shouldForceCue = !!el.querySelector('.popup-alt-senses-signal, .popup-alt-senses-note');
  }
  if (!el.dataset) return;
  if (opts.disableClamp) {
    el.dataset.disableClamp = '1';
  } else {
    delete el.dataset.disableClamp;
  }
  if (shouldForceCue) {
    el.dataset.forceTruncationCue = '1';
  } else {
    delete el.dataset.forceTruncationCue;
  }
}
export function applyDictionaryPopupClampForElement(el) {
  if (!el) return;
  var disableClamp = !!(el.dataset && el.dataset.disableClamp === '1');
  if (disableClamp) {
    clearDictionaryPopupClampForElement(el);
    return;
  }
  var forceCue = !!(el.dataset && el.dataset.forceTruncationCue === '1');
  if (window.DictPopupClamp && typeof window.DictPopupClamp.apply === 'function') {
    window.DictPopupClamp.apply(el, {
      ratio: 0.5,
      minHeightPx: 120,
      forceTruncatedIndicator: forceCue
    });
    return;
  }
  var viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  if (viewportHeight <= 0) return;
  var maxHeightPx = Math.max(120, Math.floor(viewportHeight * 0.5));
  el.classList.add('dict-popup-clamped');
  el.style.maxHeight = maxHeightPx + 'px';
  el.style.overflowY = 'hidden';
  var overflowed = el.scrollHeight - el.clientHeight > 1;
  el.classList.toggle('dict-popup-overflowed', overflowed);
  el.classList.toggle('dict-popup-truncated', overflowed || forceCue);
}
export function applyDictionaryHoverPopupClamp() {
  if (!hoverLayoutState.hoverPopupContainer || hoverLayoutState.hoverPopupContainer.style.display !== 'flex')
    return;
  if (hoverLayoutState.hoverPopup) {
    if (hoverLayoutState.hoverPopup.style.display === 'none') {
      clearDictionaryPopupClampForElement(hoverLayoutState.hoverPopup);
    } else {
      applyDictionaryPopupClampForElement(hoverLayoutState.hoverPopup);
    }
  }
  var fillPopups = hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup');
  for (var i = 0; i < fillPopups.length; i++) {
    applyDictionaryPopupClampForElement(fillPopups[i]);
  }
}
export function clearDictionaryHoverPopupClamp() {
  clearDictionaryPopupClampForElement(hoverLayoutState.hoverPopup);
  if (!hoverLayoutState.hoverPopupContainer) return;
  var fillPopups = hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup');
  for (var i = 0; i < fillPopups.length; i++) {
    clearDictionaryPopupClampForElement(fillPopups[i]);
  }
}

// Language selector dropdown
export function initializeHoverLayout() {
  // DOM refs
  hoverLayoutState.sourceText = document.getElementById('sourceText');
  hoverLayoutState.sourcePager = document.getElementById('sourcePager');
  hoverLayoutState.docToolbar = document.getElementById('docToolbar');
  hoverLayoutState.docViewportWrap = document.getElementById('docViewportWrap');
  hoverLayoutState.docPageLabel = document.getElementById('docPageLabel');
  hoverLayoutState.docPageNumberInput = document.getElementById('docPageNumberInput');
  hoverLayoutState.docPageNavigator = document.getElementById('docPageNavigator');
  hoverLayoutState.docNavPrev = document.getElementById('docNavPrev');
  hoverLayoutState.docNavNext = document.getElementById('docNavNext');
  hoverLayoutState.docNavTrack = document.getElementById('docNavTrack');
  hoverLayoutState.docNavThumb = document.getElementById('docNavThumb');
  hoverLayoutState.pdfDocControls = document.getElementById('pdfDocControls');
  hoverLayoutState.pdfModeButton = document.getElementById('pdfModeButton');
  hoverLayoutState.pdfZoomOutButton = document.getElementById('pdfZoomOutButton');
  hoverLayoutState.pdfZoomResetButton = document.getElementById('pdfZoomResetButton');
  hoverLayoutState.pdfZoomInButton = document.getElementById('pdfZoomInButton');
  hoverLayoutState.pdfSearchField = document.getElementById('pdfSearchField');
  hoverLayoutState.pdfSearchPrevButton = document.getElementById('pdfSearchPrevButton');
  hoverLayoutState.pdfSearchNextButton = document.getElementById('pdfSearchNextButton');
  hoverLayoutState.pdfSearchCountLabel = document.getElementById('pdfSearchCountLabel');
  hoverLayoutState.pdfSearchClearButton = document.getElementById('pdfSearchClearButton');
  hoverLayoutState.docCapabilityControls = document.getElementById('docCapabilityControls');
  hoverLayoutState.docContentsButton = document.getElementById('docContentsButton');
  hoverLayoutState.docContentsMenu = document.getElementById('docContentsMenu');
  hoverLayoutState.docNavMenuMeta = document.getElementById('docNavMenuMeta');
  hoverLayoutState.docNavMenuList = document.getElementById('docNavMenuList');
  hoverLayoutState.docSearchField = document.getElementById('docSearchField');
  hoverLayoutState.docSearchPrevButton = document.getElementById('docSearchPrevButton');
  hoverLayoutState.docSearchNextButton = document.getElementById('docSearchNextButton');
  hoverLayoutState.docSearchCountLabel = document.getElementById('docSearchCountLabel');
  hoverLayoutState.docSearchClearButton = document.getElementById('docSearchClearButton');
  hoverLayoutState.docSearchMenu = document.getElementById('docSearchMenu');
  hoverLayoutState.docSearchMenuMeta = document.getElementById('docSearchMenuMeta');
  hoverLayoutState.docSearchMenuList = document.getElementById('docSearchMenuList');
  hoverLayoutState.webDocControls = document.getElementById('webDocControls');
  hoverLayoutState.webInspectorButton = document.getElementById('webInspectorButton');
  hoverLayoutState.trankitChunkLookupButton = document.getElementById('trankitChunkLookupButton');
  hoverLayoutState.TRANKIT_CHUNK_LOOKUP_DISABLED = true; // Normal lookup now relies on synthetic paragraph breaks for chunk boundaries.
  hoverLayoutState.webInspectorStatus = document.getElementById('webInspectorStatus');
  stripNativeTitleTooltips(document);
  if (typeof MutationObserver === 'function') {
    try {
      hoverLayoutState.nativeTitleObserver = new MutationObserver(function (records) {
        records.forEach(function (record) {
          if (record.type === 'attributes' && record.attributeName === 'title' && record.target) {
            try {
              if (!(record.target.hasAttribute && record.target.hasAttribute('data-native-tooltip'))) {
                record.target.removeAttribute('title');
              }
            } catch (_attrErr) {}
            return;
          }
          Array.from(record.addedNodes || []).forEach(function (node) {
            if (!node || node.nodeType !== 1) return;
            if (
              node.hasAttribute &&
              node.hasAttribute('title') &&
              !(node.hasAttribute && node.hasAttribute('data-native-tooltip'))
            ) {
              node.removeAttribute('title');
            }
            stripNativeTitleTooltips(node);
          });
        });
      });
      hoverLayoutState.nativeTitleObserver.observe(document.documentElement || document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['title']
      });
    } catch (_observerErr) {}
  }
  hoverLayoutState.sourceTextHomeMarker = null;
  if (hoverLayoutState.sourceText && hoverLayoutState.sourceText.parentNode) {
    hoverLayoutState.sourceTextHomeMarker = document.createComment('sourceText-home');
    hoverLayoutState.sourceText.parentNode.insertBefore(
      hoverLayoutState.sourceTextHomeMarker,
      hoverLayoutState.sourceText
    );
  }
  hoverLayoutState.renderedText = document.getElementById('renderedText');
  hoverLayoutState.depTreeViewEl = document.getElementById('depTreeView');
  hoverLayoutState.statusText = document.getElementById('statusText');
  // statusCounts removed from UI - use dummy element to prevent errors
  hoverLayoutState.statusCounts = document.getElementById('statusCounts') || document.createElement('span');
  hoverLayoutState.dropZone = document.getElementById('dropZone');
  hoverLayoutState.fileInput = document.getElementById('fileInput');
  hoverLayoutState.fileButton = document.getElementById('fileButton');
  hoverLayoutState.fileNamePill = document.getElementById('fileNamePill');
  hoverLayoutState.fileNameText = document.getElementById('fileNameText');
  hoverLayoutState.clearFileBtn = document.getElementById('clearFileBtn');
  hoverLayoutState.rawTextPill = document.getElementById('rawTextPill');
  hoverLayoutState.rawTextText = document.getElementById('rawTextText');
  hoverLayoutState.clearRawTextBtn = document.getElementById('clearRawTextBtn');
  hoverLayoutState.hoverPopupContainer = document.getElementById('hoverPopupContainer');
  hoverLayoutState.grammarPopup = document.getElementById('grammarPopup');
  hoverLayoutState.latestGrammarPopupState = null;
  hoverLayoutState._synthHintActive = false; // set by renderTokenBanner, read by buildGrammarPopupHtml
  hoverLayoutState._syntheticEntryBarState = null;
  hoverLayoutState.hoverPopup = document.getElementById('hoverPopup');
  hoverLayoutState.udPopup = document.getElementById('udPopup');
  hoverLayoutState.g2pPopup = document.getElementById('g2pPopup');
  hoverLayoutState.notePopup = document.getElementById('notePopup');
  hoverLayoutState.subsegmentPopupsContainer = document.getElementById('subsegmentPopupsContainer');
  hoverLayoutState.sidePanel = document.getElementById('side-panel');
  hoverLayoutState.panelToggle = document.getElementById('panel-toggle');
  hoverLayoutState.topNav = document.getElementById('top-nav');
  hoverLayoutState.mainContainer = document.getElementById('main-container');
  hoverLayoutState.panelContent = document.getElementById('panel-content');
  hoverLayoutState.currentPanelDisplayState = null;
  hoverLayoutState.currentPanelEditContextByKey = Object.create(null);
  hoverLayoutState.currentPanelEditContextSeq = 0;
  hoverLayoutState.dictSearch = document.getElementById('dict-search');
  hoverLayoutState.searchBtn = document.getElementById('search-btn');
  hoverLayoutState.activeLangConfig = null;
  hoverLayoutState.currentTextDirection = 'ltr';
  hoverLayoutState.currentTextAlign = 'left';
  hoverLayoutState.currentLanguageFontFamily = '';
  hoverLayoutState._pronunciationPopupStyleInjected = false;
  hoverLayoutState.tokenMapData = null; // { segIdx, surface, lemma, posData, udTok, entry, tokenEntry, dictFill, tokenDictFill, fillMode, tokenFillMode, resolvedVia, tokenResolvedVia, surfaceLookup, lemmaLookup, lemmaPartLookups, headDecompByForm }
  hoverLayoutState.tokenMapVisible = false;
  hoverLayoutState.languageSelect = document.getElementById('languageSelect');
  if (hoverLayoutState.languageSelect) {
    documentShellState.currentLanguage = String(hoverLayoutState.languageSelect.value || '')
      .trim()
      .toLowerCase();
    documentShellState.currentTrankitOverride = String(
      (hoverLayoutState.languageSelect.options[hoverLayoutState.languageSelect.selectedIndex] &&
        hoverLayoutState.languageSelect.options[hoverLayoutState.languageSelect.selectedIndex].dataset
          .trankit) ||
        ''
    ).trim();
    if (documentShellState.currentLanguage) {
      fetchLangConfigAndApply(documentShellState.currentLanguage);
      loadXposDescriptionsForLanguage(documentShellState.currentLanguage);
      syncManualSentenceSegmentationControl();
      syncStripPunctuationControl();
      syncLookupSelectionStatus();
    } else {
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Select a language.';
    }
    hoverLayoutState.languageSelect.addEventListener('change', function () {
      documentShellState.currentLanguage = String(hoverLayoutState.languageSelect.value || '')
        .trim()
        .toLowerCase();
      documentShellState.currentTrankitOverride = String(
        (hoverLayoutState.languageSelect.options[hoverLayoutState.languageSelect.selectedIndex] &&
          hoverLayoutState.languageSelect.options[hoverLayoutState.languageSelect.selectedIndex].dataset
            .trankit) ||
          ''
      ).trim();
      if (documentShellState.currentLanguage) {
        fetchLangConfigAndApply(documentShellState.currentLanguage);
        loadXposDescriptionsForLanguage(documentShellState.currentLanguage);
        syncManualSentenceSegmentationControl();
        syncStripPunctuationControl();
        syncLookupSelectionStatus();
        // Language/dict change does not re-paginate — layout is viewport-based and language-neutral.
        if (
          false &&
          documentState.inputMode === 'doc' &&
          documentState.docText &&
          !documentState.docrenderActive
        ) {
          setDocMode(documentState.docText, {
            pageIndex: 0,
            triggerLookup: false
          });
        } else if (
          documentState.inputMode === 'raw' &&
          hoverLayoutState.sourceText &&
          hoverLayoutState.sourceText.value
        ) {
          syncRawContinuousModeForSourceText();
        }
        if (window.LEAssistant && typeof window.LEAssistant.clearHistory === 'function') {
          window.LEAssistant.clearHistory();
        }
      } else if (hoverLayoutState.statusText) {
        hoverLayoutState.statusText.textContent = 'Select a language.';
      }
    });
  } else {
    if (documentShellState.currentLanguage) {
      fetchLangConfigAndApply(documentShellState.currentLanguage);
      loadXposDescriptionsForLanguage(documentShellState.currentLanguage);
      syncManualSentenceSegmentationControl();
      syncStripPunctuationControl();
    }
  }
  hoverLayoutState.latestSeq = 0;
  hoverLayoutState.segmentLookupAbort = null;
  hoverLayoutState.latestData = null;
  hoverLayoutState.latestLlmGlosses = null; // Per-token LLM glosses (array matching segments)
  hoverLayoutState.latestLlmGlossOverrides = null; // Manual per-token gloss overrides.
  hoverLayoutState.latestLlmGlossUpgradeRequired = false;
  hoverLayoutState.latestLlmGlossSeq = 0; // Sequence counter to discard stale gloss responses
  hoverLayoutState.latestLlmDecomps = null; // Per-token inflectional decompositions (array matching segments)
  hoverLayoutState.latestLlmDecompSeq = 0; // Sequence counter to discard stale decomp responses
  hoverLayoutState.latestOrthBreakdowns = null; // Per-token orth breakdowns (array matching segments)
  hoverLayoutState.latestOrthBreakdownSeq = 0; // Sequence counter to discard stale orth responses
  hoverLayoutState.latestSegments = null;
  hoverLayoutState._currentPopupSentenceCtx = '';
  hoverLayoutState.depTreeExperimentLastHoveredSegIdx = -1;
  hoverLayoutState.depTreeInlineInitialized = false;
  hoverLayoutState.depTreeInlineController = null;
  hoverLayoutState.depTreeInlineFabStateKey = 'le_dep_tree_fab_state_v1';
  hoverLayoutState.depTreeInlineFabDragState = null;
  hoverLayoutState.depTreeInlineFabIgnoreClickUntil = 0;
  hoverLayoutState.DEP_TREE_INLINE_MARGIN = 16;
  hoverLayoutState.DEP_TREE_INLINE_GAP = 14;
  hoverLayoutState.DEP_TREE_INLINE_MIN_WIDTH = 420;
  hoverLayoutState.DEP_TREE_INLINE_MIN_HEIGHT = 280;
  hoverLayoutState.DEP_TREE_INLINE_PREF_WIDTH = 980;
  return true;
}
