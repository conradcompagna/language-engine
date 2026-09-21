import { updateNotePopupForHead } from './annotations.mjs';
import { buildUdEdgeDrawKey, getUdInfoForSegment } from './dependency-hover.mjs';
import { buildUdPopupHtml } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dictionaryPopupState } from './dictionary-popup.state.mjs';
import {
  buildConcatenatedFillEntriesHtml,
  hideSeparateGrammarPopup,
  showSeparateGrammarPopupForToken
} from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { resolveSegmentPosData } from './fill-slices.mjs';
import { setG2PPopup } from './flashcards.mjs';
import { tokenShouldShowSynthHint } from './gloss-entries.mjs';
import {
  applyDictionaryHoverPopupClamp,
  applyLanguagePresentationToElement,
  clearDictionaryHoverPopupClamp,
  setDictionaryPopupSignalFromMarkup
} from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _buildExpandedCtxForSeg } from './lookup-progress.mjs';
import { isKoreanCompoundSpawnInternalFill, koreanCompoundSynthGroupHasGreedy } from './mwt-anchors.mjs';
import { mwtContextState } from './mwt-context.state.mjs';
import {
  buildPopupEntryMetaHtmlForEntry,
  filterRenderableFillEntries,
  getEntryDisplayHead,
  getRenderableFillLabel,
  getRenderableFillState,
  hasDisplayText,
  isJapaneseLanguage
} from './presentation.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { hidePopup, renderDictTemplate } from './side-panel.mjs';
import { invalidateUiRectFor } from './token-fragments.mjs';
import { tokenFragmentsState } from './token-fragments.state.mjs';
export function buildPopupForWord(wordSpan, parentToken, segIdx, resultsBySeg, gramOverlay) {
  if (!wordSpan) return hidePopup();
  // Use dataset.word or dataset.seg (clean text without dotted circle) for pipeline operations
  var word = wordSpan.dataset.word || wordSpan.dataset.seg || wordSpan.textContent || '';
  if (!word) return hidePopup();

  // Update sentence context for entry note generation
  hoverLayoutState._currentPopupSentenceCtx = _buildExpandedCtxForSeg(
    typeof segIdx === 'number' ? segIdx : -1,
    word
  );
  var dictHtml = '';
  var g2pData = null;
  var res = resultsBySeg && resultsBySeg[segIdx] ? resultsBySeg[segIdx] : null;
  var entry = res;
  if (!entry) return hidePopup();
  var udTok = getUdInfoForSegment(segIdx);
  var posData = resolveSegmentPosData(segIdx, res, udTok);
  var useJaHoverFiltering =
    isJapaneseLanguage() ||
    !!(
      window.ReaderLanguageAdapters &&
      window.ReaderLanguageAdapters.ko &&
      typeof window.ReaderLanguageAdapters.ko.isKoreanLanguage === 'function' &&
      window.ReaderLanguageAdapters.ko.isKoreanLanguage(documentShellState.currentLanguage)
    );

  // Show grammar in the separate grammar popup
  hoverLayoutState._synthHintActive = tokenShouldShowSynthHint(res, word);
  if (dependencyPopupState.displaySettings.grammarPopup) {
    showSeparateGrammarPopupForToken(posData, udTok, word, res, {
      segIdx: segIdx
    });
  } else {
    hideSeparateGrammarPopup();
  }

  // Extract g2p from the individual word's entry
  g2pData = entry.g2p || null;
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
  var fillState = getRenderableFillState(entry && entry.dict_fill, isUnknownEntry);
  var fill = fillState.entries;
  var fillHasKnown = fillState.hasKnown;
  var mainIsUnknown = isUnknownEntry(entry) && !(fill.length && fillHasKnown);
  if (!mainIsUnknown) {
    var hasRenderableFill = false;
    for (var fci = 0; fci < fill.length; fci++) {
      if (fill[fci] && fill[fci].head) {
        hasRenderableFill = true;
        break;
      }
    }
    var useConcatenatedFill = fill.length > 1 && hasRenderableFill;
    if (useConcatenatedFill) {
      var concatHtml = buildConcatenatedFillEntriesHtml(fill, word, {
        sensesKey: 'senses_hover',
        showFilteredNote: true,
        showOtherDefsDropdown: false
      });
      if (concatHtml) dictHtml += concatHtml;
    } else {
      // Single fill or no fill � render via shared template
      var singleEntry = fill.length === 1 ? fill[0] : null;
      var senseEntry =
        singleEntry &&
        !isUnknownEntry(singleEntry) &&
        Array.isArray(singleEntry.senses) &&
        singleEntry.senses.length
          ? singleEntry
          : entry;
      var senseHead = getRenderableFillLabel(singleEntry, word) || word;
      var block = renderDictTemplate(senseEntry, senseHead, {
        showHead: false,
        showRomanUnknown: true,
        showSensesKnown: true,
        showEmpty: true,
        sensesKey: 'senses_hover',
        showFilteredNote: true,
        showOtherDefsDropdown: false,
        _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
        forceSenseHead: true
      });
      dictHtml += block.html;
    }
  } else {
    // Unknown word � render via shared template (handles red headline + romanization)
    var block = renderDictTemplate(entry, word, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: 'senses_hover',
      showFilteredNote: true,
      showOtherDefsDropdown: false,
      _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
      forceSenseHead: true
    });
    dictHtml += block.html;
  }
  displayWordPopup(dictHtml, word, segIdx, g2pData);
}

