import {
  applyFixedDocumentViewportHeight,
  showDocumentChrome,
  syncTrankitChunkLookupControls
} from './document-search.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { ensureCanonicalReaderController } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { foliateSlicesState } from './foliate-slices.state.mjs';
import {
  configureFoliateEpubRenderer,
  currentFoliateFileFormatLabel,
  ensureFoliateJs,
  epubVisibleCharSlice,
  foliateCurrentSectionIndex,
  foliateFlowGlobalPageIndex,
  foliateFlowResolvePageIndex,
  foliateVisualPageCount,
  foliateVisualPageIndex,
  foliateVisualPageIndexForCount,
  getEpubViewportSize,
  getFoliateEpubRenderer,
  getFoliateViewportClipForDoc,
  getFoliateVisibleRange,
  isActiveEpubDocument,
  isActiveFoliateFlowDocument,
  observeFoliateEpubResize,
  recomputeFoliateFlowSectionStarts,
  resetFoliateFullPagination,
  resetFoliateNativePageCounts,
  setFoliateDocumentCapabilities,
  startFoliateFullPagination,
  syncDocumentChrome
} from './foliate-viewport.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { escapeHtml } from './presentation.mjs';
export function getFoliateEpubSliceContext() {
  var renderer = getFoliateEpubRenderer();
  var contents = renderer && typeof renderer.getContents === 'function' ? renderer.getContents() : null;
  var size = getEpubViewportSize();
  var best = null;
  for (var i = 0; i < (contents || []).length; i++) {
    var doc = contents[i] && contents[i].doc;
    if (!doc || !doc.body) continue;
    var clip = getFoliateViewportClipForDoc(doc);
    if (!clip) continue;
    var win = doc.defaultView || null;
    var ctx = {
      doc: doc,
      win: win,
      iframe: clip.frame || null,
      viewportClip: {
        left: clip.left,
        top: clip.top,
        right: clip.right,
        bottom: clip.bottom,
        width: clip.width,
        height: clip.height
      },
      scrollLeft: clip.left,
      scrollTop: clip.top,
      pageW: Math.max(1, clip.width || size.width),
      pageH: Math.max(1, clip.height || size.height),
      visibleArea: clip.area || 0
    };
    if (!best || ctx.visibleArea > best.visibleArea) best = ctx;
  }
  return best;
}
export function isStaticDocumentControlTextNode(node) {
  var cur = node && node.parentElement;
  while (cur) {
    if (cur.getAttribute && cur.getAttribute('data-le-static-control')) return true;
    cur = cur.parentElement;
  }
  return false;
}
export function extractEpubVisibleText() {
  if (!documentState.epubJsRendition) {
    documentState.epubJsCurrentText = '';
    return;
  }
  try {
    var ctx = getFoliateEpubSliceContext();
    if (!ctx) {
      documentState.epubJsCurrentText = '';
      return;
    }
    var walker = ctx.doc.createTreeWalker(ctx.doc.body, NodeFilter.SHOW_TEXT, null, false);
    var parts = [],
      lastParent = null,
      node;
    while ((node = walker.nextNode())) {
      if (isStaticDocumentControlTextNode(node)) continue;
      var slice = epubVisibleCharSlice(node, ctx.doc, ctx.scrollLeft, ctx.pageW);
      if (!slice || !slice.trim()) continue;
      var parent = node.parentElement;
      var tag = parent ? parent.tagName.toLowerCase() : '';
      if (
        parent &&
        parent !== lastParent &&
        /^(p|h[1-6]|li|blockquote|div|section|article)$/.test(tag) &&
        parts.length > 0
      ) {
        parts.push('\n\n');
      }
      lastParent = parent;
      parts.push(slice);
    }
    documentState.epubJsCurrentText = parts
      .join('')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  } catch (e) {
    documentState.epubJsCurrentText = '';
  }
}
export function updateFoliateEpubLocation(detail) {
  detail = detail || {};
  if (detail.range) documentState.epubVisibleRange = detail.range;
  var sectionIndex = foliateCurrentSectionIndex();
  var sectionPageCount = foliateVisualPageCount(1);
  var sectionPageIndex = foliateVisualPageIndexForCount(sectionPageCount);
  if (documentState.foliateFullPaginationReady) {
    var total = recomputeFoliateFlowSectionStarts();
    documentState.epubJsTotalPages = Math.max(1, Math.ceil(total));
    if (!documentState.docPages || documentState.docPages.length !== documentState.epubJsTotalPages) {
      documentState.docPages = new Array(documentState.epubJsTotalPages).fill('');
    }
    var current = foliateFlowGlobalPageIndex(sectionIndex, sectionPageIndex);
    documentState.epubJsCurrentPageNum = Math.max(
      0,
      Math.min(documentState.epubJsTotalPages - 1, Math.floor(current))
    );
    documentState.epubJsPageLabel =
      'Page ' + (documentState.epubJsCurrentPageNum + 1) + ' / ' + documentState.epubJsTotalPages;
  } else {
    documentState.epubJsTotalPages = 1;
    documentState.epubJsCurrentPageNum = 0;
    documentState.epubJsPageLabel = 'Paginating...';
  }
  documentState.activePageIndex = documentState.epubJsCurrentPageNum;
  var renderer = getFoliateEpubRenderer();
  try {
    documentState.epubJsCanGoPrev = renderer ? !renderer.atStart : documentState.epubJsCurrentPageNum > 0;
    documentState.epubJsCanGoNext = renderer
      ? !renderer.atEnd
      : documentState.epubJsCurrentPageNum < documentState.epubJsTotalPages - 1;
  } catch (_e3) {
    documentState.epubJsCanGoPrev = documentState.epubJsCurrentPageNum > 0;
    documentState.epubJsCanGoNext = documentState.epubJsCurrentPageNum < documentState.epubJsTotalPages - 1;
  }
  extractEpubVisibleText();
  var canPage = buildEpubCanonicalPage();
  if (canPage) setEpubCanonicalPage(canPage);
  syncDocumentChrome();
}
export function foliateNativeGoToPage(pageIndex) {
  if (!isActiveEpubDocument() || !documentState.epubJsRendition) return Promise.resolve(false);
  if (!documentState.foliateFullPaginationReady) return Promise.resolve(false);
  var total = Math.max(1, Math.floor(Number(documentState.epubJsTotalPages) || 1));
  var requested = Math.max(0, Math.min(total - 1, Math.floor(Number(pageIndex) || 0)));
  var target = foliateFlowResolvePageIndex(requested);
  var frac = target.sectionPageCount > 1 ? target.sectionPageIndex / (target.sectionPageCount - 1) : 0;
  var renderer = getFoliateEpubRenderer();
  if (renderer && typeof renderer.goTo === 'function') {
    return Promise.resolve(
      renderer.goTo({
        index: target.sectionIndex,
        anchor: frac
      })
    ).then(function () {
      updateFoliateEpubLocation(
        (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
      );
      return true;
    });
  }
  return Promise.resolve(false);
}
export function foliateNativeStepPage(delta) {
  if (!isActiveEpubDocument() || !documentState.epubJsRendition) return Promise.resolve(false);
  var dir = Number(delta) || 0;
  var fn = dir > 0 ? documentState.epubJsRendition.next : documentState.epubJsRendition.prev;
  if (typeof fn !== 'function')
    return foliateNativeGoToPage((documentState.epubJsCurrentPageNum || 0) + (dir > 0 ? 1 : -1));
  return Promise.resolve(fn.call(documentState.epubJsRendition)).then(function () {
    updateFoliateEpubLocation(
      (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
    );
    return true;
  });
}
export function initFoliateEpub(file) {
  var loadSeq = ++documentState.epubLoadSeq;
  documentState.inputMode = 'doc';
  documentState.docPages = [''];
  documentState.epubJsCurrentPageNum = 0;
  documentState.epubJsTotalPages = 1;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.docPageScrollTopByIndex = {};
  if (hoverLayoutState.sourceText) hoverLayoutState.sourceText.style.display = 'none';
  showDocumentChrome(true);
  applyFixedDocumentViewportHeight(true);
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.innerHTML = '';
    hoverLayoutState.sourcePager.classList.remove(
      'pdfjs-native-mode',
      'orig-view-mode',
      'docrender-source-active',
      'docrender-websnapshot-active',
      'docrender-docx-continuous-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.classList.add('docrender-epub-foliate-active');
  }
  var foliateLabel = currentFoliateFileFormatLabel();
  if (hoverLayoutState.statusText)
    hoverLayoutState.statusText.textContent = 'Loading ' + foliateLabel + '...';
  ensureFoliateJs()
    .then(function () {
      if (loadSeq !== documentState.epubLoadSeq) return null;
      if (!window.customElements || !customElements.get('foliate-view')) {
        throw new Error('Foliate view component did not register');
      }
      var view = document.createElement('foliate-view');
      view.className = 'foliate-epub-view';
      documentState.epubJsRendition = view;
      if (hoverLayoutState.sourcePager) hoverLayoutState.sourcePager.appendChild(view);
      view.addEventListener('load', function () {
        configureFoliateEpubRenderer();
      });
      view.addEventListener('relocate', function (ev) {
        updateFoliateEpubLocation(ev.detail || {});
      });
      return view.open(file).then(function () {
        if (loadSeq !== documentState.epubLoadSeq) return null;
        documentState.epubJsBook = view.book || null;
        resetFoliateNativePageCounts();
        resetFoliateFullPagination(true);
        setFoliateDocumentCapabilities('foliate');
        configureFoliateEpubRenderer();
        observeFoliateEpubResize();
        return view.init({
          showTextStart: true
        });
      });
    })
    .then(function () {
      if (loadSeq !== documentState.epubLoadSeq) return;
      if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
      configureFoliateEpubRenderer();
      startFoliateFullPagination('load');
      updateFoliateEpubLocation(
        (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {}
      );
    })
    .catch(function (e) {
      if (loadSeq !== documentState.epubLoadSeq) return;
      console.warn('Foliate ebook load failed:', e);
      if (hoverLayoutState.statusText)
        hoverLayoutState.statusText.textContent = 'Failed to load ' + foliateLabel + '.';
      if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
      if (hoverLayoutState.renderedText)
        hoverLayoutState.renderedText.innerHTML =
          '<div class="reader-output-placeholder">' + escapeHtml(foliateLabel) + ' rendering failed.</div>';
    });
}
export function setEpubCanonicalPage(page) {
  if (!page || !window.CanonicalModel) return;
  try {
    var doc = window.CanonicalModel.makeDocument({
      meta: {
        format: currentFoliateFileFormatLabel(),
        parser: 'foliate'
      },
      pages: [page],
      source: {
        adapter: 'foliate'
      }
    });
    var ctl = ensureCanonicalReaderController();
    documentState.canonicalDoc = doc;
    ctl.setDocument(doc, {
      pageIndex: 0,
      clearCache: true
    });
    syncTrankitChunkLookupControls();
    // Deliberately do not overwrite docPages or activePageIndex; Foliate owns EPUB paging.
  } catch (e) {
    console.warn('setEpubCanonicalPage failed:', e);
  }
}
export function buildEpubCanonicalPage() {
  if (!documentState.epubJsRendition) return null;
  try {
    var ctx = getFoliateEpubSliceContext();
    if (!ctx) return null;
    var size = getEpubViewportSize();
    var visibleRange =
      getFoliateVisibleRange() ||
      (documentState.epubJsRendition &&
        documentState.epubJsRendition.lastLocation &&
        documentState.epubJsRendition.lastLocation.range) ||
      null;
    var pageNum = Math.max(0, Math.floor(Number(documentState.epubJsCurrentPageNum) || 0));
    var meta = {
      format: currentFoliateFileFormatLabel(),
      parser: 'foliate-visible-range',
      sourceRenderer: 'foliate',
      pageWidth: ctx.pageW || size.width,
      pageHeight: ctx.pageH || size.height,
      sourcePageIndex: pageNum,
      sourceSectionIndex: foliateCurrentSectionIndex(),
      sourceSectionPageIndex: foliateVisualPageIndex()
    };
    if (visibleRange && String(visibleRange.toString() || '').trim()) {
      var rangedPage = canonicalPageFromFoliateRange(
        visibleRange,
        0,
        meta,
        {
          width: ctx.pageW || size.width,
          height: size.height
        },
        {
          globalPageIndex: pageNum,
          sectionIndex: meta.sourceSectionIndex,
          sectionPageIndex: meta.sourceSectionPageIndex
        },
        {
          adapter: 'foliate',
          pageId: 'epub-page-' + pageNum,
          parser: 'foliate-visible-range-dom',
          clip: ctx.viewportClip || {
            left: ctx.scrollLeft,
            right: ctx.scrollLeft + ctx.pageW,
            top: ctx.scrollTop || 0,
            bottom: (ctx.scrollTop || 0) + (ctx.pageH || size.height)
          }
        }
      );
      if (rangedPage && String(rangedPage.text || '').trim()) {
        documentState.epubJsCurrentText = rangedPage.text;
        return rangedPage;
      }
    }
    var BLOCK_RE = /^(p|h[1-6]|li|blockquote|pre|td|th)$/;
    var walker = ctx.doc.createTreeWalker(ctx.doc.body, NodeFilter.SHOW_TEXT, null, false);
    var blockEls = [],
      blockTexts = [],
      blockTags = [],
      node;
    while ((node = walker.nextNode())) {
      if (isStaticDocumentControlTextNode(node)) continue;
      var slice = epubVisibleCharSlice(node, ctx.doc, ctx.scrollLeft, ctx.pageW);
      if (!slice || !slice.trim()) continue;
      var blockEl = null,
        blockTag = 'p',
        cur = node.parentElement;
      while (cur && cur !== ctx.doc.body) {
        var t = cur.tagName.toLowerCase();
        if (BLOCK_RE.test(t)) {
          blockEl = cur;
          blockTag = t;
          break;
        }
        cur = cur.parentElement;
      }
      if (!blockEl) blockEl = ctx.doc.body;
      var idx = blockEls.indexOf(blockEl);
      if (idx === -1) {
        idx = blockEls.length;
        blockEls.push(blockEl);
        blockTexts.push('');
        blockTags.push(blockTag);
      }
      blockTexts[idx] += slice;
    }
    if (!blockEls.length) return null;
    var htmlParts = [];
    for (var i = 0; i < blockEls.length; i++) {
      var tag = blockTags[i];
      var safe = blockTexts[i].replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      if (!safe.trim()) continue;
      htmlParts.push('<' + tag + '>' + safe + '</' + tag + '>');
    }
    if (!htmlParts.length) return null;
    var page = null;
    if (window.CanonicalBuilder) {
      var b = new window.CanonicalBuilder.Builder({
        format: 'epub',
        parser: 'foliate-sliced-plain'
      });
      b.startPage({
        layout: {
          mode: 'flow',
          width: ctx.pageW,
          height: size.height
        }
      });
      b.startBlock({
        type: 'paragraph',
        layout: {
          mode: 'flow'
        }
      });
      b.addRun(blockTexts.join('\n\n'));
      page = b.finish().pages[0];
    }
    if (!page || !page.text) return null;
    page.index = 0;
    page.id = 'epub-page-' + pageNum;
    page.source = Object.assign({}, page.source || {}, {
      adapter: 'foliate',
      sourcePageIndex: pageNum,
      sourceSectionIndex: meta.sourceSectionIndex,
      sourceSectionPageIndex: meta.sourceSectionPageIndex,
      fallback: 'sliced-visible-text'
    });
    documentState.epubJsCurrentText = page.text;
    return page;
  } catch (e) {
    console.warn('buildEpubCanonicalPage failed:', e);
    return null;
  }
}
export function currentFoliateFlowFormatLabel() {
  var raw = String(
    (documentState.docrenderMeta &&
      (documentState.docrenderMeta.format || documentState.docrenderMeta.fileName)) ||
      documentState.foliateFlowLabel ||
      'Document'
  );
  raw = raw.replace(/\.[^.]+$/, '').trim();
  if (/^plain text$/i.test(raw)) raw = 'TXT';
  return raw || 'Document';
}
export function foliateFlowTextLength(node) {
  if (!node) return 0;
  if (node.nodeType === 3) return String(node.nodeValue || '').length;
  if (node.nodeType !== 1) return 0;
  if (String(node.tagName || '').toUpperCase() === 'BR') return 1;
  var kids = node.childNodes || [];
  var total = 0;
  for (var i = 0; i < kids.length; i++) total += foliateFlowTextLength(kids[i]);
  return total || String(node.textContent || '').length;
}
export function splitFoliateFlowText(text, limit) {
  text = String(text || '');
  limit = Math.max(2000, Math.floor(Number(limit) || foliateSlicesState.FOLIATE_FLOW_SECTION_CHAR_LIMIT));
  if (text.length <= limit) return [text];
  var out = [];
  var start = 0;
  while (start < text.length) {
    var hard = Math.min(text.length, start + limit);
    var end = hard;
    if (hard < text.length) {
      var floor = start + Math.floor(limit * 0.55);
      var probe = text.lastIndexOf('\n\n', hard);
      if (probe < floor) probe = text.lastIndexOf('\n', hard);
      if (probe < floor) probe = text.lastIndexOf(' ', hard);
      if (probe >= floor) end = probe + 1;
    }
    if (end <= start) end = hard;
    out.push(text.slice(start, end));
    start = end;
  }
  return out;
}
export function splitFoliateFlowNode(node, limit) {
  if (!node) return [];
  var len = foliateFlowTextLength(node);
  if (len <= limit) return [node.cloneNode(true)];
  if (node.nodeType === 3) {
    return splitFoliateFlowText(node.nodeValue || '', limit).map(function (part) {
      return document.createTextNode(part);
    });
  }
  if (node.nodeType !== 1) return [node.cloneNode(true)];
  var kids = Array.prototype.slice.call(node.childNodes || []);
  if (!kids.length) return [node.cloneNode(true)];
  var chunks = [];
  var current = node.cloneNode(false);
  var currentLen = 0;
  for (var i = 0; i < kids.length; i++) {
    var pieces = splitFoliateFlowNode(kids[i], limit);
    for (var j = 0; j < pieces.length; j++) {
      var piece = pieces[j];
      var pieceLen = Math.max(1, foliateFlowTextLength(piece));
      if (current.childNodes.length && currentLen + pieceLen > limit) {
        chunks.push(current);
        current = node.cloneNode(false);
        currentLen = 0;
      }
      current.appendChild(piece);
      currentLen += pieceLen;
    }
  }
  if (current.childNodes.length) chunks.push(current);
  return chunks.length ? chunks : [node.cloneNode(true)];
}
export function buildFoliateFlowSectionHtml(wrapper, nodes) {
  var shell = wrapper && wrapper.nodeType === 1 ? wrapper.cloneNode(false) : document.createElement('div');
  var cls = String(shell.className || '').trim();
  if (!/\bdocrender-flow-doc\b/.test(cls)) cls = (cls ? cls + ' ' : '') + 'docrender-flow-doc';
  shell.className = cls;
  for (var i = 0; i < nodes.length; i++) shell.appendChild(nodes[i].cloneNode(true));
  return shell.outerHTML;
}
export function splitFoliateFlowHtmlIntoSections(richHtml, meta) {
  var html = String(richHtml || '').trim();
  if (!html) return ['<div class="docrender-flow-doc"><p></p></div>'];
  var limit = Math.max(
    4000,
    Math.floor(
      Number(meta && meta.flowSectionCharLimit) || foliateSlicesState.FOLIATE_FLOW_SECTION_CHAR_LIMIT
    )
  );
  var tmp = document.createElement('div');
  tmp.innerHTML = html;
  var wrapper =
    tmp.querySelector('.docrender-flow-doc') || (tmp.children.length === 1 ? tmp.firstElementChild : tmp);
  var children = Array.prototype.slice.call((wrapper === tmp ? tmp : wrapper).childNodes || []);
  if (!children.length) return [html];
  var groups = [];
  var current = [];
  var currentLen = 0;
  function pushCurrent() {
    if (!current.length) return;
    groups.push(current);
    current = [];
    currentLen = 0;
  }
  for (var i = 0; i < children.length; i++) {
    var pieces = splitFoliateFlowNode(children[i], limit);
    for (var j = 0; j < pieces.length; j++) {
      var piece = pieces[j];
      var pieceLen = Math.max(1, foliateFlowTextLength(piece));
      if (current.length && currentLen + pieceLen > limit) pushCurrent();
      current.push(piece);
      currentLen += pieceLen;
    }
  }
  pushCurrent();
  var sections = groups
    .map(function (group) {
      return buildFoliateFlowSectionHtml(wrapper, group);
    })
    .filter(function (sectionHtml) {
      return !!String(sectionHtml || '').trim();
    });
  return sections.length ? sections : [html];
}
export function normalizeFoliateFlowSections(sections, richHtml, meta) {
  if (Array.isArray(sections) && sections.length) {
    var cleaned = sections
      .map(function (sectionHtml) {
        return String(sectionHtml || '').trim();
      })
      .filter(function (sectionHtml) {
        return !!sectionHtml;
      });
    if (cleaned.length) return cleaned;
  }
  return splitFoliateFlowHtmlIntoSections(richHtml, meta || {});
}
export function decodeFoliateFlowFragment(value) {
  var raw = String(value || '').replace(/^#/, '');
  try {
    return decodeURIComponent(raw);
  } catch (_decodeErr) {
    return raw;
  }
}
export function registerFoliateFlowId(idIndex, id, sectionIndex) {
  var raw = String(id || '').trim();
  if (!raw) return;
  if (!idIndex[raw])
    idIndex[raw] = {
      index: sectionIndex,
      id: raw
    };
  var decoded = decodeFoliateFlowFragment(raw);
  if (decoded && !idIndex[decoded])
    idIndex[decoded] = {
      index: sectionIndex,
      id: raw
    };
}
export function prepareFoliateFlowBookData(sectionHtmls, meta) {
  var usedIds = {};
  var idIndex = {};
  var toc = [];
  var prepared = (sectionHtmls || []).map(function (sectionHtml, sectionIndex) {
    var doc = new DOMParser().parseFromString(String(sectionHtml || ''), 'text/html');
    var root = doc.body || doc.documentElement;
    Array.prototype.slice.call(root.querySelectorAll('[id]')).forEach(function (el) {
      var id = String(el.getAttribute('id') || '').trim();
      if (id) usedIds[id] = true;
    });
    var headingCount = 0;
    Array.prototype.slice.call(root.querySelectorAll('h1,h2,h3,h4,h5,h6')).forEach(function (heading) {
      var label = String(heading.textContent || '')
        .replace(/\s+/g, ' ')
        .trim();
      if (!label) return;
      var id = String(heading.getAttribute('id') || '').trim();
      if (!id) {
        do {
          id = 'le-flow-heading-' + sectionIndex + '-' + headingCount++;
        } while (usedIds[id]);
        heading.setAttribute('id', id);
        usedIds[id] = true;
      }
      var level = Math.max(0, Math.min(5, (parseInt(String(heading.tagName || 'H1').slice(1), 10) || 1) - 1));
      toc.push({
        id: 'flow-toc-' + toc.length,
        label: label,
        href: 'flow-section-' + sectionIndex + '#' + encodeURIComponent(id),
        level: level,
        kind: 'toc'
      });
    });
    Array.prototype.slice.call(root.querySelectorAll('[id],[name]')).forEach(function (el) {
      registerFoliateFlowId(idIndex, el.getAttribute('id'), sectionIndex);
      registerFoliateFlowId(idIndex, el.getAttribute('name'), sectionIndex);
    });
    return root.innerHTML;
  });
  if (meta && Array.isArray(meta.toc) && meta.toc.length) toc = meta.toc;
  return {
    sectionHtmls: prepared,
    idIndex: idIndex,
    toc: toc
  };
}
export function findFoliateFlowAnchor(doc, id) {
  if (!doc) return null;
  var raw = decodeFoliateFlowFragment(id);
  if (!raw) return doc.body || doc.documentElement;
  var found = null;
  try {
    found = doc.getElementById(raw);
  } catch (_idErr) {
    found = null;
  }
  if (found) return found;
  var nodes = doc.querySelectorAll ? doc.querySelectorAll('[name]') : [];
  for (var i = 0; i < nodes.length; i++) {
    if (String(nodes[i].getAttribute('name') || '') === raw) return nodes[i];
  }
  return doc.body || doc.documentElement;
}
export function makeFoliateFlowHtmlDocument(sectionHtml, meta, sectionIndex, totalSections) {
  var dir = /^(ar|fa|he|ur|ps|sd|ug|dv)\b/i.test(String(documentShellState.currentLanguage || ''))
    ? 'rtl'
    : 'ltr';
  var title = escapeHtml(String((meta && (meta.title || meta.fileName)) || 'Document'));
  var bodyClass =
    'foliate-flow-body foliate-flow-' +
    String((meta && meta.format) || 'document')
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, '-');
  return [
    '<!doctype html>',
    '<html dir="' + dir + '">',
    '<head>',
    '<meta charset="utf-8">',
    '<title>' + title + '</title>',
    '<style>',
    'html,body{margin:0;padding:0;background:#fff;color:#111827;}',
    'body{box-sizing:border-box;padding:24px;font:16px/1.58 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}',
    'p{margin:0 0 .85em 0;} h1,h2,h3,h4,h5,h6{line-height:1.25;margin:.8em 0 .45em;}',
    'ul,ol{margin:.4em 0 .9em 1.4em;padding:0;} li{margin:.2em 0;}',
    'table{border-collapse:collapse;max-width:100%;margin:.75em 0;} td,th{padding:.25em .5em;vertical-align:top;}',
    'img{max-width:100%;height:auto;} .docrender-txt{white-space:normal;}',
    '.mammoth-docx{max-width:100%;} .mammoth-docx p{margin:0 0 .75em 0;}',
    '.mammoth-all-caps{text-transform:uppercase;} .mammoth-small-caps{font-variant:small-caps;}',
    'mark{background:#fef08a;color:inherit;padding:0 .08em;border-radius:2px;}',
    '</style>',
    '</head>',
    '<body class="' + bodyClass + '">',
    '<main data-flow-section="' +
      Math.max(0, sectionIndex || 0) +
      '" data-flow-section-count="' +
      Math.max(1, totalSections || 1) +
      '">',
    String(sectionHtml || ''),
    '</main>',
    '</body></html>'
  ].join('');
}
export function makeFoliateFlowBook(sectionHtmls, meta) {
  sectionHtmls = normalizeFoliateFlowSections(sectionHtmls, '', meta || {});
  var prepared = prepareFoliateFlowBookData(sectionHtmls, meta || {});
  sectionHtmls = prepared.sectionHtmls;
  var idIndex = prepared.idIndex || {};
  var destroyed = false;
  function rewriteFoliateFlowSectionHref(href, sectionIndex) {
    var raw = String(href || '').trim();
    var idx = Math.max(0, Math.floor(Number(sectionIndex) || 0));
    if (!raw || /^(https?:|mailto:|tel:)/i.test(raw)) return raw;
    if (/^flow-section-\d+(?:#.*)?$/.test(raw)) return raw;
    if (raw.charAt(0) === '#') {
      var localFragment = raw.slice(1);
      var localTarget = idIndex[decodeFoliateFlowFragment(localFragment)] || idIndex[localFragment];
      return (
        'flow-section-' +
        (localTarget ? localTarget.index : idx) +
        '#' +
        encodeURIComponent(localTarget ? localTarget.id : decodeFoliateFlowFragment(localFragment))
      );
    }
    var hashIndex = raw.indexOf('#');
    if (hashIndex >= 0) {
      var fragment = raw.slice(hashIndex + 1);
      var target = idIndex[decodeFoliateFlowFragment(fragment)] || idIndex[fragment];
      return (
        'flow-section-' +
        (target ? target.index : idx) +
        '#' +
        encodeURIComponent(target ? target.id : decodeFoliateFlowFragment(fragment))
      );
    }
    var indexed = idIndex[decodeFoliateFlowFragment(raw)] || idIndex[raw];
    if (indexed) return 'flow-section-' + indexed.index + '#' + encodeURIComponent(indexed.id);
    return raw;
  }
  var records = sectionHtmls.map(function (sectionHtml, idx) {
    var html = makeFoliateFlowHtmlDocument(sectionHtml, meta || {}, idx, sectionHtmls.length);
    var url = null;
    return {
      id: 'flow-section-' + idx,
      size: Math.max(1, html.length),
      linear: 'yes',
      resolveHref: function (href) {
        return rewriteFoliateFlowSectionHref(href, idx);
      },
      load: function () {
        if (!url)
          url = URL.createObjectURL(
            new Blob([html], {
              type: 'text/html;charset=utf-8'
            })
          );
        return url;
      },
      unload: function () {
        if (url) {
          URL.revokeObjectURL(url);
          url = null;
        }
      },
      createDocument: function () {
        return new DOMParser().parseFromString(html, 'text/html');
      },
      destroy: function () {
        if (url) {
          URL.revokeObjectURL(url);
          url = null;
        }
      }
    };
  });
  function clampSectionIndex(idx) {
    idx = Math.floor(Number(idx) || 0);
    return Math.max(0, Math.min(records.length - 1, idx));
  }
  function anchorForFragment(fragment) {
    var id = decodeFoliateFlowFragment(fragment);
    return id
      ? function (doc) {
          return findFoliateFlowAnchor(doc, id);
        }
      : 0;
  }
  function targetForSectionAndFragment(idx, fragment) {
    return {
      index: clampSectionIndex(idx),
      anchor: fragment ? anchorForFragment(fragment) : 0,
      fragment: fragment ? decodeFoliateFlowFragment(fragment) : null
    };
  }
  function normalizeFoliateFlowHref(href, defaultSectionIndex) {
    var raw = String(href || '').trim();
    var fallbackIndex = defaultSectionIndex == null ? 0 : clampSectionIndex(defaultSectionIndex);
    if (!raw) return targetForSectionAndFragment(fallbackIndex, null);
    if (/^(https?:|mailto:|tel:)/i.test(raw)) return raw;
    var m = raw.match(/^flow-section-(\d+)(?:#(.+))?$/);
    if (m) return targetForSectionAndFragment(parseInt(m[1], 10), m[2] || null);
    var hashIndex = raw.indexOf('#');
    if (hashIndex >= 0) {
      var fragment = raw.slice(hashIndex + 1);
      var target = idIndex[decodeFoliateFlowFragment(fragment)] || idIndex[fragment];
      return targetForSectionAndFragment(
        target ? target.index : fallbackIndex,
        target ? target.id : fragment
      );
    }
    var indexed = idIndex[decodeFoliateFlowFragment(raw)] || idIndex[raw];
    if (indexed) return targetForSectionAndFragment(indexed.index, indexed.id);
    return targetForSectionAndFragment(fallbackIndex, null);
  }
  return {
    dir: /^(ar|fa|he|ur|ps|sd|ug|dv)\b/i.test(String(documentShellState.currentLanguage || ''))
      ? 'rtl'
      : 'ltr',
    metadata: {
      title: String((meta && (meta.title || meta.fileName)) || 'Document'),
      language: String(documentShellState.currentLanguage || '')
    },
    sections: records,
    toc: prepared.toc || [],
    pageList: Array.isArray(meta && meta.pageList) ? meta.pageList : [],
    resolveHref: function (href) {
      return normalizeFoliateFlowHref(href, 0);
    },
    splitTOCHref: function (href) {
      var target = normalizeFoliateFlowHref(href, 0);
      if (typeof target === 'string') return [(records[0] && records[0].id) || 'flow-section-0', null];
      var idx = clampSectionIndex(target && target.index);
      return [records[idx].id, (target && target.fragment) || null];
    },
    getTOCFragment: function (doc, id) {
      return findFoliateFlowAnchor(doc, id);
    },
    isExternal: function (href) {
      return /^(https?:|mailto:|tel:)/i.test(String(href || ''));
    },
    destroy: function () {
      if (destroyed) return;
      destroyed = true;
      records.forEach(function (record) {
        try {
          record.destroy();
        } catch (_recordDestroyErr) {}
      });
    }
  };
}
export function canonicalPageFromFoliateRange() {
  return null;
}
export function emptyCanonicalPage(index, meta, size) {
  var b = new window.CanonicalBuilder.Builder(
    Object.assign({}, meta || {}, {
      parser: 'foliate-empty-page'
    })
  );
  b.startPage({
    layout: {
      mode: 'flow',
      width: size && size.width,
      height: size && size.height
    }
  });
  var p = b.finish().pages[0];
  p.index = index;
  p.id = 'foliate-flow-page-' + index;
  return p;
}
export function updateFoliateFlowLocation(detail) {
  if (!isActiveFoliateFlowDocument()) return;
  detail = detail || (documentState.epubJsRendition && documentState.epubJsRendition.lastLocation) || {};
  var renderer = getFoliateEpubRenderer();
  var sectionIndex = foliateCurrentSectionIndex();
  var sectionPageCount = foliateVisualPageCount();
  var sectionPageIndex = foliateVisualPageIndex();
  if (documentState.foliateFullPaginationReady) {
    var total = Math.max(1, Math.ceil(recomputeFoliateFlowSectionStarts()));
    var current = foliateFlowGlobalPageIndex(sectionIndex, sectionPageIndex);
    current = Math.max(0, Math.min(total - 1, Math.floor(current)));
    documentState.foliateFlowTotalPages = total;
    documentState.epubJsTotalPages = total;
    documentState.epubJsCurrentPageNum = current;
    documentState.activePageIndex = current;
    if (!documentState.docPages || documentState.docPages.length !== total)
      documentState.docPages = new Array(total).fill('');
    documentState.epubJsPageLabel = 'Page ' + (current + 1) + ' / ' + total;
  } else {
    documentState.foliateFlowTotalPages = 1;
    documentState.epubJsTotalPages = 1;
    documentState.epubJsCurrentPageNum = 0;
    documentState.activePageIndex = 0;
    documentState.epubJsPageLabel = 'Paginating...';
  }
  try {
    documentState.epubJsCanGoPrev = renderer ? !renderer.atStart : documentState.activePageIndex > 0;
    documentState.epubJsCanGoNext = renderer
      ? !renderer.atEnd
      : documentState.activePageIndex < documentState.epubJsTotalPages - 1;
  } catch (_navErr) {
    documentState.epubJsCanGoPrev = documentState.activePageIndex > 0;
    documentState.epubJsCanGoNext = documentState.activePageIndex < documentState.epubJsTotalPages - 1;
  }
  documentState.foliateFlowLabel = currentFoliateFlowFormatLabel();
  syncDocumentChrome();
}
export function foliateFlowGoToPage(pageIndex) {
  if (!isActiveFoliateFlowDocument()) return Promise.resolve(false);
  if (!documentState.foliateFullPaginationReady) return Promise.resolve(false);
  var target = foliateFlowResolvePageIndex(pageIndex);
  var frac = target.sectionPageCount > 1 ? target.sectionPageIndex / (target.sectionPageCount - 1) : 0;
  return Promise.resolve(
    documentState.epubJsRendition.renderer.goTo({
      index: target.sectionIndex,
      anchor: frac
    })
  ).then(function () {
    updateFoliateFlowLocation();
    return true;
  });
}
export function foliateFlowStepPage(delta) {
  if (!isActiveFoliateFlowDocument() || !documentState.epubJsRendition) return Promise.resolve(false);
  var dir = Number(delta) || 0;
  var fn = dir > 0 ? documentState.epubJsRendition.next : documentState.epubJsRendition.prev;
  if (typeof fn !== 'function')
    return foliateFlowGoToPage((documentState.activePageIndex || 0) + (dir > 0 ? 1 : -1));
  return Promise.resolve(fn.call(documentState.epubJsRendition)).then(function () {
    updateFoliateFlowLocation();
    return true;
  });
}
export function buildFoliateRectSliceState(extraMeta) {
  if (!window.DocRenderWebSnapshotRenderer) return null;
  var ctx = getFoliateEpubSliceContext();
  if (!ctx || !ctx.doc) return null;
  var iframeWin = ctx.doc.defaultView;
  if (!iframeWin) return null;
  var size = getEpubViewportSize();
  var pageW = Math.max(1, ctx.pageW || size.width);
  var pageH = Math.max(1, ctx.pageH || size.height);
  return {
    doc: ctx.doc,
    win: iframeWin,
    iframe: ctx.iframe || null,
    viewportClip: ctx.viewportClip || null,
    pageWidth: pageW,
    pageHeight: pageH,
    meta: Object.assign({}, documentState.docrenderMeta || {}, extraMeta || {})
  };
}
export function initializeFoliateSlices() {
  foliateSlicesState.FOLIATE_FLOW_SECTION_CHAR_LIMIT = 18000;
  return true;
}
