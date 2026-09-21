import { renderSenseLines } from './annotations.mjs';
import { dictionaryPopupState } from './dictionary-popup.state.mjs';
import { hideSeparateGrammarPopup, isPunctToken } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  getCanonicalTokenEntry,
  getLookupEntryFills,
  getLookupPayloadPrimaryResult,
  getLookupPayloadResults,
  lookupSingleDictionary,
  registerPanelEditContext
} from './entry-editing.mjs';
import { showGeminiEditPanel } from './entry-forms.mjs';
import {
  buildPopupHeadwordHtml,
  buildPopupSurfaceHeadlineHtml,
  wrapPopupHeadlineHtml
} from './grammar-popup.mjs';
import { clearDictionaryHoverPopupClamp } from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  buildDictSourceBadgeHtml,
  buildEntrySenseMetaHtml,
  captureUiRenderPanelSnapshot,
  escapeHtml,
  filterRenderableFillEntries,
  getDictSourceBadgeInfo,
  getEntryDisplayHead,
  getLanguageAdapter,
  getPanelHeadwordRows,
  getRenderableFillState,
  hasSameVisibleComparisonText,
  isJapaneseLanguage,
  isUiRenderDebugEnabled,
  renderPopupRomanLine,
  startUiRenderPanelSession,
  stripZeroWidthJoiners,
  summarizeUiRenderDebugLookupEntry,
  traceUiRenderEvent
} from './presentation.mjs';
import { showDictPopupSimple } from './pronunciation-panel.mjs';
import { clearAllTokenLookupState, getExactSidePanelLookupEntry } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { sidePanelState } from './side-panel.state.mjs';
import { attachPanelHandlers } from './token-banner-menu.mjs';
import { buildAggregateLookupEntry, renderTokenBanner } from './token-banner.mjs';
import { fetchExactSidePanelLookupEntry } from './token-map.mjs';
export // Track the actual hovered element
function positionSidePanelPopup(popupEl, clientX, clientY) {
  // Position popup to LEFT of hovered word - never cover the hovered word
  // No max distance constraint - popup can be anywhere as long as it doesn't cover the word
  if (!popupEl || popupEl.style.display === 'none') return;
  var vw = window.innerWidth,
    vh = window.innerHeight;
  var margin = 10;
  popupEl.style.left = '0px';
  popupEl.style.top = '0px';
  // DIRECT DOM measurement for accuracy
  var rect = popupEl.getBoundingClientRect();
  var w = rect ? rect.width : popupEl.offsetWidth || 0;
  var h = rect ? rect.height : popupEl.offsetHeight || 0;

  // Use the actual hovered element if we have it, otherwise search - DIRECT DOM
  var hoveredRect = null;
  try {
    if (dictionaryPopupState.lastHoveredElement) {
      var r = dictionaryPopupState.lastHoveredElement.getBoundingClientRect();
      if (r && r.width > 0 && r.height > 0) {
        hoveredRect = {
          left: r.left,
          top: r.top,
          right: r.right,
          bottom: r.bottom,
          width: r.width,
          height: r.height
        };
      }
    } else if (segmentRenderingState.panelHoverToken && hoverLayoutState.panelContent) {
      var els = hoverLayoutState.panelContent.querySelectorAll('.headword-component, .panel-token');
      for (var i = 0; i < els.length; i++) {
        if (els[i].dataset.seg === segmentRenderingState.panelHoverToken) {
          var r = els[i].getBoundingClientRect();
          if (r && r.width > 0 && r.height > 0) {
            hoveredRect = {
              left: r.left,
              top: r.top,
              right: r.right,
              bottom: r.bottom,
              width: r.width,
              height: r.height
            };
          }
          break;
        }
      }
    }
  } catch (e) {}
  var x, y;
  if (hoveredRect && hoveredRect.width > 0) {
    // Position to the LEFT of the hovered word (toward the main window)
    x = hoveredRect.left - w - margin;
    y = hoveredRect.top;

    // If left placement would go off screen, try below the word
    if (x < 8) {
      x = Math.max(8, hoveredRect.left);
      y = hoveredRect.bottom + margin;
      // If below also goes off screen, position above
      if (y + h > vh - 8) {
        y = Math.max(8, hoveredRect.top - h - margin);
      }
    } else {
      // Left placement worked, but check if y needs adjustment
      if (y + h > vh - 8) {
        y = vh - h - 8;
      }
      if (y < 8) {
        y = 8;
      }
    }
  } else {
    // Fallback: position near cursor, preferring left side
    x = clientX - w - margin;
    y = clientY;
    // Clamp to viewport
    if (x < 8) {
      x = clientX + margin; // Try right of cursor if left doesn't work
    }
    x = Math.max(8, Math.min(x, vw - w - 8));
    y = Math.max(8, Math.min(y, vh - h - 8));
  }
  popupEl.style.left = x + 'px';
  popupEl.style.top = y + 'px';
}
export function hidePopup() {
  hoverLayoutState.hoverPopupContainer.style.display = 'none';
  segmentRenderingState.currentPopupAnchorEl = null;
  clearDictionaryHoverPopupClamp();
  hideSeparateGrammarPopup();
  if (hoverLayoutState.udPopup) {
    hoverLayoutState.udPopup.style.display = 'none';
    hoverLayoutState.udPopup.innerHTML = '';
  }
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (hoverLayoutState.notePopup) {
    hoverLayoutState.notePopup.style.display = 'none';
    hoverLayoutState.notePopup.textContent = '';
  }
  if (hoverLayoutState.subsegmentPopupsContainer) {
    hoverLayoutState.subsegmentPopupsContainer.style.display = 'none';
    hoverLayoutState.subsegmentPopupsContainer.innerHTML = '';
  }
  // Remove dict-fill popups from the hover container
  var oldFills = hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup');
  for (var ofi = 0; ofi < oldFills.length; ofi++) {
    oldFills[ofi].parentNode.removeChild(oldFills[ofi]);
  }
}
// ===================== SIDE PANEL =====================
export function lookupAndDisplay(token, options) {
  hoverLayoutState.panelContent.innerHTML =
    '<div style="color:#888;text-align:center;margin-top:20px;">Loading...</div>';
  clearAllTokenLookupState();
  var requestLang = String(documentShellState.currentLanguage || '');
  var onResolved = options && typeof options.onResolved === 'function' ? options.onResolved : null;
  if (!requestLang) {
    hoverLayoutState.panelContent.innerHTML =
      '<div style="color:#888;text-align:center;margin-top:20px;">Select a language first.</div>';
    return;
  }
  var useExact = options && options.exact;
  var allowFuzzy = false;
  var fuzzyNoIsland = !!(options && options.noIsland);
  var fuzzySegIdx =
    options && typeof options.segIdx === 'number' && isFinite(options.segIdx) && options.segIdx >= 0
      ? options.segIdx
      : null;
  var fuzzyBaseToken = options && options.baseToken ? String(options.baseToken) : '';
  var fuzzyUnknownPiece = options && options.unknownPiece ? String(options.unknownPiece) : '';
  var fuzzyForceWholeToken = !!(options && options.forceWholeToken);
  var clickedPiece = options && options.clickedPiece ? String(options.clickedPiece) : '';
  var lemmaHint = options && options.lemma ? String(options.lemma) : '';
  var lemmaHintRaw = options && options.lemmaRaw ? String(options.lemmaRaw) : lemmaHint;
  var uposHint = options && options.upos ? String(options.upos) : '';
  var xposHint = options && options.xpos ? String(options.xpos) : '';
  var manualPanelSearch = !!(options && options.manualPanelSearch);
  var fuzzyPanelOpt = !!(options && options.fuzzyPanel);
  // Direct dictionary lookup � bypasses the main text-NLP path.
  lookupSingleDictionary(token, requestLang, {
    lemma: lemmaHint,
    upos: uposHint,
    xpos: xposHint,
    exact: useExact,
    fuzzyPanel: fuzzyPanelOpt
  })
    .then(function (data) {
      var lookupResults = getLookupPayloadResults(data);
      var primaryResult = getLookupPayloadPrimaryResult(data);
      if (!data.ok || !lookupResults.length) {
        if (useExact) {
          var unknownEntry = {
            head: token,
            pos: 'unknown',
            senses: ['[no dictionary entry found for this segment]']
          };
          var fullData = data || {};
          if (!allowFuzzy) fullData.disableFuzzy = true;
          if (allowFuzzy && !fuzzyUnknownPiece) {
            fuzzyUnknownPiece = token;
          }
          if (allowFuzzy && typeof fuzzySegIdx === 'number') {
            fullData.fuzzySegIdx = fuzzySegIdx;
          }
          if (allowFuzzy && fuzzyBaseToken) {
            fullData.fuzzyBaseToken = fuzzyBaseToken;
          }
          if (allowFuzzy && fuzzyUnknownPiece) {
            fullData.fuzzyUnknownPiece = fuzzyUnknownPiece;
          }
          if (allowFuzzy && fuzzyForceWholeToken) {
            fullData.fuzzyForceWholeToken = true;
          }
          if (allowFuzzy && fuzzyNoIsland) {
            fullData.fuzzyNoIsland = true;
          }
          if (clickedPiece) {
            fullData.clickedPiece = clickedPiece;
          }
          fullData._panelTokenSurface = fuzzyBaseToken || token;
          if (lemmaHint) fullData._panelTokenLemma = lemmaHint;
          if (lemmaHintRaw) fullData._panelTokenLemmaRaw = lemmaHintRaw;
          if (manualPanelSearch) fullData._panelManualSearch = true;
          fullData._lookupLang = requestLang;
          displayDictEntry(unknownEntry, token, fullData);
          if (onResolved) {
            try {
              onResolved(unknownEntry, token, fullData);
            } catch (_resolveErr1) {}
          }
          return;
        }
        hoverLayoutState.panelContent.innerHTML =
          '<div style="color:#888;text-align:center;margin-top:20px;">No results for "' +
          escapeHtml(token) +
          '"</div>';
        return;
      }
      var displayEntry = buildAggregateLookupEntry(lookupResults, token) || primaryResult;
      var fullData = data || {};
      fullData._lookupLang = requestLang;
      if (!allowFuzzy) fullData.disableFuzzy = true;
      if (allowFuzzy && typeof fuzzySegIdx === 'number') {
        fullData.fuzzySegIdx = fuzzySegIdx;
      }
      if (allowFuzzy && fuzzyBaseToken) {
        fullData.fuzzyBaseToken = fuzzyBaseToken;
      }
      if (allowFuzzy && fuzzyUnknownPiece) {
        fullData.fuzzyUnknownPiece = fuzzyUnknownPiece;
      }
      if (allowFuzzy && fuzzyForceWholeToken) {
        fullData.fuzzyForceWholeToken = true;
      }
      if (allowFuzzy && fuzzyNoIsland) {
        fullData.fuzzyNoIsland = true;
      }
      if (clickedPiece) {
        fullData.clickedPiece = clickedPiece;
      }
      fullData._panelTokenSurface = fuzzyBaseToken || token;
      if (lemmaHint) fullData._panelTokenLemma = lemmaHint;
      if (lemmaHintRaw) fullData._panelTokenLemmaRaw = lemmaHintRaw;
      if (manualPanelSearch) fullData._panelManualSearch = true;
      displayDictEntry(displayEntry || primaryResult, token, fullData);
      if (onResolved) {
        try {
          onResolved(displayEntry || primaryResult, token, fullData);
        } catch (_resolveErr2) {}
      }
    })
    .catch(function (err) {
      console.error(err);
      hoverLayoutState.panelContent.innerHTML =
        '<div style="color:#c00;text-align:center;margin-top:20px;">Error loading dictionary</div>';
    });
}
export function isUnknownDictEntry(obj) {
  if (!obj) return true;
  var p = String(obj.pos || obj.upos || '').toLowerCase();
  var ss = obj.senses || [];
  var fills = getLookupEntryFills(obj);
  return (
    p.indexOf('unknown') >= 0 ||
    (!fills.length && !ss.length) ||
    (ss.length === 1 && typeof ss[0] === 'string' && ss[0].toLowerCase().indexOf('no dictionary entry') >= 0)
  );
}
// DEBUG MAP: shared popup/panel dictionary renderer.
// entryMetaHtml and forceSenseHead are passed through from callers into
// renderSenseLines/renderStackedSenseLines, which is where provenance/edit now lands.
export function renderDictTemplate(entry, fallbackHead, options) {
  // Delegate to language-specific template if the adapter provides one
  var adapter = getLanguageAdapter();
  if (adapter && typeof adapter.renderDictEntry === 'function') {
    var adapterOptions = options || {};
    var nextAdapterOptions = Object.assign({}, adapterOptions);
    if (!Object.prototype.hasOwnProperty.call(nextAdapterOptions, '_lang')) {
      nextAdapterOptions._lang = String(documentShellState.currentLanguage || '').toLowerCase();
    }
    if (!Object.prototype.hasOwnProperty.call(nextAdapterOptions, '_sentence')) {
      nextAdapterOptions._sentence = hoverLayoutState._currentPopupSentenceCtx || '';
    }
    if (!Object.prototype.hasOwnProperty.call(nextAdapterOptions, '_buildTopSurfaceHeadlineHtml')) {
      nextAdapterOptions._buildTopSurfaceHeadlineHtml = buildPopupSurfaceHeadlineHtml;
    }
    // NOTE: _buildTokenMapLookupHtml and _buildPanelSurfaceHeadlineHtml are
    // intentionally NOT injected here. Panel segment rendering is handled
    // by PanelSegmentRenderer (panel_segment_renderer.js) after the HTML is
    // written to the DOM. Reader_wikt.js therefore produces plain data-seg spans.
    adapterOptions = nextAdapterOptions;
    return adapter.renderDictEntry(entry, fallbackHead, adapterOptions);
  }
  var opts = options || {};
  var e = entry || {};
  var head = String(e.head || fallbackHead || '');
  var isUnk = isUnknownDictEntry(e);
  var senseKey = opts.sensesKey != null ? String(opts.sensesKey) : 'senses';
  var hasSenseKey = Array.isArray(e[senseKey]) && e[senseKey].length > 0;
  var senses = hasSenseKey ? e[senseKey] : [];
  var fullSenses = Array.isArray(e.senses) ? e.senses : [];
  if (!hasSenseKey && senseKey !== 'senses') senses = fullSenses;
  var formsMetaByHeader = null;
  if (senseKey === 'senses_hover') {
    formsMetaByHeader = e.senses_hover_form_meta_by_header || e.senses_form_meta_by_header || null;
  } else if (senseKey === 'senses_hover_other') {
    formsMetaByHeader = e.senses_hover_other_form_meta_by_header || e.senses_form_meta_by_header || null;
  } else {
    formsMetaByHeader = e.senses_form_meta_by_header || null;
  }
  var altSenses = Array.isArray(e.senses_hover_other) ? e.senses_hover_other : [];
  var altFormsMetaByHeader = e.senses_hover_other_form_meta_by_header || formsMetaByHeader || null;
  var hasFilteredAlternates = !isUnk && !!e.hover_has_alt_senses && altSenses.length > 0;
  var showFilteredNote = !!opts.showFilteredNote && hasFilteredAlternates;
  var showOtherDefsExpander = !!opts.showOtherDefsDropdown && hasFilteredAlternates;
  var html = '';
  if (opts.showHead !== false) {
    if (opts.headHtml != null) {
      html += String(opts.headHtml);
    } else {
      var topHeadlineHtml =
        typeof opts._buildTopSurfaceHeadlineHtml === 'function'
          ? String(opts._buildTopSurfaceHeadlineHtml(e, head, 'surface') || '')
          : '';
      html += wrapPopupHeadlineHtml(topHeadlineHtml || buildPopupHeadwordHtml(e, head));
    }
  }
  if (isUnk) {
    if (opts.showRomanUnknown !== false) {
      html += renderPopupRomanLine(e.g2p);
    }
  } else if (opts.showSensesKnown !== false) {
    if (senses.length) {
      html += renderSenseLines(senses, head, formsMetaByHeader, {
        entryMetaHtml: String(opts.entryMetaHtml || ''),
        forceSenseHead: !!opts.forceSenseHead
      });
    } else if (opts.showEmpty) {
      html += '<div class="popup-empty">[no senses]</div>';
    }
    if (showFilteredNote) {
      html += '<span class="popup-alt-senses-signal" hidden aria-hidden="true"></span>';
    }
    if (showOtherDefsExpander) {
      html += '<details class="panel-filtered-expander">';
      html += '<summary class="panel-filtered-expander-bar">';
      html += '<span class="panel-filtered-expander-arrow">&#9660;</span> ';
      html += 'Other definitions';
      html += '</summary>';
      html +=
        '<div class="panel-filtered-expander-content">' +
        renderSenseLines(altSenses, head, altFormsMetaByHeader, {
          entryMetaHtml: String(opts.entryMetaHtml || ''),
          forceSenseHead: !!opts.forceSenseHead
        }) +
        '</div>';
      html += '</details>';
    }
  }
  return {
    html: html,
    isUnknown: isUnk,
    sensesCount: senses.length,
    head: head
  };
}
export function displayDictEntry(res, originalToken, fullData) {
  var requestLang =
    fullData && fullData._lookupLang
      ? String(fullData._lookupLang)
      : String(documentShellState.currentLanguage || '');
  var sourcePayload = fullData && typeof fullData === 'object' ? fullData : hoverLayoutState.latestData;
  var panelRes = res;
  var head = getEntryDisplayHead(panelRes, originalToken);
  var nextFullData = fullData || null;
  if (nextFullData && !(nextFullData._panelTokenEntry && typeof nextFullData._panelTokenEntry === 'object')) {
    var panelTokenSurface = String(nextFullData._panelTokenSurface || '').trim();
    var liveTokenEntry = hoverLayoutState.tokenMapData
      ? getCanonicalTokenEntry(hoverLayoutState.tokenMapData)
      : null;
    if (
      liveTokenEntry &&
      panelTokenSurface &&
      hasSameVisibleComparisonText(String(hoverLayoutState.tokenMapData.surface || ''), panelTokenSurface)
    ) {
      nextFullData = Object.assign({}, nextFullData, {
        _panelTokenEntry: liveTokenEntry
      });
    }
  }
  hoverLayoutState.currentPanelDisplayState = {
    res: panelRes,
    originalToken: originalToken,
    fullData: nextFullData
  };
  if (isUiRenderDebugEnabled()) {
    startUiRenderPanelSession({
      original_token: String(originalToken || ''),
      head: head,
      lookup_lang: requestLang,
      manual_search: !!(nextFullData && nextFullData._panelManualSearch),
      panel_token_surface: String((nextFullData && nextFullData._panelTokenSurface) || ''),
      panel_token_lemma: String((nextFullData && nextFullData._panelTokenLemma) || ''),
      panel_token_lemma_raw: String((nextFullData && nextFullData._panelTokenLemmaRaw) || ''),
      entry: summarizeUiRenderDebugLookupEntry(panelRes)
    });
  }

  // Store panel-specific result without overwriting the original cached
  // tokenMapData fields (entry, tokenEntry, dictFill, etc.) which come
  // from resultsBySeg and are the source of truth for grammar popup / hover.
  if (
    hoverLayoutState.tokenMapData &&
    hoverLayoutState.tokenMapData.surface === (nextFullData && nextFullData._panelTokenSurface)
  ) {
    hoverLayoutState.tokenMapData.panelEntry = panelRes;
  }
  var dictFillState = getRenderableFillState(panelRes && panelRes.dict_fill, isUnknownDictEntry);
  var dictFillForPanel = dictFillState.entries;
  var fillHasKnown = dictFillState.hasKnown;
  var fillHasUnknown = dictFillState.hasUnknown;
  var isUnk = dictFillForPanel.length
    ? fillHasUnknown || !fillHasKnown || isUnknownDictEntry(panelRes)
    : isUnknownDictEntry(panelRes);

  // Headword decomposition via /subsegments is removed. Multi-fill surface
  // text is now rendered by buildTokenMapLookupHtml (same as the token banner)
  // which uses dict_fill + dict_fill_surface_slices directly.
  var headDecompByForm = Object.create(null);
  if (hoverLayoutState.tokenMapData) hoverLayoutState.tokenMapData.headDecompByForm = headDecompByForm;
  renderPanelEntry(panelRes, head, isUnk, headDecompByForm, nextFullData);
}
export function prefetchPanelComponentLookups(components, langOverride) {
  if (!components || !components.length) return;
  var requestLang = String(langOverride || documentShellState.currentLanguage || '');
  components.forEach(function (comp) {
    var compHead = comp && comp.head ? String(comp.head) : '';
    if (!compHead || getExactSidePanelLookupEntry(compHead, requestLang, {})) return;
    fetchExactSidePanelLookupEntry(compHead, requestLang, {
      cacheResult: true
    }).catch(function () {});
  });
}
// SIMPLIFIED: Render main dictionary entry in side panel
// DEBUG MAP: side-panel dictionary renderer.
// This is the main provenance/edit assembly point for the lower panel.
export function renderPanelEntry(res, head, isUnk, headDecompByForm, fullData) {
  var requestLang =
    fullData && fullData._lookupLang
      ? String(fullData._lookupLang)
      : String(documentShellState.currentLanguage || '');
  hoverLayoutState.currentPanelEditContextByKey = Object.create(null);
  var _koAdapter =
    window.ReaderLanguageAdapters &&
    (window.ReaderLanguageAdapters.ko || window.ReaderLanguageAdapters.korean);
  var _isKoLang =
    _koAdapter &&
    typeof _koAdapter.isKoreanLanguage === 'function' &&
    _koAdapter.isKoreanLanguage(requestLang);
  var useJaPanelFiltering = isJapaneseLanguage(requestLang) || _isKoLang;
  if (hoverLayoutState.panelContent && hoverLayoutState.panelContent.dataset) {
    hoverLayoutState.panelContent.dataset.bannerFillKey =
      fullData && fullData._panelBannerFillKey ? String(fullData._panelBannerFillKey) : '';
    hoverLayoutState.panelContent.dataset.bannerEntrySignature =
      fullData && fullData._panelEntrySignature ? String(fullData._panelEntrySignature) : '';
  }
  var html = '<div class="dict-entry" style="position:relative;">';

  // Render token banner above the dictionary panel (unless manual search)
  if (
    hoverLayoutState.tokenMapData &&
    !(fullData && fullData._panelManualSearch) &&
    !(fullData && fullData._skipBannerRender)
  ) {
    renderTokenBanner();
  } else if (!hoverLayoutState.tokenMapData || (fullData && fullData._panelManualSearch)) {
    var _bannerEl = document.getElementById('token-banner');
    if (_bannerEl) _bannerEl.style.display = 'none';
    var _synthEl = document.getElementById('synth-entry-bar');
    if (_synthEl) _synthEl.style.display = 'none';
  }

  // 1. HEADWORD rows (language-specific row-shape handled by getPanelHeadwordRows)
  var headColor = '#000';
  var headFormRows = getPanelHeadwordRows(res, head);
  var dictFill = filterRenderableFillEntries(res && res.dict_fill);
  var showAggregateHeadword = !(dictFill.length > 1);
  if (isUiRenderDebugEnabled()) {
    traceUiRenderEvent(
      'panel_render_start',
      {
        head: head,
        request_lang: requestLang,
        is_unknown: !!isUnk,
        head_form_rows: headFormRows.slice(),
        dict_fill_count: dictFill.length,
        show_aggregate_headword: !!showAggregateHeadword,
        entry: summarizeUiRenderDebugLookupEntry(res)
      },
      {
        scope: 'panel-render'
      }
    );
  }

  // DEBUG MAP: builds the actual badge HTML and edit button HTML for one entry object.
  // If Edit disappears, inspect badgeInfo/source resolution here first.
  function buildPanelEntryHeadlineMeta(entryObj, fallbackHeadText) {
    var badgeHtml = buildDictSourceBadgeHtml(entryObj);
    var badgeInfo = getDictSourceBadgeInfo(entryObj);
    var editHtml = '';
    if (badgeInfo) {
      var editContext = registerPanelEditContext(entryObj, fallbackHeadText, requestLang);
      if (editContext && editContext.snapshot) {
        var editHead = String(editContext.snapshot.headword || '').trim();
        var editSource = String(badgeInfo.source || '');
        editHtml =
          '<button type="button" class="dict-entry-edit-btn" style="pointer-events:auto;" data-edit-key="' +
          escapeHtml(editContext.key) +
          '" data-entry-id="' +
          escapeHtml(editContext.snapshot.entry_id || '') +
          '" data-headword="' +
          escapeHtml(editHead) +
          '" data-lang="' +
          escapeHtml(requestLang) +
          '" data-source="' +
          escapeHtml(editSource) +
          '">Edit</button>';
      }
    }
    return {
      badgeHtml: badgeHtml,
      editHtml: editHtml
    };
  }
  function buildPanelEntryMetaHtmlForEntry(entryObj, fallbackHeadText) {
    var meta = buildPanelEntryHeadlineMeta(entryObj, fallbackHeadText);
    return buildEntrySenseMetaHtml(meta.badgeHtml, meta.editHtml);
  }
  function renderEntryHeadword(entryObj, fallbackHeadText, baseColor, suffixHtml, trailingHtml, options) {
    // Top-level surface-slice headline is suppressed globally — per-entry headwords
    // rendered inside renderEntryGroupsHtml (reader_wikt.js) serve as the visible headlines.
    void entryObj;
    void fallbackHeadText;
    void baseColor;
    void suffixHtml;
    void trailingHtml;
    void options;
    return '';
    if (isUiRenderDebugEnabled()) {
      traceUiRenderEvent(
        'panel_entry_headword_rows',
        {
          fallback_head: String(fallbackHeadText || ''),
          rows: rows.slice(),
          entry: summarizeUiRenderDebugLookupEntry(entryObj)
        },
        {
          scope: 'panel-render'
        }
      );
    }
    var out = '<div class="popup-headline popup-headline-inline-flow" style="color:' + baseColor + ';">';
    for (var hri = 0; hri < rows.length; hri++) {
      var formText = String(rows[hri] || '');
      var formDisplay = stripZeroWidthJoiners(formText);
      if (!formText) continue;
      if (!formDisplay.trim()) continue;
      var isAltHeadForm = hri > 0;
      if (isAltHeadForm) out += '<span class="popup-headword-alt">';
      var roleClass = hri === 0 ? 'surface' : 'entry-headword';
      if (isUiRenderDebugEnabled()) {
        traceUiRenderEvent(
          'panel_entry_headword_row_render',
          {
            text: formText,
            role: roleClass,
            is_alt_form: !!isAltHeadForm
          },
          {
            scope: 'panel-render'
          }
        );
      }
      // popup-headline-inline-flow is always the surface slice heading the dict entries.
      // Never interactive — plain text only, no hover, no underline.
      out +=
        '<span class="panel-token panel-surface-token" style="cursor:text;">' +
        escapeHtml(formDisplay) +
        '</span>';
      if (isAltHeadForm) out += '</span>';
    }
    out += _suffix + '</div>';
    if (_trailing) {
      return '<div class="dict-entry-headline-row">' + out + _trailing + '</div>';
    }
    return out;
  }

  // Show aggregate headword only when there are no fill entries (bare entry).
  // Provenance/edit metadata is rendered inside the structured sense rows.
  if (showAggregateHeadword && !dictFill.length) {
    // Top-level aggregate surface-slice headline removed; per-entry headwords below serve as headlines.
    void headColor;
  }

  // 3. SENSES: Render definitions
  var hasContent = false;
  html += '<div class="dict-senses" id="dict-senses-container">';

  // If we have dict_fill entries, render each one
  if (dictFill.length) {
    var renderedFillCount = 0;
    for (var di = 0; di < dictFill.length; di++) {
      var part = dictFill[di] || {};
      var pHead = getEntryDisplayHead(part, '');
      if (!pHead) continue;
      var pUnk = isUnknownDictEntry(part);
      if (pUnk) {
        // Skip unknown parts that match the main headword (already shown above)
        if (pHead === head && isUnk) continue;
      }
      if (renderedFillCount > 0) html += '<div class="dict-fill-separator"></div>';
      // Entry-level head stays plain; provenance/edit metadata is rendered
      // inline with the structured headword rows inside the senses block.
      // DEBUG MAP: dict_fill panel entries still render a plain head row here,
      // then separately inject provenance/edit into the first structured sense row below.
      var partHeadHtml =
        '<div class="dict-entry-part-head">' + renderEntryHeadword(part, pHead, '#000') + '</div>';
      var partWrapperClass = 'dict-entry-part';
      if (pUnk) partWrapperClass += ' dict-entry-part-unknown';
      var partBlock = renderDictTemplate(part, pHead, {
        showHead: true,
        headHtml: partHeadHtml,
        showRomanUnknown: true,
        showSensesKnown: true,
        sensesKey: 'senses_hover',
        showOtherDefsDropdown: true,
        _morphDisplayMode: 'panel',
        _headDecompByForm: headDecompByForm,
        _buildEntryMetaForRow: buildPanelEntryMetaHtmlForEntry,
        forceSenseHead: true
      });
      html += '<div class="' + partWrapperClass + '">' + partBlock.html + '</div>';
      if (!partBlock.isUnknown && partBlock.sensesCount > 0) hasContent = true;
      renderedFillCount += 1;
    }
  }
  // Fallback: use top-level entry template if no dict_fill content
  else {
    var baseBlock = renderDictTemplate(res, head, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: 'senses_hover',
      showOtherDefsDropdown: true,
      _morphDisplayMode: 'panel',
      _headDecompByForm: headDecompByForm,
      _buildEntryMetaForRow: buildPanelEntryMetaHtmlForEntry,
      forceSenseHead: true
    });
    html += baseBlock.html;
    if (!baseBlock.isUnknown && baseBlock.sensesCount > 0) hasContent = true;
  }
  html += '</div>';

  // 4. FUZZY MATCHING: Automatically run if there's unknown content
  var allowFuzzy = false;
  var hasUnknown =
    isUnk ||
    dictFill.some(function (p) {
      return isUnknownDictEntry(p);
    });
  var fuzzyUnknownPiece = fullData && fullData.fuzzyUnknownPiece ? fullData.fuzzyUnknownPiece : '';
  var fuzzyForceWholeToken = !!(fullData && fullData.fuzzyForceWholeToken);
  html += '</div>';
  hoverLayoutState.panelContent.innerHTML = html;

  // Wire PSR hover callback once (idempotent).
  if (window.PanelSegmentRenderer && typeof window.PanelSegmentRenderer.init === 'function') {
    window.PanelSegmentRenderer.init({
      showPopup: showDictPopupSimple,
      hidePopup: hidePopup,
      positionPopup: function (clientX, clientY) {
        segmentRenderingState.lastMouseX = clientX;
        segmentRenderingState.lastMouseY = clientY;
        positionSidePanelPopup(hoverLayoutState.hoverPopupContainer, clientX, clientY);
      },
      setHoveredElement: function (el) {
        dictionaryPopupState.lastHoveredElement = el || null;
      }
    });
  }

  // Segment-render the panel spans (surface text, base forms) via the standalone renderer.
  if (window.PanelSegmentRenderer && typeof window.PanelSegmentRenderer.processPanel === 'function') {
    window.PanelSegmentRenderer.processPanel(hoverLayoutState.panelContent, requestLang);
  }

  // DEBUG MAP: final event binding for every rendered Edit button in the side panel.
  var editEntryBtns = hoverLayoutState.panelContent.querySelectorAll('.dict-entry-edit-btn');
  for (var ebi = 0; ebi < editEntryBtns.length; ebi++) {
    editEntryBtns[ebi].addEventListener('click', function () {
      var editKey = String(this.getAttribute('data-edit-key') || '');
      var editContext = hoverLayoutState.currentPanelEditContextByKey[editKey] || null;
      showGeminiEditPanel(editContext);
    });
  }
  var prefetchComponents = [];
  var prefSeen = Object.create(null);
  function collectPrefetchForForm(rawForm) {
    var pfText = String(rawForm || '');
    if (!pfText) return;
    var pfComps = headDecompByForm && Array.isArray(headDecompByForm[pfText]) ? headDecompByForm[pfText] : [];
    for (var pci = 0; pci < pfComps.length; pci++) {
      var pc = pfComps[pci] || {};
      var pHead = String(pc.head || '');
      if (!pHead || prefSeen[pHead]) continue;
      prefSeen[pHead] = true;
      prefetchComponents.push(pc);
    }
  }
  for (var pf = 0; pf < headFormRows.length; pf++) {
    collectPrefetchForForm(headFormRows[pf]);
  }
  for (var dpf = 0; dpf < dictFill.length; dpf++) {
    var dpEntry = dictFill[dpf] || {};
    var dpHead = String(dpEntry.head || dpEntry.text || '');
    var dpForms = getPanelHeadwordRows(dpEntry, dpHead);
    for (var dpr = 0; dpr < dpForms.length; dpr++) {
      collectPrefetchForForm(dpForms[dpr]);
    }
  }
  prefetchPanelComponentLookups(prefetchComponents, requestLang);
  // Panel definition text is no longer segmented here.
  // PanelSegmentRenderer owns the interactive token/headword spans.
  attachPanelHandlers();
  captureUiRenderPanelSnapshot('panel_render_complete');

  // Token Info chip removed � replaced by token banner above panel

  // Auto-trigger fuzzy matching if there's unknown content
}
// Segment a fuzzy headword into hoverable component spans
export function isPanelSegResultUnknown(res) {
  if (!res) return true;
  if (!res.source || res.source === 'UNKNOWN' || res.source === 'PUNCT') return true;
  var p = String(res.pos || '').toLowerCase();
  if (p.indexOf('unknown') >= 0) return true;
  var ss = res.senses || [];
  if (ss.length === 1 && typeof ss[0] === 'string' && ss[0].toLowerCase().indexOf('no dictionary entry') >= 0)
    return true;
  return false;
}
export function segmentBurmeseInElement(el) {
  // Universal dictionary-validated panel segmentation.
  // Works for every language: splits all text into word tokens, looks each up
  // via /lookup_dp_only, and only wraps words with actual dictionary entries
  // (not UNKNOWN/PUNCT) as hoverable .panel-token spans.
  // No per-language script regex is needed � the dictionary itself is the filter.
  var requestLang = String(documentShellState.currentLanguage || '');
  var lang = String(requestLang || '').toLowerCase();

  // Only run if the language has a registered adapter (i.e. has a dictionary)
  var adapter = getLanguageAdapter(lang);
  if (!adapter) return;

  // Only segment text inside .panel-segmentable elements (gloss/definition text).
  // This avoids making POS labels, morph tags, etymology, relation labels, etc. hoverable.
  var segmentableEls = el.querySelectorAll('.panel-segmentable');
  var textNodes = [];
  for (var sei = 0; sei < segmentableEls.length; sei++) {
    var walker = document.createTreeWalker(segmentableEls[sei], NodeFilter.SHOW_TEXT, null, false);
    var n;
    while ((n = walker.nextNode())) {
      var parentEl = n.parentElement;
      if (parentEl && parentEl.closest('.headword-component')) continue;
      if (parentEl && parentEl.closest('.panel-token')) continue;
      if (!n.nodeValue || !/\S/.test(n.nodeValue)) continue;
      textNodes.push(n);
    }
  }
  textNodes.forEach(function (textNode) {
    var text = textNode.nodeValue;
    if (!text) return;

    // Split into alternating word / non-word parts
    var wordParts = [];
    var wordRx = /[\p{L}\p{M}'\u2019-]+/gu;
    var match;
    var lastEnd = 0;
    while ((match = wordRx.exec(text)) !== null) {
      if (match.index > lastEnd) {
        wordParts.push({
          type: 'other',
          text: text.slice(lastEnd, match.index)
        });
      }
      wordParts.push({
        type: 'word',
        text: match[0]
      });
      lastEnd = match.index + match[0].length;
    }
    if (lastEnd < text.length) {
      wordParts.push({
        type: 'other',
        text: text.slice(lastEnd)
      });
    }
    var wordTokens = wordParts.filter(function (p) {
      return p.type === 'word' && p.text.trim();
    });
    if (!wordTokens.length) return;

    // Look up each word via the API
    var wordPromises = wordTokens.map(function (p) {
      return lookupSingleDictionary(p.text || '', requestLang, {})
        .then(function (data) {
          p.segments = data.segments || [];
          p.results_by_seg = data.results_by_seg || {};
          var lookupResults = getLookupPayloadResults(data);
          var res = getLookupPayloadPrimaryResult(data);
          p.isKnown = !isPanelSegResultUnknown(res);
          p.result = res;
        })
        .catch(function () {
          p.isKnown = false;
          p.result = null;
          p.segments = [];
          p.results_by_seg = {};
        });
    });
    Promise.all(wordPromises).then(function () {
      var frag = document.createDocumentFragment();
      for (var pi = 0; pi < wordParts.length; pi++) {
        var part = wordParts[pi];
        if (part.type === 'other') {
          frag.appendChild(document.createTextNode(part.text));
          continue;
        }
        if (!part.isKnown) {
          // UNKNOWN � leave as plain text (not inspectable)
          frag.appendChild(document.createTextNode(part.text));
          continue;
        }
        // Check for multi-segment results (e.g. CJK compound split into parts)
        var segs = part.segments || [];
        var resultsBySeg = part.results_by_seg || {};
        if (segs.length > 1) {
          // Multiple segments returned � wrap each known segment individually
          var txt = part.text;
          var idx = 0;
          for (var si = 0; si < segs.length; si++) {
            var seg = segs[si];
            var pos = txt.indexOf(seg, idx);
            if (pos > idx) {
              frag.appendChild(document.createTextNode(txt.slice(idx, pos)));
            }
            if (pos >= 0) {
              if (isPunctToken(seg)) {
                frag.appendChild(document.createTextNode(seg));
                idx = pos + seg.length;
                continue;
              }
              var segRes = resultsBySeg[si] || null;
              if (isPanelSegResultUnknown(segRes)) {
                frag.appendChild(document.createTextNode(seg));
                idx = pos + seg.length;
                continue;
              }
              var dictFill = getLookupEntryFills(segRes);
              if (dictFill.length > 0) {
                for (var di = 0; di < dictFill.length; di++) {
                  var fillEntry = dictFill[di];
                  var fillText = fillEntry.text || fillEntry.head || '';
                  var fillHead = fillEntry.head || fillText;
                  if (!fillText) continue;
                  var subspan = document.createElement('span');
                  subspan.className = 'panel-token';
                  subspan.textContent = fillText;
                  subspan.dataset.seg = fillHead;
                  frag.appendChild(subspan);
                }
              } else {
                var span = document.createElement('span');
                span.className = 'panel-token';
                span.textContent = seg;
                span.dataset.seg = seg;
                frag.appendChild(span);
              }
              idx = pos + seg.length;
            }
          }
          if (idx < txt.length) {
            frag.appendChild(document.createTextNode(txt.slice(idx)));
          }
        } else {
          var res = part.result;
          var fill = getLookupEntryFills(res);
          if (fill.length > 0) {
            for (var fi = 0; fi < fill.length; fi++) {
              var fEntry = fill[fi];
              var fText = fEntry.text || fEntry.head || '';
              var fHead = fEntry.head || fText;
              if (!fText) continue;
              var fSpan = document.createElement('span');
              fSpan.className = 'panel-token';
              fSpan.textContent = fText;
              fSpan.dataset.seg = fHead;
              frag.appendChild(fSpan);
            }
          } else {
            var wSpan = document.createElement('span');
            wSpan.className = 'panel-token';
            wSpan.textContent = part.text;
            wSpan.dataset.seg = (res && res.head) || part.text;
            frag.appendChild(wSpan);
          }
        }
      }
      if (textNode.parentNode) {
        textNode.parentNode.replaceChild(frag, textNode);
      }
    });
  });
}
// ===========================================================================
// Decomp hover popup — replaces the inline +decomp/note-style affordance.
//
// Hover a headword in the side panel (.entry-headword-block) → tiny floating
// tooltip appears showing "+ decomp" (no existing) or "decomp" (existing).
// Click headword → if no decomp yet, generate via Gemini and show the
// result in a transient floating popup. If decomp already exists, that
// popup just displays it. Click headword again while popup is open → flip
// to a persistent editor with two contenteditable rows + ✓ / ✗ / 🗑.
// Delete prompts confirm() before firing /api/entry_decomp/delete.
// ===========================================================================
export function initializeSidePanel() {
  sidePanelState._decompFloat = null;
  sidePanelState._decompFloatState = 'hidden'; // 'hidden' | 'tooltip' | 'view' | 'edit'
  sidePanelState._decompFloatBlock = null; // currently bound .entry-headword-block
  sidePanelState._decompFloatBusy = false;
  sidePanelState._decompCache = Object.create(null); // alias|rowId -> decomp text (latest)
  return true;
}
