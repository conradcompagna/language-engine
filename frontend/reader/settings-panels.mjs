import { _fireLlmDecompRequest } from './decomposition-requests.mjs';
import { rebuildConnectedIslandGroups } from './dependency-geometry.mjs';
import {
  clearBottomUpCascadeCache,
  clearBottomUpChunkCache,
  drawUdLinesForToken
} from './dependency-hover.mjs';
import { computeChunks, ensureLmWeightsInitialized } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import {
  closeInlineDepTreeTool,
  isInlineDepTreeOpen,
  openInlineDepTreeTool,
  refitInlineDepTreeSoon,
  restoreInlineDepTreeFabPosition,
  setInlineDepTreeFabPosition,
  startInlineDepTreeFabDrag,
  syncInlineDepTreeButtonState,
  toggleInlineDepTreeTool
} from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { debounce, hideSeparateGrammarPopup } from './document-shell.mjs';
import { documentState } from './document-state.state.mjs';
import { restorePanelDisplayState } from './entry-editing.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import {
  _fireLlmGlossRequest,
  applyChunkHighlight,
  clearChunkHighlight,
  saveDisplaySettings
} from './gloss-requests.mjs';
import { computeAndCacheRowBands, invalidateRowBandCache } from './hover-interaction.mjs';
import { clearDictionaryHoverPopupClamp } from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _resetSentenceTabletGlossOverrides } from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import {
  _fireOrthBreakdownRequest,
  _refreshLlmDecompUI,
  _refreshLlmGlossUI,
  _refreshOrthBreakdownUI,
  applyViewMode,
  closeGrammarOverlayPanel,
  getCurrentHoverSegIdx,
  initDepTreeView,
  openGrammarOverlayPanelUI,
  renderGrammarTypeCheckboxes,
  syncManualSentenceSegmentationControl
} from './orthography.mjs';
import { orthographyState } from './orthography.state.mjs';
import { escapeHtml } from './presentation.mjs';
import { renderSegments } from './segment-rendering.mjs';
import { settingsPanelsState } from './settings-panels.state.mjs';
import { lookupAndDisplay } from './side-panel.mjs';
import { tokenBannerMenuState } from './token-banner-menu.state.mjs';
import {
  hideNerHover,
  hideUdLines,
  invalidateUdRectCache,
  invalidateUiRectCache,
  renderNerHoverForToken
} from './token-fragments.mjs';
export function renderLmWeightsPanel() {
  if (!orthographyState.lmWeightsPanel) return;
  ensureLmWeightsInitialized();
  orthographyState.lmWeightsPanel.innerHTML = '';
  var header = document.createElement('h4');
  header.textContent = 'LM weights';
  orthographyState.lmWeightsPanel.appendChild(header);
  var list = document.createElement('div');
  list.className = 'toggle-grid';
  orthographyState.lmWeightsPanel.appendChild(list);
  var updateWeights = debounce(function () {
    saveDisplaySettings();
    if (hoverLayoutState.sourceText && hoverLayoutState.sourceText.value) {
      triggerUpdate();
    }
  }, 300);
  var inputsByKey = {};
  dependencyPopupState.LM_WEIGHT_FIELDS.forEach(function (field) {
    var row = document.createElement('label');
    row.className = 'toggle-label';
    row.style.justifyContent = 'space-between';
    row.style.width = '100%';
    var name = document.createElement('span');
    name.textContent = field.label;
    var input = document.createElement('input');
    input.type = 'number';
    input.step = field.step || '0.1';
    input.value = String(dependencyPopupState.displaySettings.lmWeights[field.key]);
    input.style.width = '90px';
    input.dataset.lmKey = field.key;
    inputsByKey[field.key] = input;
    input.addEventListener('input', function () {
      var nextVal = parseFloat(this.value);
      if (!isFinite(nextVal)) return;
      dependencyPopupState.displaySettings.lmWeights[field.key] = nextVal;
      updateWeights();
    });
    input.addEventListener('change', function () {
      var nextVal = parseFloat(this.value);
      if (!isFinite(nextVal)) {
        this.value = String(dependencyPopupState.displaySettings.lmWeights[field.key]);
        return;
      }
      dependencyPopupState.displaySettings.lmWeights[field.key] = nextVal;
      updateWeights();
    });
    row.appendChild(name);
    row.appendChild(input);
    list.appendChild(row);
  });
  var resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.className = 'dropdown-button';
  resetBtn.textContent = 'Reset to defaults';
  resetBtn.addEventListener('click', function () {
    dependencyPopupState.displaySettings.lmWeights = Object.assign(
      {},
      dependencyPopupState.LM_WEIGHT_DEFAULTS
    );
    Object.keys(inputsByKey).forEach(function (key) {
      if (inputsByKey[key]) {
        inputsByKey[key].value = String(dependencyPopupState.displaySettings.lmWeights[key]);
      }
    });
    saveDisplaySettings();
    if (hoverLayoutState.sourceText && hoverLayoutState.sourceText.value) {
      triggerUpdate();
    }
  });
  orthographyState.lmWeightsPanel.appendChild(resetBtn);
}
export function openLmWeightsPanelUI() {
  if (!orthographyState.displayDropdown) return;
  if (!orthographyState.lmWeightsPanel) {
    orthographyState.lmWeightsPanel = document.createElement('div');
    orthographyState.lmWeightsPanel.id = 'lmWeightsPanel';
    orthographyState.lmWeightsPanel.className = 'grammar-overlay-panel';
    orthographyState.displayDropdown.appendChild(orthographyState.lmWeightsPanel);
  }
  closeGrammarOverlayPanel();
  renderLmWeightsPanel();
  orthographyState.lmWeightsPanel.style.display = 'block';
}
export function closeLmWeightsPanel() {
  if (orthographyState.lmWeightsPanel) orthographyState.lmWeightsPanel.style.display = 'none';
}
export // Legacy closeAllMenus - now handled by left sidebar
function closeAllMenus(except) {
  closeGrammarOverlayPanel();
  closeLmWeightsPanel();
}
// Invalidate row band cache on resize/scroll (positions change)
export // Panel toggle
function togglePanel(open) {
  lookupProgressState.panelOpen = open !== undefined ? open : !lookupProgressState.panelOpen;
  hoverLayoutState.sidePanel.classList.toggle('open', lookupProgressState.panelOpen);
  hoverLayoutState.panelToggle.classList.toggle('panel-open', lookupProgressState.panelOpen);
  hoverLayoutState.mainContainer.classList.toggle('panel-open', lookupProgressState.panelOpen);
}
export function _applyFuzzyToggleStyle() {
  if (!settingsPanelsState.fuzzyToggleBtn) return;
  settingsPanelsState.fuzzyToggleBtn.setAttribute(
    'aria-pressed',
    settingsPanelsState._fuzzyPanelOn ? 'true' : 'false'
  );
  settingsPanelsState.fuzzyToggleBtn.style.opacity = settingsPanelsState._fuzzyPanelOn ? '1' : '0.45';
}
export function doSearch() {
  var q = (hoverLayoutState.dictSearch.value || '').trim();
  if (!q) return;
  hoverLayoutState.tokenMapData = null;
  hoverLayoutState.tokenMapVisible = false;
  tokenBannerMenuState._bannerActiveFillKey = null;
  var _bEl = document.getElementById('token-banner');
  if (_bEl) _bEl.style.display = 'none';
  var _sEl = document.getElementById('synth-entry-bar');
  if (_sEl) _sEl.style.display = 'none';
  togglePanel(true);
  lookupAndDisplay(q, {
    raw: true,
    exact: true,
    allowFuzzy: true,
    noIsland: true,
    forceWholeToken: true,
    manualPanelSearch: true,
    fuzzyPanel: settingsPanelsState._fuzzyPanelOn
  });
}
export function closeEntryFormPanel(preferredHeadword, returnState) {
  if (restorePanelDisplayState(returnState)) {
    return;
  }
  var fallbackHead = String(preferredHeadword || '').trim();
  if (!fallbackHead && hoverLayoutState.tokenMapData) {
    var panelEntryHead = '';
    if (hoverLayoutState.tokenMapData.panelEntry && hoverLayoutState.tokenMapData.panelEntry.head) {
      panelEntryHead = String(hoverLayoutState.tokenMapData.panelEntry.head || '').trim();
    }
    fallbackHead =
      panelEntryHead ||
      String(hoverLayoutState.tokenMapData.surface || hoverLayoutState.tokenMapData.lemma || '').trim();
  }
  if (fallbackHead) {
    lookupAndDisplay(fallbackHead, {
      raw: true,
      exact: true,
      allowFuzzy: true,
      noIsland: true,
      forceWholeToken: true
    });
    return;
  }
  hoverLayoutState.panelContent.innerHTML =
    '<div style="color:#888;text-align:center;margin-top:20px;">No entry selected.</div>';
}
// ---------------------------------------------------------------------------
// Gemini entry form � for editing Gemini-generated entries.
// Headword is auto-set (disabled). Shows pronunciation, pos, glosses,
// commentary, and lemma fields.  No forms section.
// opts: { headword, romanization, pos, glosses:[], commentary, lemma, lang, source, editMode }
// ---------------------------------------------------------------------------
export function buildEntryDeleteActionHtml(editMode) {
  if (!editMode) return '';
  return '    <button type="button" id="ef-delete-btn" class="gemini-edit-delete-btn">Delete</button>';
}
export function buildEntryDeletePanelHtml(editMode) {
  return '';
}
export function buildGeminiSynthPosSelectHtml(currentPos) {
  var selectedPos = String(currentPos || '')
    .trim()
    .toLowerCase();
  var html = '<select id="ef-pos" class="userdict-input" required>';
  for (var i = 0; i < settingsPanelsState.GEMINI_SYNTH_POS_OPTIONS.length; i++) {
    var posValue = settingsPanelsState.GEMINI_SYNTH_POS_OPTIONS[i];
    html +=
      '<option value="' +
      escapeHtml(posValue) +
      '"' +
      (selectedPos === posValue ? ' selected' : '') +
      '>' +
      escapeHtml(posValue) +
      '</option>';
  }
  html += '</select>';
  return html;
}

