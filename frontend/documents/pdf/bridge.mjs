import { bridgeState } from './bridge.state.mjs';
export function post(type, extra) {
  var payload = {
    source: 'pdfjs-iframe',
    type: type,
    sessionId: String(bridgeState.sessionId || '')
  };
  if (extra && typeof extra === 'object') {
    for (var k in extra) {
      if (Object.prototype.hasOwnProperty.call(extra, k)) {
        payload[k] = extra[k];
      }
    }
  }
  window.parent.postMessage(payload, bridgeState.appOrigin);
}
export function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
export function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
export function normalizeSearchText(str) {
  return String(str || '')
    .replace(/\s+/g, ' ')
    .trim();
}
export function initializeBridge() {
  bridgeState.params = new URLSearchParams(window.location.search || '');
  bridgeState.cacheId = bridgeState.params.get('cache_id') || '';
  bridgeState.pdfUrl = bridgeState.params.get('pdf_url') || '';
  bridgeState.sessionId = bridgeState.params.get('session_id') || '';
  bridgeState.parentChrome = bridgeState.params.get('chrome') === '0';
  bridgeState.appOrigin = window.location.origin;
  if (bridgeState.parentChrome && document.body) {
    document.body.classList.add('parent-chrome');
  }
  if (!bridgeState.cacheId && !bridgeState.pdfUrl) {
    post('pdfjs-error', {
      error: 'missing_pdf_source'
    });
    return false;
  }
  if (!window.pdfjsLib) {
    post('pdfjs-error', {
      error: 'pdfjs_missing'
    });
    return false;
  }
  if (!window.pdfjsViewer || !window.pdfjsViewer.PDFSinglePageViewer) {
    post('pdfjs-error', {
      error: 'pdfjs_viewer_missing'
    });
    return false;
  }
  window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.js';
  bridgeState.pdfContainer = document.getElementById('pdfContainer');
  bridgeState.pdfViewerEl = document.getElementById('pdfViewer');
  bridgeState.pageBadge = document.getElementById('pageCornerBadge');
  bridgeState.searchBar = document.getElementById('pdfSearchBar');
  bridgeState.modeToggleBtn = document.getElementById('pdfModeToggle');
  bridgeState.zoomOutBtn = document.getElementById('pdfZoomOut');
  bridgeState.zoomResetBtn = document.getElementById('pdfZoomReset');
  bridgeState.zoomInBtn = document.getElementById('pdfZoomIn');
  bridgeState.searchInput = document.getElementById('pdfSearchInput');
  bridgeState.searchPrev = document.getElementById('pdfSearchPrev');
  bridgeState.searchNext = document.getElementById('pdfSearchNext');
  bridgeState.searchCount = document.getElementById('pdfSearchCount');
  bridgeState.searchClear = document.getElementById('pdfSearchClear');
  bridgeState.searchDropdown = document.getElementById('pdfSearchDropdown');
  bridgeState.searchDropdownMeta = document.getElementById('pdfSearchDropdownMeta');
  bridgeState.searchDropdownList = document.getElementById('pdfSearchDropdownList');
  bridgeState.navPrev = document.getElementById('navPrev');
  bridgeState.navNext = document.getElementById('navNext');
  bridgeState.navTrack = document.getElementById('navTrack');
  bridgeState.navThumb = document.getElementById('navThumb');
  bridgeState.viewerEventBus = new window.pdfjsViewer.EventBus();
  bridgeState.pdfLinkService = new window.pdfjsViewer.PDFLinkService({
    eventBus: bridgeState.viewerEventBus
  });
  bridgeState.pdfFindController = new window.pdfjsViewer.PDFFindController({
    eventBus: bridgeState.viewerEventBus,
    linkService: bridgeState.pdfLinkService
  });
  bridgeState.nullL10n = window.pdfjsViewer.NullL10n || {
    get: function (_key, _args, fallback) {
      return Promise.resolve(fallback || '');
    },
    getLanguage: function () {
      return Promise.resolve('en-us');
    },
    getDirection: function () {
      return Promise.resolve('ltr');
    },
    translate: function () {
      return Promise.resolve();
    }
  };
  bridgeState.pdfViewer = new window.pdfjsViewer.PDFSinglePageViewer({
    container: bridgeState.pdfContainer,
    viewer: bridgeState.pdfViewerEl,
    eventBus: bridgeState.viewerEventBus,
    linkService: bridgeState.pdfLinkService,
    findController: bridgeState.pdfFindController,
    textLayerMode: 1,
    annotationMode: 0,
    removePageBorders: true,
    l10n: bridgeState.nullL10n
  });
  bridgeState.pdfLinkService.setViewer(bridgeState.pdfViewer);
  bridgeState.pdfDoc = null;
  bridgeState.totalPages = 0;
  bridgeState.currentPageNumber = 1;
  bridgeState.pageDimsCache = [];
  bridgeState.hoverQueued = false;
  bridgeState.lastFindQuery = '';
  bridgeState.useExactSearch = true;
  bridgeState.pageSearchTextCache = [];
  bridgeState.pageSearchLowerCache = [];
  bridgeState.searchResults = [];
  bridgeState.searchResultsTotal = 0;
  bridgeState.activeSearchResultIndex = -1;
  bridgeState.searchPageFirstGlobalIndex = [];
  bridgeState.searchPageFirstStoredIndex = [];
  bridgeState.searchPageMatchCount = [];
  bridgeState.searchRunToken = 0;
  bridgeState.pdfOutlineDestById = {};
  bridgeState.searchDebounceTimer = 0;
  bridgeState.SEARCH_INPUT_DEBOUNCE_MS = 140;
  bridgeState.MAX_SEARCH_DROPDOWN_ROWS = 120;
  bridgeState.ZOOM_MIN_SCALE = 0.5;
  bridgeState.ZOOM_MAX_SCALE = 4.0;
  bridgeState.ZOOM_STEP_FACTOR = 1.15;
  bridgeState.manualZoomEnabled = false;
  bridgeState.interactionMode = 'drag';
  bridgeState.sourceInspectorActive = false;
  bridgeState.panDragActive = false;
  bridgeState.panPointerId = null;
  bridgeState.panStartX = 0;
  bridgeState.panStartY = 0;
  bridgeState.panStartLeft = 0;
  bridgeState.panStartTop = 0;
  bridgeState.lastWheelStepAt = 0;
  bridgeState.wheelStepLock = false;
  bridgeState.wheelUnlockTimer = 0;
  bridgeState.WHEEL_STEP_COOLDOWN_MS = 110;
  bridgeState.WHEEL_GESTURE_LOCK_MS = 220;
  bridgeState.thumbDragging = false;
  bridgeState.thumbDragOffsetY = 0;
  bridgeState.trackHoldDirection = 0;
  bridgeState.trackHoldDelayTimer = 0;
  bridgeState.trackHoldRepeatTimer = 0;
  bridgeState.TRACK_HOLD_DELAY_MS = 280;
  bridgeState.TRACK_HOLD_REPEAT_MS = 70;
  bridgeState.searchArrowHoldDirection = 0;
  bridgeState.searchArrowHoldDelayTimer = 0;
  bridgeState.searchArrowHoldRepeatTimer = 0;
  bridgeState.searchArrowHoldDidRepeat = false;
  bridgeState.searchArrowHoldPointerId = null;
  bridgeState.suppressSearchArrowClick = false;
  bridgeState.SEARCH_ARROW_HOLD_DELAY_MS = 250;
  bridgeState.SEARCH_ARROW_HOLD_REPEAT_MS = 55;
  bridgeState.highlightRestoreTimerA = 0;
  bridgeState.highlightRestoreTimerB = 0;
  bridgeState.highlightRestoreToken = 0;
  bridgeState.highlightQueueTimer = 0;
  bridgeState.highlightQueueToken = 0;
  return true;
}