// Render dict_fill entries as separate popups inside the given container (left-to-right order).
// These participate in the existing hover popup collision detection since they're children of hoverPopupContainer.
export function renderDictFillPopups(fills, posData, container, options) {
  var opts = options || {};
  var renderableFills = filterRenderableFillEntries(fills);
  for (var i = 0; i < renderableFills.length; i++) {
    var sub = renderableFills[i];
    var subHead = getRenderableFillLabel(sub, '');
    if (!sub || !subHead) continue;
    var popupDiv = document.createElement('div');
    popupDiv.className = 'dict-fill-popup subsegment-popup';
    popupDiv.style.display = 'block';
    applyLanguagePresentationToElement(popupDiv, {
      direction: 'ltr',
      alignText: false
    });
    var block = renderDictTemplate(sub, subHead, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: opts.sensesKey,
      showFilteredNote: !!opts.showFilteredNote,
      showOtherDefsDropdown: !!opts.showOtherDefsDropdown,
      _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
      forceSenseHead: true
    });
    popupDiv.innerHTML = block.html;
    setDictionaryPopupSignalFromMarkup(popupDiv, block.html);
    container.appendChild(popupDiv);
  }
}
export function displayWordPopup(dictHtml, word, segIdx, g2pData) {
  segmentRenderingState.currentPopupHead = word;
  var oldFills = hoverLayoutState.hoverPopupContainer
    ? hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup')
    : [];
  for (var ofi = 0; ofi < oldFills.length; ofi++) {
    if (oldFills[ofi] && oldFills[ofi].parentNode) oldFills[ofi].parentNode.removeChild(oldFills[ofi]);
  }
  if (dependencyPopupState.displaySettings.dictPopup && String(dictHtml || '').trim()) {
    hoverLayoutState.hoverPopup.innerHTML = dictHtml;
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, dictHtml);
    hoverLayoutState.hoverPopup.style.display = 'block';
  } else {
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, '');
    hoverLayoutState.hoverPopup.style.display = 'none';
  }
  // Set pronunciation popup for the individual word
  setG2PPopup(word, documentShellState.currentLanguage, g2pData);
  // UD popup for the parent segment
  if (hoverLayoutState.udPopup) {
    if (dependencyPopupState.displaySettings.udPopup && segIdx >= 0) {
      var udHtml = buildUdPopupHtml(segIdx);
      if (udHtml) {
        hoverLayoutState.udPopup.innerHTML = udHtml;
        hoverLayoutState.udPopup.style.display = 'block';
      } else {
        hoverLayoutState.udPopup.style.display = 'none';
        hoverLayoutState.udPopup.innerHTML = '';
      }
    } else {
      hoverLayoutState.udPopup.style.display = 'none';
      hoverLayoutState.udPopup.innerHTML = '';
    }
  }
  var anyPopupVisible =
    (dependencyPopupState.displaySettings.pronunciation &&
      hoverLayoutState.g2pPopup &&
      hoverLayoutState.g2pPopup.style.display !== 'none') ||
    (dependencyPopupState.displaySettings.udPopup &&
      hoverLayoutState.udPopup &&
      hoverLayoutState.udPopup.style.display !== 'none') ||
    (dependencyPopupState.displaySettings.dictPopup &&
      hoverLayoutState.hoverPopup &&
      hoverLayoutState.hoverPopup.style.display !== 'none') ||
    (dependencyPopupState.displaySettings.grammarPopup &&
      hoverLayoutState.grammarPopup &&
      hoverLayoutState.grammarPopup.style.display !== 'none') ||
    dependencyPopupState.displaySettings.comments;
  hoverLayoutState.hoverPopupContainer.style.display = anyPopupVisible ? 'flex' : 'none';
  if (anyPopupVisible) {
    applyDictionaryHoverPopupClamp();
  } else {
    clearDictionaryHoverPopupClamp();
  }
  if (dependencyPopupState.displaySettings.comments) {
    updateNotePopupForHead(word);
  }
  // Fetch and display subsegment popups if enabled
  if (hoverLayoutState.subsegmentPopupsContainer) {
    hoverLayoutState.subsegmentPopupsContainer.style.display = 'none';
    hoverLayoutState.subsegmentPopupsContainer.innerHTML = '';
  }
}
export function buildPopupForSpan(span, resultsBySeg, gramOverlay, activeFillIndexes, popupOptions) {
  if (!span) return;
  var popupOpts = popupOptions && typeof popupOptions === 'object' ? popupOptions : {};
  var allowDictPopup = !!dependencyPopupState.displaySettings.dictPopup && !popupOpts.suppressDict;
  var allowGrammarPopup = !!dependencyPopupState.displaySettings.grammarPopup && !popupOpts.suppressGrammar;
  var popupContext =
    span && span.__mwtSpawnContext && typeof span.__mwtSpawnContext === 'object'
      ? span.__mwtSpawnContext
      : null;
  var idx =
    popupContext && isFinite(Number(popupContext.segIdx))
      ? Number(popupContext.segIdx)
      : parseInt(span.dataset.index || '-1', 10);
  var seg =
    popupContext && popupContext.childText ? String(popupContext.childText || '') : span.dataset.seg || '';
  if (!seg || isNaN(idx)) {
    hidePopup();
    return;
  }
  var isKoreanCompoundSpawn = !!(popupContext && popupContext.isKoreanCompoundLemmaSpawn);
  if (isKoreanCompoundSpawn && popupContext && popupContext.synthGroup) {
    koreanCompoundSynthGroupHasGreedy(popupContext.synthGroup);
  }
  var res = isKoreanCompoundSpawn
    ? popupContext.lookupResult || null
    : popupContext && popupContext.lookupResult
      ? popupContext.lookupResult
      : resultsBySeg && idx >= 0
        ? resultsBySeg[idx]
        : null;
  var head = seg,
    g2pData = null;
  if (res) {
    head = getEntryDisplayHead(res, seg);
    g2pData = res.g2p || null;
  }
  // Determine if entry is unknown BEFORE building the headline
  var dictHtml = '';
  var mainIsUnknown = false;
  function isUnknownEntry(obj) {
    if (!obj) return true;
    var p = (obj.pos || '').toLowerCase();
    var ss = obj.senses || [];
    return (
      p.indexOf('unknown') >= 0 ||
      (ss.length === 1 &&
        typeof ss[0] === 'string' &&
        ss[0].toLowerCase().indexOf('no dictionary entry') >= 0)
    );
  }
  var fill = [];
  var renderableFill = [];
  if (res && allowDictPopup) {
    var firstD = res;
    fill = Array.isArray(firstD.dict_fill) ? firstD.dict_fill : [];
    var fillState = getRenderableFillState(fill, isUnknownEntry);
    renderableFill = fillState.entries;
    var fillHasKnown = fillState.hasKnown;

    // Check if main entry is unknown
    var hasKnownFill = fillHasKnown && renderableFill.length > 0;
    var hasAnyContent = (Array.isArray(firstD.senses) ? firstD.senses.length : 0) || hasKnownFill;
    mainIsUnknown =
      (firstD.pos || '').toLowerCase().indexOf('unknown') >= 0 ||
      !hasAnyContent ||
      (renderableFill.length && !fillHasKnown);
  }

  // Build headline with proper color for unknowns
  var udTok = popupContext && popupContext.udTok ? popupContext.udTok : getUdInfoForSegment(idx);
  var posData =
    popupContext && popupContext.posData ? popupContext.posData : resolveSegmentPosData(idx, res, udTok);
  var grammarEntry = popupContext ? (resultsBySeg && idx >= 0 ? resultsBySeg[idx] : res) : res;
  var grammarUdTok = popupContext ? getUdInfoForSegment(idx) : udTok;
  var grammarPosData = popupContext ? resolveSegmentPosData(idx, grammarEntry, grammarUdTok) : posData;
  var grammarTokenText = popupContext
    ? String(
        (grammarEntry && grammarEntry.surface_form) ||
          (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[idx]) ||
          seg
      )
    : seg;
  var useJaHoverFiltering =
    isJapaneseLanguage() ||
    !!(
      window.ReaderLanguageAdapters &&
      window.ReaderLanguageAdapters.ko &&
      typeof window.ReaderLanguageAdapters.ko.isKoreanLanguage === 'function' &&
      window.ReaderLanguageAdapters.ko.isKoreanLanguage(documentShellState.currentLanguage)
    );

  // Show grammar in the separate grammar popup
  hoverLayoutState._synthHintActive = tokenShouldShowSynthHint(grammarEntry || res, grammarTokenText);
  if (allowGrammarPopup) {
    var grammarOptions = {
      segIdx: idx
    };
    if (isKoreanCompoundSpawn && popupContext && popupContext.synthGroup) {
      grammarOptions.koreanCompoundSynthGroup = popupContext.synthGroup;
      grammarOptions.forceSynthHint = koreanCompoundSynthGroupHasGreedy(popupContext.synthGroup);
    }
    if (popupContext && !popupContext.isKoreanCompoundLemmaSpawn && isFinite(Number(popupContext.partIdx))) {
      grammarOptions.mwtPartIndex = Number(popupContext.partIdx);
      grammarOptions.mwtChildText = String(popupContext.childText || '');
      grammarOptions.lookupText = String(popupContext.lookupText || popupContext.childText || '');
      grammarOptions.mwtSurfaceSlice = String(popupContext.anchorText || '');
      grammarOptions.anchorText = String(popupContext.anchorText || '');
      grammarOptions.mwtPopupReason = String(popupContext.popupReason || '');
    } else if (popupOpts && isFinite(Number(popupOpts.hoverMwtPartIdx))) {
      grammarOptions.mwtPartIndex = Number(popupOpts.hoverMwtPartIdx);
      grammarOptions.mwtChildText = String(popupOpts.hoverMwtChildText || '');
      grammarOptions.lookupText = String(popupOpts.hoverMwtChildText || '');
      grammarOptions.mwtSurfaceSlice = String(popupOpts.hoverMwtSurfaceSlice || '');
      grammarOptions.anchorText = String(popupOpts.hoverMwtSurfaceSlice || '');
    }
    showSeparateGrammarPopupForToken(
      grammarPosData,
      grammarUdTok,
      grammarTokenText,
      grammarEntry,
      grammarOptions
    );
  } else {
    hideSeparateGrammarPopup();
  }
  setG2PPopup(seg, documentShellState.currentLanguage, g2pData);

  // Clear any previous dict-fill popups from the container before rebuilding.
  var oldFills = hoverLayoutState.hoverPopupContainer.querySelectorAll('.dict-fill-popup');
  for (var ofi = 0; ofi < oldFills.length; ofi++) {
    if (oldFills[ofi] && oldFills[ofi].parentNode) oldFills[ofi].parentNode.removeChild(oldFills[ofi]);
  }
  if (mainIsUnknown && allowDictPopup) {
    // Unknown entry � render via shared template (handles red headline + romanization)
    var block = renderDictTemplate(res, head, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: true,
      sensesKey: 'senses_hover',
      showFilteredNote: true,
      showOtherDefsDropdown: false,
      _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
      forceSenseHead: true
    });
    dictHtml += block.html;
  } else {
    // Known entry. Multi-entry dict_fill tokens: show the targeted fill slice,
    // or all fills attached to that slice, otherwise fall back to aggregate rendering.
    renderableFill = filterRenderableFillEntries(fill);
    var isMultiFill = renderableFill.length > 1;
    var koreanInternalFill = false;
    if (isKoreanCompoundSpawn && res) {
      var koreanFillSlices = Array.isArray(res.dict_fill_surface_slices)
        ? res.dict_fill_surface_slices
        : null;
      koreanInternalFill = isKoreanCompoundSpawnInternalFill(res, koreanFillSlices);
      if (isMultiFill && !koreanInternalFill) isMultiFill = false;
    }
    if (res && allowDictPopup) {
      fill = Array.isArray(res.dict_fill) ? res.dict_fill : [];
      var targetedFillIndexes = Array.isArray(activeFillIndexes) ? activeFillIndexes.slice() : [];
      if (isKoreanCompoundSpawn && koreanInternalFill && isMultiFill && !targetedFillIndexes.length) {
        // Korean compound child spans are rewritten into concrete fill-hit
        // targets. Until the pointer is over one, do not flash the aggregate
        // "all fills" popup.
      } else if (
        isMultiFill &&
        targetedFillIndexes.length === 1 &&
        targetedFillIndexes[0] >= 0 &&
        targetedFillIndexes[0] < fill.length
      ) {
        // ---- Per-fill hover: show only the targeted fill entry ----
        var targetFill = fill[targetedFillIndexes[0]];
        var targetFillHead = getRenderableFillLabel(targetFill, '');
        if (targetFill && targetFillHead) {
          var fillBlock = renderDictTemplate(targetFill, targetFillHead, {
            showHead: false,
            showRomanUnknown: true,
            showSensesKnown: true,
            sensesKey: 'senses_hover',
            showFilteredNote: true,
            showOtherDefsDropdown: false,
            _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
            forceSenseHead: true
          });
          dictHtml += fillBlock.html;
        }
      } else if (isMultiFill && targetedFillIndexes.length > 1) {
        var groupedFills = [];
        for (var gfi = 0; gfi < targetedFillIndexes.length; gfi++) {
          var groupedIndex = targetedFillIndexes[gfi];
          if (!isFinite(groupedIndex) || groupedIndex < 0 || groupedIndex >= fill.length) continue;
          if (
            hasDisplayText(
              fill[groupedIndex] &&
                (fill[groupedIndex].head != null ? fill[groupedIndex].head : fill[groupedIndex].text)
            )
          ) {
            groupedFills.push(fill[groupedIndex]);
          }
        }
        if (groupedFills.length) {
          renderDictFillPopups(groupedFills, posData, hoverLayoutState.hoverPopupContainer, {
            sensesKey: 'senses_hover',
            showFilteredNote: true,
            showOtherDefsDropdown: false
          });
        }
      } else if (isMultiFill) {
        // Multi-fill but no specific fill targeted (cursor on gap) � show all
        renderDictFillPopups(renderableFill, posData, hoverLayoutState.hoverPopupContainer, {
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false
        });
      } else {
        // Single fill or no fill � render via shared template
        var singleEntry = renderableFill.length === 1 ? renderableFill[0] : null;
        var senseEntry =
          singleEntry &&
          !isUnknownEntry(singleEntry) &&
          Array.isArray(singleEntry.senses) &&
          singleEntry.senses.length
            ? singleEntry
            : res;
        var senseHead = getRenderableFillLabel(singleEntry, head) || head;
        var block = renderDictTemplate(senseEntry, senseHead, {
          showHead: false,
          showRomanUnknown: true,
          showSensesKnown: true,
          sensesKey: 'senses_hover',
          showFilteredNote: true,
          showOtherDefsDropdown: false,
          _buildEntryMetaForRow: buildPopupEntryMetaHtmlForEntry,
          forceSenseHead: true
        });
        dictHtml += block.html;
      }
    }
  }
  // Pronunciation stays in the dedicated G2P popup only
  segmentRenderingState.currentPopupHead = head;
  if (hoverLayoutState.notePopup) {
    hoverLayoutState.notePopup.textContent = '';
    hoverLayoutState.notePopup.style.display = 'none';
  }
  if (hoverLayoutState.udPopup) {
    if (dependencyPopupState.displaySettings.udPopup) {
      var udHtml = buildUdPopupHtml(idx);
      if (udHtml) {
        hoverLayoutState.udPopup.innerHTML = udHtml;
        hoverLayoutState.udPopup.style.display = 'block';
      } else {
        hoverLayoutState.udPopup.style.display = 'none';
        hoverLayoutState.udPopup.innerHTML = '';
      }
    } else {
      hoverLayoutState.udPopup.style.display = 'none';
      hoverLayoutState.udPopup.innerHTML = '';
    }
  }
  if (allowDictPopup && String(dictHtml || '').trim()) {
    hoverLayoutState.hoverPopup.innerHTML = dictHtml;
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, dictHtml);
    hoverLayoutState.hoverPopup.style.display = 'block';
  } else {
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, '');
    hoverLayoutState.hoverPopup.style.display = 'none';
  }
  var hasDictFillPopups =
    allowDictPopup && !!hoverLayoutState.hoverPopupContainer.querySelector('.dict-fill-popup');
  // Also clear the separate subsegment container (not used for dict_fill anymore)
  if (hoverLayoutState.subsegmentPopupsContainer) {
    hoverLayoutState.subsegmentPopupsContainer.innerHTML = '';
    hoverLayoutState.subsegmentPopupsContainer.style.display = 'none';
  }
  // Show container if any popup is enabled
  var anyPopupVisible =
    (dependencyPopupState.displaySettings.pronunciation &&
      hoverLayoutState.g2pPopup &&
      hoverLayoutState.g2pPopup.style.display !== 'none') ||
    (dependencyPopupState.displaySettings.udPopup &&
      hoverLayoutState.udPopup &&
      hoverLayoutState.udPopup.style.display !== 'none') ||
    (allowDictPopup && hoverLayoutState.hoverPopup && hoverLayoutState.hoverPopup.style.display !== 'none') ||
    (allowDictPopup && hasDictFillPopups) ||
    (allowGrammarPopup &&
      hoverLayoutState.grammarPopup &&
      hoverLayoutState.grammarPopup.style.display !== 'none') ||
    dependencyPopupState.displaySettings.comments;
  hoverLayoutState.hoverPopupContainer.style.display = anyPopupVisible ? 'flex' : 'none';
  if (anyPopupVisible) {
    applyDictionaryHoverPopupClamp();
  } else {
    clearDictionaryHoverPopupClamp();
  }
  if (dependencyPopupState.displaySettings.comments) {
    updateNotePopupForHead(head);
  }
}
export function positionPopup(clientX, clientY) {
  if (hoverLayoutState.hoverPopupContainer.style.display !== 'flex') return;
  var vw = window.innerWidth,
    vh = window.innerHeight;

  // Refresh container rect to account for scrolling/layout changes
  // This is critical: udContainerRect is used for coordinate conversions,
  // and if stale, all positions will be offset by the scroll amount
  if (hoverLayoutState.renderedText) {
    tokenFragmentsState.udContainerRect = hoverLayoutState.renderedText.getBoundingClientRect();
  }
  hoverLayoutState.hoverPopupContainer.style.left = '0px';
  hoverLayoutState.hoverPopupContainer.style.top = '0px';
  invalidateUiRectFor(hoverLayoutState.hoverPopupContainer);

  // Measure each visible popup individually (store relative positions) - DIRECT DOM
  // Dynamically gather all direct children so dict-fill popups are included
  var popups = [];
  var containerChildren = hoverLayoutState.hoverPopupContainer.children;
  for (var ci = 0; ci < containerChildren.length; ci++) {
    popups.push(containerChildren[ci]);
  }
  var popupRects = []; // Array of {left, top, width, height} relative to container origin
  var minLeft = Infinity,
    minTop = Infinity,
    maxRight = 0,
    maxBottom = 0;
  var hasVisiblePopup = false;
  for (var pi = 0; pi < popups.length; pi++) {
    var p = popups[pi];
    if (!p || p.style.display === 'none') continue;
    var pr = p.getBoundingClientRect();
    if (!pr || pr.width <= 0 || pr.height <= 0) continue;
    hasVisiblePopup = true;
    popupRects.push({
      left: pr.left,
      top: pr.top,
      width: pr.width,
      height: pr.height,
      right: pr.right,
      bottom: pr.bottom
    });
    if (pr.left < minLeft) minLeft = pr.left;
    if (pr.top < minTop) minTop = pr.top;
    if (pr.right > maxRight) maxRight = pr.right;
    if (pr.bottom > maxBottom) maxBottom = pr.bottom;
  }
  // If no visible popups at all, nothing to position.
  if (!hasVisiblePopup) return;
  var w = 0,
    h = 0;
  if (hasVisiblePopup) {
    w = maxRight - minLeft;
    h = maxBottom - minTop;
    // Convert popup rects to be relative to the combined bounding box origin
    for (var pri = 0; pri < popupRects.length; pri++) {
      popupRects[pri].left -= minLeft;
      popupRects[pri].top -= minTop;
    }
  }
  function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
  }
  function rectsOverlap(a, b) {
    return !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
  }

  // no screen-bounds gating

  // Get hovered token rect - DIRECT DOM measurement for accuracy
  var anchorRect = null;
  try {
    var anchorEl = segmentRenderingState.currentPopupAnchorEl || null;
    if (
      !anchorEl &&
      segmentRenderingState.currentSpan &&
      hoverLayoutState.renderedText &&
      hoverLayoutState.renderedText.contains(segmentRenderingState.currentSpan)
    ) {
      anchorEl = segmentRenderingState.currentSpan.classList.contains('reader-subtoken')
        ? segmentRenderingState.currentSpan.closest('.reader-token')
        : segmentRenderingState.currentSpan;
    }
    if (anchorEl && anchorEl.getBoundingClientRect) {
      var r = anchorEl.getBoundingClientRect();
      if (r && r.width > 0 && r.height > 0) {
        anchorRect = {
          left: r.left,
          top: r.top,
          right: r.right,
          bottom: r.bottom
        };
      }
    }
  } catch (e) {}

  // === COLLECT FORBIDDEN REGIONS (DOM-based for reliability) ===
  var forbiddenRegions = [];

  // 1. UD lines - query DOM directly for all visible .ud-dep-line paths
  var udLinePoints = [];
  var udLineThickness = 2;
  var udPaths = document.querySelectorAll('.ud-dep-line');
  for (var ei = 0; ei < udPaths.length; ei++) {
    var el = udPaths[ei];
    var lineKey = buildUdEdgeDrawKey(
      el.getAttribute('data-from-idx'),
      el.getAttribute('data-to-idx'),
      el.getAttribute('data-from-part'),
      el.getAttribute('data-to-part')
    );
    try {
      var pathLen = el.getTotalLength();
      var sampleStep = 50;
      for (var t = 0; t <= pathLen; t += sampleStep) {
        var pt = el.getPointAtLength(t);
        var svgEl = el.ownerSVGElement;
        if (svgEl && svgEl.createSVGPoint) {
          var svgPoint = svgEl.createSVGPoint();
          svgPoint.x = pt.x;
          svgPoint.y = pt.y;
          var ctm = el.getScreenCTM();
          if (ctm) {
            var screenPoint = svgPoint.matrixTransform(ctm);
            udLinePoints.push({
              x: screenPoint.x,
              y: screenPoint.y,
              line: lineKey
            });
          }
        }
      }
    } catch (e) {}
  }

  // 2. Highlighted POS chunk tokens - query DOM for .chunk-active elements
  var chunkActiveEls = document.querySelectorAll('.chunk-active');
  var pad = 4;
  for (var hti = 0; hti < chunkActiveEls.length; hti++) {
    var r = chunkActiveEls[hti].getBoundingClientRect();
    if (r && r.width > 0 && r.height > 0) {
      forbiddenRegions.push({
        left: r.left - pad,
        top: r.top - pad,
        right: r.right + pad,
        bottom: r.bottom + pad
      });
    }
  }

  // 3. NER label chips - query DOM for .ner-label elements
  var nerLabels = document.querySelectorAll('.ner-label');
  var chipPad = 2;
  for (var ci = 0; ci < nerLabels.length; ci++) {
    var cr = nerLabels[ci].getBoundingClientRect();
    if (cr && cr.width > 0 && cr.height > 0) {
      forbiddenRegions.push({
        left: cr.left - chipPad,
        top: cr.top - chipPad,
        right: cr.right + chipPad,
        bottom: cr.bottom + chipPad
      });
    }
  }

  // 4. Hovered token + radius - HARD GUARD: popup can NEVER cover this area
  var tokenForbidden = null;
  if (anchorRect) {
    var rad = 10;
    tokenForbidden = {
      left: anchorRect.left - rad,
      top: anchorRect.top - rad,
      right: anchorRect.right + rad,
      bottom: anchorRect.bottom + rad
    };
  }
  if (mwtContextState._mwtSpawnBox && mwtContextState._mwtSpawnBox.style.display !== 'none') {
    var spawnRect = mwtContextState._mwtSpawnBox.getBoundingClientRect();
    if (spawnRect && spawnRect.width > 0 && spawnRect.height > 0) {
      forbiddenRegions.push({
        left: spawnRect.left - 4,
        top: spawnRect.top - 4,
        right: spawnRect.right + 4,
        bottom: spawnRect.bottom + 4
      });
    }
  }

  // === HELPER: Check if any individual popup rect overlaps a region ===
  function anyPopupOverlapsRect(x, y, region) {
    if (!hasVisiblePopup) return false;
    for (var pi = 0; pi < popupRects.length; pi++) {
      var pr = popupRects[pi];
      var absRect = {
        left: x + pr.left,
        top: y + pr.top,
        right: x + pr.left + pr.width,
        bottom: y + pr.top + pr.height
      };
      if (rectsOverlap(absRect, region)) return true;
    }
    return false;
  }

  // === HELPER: Check if any popup rect overlaps a line point ===
  function anyPopupOverlapsLinePoint(x, y, pt) {
    if (!hasVisiblePopup) return false;
    for (var pi = 0; pi < popupRects.length; pi++) {
      var pr = popupRects[pi];
      var left = x + pr.left - udLineThickness;
      var right = x + pr.left + pr.width + udLineThickness;
      var top = y + pr.top - udLineThickness;
      var bottom = y + pr.top + pr.height + udLineThickness;
      if (pt.x >= left && pt.x <= right && pt.y >= top && pt.y <= bottom) return true;
    }
    return false;
  }

  // === HELPER: Check if any popup rect overflows viewport ===
  function anyPopupOverflowsViewport(x, y, margin) {
    if (!hasVisiblePopup) return false;
    for (var pi = 0; pi < popupRects.length; pi++) {
      var pr = popupRects[pi];
      if (x + pr.left < margin) return true;
      if (y + pr.top < margin) return true;
      if (x + pr.left + pr.width > vw - margin) return true;
      if (y + pr.top + pr.height > vh - margin) return true;
    }
    return false;
  }

  // === HELPER: Count how many things a position overlaps ===
  function countOverlaps(x, y) {
    var count = 0;

    // Count overlapping POS/NER regions (using individual popup rects)
    for (var i = 0; i < forbiddenRegions.length; i++) {
      if (anyPopupOverlapsRect(x, y, forbiddenRegions[i])) count++;
    }

    // Count overlapping UD line points (count per line)
    var hitLines = null;
    for (var i = 0; i < udLinePoints.length; i++) {
      var pt = udLinePoints[i];
      if (anyPopupOverlapsLinePoint(x, y, pt)) {
        if (!hitLines) hitLines = {};
        var key = pt.line || pt.x + ',' + pt.y;
        hitLines[key] = true;
      }
    }
    if (hitLines) count += Object.keys(hitLines).length;
    return count;
  }

  // === GENERATE GRID OF CANDIDATE POSITIONS ===
  var gridStep = 50;
  var margin = 4;

  // Token center for distance calculation
  var tokenCenterX = anchorRect ? (anchorRect.left + anchorRect.right) / 2 : clientX;
  var tokenCenterY = anchorRect ? (anchorRect.top + anchorRect.bottom) / 2 : clientY;

  // Two-pass selection:
  // Pass 1: Find closest non-overlapping position within viewport
  // Pass 2: If none found, find closest to token that doesn't overlap token, with least obstacle overlaps
  var bestX = null,
    bestY = null;
  var bestDistance = Infinity;
  var bestOverlaps = Infinity;
  var foundPerfect = false;

  // Iterate over grid positions
  if (hasVisiblePopup) {
    for (var gx = margin; gx + w <= vw - margin; gx += gridStep) {
      for (var gy = margin; gy + h <= vh - margin; gy += gridStep) {
        // Check if any popup overflows viewport
        if (anyPopupOverflowsViewport(gx, gy, margin)) continue;

        // HARD GUARD: Skip positions where any popup would cover hovered token + 10px buffer
        if (tokenForbidden && anyPopupOverlapsRect(gx, gy, tokenForbidden)) continue;
        var overlaps = countOverlaps(gx, gy);

        // Calculate distance from popup center to token center
        var popupCenterX = gx + w / 2;
        var popupCenterY = gy + h / 2;
        var dx = popupCenterX - tokenCenterX;
        var dy = popupCenterY - tokenCenterY;
        var distance = Math.sqrt(dx * dx + dy * dy);
        if (overlaps === 0) {
          // Pass 1: Perfect position (no overlaps) - pick closest
          if (!foundPerfect || distance < bestDistance) {
            foundPerfect = true;
            bestDistance = distance;
            bestX = gx;
            bestY = gy;
          }
        } else if (!foundPerfect) {
          // Pass 2: No perfect position yet - pick by (least overlaps, then closest distance)
          if (overlaps < bestOverlaps || (overlaps === bestOverlaps && distance < bestDistance)) {
            bestDistance = distance;
            bestOverlaps = overlaps;
            bestX = gx;
            bestY = gy;
          }
        }
      }
    }
  }
  if (bestX !== null && bestY !== null) {
    hoverLayoutState.hoverPopupContainer.style.left = bestX + 'px';
    hoverLayoutState.hoverPopupContainer.style.top = bestY + 'px';
  }
}
export function initializeDictionaryPopup() {
  dictionaryPopupState.lastHoveredElement = null; // Track the actual hovered element
  return true;
}
