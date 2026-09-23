import { normalizeSearchText, post } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import {
  goToOutlineItem,
  publishPdfDocumentNav,
  resetZoom,
  zoomIn,
  zoomOut
} from './document-navigation.mjs';
import { eventsState } from './events.state.mjs';
import {
  beginPanDrag,
  endPanDrag,
  isDragMode,
  movePanDrag,
  setInteractionMode,
  setSourceInspectorEnabled
} from './interaction.mjs';
import {
  applyNativePageFit,
  emitDimensions,
  emitHover,
  emitPageChange,
  emitScroll,
  emitState,
  updatePageBadge
} from './lifecycle.mjs';
import {
  beginThumbDrag,
  clearTrackHold,
  endThumbDrag,
  goToPage,
  moveThumbDrag,
  startSearchArrowHold,
  startTrackHold,
  stepPage,
  stopSearchArrowHold,
  updateNavigator
} from './pagination.mjs';
import {
  focusSearchResult,
  runExactSearch,
  stepSearchControls,
  stepSearchResult
} from './search-results.mjs';
import {
  clearPendingHighlightRestore,
  clearQueuedHighlightRefresh,
  renderSearchDropdown,
  resetExactSearchUI,
  runFind,
  setSearchDropdownVisible
} from './search-ui.mjs';
import { extractAndPostTextLayer } from './text-layer.mjs';
export function handleHover() {
  if (bridgeState.sourceInspectorActive) return;
  if (isDragMode()) return;
  if (bridgeState.hoverQueued) return;
  bridgeState.hoverQueued = true;
  requestAnimationFrame(function () {
    bridgeState.hoverQueued = false;
    emitHover(bridgeState.currentPageNumber);
  });
}
export function queueExactSearch() {
  if (bridgeState.searchDebounceTimer) {
    clearTimeout(bridgeState.searchDebounceTimer);
    bridgeState.searchDebounceTimer = 0;
  }
  var query = normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  if (!query) {
    bridgeState.lastFindQuery = '';
    resetExactSearchUI();
    if (bridgeState.searchCount) {
      bridgeState.searchCount.textContent = '0/0';
      bridgeState.searchCount.dataset.state = 'idle';
    }
    clearQueuedHighlightRefresh();
    clearPendingHighlightRestore();
    runFind('highlightallchange', false);
    return;
  }
  if (bridgeState.searchCount) {
    bridgeState.searchCount.textContent = '...';
    bridgeState.searchCount.dataset.state = 'pending';
  }
  bridgeState.searchDebounceTimer = setTimeout(function () {
    bridgeState.searchDebounceTimer = 0;
    runExactSearch(query);
  }, bridgeState.SEARCH_INPUT_DEBOUNCE_MS);
}
export function runExactSearchFromSubmit(_backward) {
  var query = normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  if (!query) {
    bridgeState.lastFindQuery = '';
    resetExactSearchUI();
    if (bridgeState.searchCount) {
      bridgeState.searchCount.textContent = '0/0';
      bridgeState.searchCount.dataset.state = 'idle';
    }
    clearQueuedHighlightRefresh();
    clearPendingHighlightRestore();
    runFind('highlightallchange', false);
    return;
  }
  if (bridgeState.searchDebounceTimer) {
    clearTimeout(bridgeState.searchDebounceTimer);
    bridgeState.searchDebounceTimer = 0;
  }
  // Enter should only refresh the result list; it should not auto-jump.
  runExactSearch(query);
}
export function initializeEvents() {
  bridgeState.pdfContainer.addEventListener('mousemove', handleHover, {
    passive: true
  });
  bridgeState.pdfContainer.addEventListener(
    'click',
    function () {
      if (bridgeState.sourceInspectorActive) return;
      if (isDragMode()) return;
      emitHover(bridgeState.currentPageNumber);
    },
    true
  );
  bridgeState.pdfContainer.addEventListener('pointerdown', function (ev) {
    beginPanDrag(ev);
  });
  bridgeState.pdfContainer.addEventListener('pointermove', function (ev) {
    movePanDrag(ev);
  });
  bridgeState.pdfContainer.addEventListener('pointerup', function (ev) {
    endPanDrag(ev);
  });
  bridgeState.pdfContainer.addEventListener('pointercancel', function (ev) {
    endPanDrag(ev);
  });
  bridgeState.pdfContainer.addEventListener(
    'wheel',
    function (ev) {
      if (bridgeState.sourceInspectorActive) return;
      if (isDragMode()) return;
      if (!bridgeState.totalPages) return;
      if (!ev || !isFinite(ev.deltaY) || ev.deltaY === 0) return;
      ev.preventDefault();
      clearTrackHold();
      if (bridgeState.wheelUnlockTimer) {
        clearTimeout(bridgeState.wheelUnlockTimer);
        bridgeState.wheelUnlockTimer = 0;
      }
      bridgeState.wheelUnlockTimer = setTimeout(function () {
        bridgeState.wheelStepLock = false;
        bridgeState.wheelUnlockTimer = 0;
      }, bridgeState.WHEEL_GESTURE_LOCK_MS);
      if (bridgeState.wheelStepLock) return;
      var now = Date.now();
      if (now - bridgeState.lastWheelStepAt < bridgeState.WHEEL_STEP_COOLDOWN_MS) return;
      bridgeState.lastWheelStepAt = now;
      bridgeState.wheelStepLock = true;
      stepPage(ev.deltaY > 0 ? 1 : -1);
    },
    {
      passive: false
    }
  );
  if (bridgeState.navPrev) {
    bridgeState.navPrev.addEventListener('click', function (ev) {
      ev.preventDefault();
      clearTrackHold();
      stepPage(-1);
    });
  }
  if (bridgeState.navNext) {
    bridgeState.navNext.addEventListener('click', function (ev) {
      ev.preventDefault();
      clearTrackHold();
      stepPage(1);
    });
  }
  if (bridgeState.navTrack) {
    bridgeState.navTrack.addEventListener('pointerdown', function (ev) {
      if (!bridgeState.totalPages) return;
      if (ev.button !== 0) return;
      ev.preventDefault();
      if (ev.target === bridgeState.navThumb) {
        beginThumbDrag(ev);
        return;
      }
      var thumbRect = bridgeState.navThumb.getBoundingClientRect();
      if (ev.clientY < thumbRect.top) {
        startTrackHold(-1);
      } else if (ev.clientY > thumbRect.bottom) {
        startTrackHold(1);
      } else {
        beginThumbDrag(ev);
      }
      if (typeof bridgeState.navTrack.setPointerCapture === 'function') {
        try {
          bridgeState.navTrack.setPointerCapture(ev.pointerId);
        } catch (e) {}
      }
    });
    bridgeState.navTrack.addEventListener('pointermove', function (ev) {
      if (!bridgeState.thumbDragging) return;
      moveThumbDrag(ev);
    });
    bridgeState.navTrack.addEventListener('pointerup', function (ev) {
      clearTrackHold();
      if (typeof bridgeState.navTrack.releasePointerCapture === 'function') {
        try {
          bridgeState.navTrack.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      endThumbDrag(ev);
    });
    bridgeState.navTrack.addEventListener('pointercancel', function (ev) {
      clearTrackHold();
      if (typeof bridgeState.navTrack.releasePointerCapture === 'function') {
        try {
          bridgeState.navTrack.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      endThumbDrag(ev);
    });
  }
  window.addEventListener('pointerup', function (ev) {
    clearTrackHold();
    stopSearchArrowHold(ev && ev.pointerId);
    endPanDrag(ev);
  });
  window.addEventListener('pointercancel', function (ev) {
    clearTrackHold();
    stopSearchArrowHold(ev && ev.pointerId);
    endPanDrag(ev);
  });
  window.addEventListener('pointerdown', function (ev) {
    if (!bridgeState.searchDropdown || bridgeState.searchDropdown.hidden) return;
    var t = ev && ev.target;
    if (bridgeState.searchBar && bridgeState.searchBar.contains(t)) return;
    if (bridgeState.searchDropdown && bridgeState.searchDropdown.contains(t)) return;
    setSearchDropdownVisible(false);
  });
  if (bridgeState.zoomOutBtn) {
    bridgeState.zoomOutBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      zoomOut();
    });
  }
  if (bridgeState.zoomInBtn) {
    bridgeState.zoomInBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      zoomIn();
    });
  }
  if (bridgeState.zoomResetBtn) {
    bridgeState.zoomResetBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      resetZoom();
    });
  }
  if (bridgeState.modeToggleBtn) {
    bridgeState.modeToggleBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      setInteractionMode(isDragMode() ? 'highlight' : 'drag');
    });
  }
  setInteractionMode('drag');
  if (bridgeState.searchDropdownList) {
    bridgeState.searchDropdownList.addEventListener('click', function (ev) {
      var target = ev.target;
      var row = target && target.closest ? target.closest('button[data-result-index]') : null;
      if (!row) return;
      ev.preventDefault();
      var idx = Number(row.getAttribute('data-result-index'));
      if (!isFinite(idx)) return;
      focusSearchResult(idx, true);
    });
  }
  if (bridgeState.searchInput) {
    bridgeState.searchInput.addEventListener('input', function () {
      queueExactSearch();
    });
    bridgeState.searchInput.addEventListener('focus', function () {
      var query = normalizeSearchText(bridgeState.searchInput.value || '');
      if (!query) return;
      if (bridgeState.searchResults.length) {
        renderSearchDropdown(query);
        return;
      }
      queueExactSearch();
    });
    bridgeState.searchInput.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        runExactSearchFromSubmit(!!ev.shiftKey);
        return;
      }
      if (ev.key === 'ArrowDown') {
        if (!bridgeState.searchResults.length) return;
        ev.preventDefault();
        stepSearchResult(1);
        return;
      }
      if (ev.key === 'ArrowUp') {
        if (!bridgeState.searchResults.length) return;
        ev.preventDefault();
        stepSearchResult(-1);
        return;
      }
      if (ev.key === 'Escape') {
        ev.preventDefault();
        setSearchDropdownVisible(false);
      }
    });
  }
  if (bridgeState.searchPrev) {
    bridgeState.searchPrev.addEventListener('pointerdown', function (ev) {
      if (!ev || ev.button !== 0) return;
      ev.preventDefault();
      clearTrackHold();
      startSearchArrowHold(-1, ev.pointerId);
      if (typeof bridgeState.searchPrev.setPointerCapture === 'function') {
        try {
          bridgeState.searchPrev.setPointerCapture(ev.pointerId);
        } catch (e) {}
      }
    });
    bridgeState.searchPrev.addEventListener('pointerup', function (ev) {
      if (typeof bridgeState.searchPrev.releasePointerCapture === 'function') {
        try {
          bridgeState.searchPrev.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      stopSearchArrowHold(ev && ev.pointerId);
    });
    bridgeState.searchPrev.addEventListener('pointercancel', function (ev) {
      if (typeof bridgeState.searchPrev.releasePointerCapture === 'function') {
        try {
          bridgeState.searchPrev.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      stopSearchArrowHold(ev && ev.pointerId);
    });
    bridgeState.searchPrev.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (bridgeState.suppressSearchArrowClick) {
        bridgeState.suppressSearchArrowClick = false;
        return;
      }
      clearTrackHold();
      stepSearchControls(-1);
    });
  }
  if (bridgeState.searchNext) {
    bridgeState.searchNext.addEventListener('pointerdown', function (ev) {
      if (!ev || ev.button !== 0) return;
      ev.preventDefault();
      clearTrackHold();
      startSearchArrowHold(1, ev.pointerId);
      if (typeof bridgeState.searchNext.setPointerCapture === 'function') {
        try {
          bridgeState.searchNext.setPointerCapture(ev.pointerId);
        } catch (e) {}
      }
    });
    bridgeState.searchNext.addEventListener('pointerup', function (ev) {
      if (typeof bridgeState.searchNext.releasePointerCapture === 'function') {
        try {
          bridgeState.searchNext.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      stopSearchArrowHold(ev && ev.pointerId);
    });
    bridgeState.searchNext.addEventListener('pointercancel', function (ev) {
      if (typeof bridgeState.searchNext.releasePointerCapture === 'function') {
        try {
          bridgeState.searchNext.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      stopSearchArrowHold(ev && ev.pointerId);
    });
    bridgeState.searchNext.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (bridgeState.suppressSearchArrowClick) {
        bridgeState.suppressSearchArrowClick = false;
        return;
      }
      clearTrackHold();
      stepSearchControls(1);
    });
  }
  if (bridgeState.searchClear) {
    bridgeState.searchClear.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (bridgeState.searchDebounceTimer) {
        clearTimeout(bridgeState.searchDebounceTimer);
        bridgeState.searchDebounceTimer = 0;
      }
      if (bridgeState.searchInput) bridgeState.searchInput.value = '';
      bridgeState.lastFindQuery = '';
      resetExactSearchUI();
      clearQueuedHighlightRefresh();
      clearPendingHighlightRestore();
      runFind('highlightallchange', false);
      if (bridgeState.searchCount) {
        bridgeState.searchCount.textContent = '0/0';
        bridgeState.searchCount.dataset.state = 'idle';
      }
    });
  }
  window.addEventListener('resize', function () {
    if (!bridgeState.manualZoomEnabled) applyNativePageFit();
    updateNavigator();
    emitDimensions(bridgeState.currentPageNumber);
  });
  window.addEventListener('message', function (event) {
    if (event.origin !== bridgeState.appOrigin) return;
    var data = event.data || {};
    if (!data || data.source !== 'reader-parent') return;
    if (String(data.sessionId || '') !== String(bridgeState.sessionId || '')) return;
    if (data.type === 'pdfjs-command') {
      var action = String(data.action || '');
      if (action === 'goToPage') {
        goToPage(Number(data.pageNumber) || 1, true);
        return;
      }
      if (action === 'goToOutlineItem') {
        goToOutlineItem(data.id);
        return;
      }
      if (action === 'nextPage') {
        stepPage(1);
        emitState();
        return;
      }
      if (action === 'prevPage') {
        stepPage(-1);
        emitState();
        return;
      }
      if (action === 'zoomIn') {
        zoomIn();
        return;
      }
      if (action === 'zoomOut') {
        zoomOut();
        return;
      }
      if (action === 'zoomReset') {
        resetZoom();
        return;
      }
      if (action === 'toggleMode') {
        setInteractionMode(isDragMode() ? 'highlight' : 'drag');
        return;
      }
      if (action === 'setMode') {
        setInteractionMode(String(data.mode || '') === 'drag' ? 'drag' : 'highlight');
        return;
      }
      if (action === 'setSourceInspector') {
        setSourceInspectorEnabled(!!data.enabled);
        return;
      }
      if (action === 'search') {
        if (bridgeState.searchInput) bridgeState.searchInput.value = String(data.query || '');
        queueExactSearch();
        emitState();
        return;
      }
      if (action === 'searchNext') {
        stepSearchControls(1);
        emitState();
        return;
      }
      if (action === 'searchPrev') {
        stepSearchControls(-1);
        emitState();
        return;
      }
      if (action === 'goToSearchResult') {
        focusSearchResult(Number(data.resultIndex) || 0, true, true);
        emitState();
        return;
      }
      if (action === 'searchClear') {
        if (bridgeState.searchDebounceTimer) {
          clearTimeout(bridgeState.searchDebounceTimer);
          bridgeState.searchDebounceTimer = 0;
        }
        if (bridgeState.searchInput) bridgeState.searchInput.value = '';
        bridgeState.lastFindQuery = '';
        resetExactSearchUI();
        clearQueuedHighlightRefresh();
        clearPendingHighlightRestore();
        runFind('highlightallchange', false);
        if (bridgeState.searchCount) {
          bridgeState.searchCount.textContent = '0/0';
          bridgeState.searchCount.dataset.state = 'idle';
        }
        emitState();
        return;
      }
      if (action === 'getState') {
        emitState();
        return;
      }
    }
    if (data.type === 'pdfjs-parent-resize') {
      if (!bridgeState.manualZoomEnabled) applyNativePageFit();
      updateNavigator();
      emitDimensions(bridgeState.currentPageNumber);
      return;
    }
    if (data.type === 'pdfjs-set-page-dims-cache') {
      var arr = Array.isArray(data.pageDims) ? data.pageDims : [];
      bridgeState.pageDimsCache = arr;
      return;
    }
    if (data.type === 'pdfjs-get-text-layer') {
      extractAndPostTextLayer(Number(data.pageNumber) || bridgeState.currentPageNumber || 1);
      return;
    }
  });
  eventsState.pdfSource = bridgeState.pdfUrl || '/api/serve_pdf/' + encodeURIComponent(bridgeState.cacheId);
  eventsState.loadingTask = window.pdfjsLib.getDocument(eventsState.pdfSource);
  eventsState.loadingTask.promise
    .then(function (doc) {
      bridgeState.pdfDoc = doc;
      bridgeState.totalPages = Number(doc.numPages) || 0;
      bridgeState.pageSearchTextCache = [];
      bridgeState.pageSearchLowerCache = [];
      bridgeState.searchResults = [];
      bridgeState.searchResultsTotal = 0;
      bridgeState.activeSearchResultIndex = -1;
      bridgeState.searchPageFirstGlobalIndex = [];
      bridgeState.searchPageFirstStoredIndex = [];
      bridgeState.searchPageMatchCount = [];
      bridgeState.searchRunToken++;
      if (bridgeState.searchDropdownMeta) bridgeState.searchDropdownMeta.textContent = 'Type to search';
      if (bridgeState.searchDropdownList) bridgeState.searchDropdownList.innerHTML = '';
      setSearchDropdownVisible(false);
      if (bridgeState.totalPages < 1) {
        post('pdfjs-error', {
          error: 'pdf_no_pages'
        });
        return;
      }
      bridgeState.pdfViewer.setDocument(bridgeState.pdfDoc);
      bridgeState.pdfLinkService.setDocument(bridgeState.pdfDoc, null);
      bridgeState.pdfFindController.setDocument(bridgeState.pdfDoc);
      publishPdfDocumentNav();
      bridgeState.currentPageNumber = 1;
      updatePageBadge(1);
      updateNavigator();
      applyNativePageFit();
      post('pdfjs-ready', {
        numPages: bridgeState.totalPages
      });
      emitPageChange(1);
      emitScroll(1);
      emitDimensions(1);
      emitState();
    })
    .catch(function (err) {
      post('pdfjs-error', {
        error: String((err && err.message) || err || 'pdf_load_failed')
      });
    });
  return true;
}
