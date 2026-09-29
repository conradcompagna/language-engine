import { clamp, normalizeSearchText } from './bridge.mjs';
import { bridgeState } from './bridge.state.mjs';
import { goToPage, stepPage } from './pagination.mjs';
import {
  emitSearchResults,
  queueNativeHighlight,
  renderSearchDropdown,
  resetExactSearchUI,
  setSearchDropdownVisible,
  updateExactCountLabel
} from './search-ui.mjs';
export function syncSearchPositionToPage(pageNumber) {
  var query = normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  if (!query || bridgeState.searchResultsTotal <= 0) return;
  var pageIdx =
    clamp(
      Number(pageNumber) || bridgeState.currentPageNumber || 1,
      1,
      Math.max(1, bridgeState.totalPages || 1)
    ) - 1;
  var globalPos = Number(bridgeState.searchPageFirstGlobalIndex[pageIdx] || 0);
  var storedRaw = bridgeState.searchPageFirstStoredIndex[pageIdx];
  var storedIdx = isFinite(storedRaw) ? Number(storedRaw) : -1;
  if (storedIdx >= 0 && storedIdx < bridgeState.searchResults.length) {
    bridgeState.activeSearchResultIndex = storedIdx;
  } else {
    bridgeState.activeSearchResultIndex = -1;
  }
  if (bridgeState.searchCount) {
    if (globalPos > 0) {
      bridgeState.searchCount.textContent = globalPos + '/' + bridgeState.searchResultsTotal;
      bridgeState.searchCount.dataset.state = 'results';
    } else {
      bridgeState.searchCount.textContent = '0/' + bridgeState.searchResultsTotal;
      bridgeState.searchCount.dataset.state = 'results';
    }
  }
  if (bridgeState.searchDropdown && !bridgeState.searchDropdown.hidden) {
    renderSearchDropdown(query);
  }
  emitSearchResults(query, false);
}
export function findFirstStoredIndexOnPageOrAfter(startPageIdx) {
  var s = clamp(Number(startPageIdx) || 0, 0, Math.max(0, bridgeState.totalPages - 1));
  var p;
  for (p = s; p < bridgeState.totalPages; p++) {
    if (
      (Number(bridgeState.searchPageMatchCount[p]) || 0) > 0 &&
      isFinite(bridgeState.searchPageFirstStoredIndex[p])
    ) {
      return Number(bridgeState.searchPageFirstStoredIndex[p]);
    }
  }
  for (p = 0; p < s; p++) {
    if (
      (Number(bridgeState.searchPageMatchCount[p]) || 0) > 0 &&
      isFinite(bridgeState.searchPageFirstStoredIndex[p])
    ) {
      return Number(bridgeState.searchPageFirstStoredIndex[p]);
    }
  }
  return -1;
}
export function findLastStoredIndexOnPageOrBefore(startPageIdx) {
  var s = clamp(Number(startPageIdx) || 0, 0, Math.max(0, bridgeState.totalPages - 1));
  var p;
  for (p = s; p >= 0; p--) {
    var count = Number(bridgeState.searchPageMatchCount[p]) || 0;
    var first = Number(bridgeState.searchPageFirstStoredIndex[p]);
    if (count > 0 && isFinite(first)) {
      return first + count - 1;
    }
  }
  for (p = bridgeState.totalPages - 1; p > s; p--) {
    var countWrap = Number(bridgeState.searchPageMatchCount[p]) || 0;
    var firstWrap = Number(bridgeState.searchPageFirstStoredIndex[p]);
    if (countWrap > 0 && isFinite(firstWrap)) {
      return firstWrap + countWrap - 1;
    }
  }
  return -1;
}
export function ensurePageSearchText(pageNumber) {
  var idx = clamp(Number(pageNumber) || 1, 1, Math.max(1, bridgeState.totalPages || 1)) - 1;
  if (typeof bridgeState.pageSearchTextCache[idx] === 'string') {
    return Promise.resolve(bridgeState.pageSearchTextCache[idx]);
  }
  if (!bridgeState.pdfDoc) return Promise.resolve('');
  return bridgeState.pdfDoc
    .getPage(idx + 1)
    .then(function (page) {
      return page.getTextContent();
    })
    .then(function (textContent) {
      var items = Array.isArray(textContent && textContent.items) ? textContent.items : [];
      var chunks = [];
      for (var i = 0; i < items.length; i++) {
        var it = items[i] || {};
        if (it.str) chunks.push(String(it.str));
        if (it.hasEOL) chunks.push('\n');
      }
      var text = normalizeSearchText(chunks.join(' '));
      bridgeState.pageSearchTextCache[idx] = text;
      bridgeState.pageSearchLowerCache[idx] = text.toLocaleLowerCase();
      return text;
    })
    .catch(function () {
      bridgeState.pageSearchTextCache[idx] = '';
      bridgeState.pageSearchLowerCache[idx] = '';
      return '';
    });
}
export function runExactSearch(query) {
  var q = normalizeSearchText(query);
  var token = ++bridgeState.searchRunToken;
  bridgeState.searchResults = [];
  bridgeState.searchResultsTotal = 0;
  bridgeState.activeSearchResultIndex = -1;
  bridgeState.searchPageFirstGlobalIndex = [];
  bridgeState.searchPageFirstStoredIndex = [];
  bridgeState.searchPageMatchCount = [];
  bridgeState.lastFindQuery = q;
  if (!q) {
    resetExactSearchUI();
    if (bridgeState.searchCount) {
      bridgeState.searchCount.textContent = '0/0';
      bridgeState.searchCount.dataset.state = 'idle';
    }
    return Promise.resolve([]);
  }
  queueNativeHighlight(true, 0);
  if (bridgeState.searchCount) {
    bridgeState.searchCount.textContent = '...';
    bridgeState.searchCount.dataset.state = 'pending';
  }
  if (bridgeState.searchDropdownMeta)
    bridgeState.searchDropdownMeta.textContent = 'Searching exact matches for "' + q + '"...';
  if (bridgeState.searchDropdownList) bridgeState.searchDropdownList.innerHTML = '';
  setSearchDropdownVisible(true);
  emitSearchResults(q, true);
  var qLower = q.toLocaleLowerCase();
  return (async function () {
    for (var page = 1; page <= bridgeState.totalPages; page++) {
      var text = await ensurePageSearchText(page);
      if (token !== bridgeState.searchRunToken) return [];
      if (!text) continue;
      var hay = bridgeState.pageSearchLowerCache[page - 1] || text.toLocaleLowerCase();
      var from = 0;
      while (true) {
        var hit = hay.indexOf(qLower, from);
        if (hit < 0) break;
        bridgeState.searchResultsTotal++;
        bridgeState.searchPageMatchCount[page - 1] =
          (Number(bridgeState.searchPageMatchCount[page - 1]) || 0) + 1;
        if (!bridgeState.searchPageFirstGlobalIndex[page - 1]) {
          bridgeState.searchPageFirstGlobalIndex[page - 1] = bridgeState.searchResultsTotal;
        }
        if (!isFinite(bridgeState.searchPageFirstStoredIndex[page - 1])) {
          bridgeState.searchPageFirstStoredIndex[page - 1] = bridgeState.searchResults.length;
        }
        bridgeState.searchResults.push({
          pageNumber: page,
          index: hit,
          length: q.length,
          text: text
        });
        from = hit + Math.max(1, qLower.length);
      }
    }
    if (token !== bridgeState.searchRunToken) return [];
    bridgeState.activeSearchResultIndex = bridgeState.searchResults.length ? 0 : -1;
    renderSearchDropdown(q);
    if (bridgeState.searchResultsTotal > 0) {
      syncSearchPositionToPage(bridgeState.currentPageNumber || 1);
    } else if (bridgeState.searchCount) {
      bridgeState.searchCount.textContent = 'No matches';
      bridgeState.searchCount.dataset.state = 'no-results';
    }
    return bridgeState.searchResults;
  })();
}
export function focusSearchResult(resultIndex, triggerNativeFind, preserveDropdownVisibility) {
  if (!bridgeState.searchResults.length) return;
  var idx = clamp(Number(resultIndex) || 0, 0, bridgeState.searchResults.length - 1);
  var keepVisibility = !!preserveDropdownVisibility;
  var dropdownWasOpen = !!(bridgeState.searchDropdown && !bridgeState.searchDropdown.hidden);
  bridgeState.activeSearchResultIndex = idx;
  var result = bridgeState.searchResults[idx];
  if (!keepVisibility || dropdownWasOpen) {
    renderSearchDropdown(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  }
  updateExactCountLabel(idx + 1, bridgeState.searchResultsTotal);
  goToPage(result.pageNumber, true);
  emitSearchResults(bridgeState.searchInput ? bridgeState.searchInput.value : '', false);
  if (triggerNativeFind) {
    queueNativeHighlight(true, 0);
  }
}
export function stepSearchResult(delta) {
  if (!bridgeState.searchResults.length) return;
  var dir = Number(delta) >= 0 ? 1 : -1;
  var idx = bridgeState.activeSearchResultIndex;
  if (!isFinite(idx) || idx < 0 || idx >= bridgeState.searchResults.length) {
    var pageIdx = clamp(
      (Number(bridgeState.currentPageNumber) || 1) - 1,
      0,
      Math.max(0, bridgeState.totalPages - 1)
    );
    var seed =
      dir > 0 ? findFirstStoredIndexOnPageOrAfter(pageIdx) : findLastStoredIndexOnPageOrBefore(pageIdx);
    if (seed >= 0 && seed < bridgeState.searchResults.length) {
      focusSearchResult(seed, true, true);
      return;
    }
    idx = dir > 0 ? -1 : bridgeState.searchResults.length;
  }
  var next = idx + dir;
  if (next < 0) next = bridgeState.searchResults.length - 1;
  if (next >= bridgeState.searchResults.length) next = 0;
  focusSearchResult(next, true, true);
}
export function stepSearchControls(delta) {
  var query = normalizeSearchText(bridgeState.searchInput ? bridgeState.searchInput.value : '');
  if (query && bridgeState.searchResultsTotal > 0) {
    stepSearchResult(delta);
    return;
  }
  stepPage(delta);
}
