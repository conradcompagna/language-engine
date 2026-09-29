import { clamp, escapeHtml, normalizeSearchText, post } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import { emitState } from './lifecycle.mjs';
import { goToPage } from './pagination.mjs';
export function getFindState(findPrevious) {
  return {
    query: String(bridgeState.searchInput ? bridgeState.searchInput.value || '' : ''),
    phraseSearch: true,
    caseSensitive: false,
    entireWord: false,
    highlightAll: true,
    findPrevious: !!findPrevious,
    matchDiacritics: true
  };
}
export function runFind(command, findPrevious) {
  if (!bridgeState.pdfFindController) return;
  var state = getFindState(findPrevious);
  var eventType = '';
  if (command === 'findagain') eventType = 'again';
  else if (command === 'find') eventType = '';
  else eventType = String(command || '');
  // Use the same event path as the native PDF.js find bar.
  bridgeState.viewerEventBus.dispatch('find', {
    source: bridgeState.searchInput || window,
    type: eventType,
    query: state.query,
    phraseSearch: state.phraseSearch,
    caseSensitive: state.caseSensitive,
    entireWord: state.entireWord,
    highlightAll: state.highlightAll,
    findPrevious: state.findPrevious,
    matchDiacritics: state.matchDiacritics
  });
}
export function clearPendingHighlightRestore() {
  if (bridgeState.highlightRestoreTimerA) {
    clearTimeout(bridgeState.highlightRestoreTimerA);
    bridgeState.highlightRestoreTimerA = 0;
  }
  if (bridgeState.highlightRestoreTimerB) {
    clearTimeout(bridgeState.highlightRestoreTimerB);
    bridgeState.highlightRestoreTimerB = 0;
  }
}
export function clearQueuedHighlightRefresh() {
  if (bridgeState.highlightQueueTimer) {
    clearTimeout(bridgeState.highlightQueueTimer);
    bridgeState.highlightQueueTimer = 0;
  }
}
export function applyNativeHighlight(preservePage) {
  clearQueuedHighlightRefresh();
  clearPendingHighlightRestore();
  bridgeState.highlightRestoreToken++;
  var query = normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  if (!query) {
    runFind('highlightallchange', false);
    return;
  }
  var keepPage = preservePage ? bridgeState.currentPageNumber : 0;
  // Highlight all matches without navigating to a selected match.
  runFind('highlightallchange', false);
  if (keepPage > 0) {
    var token = bridgeState.highlightRestoreToken;
    bridgeState.highlightRestoreTimerA = setTimeout(function () {
      if (token !== bridgeState.highlightRestoreToken) return;
      goToPage(keepPage, false);
    }, 0);
    bridgeState.highlightRestoreTimerB = setTimeout(function () {
      if (token !== bridgeState.highlightRestoreToken) return;
      goToPage(keepPage, false);
    }, 110);
  }
}
export function queueNativeHighlight(preservePage, delayMs) {
  clearQueuedHighlightRefresh();
  clearPendingHighlightRestore();
  bridgeState.highlightRestoreToken++;
  var d = Math.max(0, Number(delayMs) || 0);
  bridgeState.highlightQueueToken++;
  var token = bridgeState.highlightQueueToken;
  bridgeState.highlightQueueTimer = setTimeout(function () {
    bridgeState.highlightQueueTimer = 0;
    if (token !== bridgeState.highlightQueueToken) return;
    applyNativeHighlight(!!preservePage);
  }, d);
}
export function setSearchCountLabel(current, total, limit) {
  if (!bridgeState.searchCount) return;
  var c = Math.max(0, Number(current) || 0);
  var t = Math.max(0, Number(total) || 0);
  var lim = Math.max(0, Number(limit) || 0);
  if (!bridgeState.searchInput || !String(bridgeState.searchInput.value || '').trim()) {
    bridgeState.searchCount.textContent = '0/0';
    bridgeState.searchCount.dataset.state = 'idle';
    emitState();
    return;
  }
  if (lim > 0 && t > lim) {
    bridgeState.searchCount.textContent = c + '/>' + lim;
    bridgeState.searchCount.dataset.state = 'results';
    emitState();
    return;
  }
  bridgeState.searchCount.textContent = c + '/' + t;
  bridgeState.searchCount.dataset.state = 'results';
  emitState();
}
export function setSearchDropdownVisible(show) {
  if (!bridgeState.searchDropdown) return;
  bridgeState.searchDropdown.hidden = !show;
}
export function updateExactCountLabel(current, total) {
  if (!bridgeState.searchCount) return;
  var c = Math.max(0, Number(current) || 0);
  var t = Math.max(0, Number(total) || 0);
  if (t <= 0) {
    bridgeState.searchCount.textContent = 'No matches';
    bridgeState.searchCount.dataset.state = 'no-results';
    emitState();
    return;
  }
  bridgeState.searchCount.textContent = c + '/' + t;
  bridgeState.searchCount.dataset.state = 'results';
  emitState();
}
export function resetExactSearchUI() {
  bridgeState.searchRunToken++;
  bridgeState.searchResults = [];
  bridgeState.searchResultsTotal = 0;
  bridgeState.activeSearchResultIndex = -1;
  bridgeState.searchPageFirstGlobalIndex = [];
  bridgeState.searchPageFirstStoredIndex = [];
  bridgeState.searchPageMatchCount = [];
  if (bridgeState.searchDropdownMeta) bridgeState.searchDropdownMeta.textContent = 'Type to search';
  if (bridgeState.searchDropdownList) bridgeState.searchDropdownList.innerHTML = '';
  setSearchDropdownVisible(false);
  emitSearchResults('', false);
}
export function buildSearchSnippetHtml(pageText, matchStart, matchLen) {
  var start = Math.max(0, Number(matchStart) || 0);
  var len = Math.max(1, Number(matchLen) || 1);
  var from = Math.max(0, start - 34);
  var to = Math.min(pageText.length, start + len + 34);
  var lead = from > 0 ? '...' : '';
  var tail = to < pageText.length ? '...' : '';
  var before = escapeHtml(pageText.slice(from, start));
  var exact = escapeHtml(pageText.slice(start, start + len));
  var after = escapeHtml(pageText.slice(start + len, to));
  return lead + before + '<span class="search-result-mark">' + exact + '</span>' + after + tail;
}
export function buildSearchExcerptParts(pageText, matchStart, matchLen) {
  var text = String(pageText || '');
  var start = Math.max(0, Number(matchStart) || 0);
  var len = Math.max(1, Number(matchLen) || 1);
  var from = Math.max(0, start - 48);
  var to = Math.min(text.length, start + len + 64);
  return {
    pre: (from > 0 ? '...' : '') + text.slice(from, start),
    match: text.slice(start, start + len),
    post: text.slice(start + len, to) + (to < text.length ? '...' : '')
  };
}
export function getDropdownWindowBounds(totalItems) {
  var total = Math.max(0, Number(totalItems) || 0);
  if (total <= 0)
    return {
      start: 0,
      end: 0
    };
  var cap = Math.max(1, Number(bridgeState.MAX_SEARCH_DROPDOWN_ROWS) || 1);
  if (total <= cap)
    return {
      start: 0,
      end: total
    };
  var active = clamp(Number(bridgeState.activeSearchResultIndex) || 0, 0, total - 1);
  var half = Math.floor(cap / 2);
  var start = active - half;
  if (start < 0) start = 0;
  if (start + cap > total) start = total - cap;
  return {
    start: start,
    end: start + cap
  };
}
export function emitSearchResults(query, pending) {
  var q = normalizeSearchText(
    query != null ? query : bridgeState.searchInput ? bridgeState.searchInput.value : ''
  );
  var win = getDropdownWindowBounds(bridgeState.searchResults.length);
  var rows = [];
  for (var i = win.start; i < win.end; i++) {
    var r = bridgeState.searchResults[i] || {};
    rows.push({
      id: 'pdf-search-' + i,
      resultIndex: i,
      pageIndex: Math.max(0, (Number(r.pageNumber) || 1) - 1),
      label: 'Page ' + (Number(r.pageNumber) || 1),
      excerpt: buildSearchExcerptParts(r.text || '', r.index, r.length)
    });
  }
  post('pdfjs-search-results', {
    query: q,
    total: Math.max(bridgeState.searchResultsTotal || 0, bridgeState.searchResults.length),
    activeIndex:
      bridgeState.activeSearchResultIndex >= win.start && bridgeState.activeSearchResultIndex < win.end
        ? bridgeState.activeSearchResultIndex - win.start
        : -1,
    pending: !!pending,
    results: rows
  });
}
export function renderSearchDropdown(query) {
  if (!bridgeState.searchDropdown || !bridgeState.searchDropdownMeta || !bridgeState.searchDropdownList)
    return;
  var q = normalizeSearchText(query);
  if (!q) {
    bridgeState.searchDropdownMeta.textContent = 'Type to search';
    bridgeState.searchDropdownList.innerHTML = '';
    setSearchDropdownVisible(false);
    emitSearchResults(q, false);
    return;
  }
  var total = bridgeState.searchResults.length;
  var win = getDropdownWindowBounds(total);
  var shown = Math.max(0, win.end - win.start);
  var suffix = total > shown ? ' (showing ' + (win.start + 1) + '-' + win.end + ')' : '';
  bridgeState.searchDropdownMeta.textContent = 'Exact matches for "' + q + '": ' + total + suffix;
  if (!shown) {
    bridgeState.searchDropdownList.innerHTML =
      '<button class="search-result-row" type="button" disabled>No exact matches</button>';
    setSearchDropdownVisible(true);
    emitSearchResults(q, false);
    return;
  }
  var rows = [];
  for (var i = win.start; i < win.end; i++) {
    var r = bridgeState.searchResults[i];
    var cls = 'search-result-row' + (i === bridgeState.activeSearchResultIndex ? ' active' : '');
    rows.push(
      '<button class="' +
        cls +
        '" type="button" data-result-index="' +
        i +
        '">' +
        '<span class="search-result-page">p.' +
        r.pageNumber +
        '</span>' +
        buildSearchSnippetHtml(r.text, r.index, r.length) +
        '</button>'
    );
  }
  bridgeState.searchDropdownList.innerHTML = rows.join('');
  setSearchDropdownVisible(true);
  emitSearchResults(q, false);
}
