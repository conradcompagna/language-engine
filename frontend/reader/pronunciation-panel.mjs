import { dependencyPopupState } from './dependency-popup.state.mjs';
import { renderDictFillPopups } from './dictionary-popup.mjs';
import { hideSeparateGrammarPopup } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { hasExactTokenLookupMatch } from './entry-editing.mjs';
import { renderUnknownPopup } from './flashcards.mjs';
import {
  applyDictionaryHoverPopupClamp,
  clearDictionaryHoverPopupClamp,
  setDictionaryPopupSignalFromMarkup
} from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _getGraphemePronunciationApi } from './orthography.mjs';
import {
  buildPopupEntryMetaHtmlForEntry,
  captureUiRenderPanelSnapshot,
  escapeHtml,
  getEntryDisplayHead,
  getRenderableFillLabel,
  getRenderableFillState,
  hasDisplayText,
  hasSameVisibleComparisonText,
  isJapaneseLanguage,
  normalizeVisibleComparisonText,
  summarizeUiRenderDebugLookupEntry,
  traceUiRenderEvent
} from './presentation.mjs';
import { getExactSidePanelLookupEntry } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { hidePopup, positionSidePanelPopup, renderDictTemplate } from './side-panel.mjs';
import { buildTokenMapLookupRequestOptions } from './token-banner.mjs';
import {
  buildPendingPanelSurfaceTokenHtml,
  buildTokenMapLookupHtml,
  fetchExactSidePanelLookupEntry,
  getCurrentPanelSurfaceLookupEntry,
  getTokenMapLemmaPartTexts
} from './token-map.mjs';
import { tokenMapState } from './token-map.state.mjs';
export function getPendingPanelSurfaceLookupKey(surfaceText, langOverride) {
  return (
    String(langOverride || documentShellState.currentLanguage || '')
      .trim()
      .toLowerCase() +
    '\n' +
    String(surfaceText || '').trim()
  );
}
export function ensurePendingPanelSurfaceLookup(surfaceText) {
  var text = String(surfaceText || '').trim();
  var requestLang = String(documentShellState.currentLanguage || '').trim();
  if (!text || !requestLang) return;
  if (getExactPanelSurfaceLookupEntry(text)) return;
  var lookupOpts = buildTokenMapLookupRequestOptions('surface', hoverLayoutState.tokenMapData, null);
  var promiseKey = getPendingPanelSurfaceLookupKey(text, requestLang);
  if (tokenMapState._pendingPanelSurfaceLookupPromises[promiseKey]) return;
  traceUiRenderEvent(
    'panel_surface_hydrate_requested',
    {
      text: text,
      lang: requestLang
    },
    {
      scope: 'panel-surface'
    }
  );
  tokenMapState._pendingPanelSurfaceLookupPromises[promiseKey] = fetchExactSidePanelLookupEntry(
    text,
    requestLang,
    Object.assign(
      {
        cacheResult: true
      },
      lookupOpts
    )
  ).then(
    function (entry) {
      delete tokenMapState._pendingPanelSurfaceLookupPromises[promiseKey];
      traceUiRenderEvent(
        'panel_surface_hydrate_resolved',
        {
          text: text,
          lang: requestLang,
          found_entry: !!entry,
          lookup_entry: summarizeUiRenderDebugLookupEntry(entry)
        },
        {
          scope: 'panel-surface'
        }
      );
      if (entry) upgradePendingPanelSurfaceTokens(text, entry);
      return entry || null;
    },
    function () {
      delete tokenMapState._pendingPanelSurfaceLookupPromises[promiseKey];
      traceUiRenderEvent(
        'panel_surface_hydrate_resolved',
        {
          text: text,
          lang: requestLang,
          found_entry: false,
          error: 'lookup_failed'
        },
        {
          scope: 'panel-surface'
        }
      );
      return null;
    }
  );
}
export function resolvePanelSurfaceLookupDecision(surfaceText) {
  var text = String(surfaceText || '').trim();
  if (!text)
    return {
      entry: null,
      source: 'empty'
    };
  var liveEntry = getCurrentPanelSurfaceLookupEntry(text);
  if (liveEntry && hasExactTokenLookupMatch(liveEntry, text)) {
    return {
      entry: liveEntry,
      source: 'live_token_exact'
    };
  }
  var cachedEntry = getExactSidePanelLookupEntry(
    text,
    documentShellState.currentLanguage || '',
    buildTokenMapLookupRequestOptions('surface', hoverLayoutState.tokenMapData, null)
  );
  if (cachedEntry && hasExactTokenLookupMatch(cachedEntry, text)) {
    return {
      entry: cachedEntry,
      source: 'panel_cache_exact'
    };
  }
  return {
    entry: null,
    source: 'pending_lookup'
  };
}
export function getExactPanelSurfaceLookupEntry(surfaceText) {
  return resolvePanelSurfaceLookupDecision(surfaceText).entry || null;
}
export function buildPanelSurfaceFlowHtml(lookupEntry, text, role) {
  var surfaceText = String(text || '');
  var roleClass = String(role || 'surface').trim();
  traceUiRenderEvent(
    'panel_surface_flow',
    {
      text: surfaceText,
      role: roleClass,
      lookup_entry: summarizeUiRenderDebugLookupEntry(lookupEntry)
    },
    {
      scope: 'panel-surface'
    }
  );
  var lookupHtml = buildTokenMapLookupHtml(lookupEntry, surfaceText, 'surface', {
    suppressCache: true,
    tokenMapData: hoverLayoutState.tokenMapData
  });
  if (!lookupHtml) return '';
  var flowClasses = ['panel-headword-flow'];
  if (roleClass) flowClasses.push('panel-' + roleClass + '-flow');
  return '<span class="' + flowClasses.join(' ') + '">' + lookupHtml + '</span>';
}
export function buildPanelSurfaceHeadlineHtml(surfaceText, role) {
  var text = String(surfaceText || '').trim();
  if (!text) return '';
  var roleClass = String(role || 'surface').trim() || 'surface';
  traceUiRenderEvent(
    'panel_surface_decision',
    {
      text: text,
      role: roleClass,
      source: 'psr_placeholder',
      lookup_entry: null
    },
    {
      scope: 'panel-surface'
    }
  );
  return buildPendingPanelSurfaceTokenHtml(text, roleClass);
}
export function upgradePendingPanelSurfaceTokens(surfaceText, lookupEntry) {
  // Bypassed � PSR owns panel surface span rendering. Token banner upgrade still handled above.
  return;
  var pendingEls = hoverLayoutState.panelContent.querySelectorAll('[data-panel-surface-seg]');
  var replacedCount = 0;
  for (var i = 0; i < pendingEls.length; i++) {
    var el = pendingEls[i];
    var pendingText = String(el.getAttribute('data-panel-surface-seg') || '').trim();
    if (!pendingText) continue;
    if (!hasSameVisibleComparisonText(pendingText, expectedText)) continue;
    var roleClass = String(el.getAttribute('data-panel-head-role') || 'surface').trim() || 'surface';
    var replacementHtml = buildPanelSurfaceFlowHtml(lookupEntry, pendingText, roleClass);
    if (!replacementHtml) continue;
    var wrapper = document.createElement('span');
    wrapper.innerHTML = replacementHtml;
    var replacementNode = wrapper.firstElementChild;
    if (!replacementNode || !el.parentNode) continue;
    el.parentNode.replaceChild(replacementNode, el);
    replacedCount += 1;
  }
  traceUiRenderEvent(
    'panel_surface_upgrade',
    {
      surface: expectedText,
      replaced_count: replacedCount,
      lookup_entry: summarizeUiRenderDebugLookupEntry(lookupEntry)
    },
    {
      scope: 'panel-surface'
    }
  );
  if (replacedCount) captureUiRenderPanelSnapshot('panel_surface_upgrade');
}
export function getCachedSidePanelLookupEntry(seg, langOverride, options) {
  return getExactSidePanelLookupEntry(seg, langOverride, options || {});
}
export function fetchSidePanelLookupEntry(seg, langOverride, lookupOptions) {
  return fetchExactSidePanelLookupEntry(seg, langOverride, lookupOptions || {});
}
// Show simple dict popup (NO fuzzy matches)
export function showDictPopupSimple(seg, lookupOptions) {
  var requestLang = String(documentShellState.currentLanguage || '');
  var lookupOpts = lookupOptions || {};
  var hoverTarget = seg && typeof seg === 'object' && !Array.isArray(seg) ? seg : null;
  var segText = hoverTarget ? String(hoverTarget.seg || hoverTarget.text || '') : String(seg || '');
  var targetedFillIndexes =
    hoverTarget && Array.isArray(hoverTarget.fillIndexes) ? hoverTarget.fillIndexes.slice() : [];
  if (hoverTarget && hoverTarget.lookupResult && typeof hoverTarget.lookupResult === 'object') {
    renderDictPopupSimple(hoverTarget.lookupResult, segText, targetedFillIndexes);
    return;
  }
  var cached = getExactSidePanelLookupEntry(segText, requestLang, lookupOpts);
  if (cached) {
    renderDictPopupSimple(cached, segText, []);
    return;
  }
  fetchSidePanelLookupEntry(segText, requestLang, lookupOpts)
    .then(function (res) {
      if (res) {
        renderDictPopupSimple(res, segText, []);
      } else {
        renderUnknownPopup(segText);
      }
    })
    .catch(function () {
      renderUnknownPopup(segText);
    });
}
// Wrap component words in an element with hoverable spans
export function wrapComponentWords(seg, components) {
  var html = '';
  for (var i = 0; i < components.length; i++) {
    var comp = components[i];
    var compHead = comp.head || '';
    if (compHead) {
      html +=
        '<span class="panel-token" data-seg="' +
        escapeHtml(compHead) +
        '">' +
        escapeHtml(compHead) +
        '</span>';
    }
  }
  return html;
}
export function renderSubsegmentsPopupSimple(seg, subsegments) {
  var useJaHoverFiltering =
    isJapaneseLanguage() ||
    !!(
      window.ReaderLanguageAdapters &&
      window.ReaderLanguageAdapters.ko &&
      typeof window.ReaderLanguageAdapters.ko.isKoreanLanguage === 'function' &&
      window.ReaderLanguageAdapters.ko.isKoreanLanguage(documentShellState.currentLanguage)
    );
  hideSeparateGrammarPopup();
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (!dependencyPopupState.displaySettings.dictPopup) {
    hoverLayoutState.hoverPopup.style.display = 'none';
    hoverLayoutState.hoverPopupContainer.style.display = 'none';
    clearDictionaryHoverPopupClamp();
    return;
  }
  var html = '';
  for (var i = 0; i < subsegments.length; i++) {
    var sub = subsegments[i] || {};
    var sHead = sub.head || '';
    if (!sHead) continue;
    if (i > 0) {
      html += '<div class="dict-fill-separator"></div>';
    }
    html += renderDictTemplate(sub, sHead, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: 'senses_hover',
      showFilteredNote: true,
      showOtherDefsDropdown: false
    }).html;
  }
  if (!html) {
    renderUnknownPopup(seg);
    return;
  }
  hoverLayoutState.hoverPopup.innerHTML = html;
  setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html);
  hoverLayoutState.hoverPopup.style.display = 'block';
  hoverLayoutState.hoverPopupContainer.style.display = dependencyPopupState.displaySettings.dictPopup
    ? 'flex'
    : 'none';
  applyDictionaryHoverPopupClamp();
  positionSidePanelPopup(
    hoverLayoutState.hoverPopupContainer,
    segmentRenderingState.lastMouseX,
    segmentRenderingState.lastMouseY
  );
}
export function parseFormMetaPayloadFromElement(metaEl) {
  if (!metaEl) return null;
  var encoded = String(metaEl.getAttribute('data-form-meta') || '');
  if (encoded) {
    try {
      var parsed = JSON.parse(decodeURIComponent(encoded));
      if (parsed && typeof parsed === 'object') return parsed;
    } catch (e) {}
  }
  return {
    kind: String(metaEl.getAttribute('data-meta-kind') || ''),
    form: String(metaEl.getAttribute('data-meta-form') || metaEl.textContent || '')
  };
}
export function joinMetaTags(tags) {
  if (!Array.isArray(tags) || !tags.length) return '';
  var out = [];
  for (var i = 0; i < tags.length; i++) {
    var txt = String(tags[i] || '').trim();
    if (txt) out.push(txt);
  }
  return out.length ? out.join(', ') : '';
}
export function renderFormMetaPopupHtml(meta) {
  var payload = meta || {};
  var form = String(payload.form || '');
  var kind = String(payload.kind || '');
  var infoTags = joinMetaTags(payload.info_tags);
  var rawPriTags = Array.isArray(payload.priority_tags) ? payload.priority_tags : [];
  var priTagsFiltered = [];
  for (var pti = 0; pti < rawPriTags.length; pti++) {
    var ptag = String(rawPriTags[pti] || '').trim();
    if (!ptag) continue;
    var ptagLower = ptag.toLowerCase();
    if (ptagLower === 'spec1' || ptagLower === 'spec2') continue;
    priTagsFiltered.push(ptag);
  }
  var priTags = joinMetaTags(priTagsFiltered);
  var priScoreNum =
    typeof payload.priority_score === 'number' && isFinite(payload.priority_score)
      ? payload.priority_score
      : 0;
  var priScore = priScoreNum.toFixed(1) + '%';
  var priBasisTag = String(payload.priority_basis_tag || '').trim();
  var specTag = String(payload.spec_priority_tag || '').trim();
  function row(label, valueHtml) {
    var value = String(valueHtml || '').trim();
    if (!value) return '';
    return '<div style="color:#6b7280;">' + escapeHtml(label) + '</div><div>' + value + '</div>';
  }
  var html = '';
  html += '<div class="popup-headline">' + escapeHtml(form) + '</div>';
  html +=
    '<div style="display:grid;grid-template-columns:auto 1fr;gap:2px 10px;align-items:start;font-size:12px;line-height:1.55;">';
  html += row('Spec priority', escapeHtml(specTag));
  html += row('Priority tags', escapeHtml(priTags));
  html += row('Frequency score', escapeHtml(priScore));
  html += row('Info tags', escapeHtml(infoTags));
  if (kind === 'reading') {
    var noKanji = payload.no_kanji ? 'yes' : '';
    var restrictedTo = joinMetaTags(payload.restricted_to_kanji);
    html += row('No-kanji reading', escapeHtml(noKanji));
    html += row('Restricted reading', escapeHtml(restrictedTo));
  }
  html += '</div>';
  return html;
}
export function parseKoGlossPayloadFromElement(glossEl) {
  if (!glossEl) return null;
  var encoded = String(glossEl.getAttribute('data-ko-gloss') || '').trim();
  if (!encoded) return null;
  try {
    var parsed = JSON.parse(decodeURIComponent(encoded));
    if (!parsed || typeof parsed !== 'object') return null;
    var defs = [];
    var rawDefs = Array.isArray(parsed.defs) ? parsed.defs : [];
    for (var i = 0; i < rawDefs.length; i++) {
      var txt = String(rawDefs[i] || '').trim();
      if (txt) defs.push(txt);
    }
    if (!defs.length) return null;
    var title = String(parsed.title || glossEl.textContent || '').trim();
    return {
      title: title,
      defs: defs
    };
  } catch (e) {
    return null;
  }
}
export function renderKoGlossPopupHtml(payload) {
  var p = payload || {};
  var defs = Array.isArray(p.defs) ? p.defs : [];
  if (!defs.length) return '';
  var html = '';
  html += '<div style="font-size:12px;line-height:1.65;">';
  for (var i = 0; i < defs.length; i++) {
    var defLine = String(defs[i] || '').trim();
    if (!defLine) continue;
    html += '<div>';
    if (defs.length > 1) {
      html += '<span style="color:#888;font-size:11px;margin-right:4px;">' + (i + 1) + '.</span>';
    }
    html += escapeHtml(defLine);
    html += '</div>';
  }
  html += '</div>';
  return html;
}
export function showKoGlossPopupSimple(glossEl) {
  hideSeparateGrammarPopup();
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (hoverLayoutState.udPopup) {
    hoverLayoutState.udPopup.style.display = 'none';
    hoverLayoutState.udPopup.innerHTML = '';
  }
  if (hoverLayoutState.notePopup) {
    hoverLayoutState.notePopup.style.display = 'none';
    hoverLayoutState.notePopup.textContent = '';
  }
  if (!dependencyPopupState.displaySettings.dictPopup) {
    hoverLayoutState.hoverPopup.style.display = 'none';
    hoverLayoutState.hoverPopupContainer.style.display = 'none';
    clearDictionaryHoverPopupClamp();
    return;
  }
  var payload = parseKoGlossPayloadFromElement(glossEl);
  if (!payload || !payload.defs || !payload.defs.length) {
    hidePopup();
    return;
  }
  var html = renderKoGlossPopupHtml(payload);
  if (!html) {
    hidePopup();
    return;
  }
  hoverLayoutState.hoverPopup.innerHTML = html;
  setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html, {
    disableClamp: true
  });
  hoverLayoutState.hoverPopup.style.display = 'block';
  hoverLayoutState.hoverPopupContainer.style.display = 'flex';
  applyDictionaryHoverPopupClamp();
  positionSidePanelPopup(
    hoverLayoutState.hoverPopupContainer,
    segmentRenderingState.lastMouseX,
    segmentRenderingState.lastMouseY
  );
}
export function showFormMetaPopupSimple(metaEl) {
  hideSeparateGrammarPopup();
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (hoverLayoutState.udPopup) {
    hoverLayoutState.udPopup.style.display = 'none';
    hoverLayoutState.udPopup.innerHTML = '';
  }
  if (hoverLayoutState.notePopup) {
    hoverLayoutState.notePopup.style.display = 'none';
    hoverLayoutState.notePopup.textContent = '';
  }
  if (!dependencyPopupState.displaySettings.dictPopup) {
    hoverLayoutState.hoverPopup.style.display = 'none';
    hoverLayoutState.hoverPopupContainer.style.display = 'none';
    clearDictionaryHoverPopupClamp();
    return;
  }
  var payload = parseFormMetaPayloadFromElement(metaEl);
  if (!payload || !payload.form) {
    hidePopup();
    return;
  }
  var html = renderFormMetaPopupHtml(payload);
  hoverLayoutState.hoverPopup.innerHTML = html;
  setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html);
  hoverLayoutState.hoverPopup.style.display = 'block';
  hoverLayoutState.hoverPopupContainer.style.display = 'flex';
  applyDictionaryHoverPopupClamp();
  positionSidePanelPopup(
    hoverLayoutState.hoverPopupContainer,
    segmentRenderingState.lastMouseX,
    segmentRenderingState.lastMouseY
  );
}
// SIMPLIFIED: Render dictionary popup for side panel hover
export function renderDictPopupSimple(res, seg, activeFillIndexes) {
  var useJaHoverFiltering =
    isJapaneseLanguage() ||
    !!(
      window.ReaderLanguageAdapters &&
      window.ReaderLanguageAdapters.ko &&
      typeof window.ReaderLanguageAdapters.ko.isKoreanLanguage === 'function' &&
      window.ReaderLanguageAdapters.ko.isKoreanLanguage(documentShellState.currentLanguage)
    );
  hideSeparateGrammarPopup();
  var head = getEntryDisplayHead(res, seg);
  var isUnknownEntry = function (obj) {
    if (!obj) return true;
    var p = (obj.pos || '').toLowerCase();
    var ss = obj.senses || [];
    return (
      p.indexOf('unknown') >= 0 ||
      (ss.length === 1 &&
        typeof ss[0] === 'string' &&
        ss[0].toLowerCase().indexOf('no dictionary entry') >= 0)
    );
  };

  // Disable G2P pronunciation popup in side panel (pronunciation only in main window)
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (!dependencyPopupState.displaySettings.dictPopup) {
    hoverLayoutState.hoverPopup.style.display = 'none';
    hoverLayoutState.hoverPopupContainer.style.display = 'none';
    clearDictionaryHoverPopupClamp();
    return;
  }
  var oldFills = hoverLayoutState.hoverPopupContainer
    ? hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup')
    : [];
  for (var ofi = 0; ofi < oldFills.length; ofi++) {
    if (oldFills[ofi] && oldFills[ofi].parentNode) oldFills[ofi].parentNode.removeChild(oldFills[ofi]);
  }
  var html = '';
  var rawFill = Array.isArray(res && res.dict_fill) ? res.dict_fill : [];
  var fillState = getRenderableFillState(rawFill, isUnknownEntry);
  var fill = fillState.entries;
  var fillHasKnown = fillState.hasKnown;
  var targetedFillIndexes = Array.isArray(activeFillIndexes) ? activeFillIndexes.slice() : [];
  var mainIsUnknown = isUnknownEntry(res) && !(fill.length && fillHasKnown);
  traceUiRenderEvent(
    'hover_popup_render_start',
    {
      seg: String(seg || ''),
      head: head,
      main_is_unknown: !!mainIsUnknown,
      fill_count: fill.length,
      entry: summarizeUiRenderDebugLookupEntry(res)
    },
    {
      scope: 'hover'
    }
  );
  if (!mainIsUnknown) {
    var useSeparateFillPopups = fill.length > 1;
    if (
      useSeparateFillPopups &&
      targetedFillIndexes.length === 1 &&
      targetedFillIndexes[0] >= 0 &&
      targetedFillIndexes[0] < rawFill.length
    ) {
      var targetFill = rawFill[targetedFillIndexes[0]];
      var targetHead = getRenderableFillLabel(targetFill, head);
      if (targetFill && targetHead) {
        html += renderDictTemplate(targetFill, targetHead, {
          showHead: false,
          showRomanUnknown: true,
          showSensesKnown: true,
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false,
          _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
          forceSenseHead: true
        }).html;
      } else {
        renderDictFillPopups(fill, null, hoverLayoutState.hoverPopupContainer, {
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false
        });
      }
    } else if (useSeparateFillPopups && targetedFillIndexes.length > 1) {
      var groupedFills = [];
      for (var gfi = 0; gfi < targetedFillIndexes.length; gfi++) {
        var groupedIndex = targetedFillIndexes[gfi];
        if (!isFinite(groupedIndex) || groupedIndex < 0 || groupedIndex >= rawFill.length) continue;
        var groupedFill = rawFill[groupedIndex];
        if (!groupedFill || !hasDisplayText(getRenderableFillLabel(groupedFill, ''))) continue;
        groupedFills.push(groupedFill);
      }
      if (groupedFills.length) {
        renderDictFillPopups(groupedFills, null, hoverLayoutState.hoverPopupContainer, {
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false
        });
      } else {
        renderDictFillPopups(fill, null, hoverLayoutState.hoverPopupContainer, {
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false
        });
      }
    } else if (useSeparateFillPopups) {
      renderDictFillPopups(fill, null, hoverLayoutState.hoverPopupContainer, {
        sensesKey: 'senses_hover',
        showFilteredNote: true,
        showOtherDefsDropdown: false
      });
    } else {
      var singleEntry = fill.length === 1 ? fill[0] : null;
      var senseEntry =
        singleEntry &&
        !isUnknownEntry(singleEntry) &&
        Array.isArray(singleEntry.senses) &&
        singleEntry.senses.length
          ? singleEntry
          : res;
      var senseHead = getRenderableFillLabel(singleEntry, head) || head;
      html += renderDictTemplate(senseEntry, senseHead, {
        showHead: false,
        showRomanUnknown: true,
        showSensesKnown: true,
        sensesKey: 'senses_hover',
        showFilteredNote: true,
        showOtherDefsDropdown: false,
        _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
        forceSenseHead: true
      }).html;
    }
  } else {
    html = renderDictTemplate(res, head, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: 'senses_hover',
      showFilteredNote: true,
      showOtherDefsDropdown: false,
      _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
      forceSenseHead: true
    }).html;
  }
  if (dependencyPopupState.displaySettings.dictPopup && String(html || '').trim()) {
    hoverLayoutState.hoverPopup.innerHTML = html;
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html);
    hoverLayoutState.hoverPopup.style.display = 'block';
  } else {
    hoverLayoutState.hoverPopup.innerHTML = '';
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, '');
    hoverLayoutState.hoverPopup.style.display = 'none';
  }
  var hasDictFillPopups = !!hoverLayoutState.hoverPopupContainer.querySelector('.dict-fill-popup');

  // Show only dict popup (pronunciation disabled in side panel)
  hoverLayoutState.hoverPopupContainer.style.display =
    dependencyPopupState.displaySettings.dictPopup &&
    (hoverLayoutState.hoverPopup.style.display !== 'none' || hasDictFillPopups)
      ? 'flex'
      : 'none';
  if (hoverLayoutState.hoverPopupContainer.style.display === 'flex') {
    applyDictionaryHoverPopupClamp();
    positionSidePanelPopup(
      hoverLayoutState.hoverPopupContainer,
      segmentRenderingState.lastMouseX,
      segmentRenderingState.lastMouseY
    );
  } else {
    clearDictionaryHoverPopupClamp();
  }
  traceUiRenderEvent(
    'hover_popup_render_complete',
    {
      seg: String(seg || ''),
      head: head,
      html_length: String(html || '').length,
      has_dict_fill_popups: !!hasDictFillPopups,
      container_visible: hoverLayoutState.hoverPopupContainer.style.display === 'flex'
    },
    {
      scope: 'hover'
    }
  );
}
export function _normalizeLegacyG2PData(g2pData, rawText, rawLang) {
  var lang = String(rawLang || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  var text = String(rawText || '').trim();
  if (typeof g2pData === 'string') {
    var romanString = String(g2pData || '').trim();
    if (!romanString) return null;
    return {
      language: lang,
      script: '',
      text: text,
      overallRomanization: romanString,
      overallSound: romanString,
      syllables: text
        ? [
            {
              orth: text,
              roman: romanString,
              sound: romanString,
              notes: [],
              components: [],
              part_count: 0,
              has_decomposition: false
            }
          ]
        : []
    };
  }
  if (!g2pData || typeof g2pData !== 'object') return null;
  var syllables = [];
  var srcSyllables = Array.isArray(g2pData.syllables) ? g2pData.syllables : [];
  for (var i = 0; i < srcSyllables.length; i++) {
    var s = srcSyllables[i] || {};
    var rawComponents = Array.isArray(s.components) ? s.components : [];
    var components = [];
    for (var j = 0; j < rawComponents.length; j++) {
      var p = rawComponents[j] || {};
      var ch = String(p.ch || p.char || '');
      var roman = String(p.roman || p.sound || p.pronunciation || '');
      var meta = String(p.meta || p.codePoint || p.codepoint || '');
      var label = String(p.label || p.role || '');
      components.push({
        ch: ch,
        roman: roman,
        sound: roman,
        label: label,
        meta: meta,
        role: label,
        codePoint: meta,
        emphasis: !!p.emphasis
      });
    }
    var syllRoman = String(s.roman || s.sound || s.pronunciation || '').trim();
    syllables.push({
      orth: String(s.orth || s.cluster || s.text || ''),
      roman: syllRoman,
      sound: String(s.sound || s.roman || s.pronunciation || ''),
      notes: Array.isArray(s.notes) ? s.notes.slice() : [],
      components: components,
      part_count: components.length,
      has_decomposition: components.length > 1
    });
  }
  var overall = String(
    g2pData.overallRomanization ||
      g2pData.overall_roman ||
      g2pData.romanization ||
      g2pData.pronunciation ||
      ''
  ).trim();
  if (!syllables.length && text && overall) {
    syllables.push({
      orth: text,
      roman: overall,
      sound: overall,
      notes: [],
      components: [],
      part_count: 0,
      has_decomposition: false
    });
  }
  if (!syllables.length && !overall) return null;
  return {
    language: lang,
    script: String(g2pData.script || ''),
    text: text,
    overallRomanization: overall,
    overallSound: String(g2pData.overallSound || g2pData.overall_sound || overall),
    syllables: syllables
  };
}
export function _buildPronunciationPopupModel(rawText, rawLang, g2pData) {
  var lang = String(rawLang || documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  var text = String(rawText || '').trim();
  var api = _getGraphemePronunciationApi();
  var model = null;
  if (api && text && typeof api.buildPronunciationAnalysis === 'function') {
    try {
      model = api.buildPronunciationAnalysis(lang, text, {
        normalize: true,
        decompose: true,
        compatibility: true,
        preserveUnknown: false
      });
    } catch (e) {
      model = null;
    }
  }
  if (!model) {
    model = _normalizeLegacyG2PData(g2pData, text, lang);
  }
  if (!model && text && typeof g2pData === 'string') {
    var roman = String(g2pData || '').trim();
    if (roman) {
      model = {
        language: lang,
        script: '',
        text: text,
        overallRomanization: roman,
        overallSound: roman,
        syllables: [
          {
            orth: text,
            roman: roman,
            sound: roman,
            notes: [],
            components: [],
            part_count: 0,
            has_decomposition: false
          }
        ]
      };
    }
  }
  if (!model) return null;
  if (!Array.isArray(model.syllables)) model.syllables = [];
  if (!model.overallRomanization) {
    var overallParts = [];
    for (var i = 0; i < model.syllables.length; i++) {
      var syll = model.syllables[i] || {};
      var syllRoman = String(syll.roman || syll.sound || '').trim();
      if (syllRoman) overallParts.push(syllRoman);
    }
    model.overallRomanization = overallParts.join(' ');
  }
  if (!model.overallSound) model.overallSound = model.overallRomanization;
  model.text = text || model.text || '';
  model.language = lang || model.language || '';
  return model;
}
export function getG2PMiniGroupTextSets(surfaceText, udTok, tokenEntry) {
  var sets = [];
  var seen = Object.create(null);
  function addSet(parts) {
    if (!Array.isArray(parts) || parts.length < 2) return;
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var rawPart = parts[i];
      var text = '';
      if (rawPart && typeof rawPart === 'object') {
        text = String(rawPart.text || rawPart.form || rawPart.source_text || '').trim();
      } else {
        text = String(rawPart || '').trim();
      }
      if (text) out.push(text);
    }
    if (out.length < 2) return;
    var key = out
      .map(function (part) {
        return normalizeVisibleComparisonText(part).replace(/\s+/g, '');
      })
      .join('|');
    if (!key || seen[key]) return;
    seen[key] = true;
    sets.push(out);
  }
  var tokenMwtParts =
    tokenEntry && Array.isArray(tokenEntry.mwt_parts) && tokenEntry.mwt_parts.length
      ? tokenEntry.mwt_parts
      : [];
  var udMwtParts = udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length ? udTok.mwt_parts : [];
  addSet(udMwtParts.length ? udMwtParts : tokenMwtParts);
  var lemmaText = String(
    (udTok && (udTok.lemma_raw || udTok.lemma)) ||
      (tokenEntry && (tokenEntry.lemma_raw || tokenEntry.lemma_form || tokenEntry.lemma)) ||
      ''
  ).trim();
  if (/[+\uFF0B]/.test(lemmaText)) {
    addSet(getTokenMapLemmaPartTexts(lemmaText));
  }
  return sets;
}