// DEBUG MAP: synthetic/gemini edit form.
// Save-button state here is intended to be a single stable state machine:
// baseline snapshot -> current serialized form state -> canSave -> disabled flag.
export function initializeSettingsPanels() {
  renderGrammarTypeCheckboxes();
  initDepTreeView();
  applyViewMode();
  settingsPanelsState.resizeDebounceTimer = null;
  window.addEventListener('resize', function () {
    invalidateUdRectCache();
    invalidateUiRectCache();
    if (settingsPanelsState.resizeDebounceTimer) clearTimeout(settingsPanelsState.resizeDebounceTimer);
    settingsPanelsState.resizeDebounceTimer = setTimeout(function () {
      invalidateRowBandCache();
      computeAndCacheRowBands();
    }, 100);
  });
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.addEventListener('scroll', function () {
      invalidateRowBandCache();
      invalidateUdRectCache();
      invalidateUiRectCache();
    });
  }
  // Grammar overlay master toggle (select/deselect all)
  if (orthographyState.toggleGrammarOverlayAll) {
    orthographyState.toggleGrammarOverlayAll.addEventListener('change', function () {
      var val = this.checked;
      dependencyPopupState.GRAMMAR_TYPES.forEach(function (t) {
        dependencyPopupState.displaySettings.grammarTypes[t] = val;
      });
      saveDisplaySettings();
      renderGrammarTypeCheckboxes();
      if (hoverLayoutState.latestData) {
        renderSegments(hoverLayoutState.latestData, hoverLayoutState.sourceText.value);
      }
    });
  }
  // Open grammar overlay panel
  if (orthographyState.openGrammarOverlayPanel) {
    orthographyState.openGrammarOverlayPanel.addEventListener('click', function (e) {
      e.stopPropagation();
      openGrammarOverlayPanelUI();
    });
  }
  if (orthographyState.openLmWeightsPanel) {
    orthographyState.openLmWeightsPanel.addEventListener('click', function (e) {
      e.stopPropagation();
      openLmWeightsPanelUI();
    });
  }
  if (orthographyState.toggleDepTreeView) {
    orthographyState.toggleDepTreeView.addEventListener('change', function () {
      dependencyPopupState.displaySettings.depTreeView = this.checked;
      saveDisplaySettings();
      applyViewMode();
    });
  }
  // OBSOLETE: greedy/split post-passes replaced by DP resegmentation
  // if (toggleMergeGreedy) {
  //   toggleMergeGreedy.addEventListener('change', function() {
  //     displaySettings.mergeGreedy = this.checked;
  //     saveDisplaySettings();
  //     if (sourceText && sourceText.value) {
  //       triggerUpdate();
  //     }
  //   });
  // }
  // if (toggleSplitDictFill) {
  //   toggleSplitDictFill.addEventListener('change', function() {
  //     displaySettings.splitDictFill = this.checked;
  //     saveDisplaySettings();
  //     if (sourceText && sourceText.value) {
  //       triggerUpdate();
  //     }
  //   });
  // }
  // Event listeners for posOverride, stanzaNer, collapseNerUd, dpResegment removed
  // These settings are now hardcoded to true
  if (orthographyState.toggleUdOverlay) {
    orthographyState.toggleUdOverlay.addEventListener('change', function () {
      dependencyPopupState.displaySettings.udOverlay = this.checked;
      // DEPLOYMENT: Auto-enable bottom-up chunk when UD arrows or chunks are on
      if (
        dependencyPopupState.displaySettings.udOverlay ||
        dependencyPopupState.displaySettings.chunkHighlight
      ) {
        dependencyPopupState.displaySettings.bottomUpChunk = true;
        if (orthographyState.toggleBottomUpChunk) orthographyState.toggleBottomUpChunk.checked = true;
      }
      saveDisplaySettings();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        // Re-apply UD lines
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        } else {
          hideUdLines();
        }
        // Also re-apply chunk highlighting (keep in sync)
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
      }
    });
  }
  if (orthographyState.toggleChunkHighlight) {
    orthographyState.toggleChunkHighlight.addEventListener('change', function () {
      dependencyPopupState.displaySettings.chunkHighlight = this.checked;
      dependencyPopupState.displaySettings.linearClauseSplit = this.checked; // UD chunks now controls linear clause split
      // DEPLOYMENT: Auto-enable bottom-up chunk when UD arrows or chunks are on
      if (
        dependencyPopupState.displaySettings.udOverlay ||
        dependencyPopupState.displaySettings.chunkHighlight
      ) {
        dependencyPopupState.displaySettings.bottomUpChunk = true;
        if (orthographyState.toggleBottomUpChunk) orthographyState.toggleBottomUpChunk.checked = true;
      }
      saveDisplaySettings();
      // Recompute chunks (use max depth 100 when on, 0 when off)
      if (dependencyState.latestUdOverlay) {
        dependencyPopupState.latestChunks = computeChunks(
          dependencyState.latestUdOverlay,
          dependencyPopupState.displaySettings.chunkHighlight ? 100 : 0,
          dependencyPopupState.displaySettings.linearClauseSplit ||
            dependencyPopupState.displaySettings.udOverlay,
          dependencyPopupState.displaySettings.branchDepthMin,
          dependencyPopupState.displaySettings.clauseDepthDrop
        );
      }
      // Sync with tree view
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setChunkHighlight === 'function'
      ) {
        lookupProgressState.depTreeController.setChunkHighlight(
          dependencyPopupState.displaySettings.chunkHighlight
        );
      }
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setLinearClauseSplit === 'function'
      ) {
        lookupProgressState.depTreeController.setLinearClauseSplit(
          dependencyPopupState.displaySettings.linearClauseSplit
        );
      }
      // Re-apply all hover highlights if applicable
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        // Re-apply UD lines (keep in sync)
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        // Re-apply chunk highlighting
        applyChunkHighlight(segIdx);
      } else {
        // Clear highlighting if no hover
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.toggleNerOverlay) {
    orthographyState.toggleNerOverlay.addEventListener('change', function () {
      dependencyPopupState.displaySettings.nerOverlay = this.checked;
      saveDisplaySettings();
      var segIdx = getCurrentHoverSegIdx();
      if (dependencyPopupState.displaySettings.nerOverlay && segIdx >= 0) {
        renderNerHoverForToken(segIdx);
      } else {
        hideNerHover();
      }
    });
  }
  if (orthographyState.toggleGeminiNer) {
    orthographyState.toggleGeminiNer.addEventListener('change', function () {
      dependencyPopupState.displaySettings.geminiNer = this.checked;
      saveDisplaySettings();
      triggerUpdate();
    });
  }
  if (orthographyState.toggleIslandDepTree) {
    orthographyState.toggleIslandDepTree.addEventListener('change', function () {
      dependencyPopupState.displaySettings.islandDepTree = this.checked;
      saveDisplaySettings();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.toggleConnectedIslands) {
    orthographyState.toggleConnectedIslands.addEventListener('change', function () {
      dependencyPopupState.displaySettings.connectedIslands = this.checked;
      saveDisplaySettings();
      rebuildConnectedIslandGroups();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.toggleConnectedIslandsAclGate) {
    orthographyState.toggleConnectedIslandsAclGate.addEventListener('change', function () {
      dependencyPopupState.displaySettings.connectedIslandsAclGate = this.checked;
      saveDisplaySettings();
      rebuildConnectedIslandGroups();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.toggleContextWindow) {
    orthographyState.toggleContextWindow.addEventListener('change', function () {
      dependencyPopupState.displaySettings.contextWindow = this.checked;
      saveDisplaySettings();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.contextWindowSizeInput) {
    orthographyState.contextWindowSizeInput.addEventListener('change', function () {
      var val = parseInt(this.value, 10);
      if (isNaN(val)) val = 10;
      if (val < 1) val = 1;
      if (val > 50) val = 50;
      this.value = val;
      dependencyPopupState.displaySettings.contextWindowSize = val;
      saveDisplaySettings();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0 && dependencyPopupState.displaySettings.contextWindow) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      }
    });
  }
  if (orthographyState.toggleBottomUpChunk) {
    orthographyState.toggleBottomUpChunk.addEventListener('change', function () {
      dependencyPopupState.displaySettings.bottomUpChunk = this.checked;
      saveDisplaySettings();
      clearBottomUpChunkCache();
      clearBottomUpCascadeCache();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.toggleBottomUpCascade) {
    orthographyState.toggleBottomUpCascade.addEventListener('change', function () {
      dependencyPopupState.displaySettings.bottomUpCascade = this.checked;
      saveDisplaySettings();
      clearBottomUpChunkCache();
      clearBottomUpCascadeCache();
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      } else {
        hideUdLines();
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.bottomUpChunkThresholdInput) {
    orthographyState.bottomUpChunkThresholdInput.addEventListener('change', function () {
      var val = parseInt(this.value, 10);
      if (isNaN(val)) val = 5;
      if (val < 1) val = 1;
      if (val > 10) val = 10;
      this.value = val;
      dependencyPopupState.displaySettings.bottomUpChunkThreshold = val;
      saveDisplaySettings();
      // Sync with dep tree view
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setBottomUpChunkThreshold === 'function'
      ) {
        lookupProgressState.depTreeController.setBottomUpChunkThreshold(val);
      }
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0 && dependencyPopupState.displaySettings.bottomUpChunk) {
        clearBottomUpChunkCache();
        clearBottomUpCascadeCache();
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      }
    });
  }
  settingsPanelsState.resetThresholdBtn = document.getElementById('resetThresholdBtn');
  if (settingsPanelsState.resetThresholdBtn && orthographyState.bottomUpChunkThresholdInput) {
    settingsPanelsState.resetThresholdBtn.addEventListener('click', function () {
      var defaultVal = 5;
      orthographyState.bottomUpChunkThresholdInput.value = defaultVal;
      dependencyPopupState.displaySettings.bottomUpChunkThreshold = defaultVal;
      saveDisplaySettings();
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setBottomUpChunkThreshold === 'function'
      ) {
        lookupProgressState.depTreeController.setBottomUpChunkThreshold(defaultVal);
      }
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0 && dependencyPopupState.displaySettings.bottomUpChunk) {
        clearBottomUpChunkCache();
        clearBottomUpCascadeCache();
        if (dependencyPopupState.displaySettings.udOverlay) {
          drawUdLinesForToken(segIdx);
        }
        applyChunkHighlight(segIdx);
      }
    });
  }
  if (orthographyState.branchDepthMinInput) {
    orthographyState.branchDepthMinInput.addEventListener('change', function () {
      var val = parseInt(this.value, 10);
      if (isNaN(val)) val = 1;
      if (val < 1) val = 1;
      if (val > 10) val = 10;
      this.value = val;
      dependencyPopupState.displaySettings.branchDepthMin = val;
      saveDisplaySettings();
      if (dependencyState.latestUdOverlay) {
        dependencyPopupState.latestChunks = computeChunks(
          dependencyState.latestUdOverlay,
          dependencyPopupState.displaySettings.chunkHighlight ? 100 : 0,
          dependencyPopupState.displaySettings.linearClauseSplit ||
            dependencyPopupState.displaySettings.udOverlay,
          dependencyPopupState.displaySettings.branchDepthMin,
          dependencyPopupState.displaySettings.clauseDepthDrop
        );
      }
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setBranchDepthMin === 'function'
      ) {
        lookupProgressState.depTreeController.setBranchDepthMin(
          dependencyPopupState.displaySettings.branchDepthMin
        );
      }
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        applyChunkHighlight(segIdx);
      } else {
        clearChunkHighlight();
      }
    });
  }
  if (orthographyState.clauseDepthDropInput) {
    orthographyState.clauseDepthDropInput.addEventListener('change', function () {
      var val = parseInt(this.value, 10);
      if (isNaN(val)) val = 3;
      if (val < 0) val = 0;
      if (val > 10) val = 10;
      this.value = val;
      dependencyPopupState.displaySettings.clauseDepthDrop = val;
      saveDisplaySettings();
      if (dependencyState.latestUdOverlay) {
        dependencyPopupState.latestChunks = computeChunks(
          dependencyState.latestUdOverlay,
          dependencyPopupState.displaySettings.chunkHighlight ? 100 : 0,
          dependencyPopupState.displaySettings.linearClauseSplit ||
            dependencyPopupState.displaySettings.udOverlay,
          dependencyPopupState.displaySettings.branchDepthMin,
          dependencyPopupState.displaySettings.clauseDepthDrop
        );
      }
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setClauseDepthDrop === 'function'
      ) {
        lookupProgressState.depTreeController.setClauseDepthDrop(
          dependencyPopupState.displaySettings.clauseDepthDrop
        );
      }
      var segIdx = getCurrentHoverSegIdx();
      if (segIdx >= 0) {
        applyChunkHighlight(segIdx);
      } else {
        clearChunkHighlight();
      }
    });
  }
  // Pronunciation popup toggle
  if (orthographyState.toggleStripPunctuation) {
    orthographyState.toggleStripPunctuation.addEventListener('change', function () {
      dependencyPopupState.displaySettings.stripPunctuation = this.checked;
      saveDisplaySettings();
    });
  }
  if (orthographyState.toggleManualSentenceSegmentation) {
    orthographyState.toggleManualSentenceSegmentation.addEventListener('change', function () {
      dependencyPopupState.displaySettings.manualSentenceSegmentation = this.checked;
      saveDisplaySettings();
      syncManualSentenceSegmentationControl();
    });
  }
  if (orthographyState.togglePronunciation) {
    orthographyState.togglePronunciation.addEventListener('change', function () {
      dependencyPopupState.displaySettings.pronunciation = this.checked;
      saveDisplaySettings();
      if (!this.checked && hoverLayoutState.g2pPopup) {
        hoverLayoutState.g2pPopup.style.display = 'none';
      }
    });
  }
  // LLM gloss toggle
  if (orthographyState.toggleLlmGloss) {
    orthographyState.toggleLlmGloss.addEventListener('change', function () {
      dependencyPopupState.displaySettings.llmGloss = this.checked;
      saveDisplaySettings();
      if (
        this.checked &&
        hoverLayoutState.latestData &&
        hoverLayoutState.latestData.segments &&
        hoverLayoutState.latestData.segments.length
      ) {
        _fireLlmGlossRequest(hoverLayoutState.latestData);
      }
      if (!this.checked) {
        hoverLayoutState.latestLlmGlossSeq++;
        hoverLayoutState.latestLlmGlosses = null;
        hoverLayoutState.latestLlmGlossUpgradeRequired = false;
        _resetSentenceTabletGlossOverrides();
        _refreshLlmGlossUI();
      }
    });
  }
  // LLM decomposition toggle
  if (orthographyState.toggleLlmDecomp) {
    orthographyState.toggleLlmDecomp.addEventListener('change', function () {
      dependencyPopupState.displaySettings.llmDecomp = this.checked;
      saveDisplaySettings();
      if (
        this.checked &&
        hoverLayoutState.latestData &&
        hoverLayoutState.latestData.segments &&
        hoverLayoutState.latestData.segments.length
      ) {
        _fireLlmDecompRequest(hoverLayoutState.latestData);
      }
      if (!this.checked) {
        hoverLayoutState.latestLlmDecompSeq++;
        hoverLayoutState.latestLlmDecomps = null;
        _refreshLlmDecompUI();
      }
    });
  }
  // Gemini ROM toggle (ORTH stays on because it is local/free)
  if (orthographyState.toggleOrthBreakdown) {
    orthographyState.toggleOrthBreakdown.addEventListener('change', function () {
      dependencyPopupState.displaySettings.orthBreakdown = this.checked;
      saveDisplaySettings();
      if (
        this.checked &&
        hoverLayoutState.latestData &&
        hoverLayoutState.latestData.segments &&
        hoverLayoutState.latestData.segments.length
      ) {
        _fireOrthBreakdownRequest(hoverLayoutState.latestData);
      }
      if (!this.checked) {
        hoverLayoutState.latestOrthBreakdowns = null;
        _refreshOrthBreakdownUI();
      }
    });
  }
  // Grammar popup toggle
  if (orthographyState.toggleGrammarPopup) {
    orthographyState.toggleGrammarPopup.addEventListener('change', function () {
      dependencyPopupState.displaySettings.grammarPopup = this.checked;
      saveDisplaySettings();
      if (!this.checked) hideSeparateGrammarPopup();
    });
  }
  // Dictionary popup toggle
  if (orthographyState.toggleDictPopup) {
    orthographyState.toggleDictPopup.addEventListener('change', function () {
      dependencyPopupState.displaySettings.dictPopup = this.checked;
      saveDisplaySettings();
      if (!this.checked && hoverLayoutState.hoverPopup) {
        hoverLayoutState.hoverPopup.style.display = 'none';
        clearDictionaryHoverPopupClamp();
      }
      // Sync with tree view
      if (
        lookupProgressState.depTreeController &&
        typeof lookupProgressState.depTreeController.setDictPopup === 'function'
      ) {
        lookupProgressState.depTreeController.setDictPopup(dependencyPopupState.displaySettings.dictPopup);
      }
    });
  }
  if (orthographyState.debugCaptureMode) {
    orthographyState.debugCaptureMode.addEventListener('change', function () {
      dependencyPopupState.displaySettings.debugCapture = this.value === 'on';
      saveDisplaySettings();
      if (hoverLayoutState.sourceText && hoverLayoutState.sourceText.value) {
        triggerUpdate();
      }
    });
  }
  if (orthographyState.openLegacyDepTreeToolBtn) {
    orthographyState.openLegacyDepTreeToolBtn.addEventListener('click', function () {
      openInlineDepTreeTool();
    });
  }
  if (orthographyState.depTreeInlineToggleBtn) {
    syncInlineDepTreeButtonState(isInlineDepTreeOpen());
    window.setTimeout(function () {
      restoreInlineDepTreeFabPosition();
      if (isInlineDepTreeOpen()) {
        refitInlineDepTreeSoon();
      }
    }, 0);
    orthographyState.depTreeInlineToggleBtn.addEventListener('mousedown', startInlineDepTreeFabDrag);
    orthographyState.depTreeInlineToggleBtn.addEventListener('click', function () {
      if (Date.now() < hoverLayoutState.depTreeInlineFabIgnoreClickUntil) return;
      toggleInlineDepTreeTool();
    });
  }
  window.addEventListener('resize', function () {
    if (orthographyState.depTreeInlineToggleBtn) {
      var rect = orthographyState.depTreeInlineToggleBtn.getBoundingClientRect();
      if (rect && rect.width && rect.height) {
        setInlineDepTreeFabPosition(rect.left, rect.top, true);
      }
    }
    if (isInlineDepTreeOpen()) {
      refitInlineDepTreeSoon();
    }
  });
  window.addEventListener('keydown', function (event) {
    if ((event.key || '') === 'Escape' && isInlineDepTreeOpen()) {
      closeInlineDepTreeTool();
    }
  });
  // SQLite mode is now always on � no toggle needed
  // PDF OCR cleanup toggle
  if (orthographyState.togglePdfOcrCleanup) {
    orthographyState.togglePdfOcrCleanup.checked = !!dependencyPopupState.displaySettings.pdfOcrCleanup;
    orthographyState.togglePdfOcrCleanup.addEventListener('change', function () {
      dependencyPopupState.displaySettings.pdfOcrCleanup = !!orthographyState.togglePdfOcrCleanup.checked;
      saveDisplaySettings();
      documentState.originalLayoutCache = {};
      documentState.pageLookupTextByIndex = {};
      documentState.lastLookupPageIndex = -1;
      documentState.pendingPdfLookupPageIndex = -1;
      hoverLayoutState.latestSeq += 1;
      triggerUpdate();
    });
  }
  if (orthographyState.fuzzyMaxEditDistanceInput) {
    orthographyState.fuzzyMaxEditDistanceInput.addEventListener('change', function () {
      var val = parseInt(this.value, 10);
      if (isNaN(val)) {
        this.value = dependencyPopupState.displaySettings.fuzzyMaxEditDistance;
        return;
      }
      if (val < 0) val = 0;
      if (val > 6) val = 6;
      dependencyPopupState.displaySettings.fuzzyMaxEditDistance = val;
      this.value = val;
      saveDisplaySettings();
    });
  }
  // Comments toggle
  if (orthographyState.toggleComments) {
    orthographyState.toggleComments.addEventListener('change', function () {
      dependencyPopupState.displaySettings.comments = this.checked;
      saveDisplaySettings();
      if (!this.checked && hoverLayoutState.notePopup) {
        hoverLayoutState.notePopup.style.display = 'none';
      }
    });
  }
  // Subsegment popups toggle
  if (orthographyState.toggleSubsegmentPopups) {
    orthographyState.toggleSubsegmentPopups.addEventListener('change', function () {
      dependencyPopupState.displaySettings.subsegmentPopups = this.checked;
      saveDisplaySettings();
    });
  }
  hoverLayoutState.panelToggle.addEventListener('click', function () {
    togglePanel();
  });
  // Search
  settingsPanelsState.fuzzyToggleBtn = document.getElementById('fuzzy-toggle');
  settingsPanelsState._fuzzyPanelOn = false;
  try {
    settingsPanelsState._fuzzyPanelOn =
      window.localStorage && localStorage.getItem('dict_search_fuzzy') === '1';
  } catch (_) {}
  _applyFuzzyToggleStyle();
  if (settingsPanelsState.fuzzyToggleBtn) {
    settingsPanelsState.fuzzyToggleBtn.addEventListener('click', function () {
      settingsPanelsState._fuzzyPanelOn = !settingsPanelsState._fuzzyPanelOn;
      try {
        if (window.localStorage)
          localStorage.setItem('dict_search_fuzzy', settingsPanelsState._fuzzyPanelOn ? '1' : '0');
      } catch (_) {}
      _applyFuzzyToggleStyle();
    });
  }
  hoverLayoutState.searchBtn.addEventListener('click', doSearch);
  hoverLayoutState.dictSearch.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') doSearch();
  });
  settingsPanelsState.GEMINI_SYNTH_POS_OPTIONS = [
    'noun',
    'verb',
    'adj',
    'adv',
    'pron',
    'det',
    'num',
    'conj',
    'prep',
    'postp',
    'particle',
    'intj',
    'suffix',
    'prefix',
    'name',
    'phrase'
  ];
  return true;
}
