/* canonical_renderer.js
 *
 * Renders an AnnotatedCanonicalPage into the bottom lookup window.
 * It creates fresh app-owned DOM, preserving canonical text styles while
 * wrapping token spans for the existing dictionary/grammar UI.
 *
 * Browser global:
 *   window.CanonicalRenderer
 */
(function(global) {
  'use strict';

  function requireDeps() {
    if (!global.CanonicalModel || !global.CanonicalStyle) {
      throw new Error('CanonicalModel and CanonicalStyle must be loaded before CanonicalRenderer');
    }
  }

  function str(v) { return v == null ? '' : String(v); }
  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) ? n : (fallback || 0);
  }
  function clamp(v, lo, hi) {
    v = num(v, lo);
    return Math.max(lo, Math.min(hi, v));
  }

  function createEl(tag, cls) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    return el;
  }

  function tokenClass(token, opts) {
    var cls = ['reader-token', 'canonical-token'];
    if (token.upos) cls.push('upos-' + String(token.upos).toLowerCase().replace(/[^a-z0-9_-]+/g, '-'));
    if (token.ner) cls.push('has-ner');
    if (token.fillHits && token.fillHits.length) cls.push('has-fill-hits');
    if (opts && typeof opts.tokenClass === 'function') {
      var extra = opts.tokenClass(token);
      if (extra) cls.push(extra);
    }
    return cls.join(' ');
  }

  function stampTokenMetadata(el, token) {
    if (!el || !token) return el;
    el.dataset.index = String(token.index);
    el.dataset.tokenIndex = String(token.index);
    el.dataset.seg = token.segment || token.text || '';
    el.dataset.canonicalStart = String(token.start);
    el.dataset.canonicalEnd = String(token.end);
    if (token.lemma) el.dataset.lemma = token.lemma;
    if (token.upos) el.dataset.upos = token.upos;
    if (token.xpos) el.dataset.xpos = token.xpos;
    if (token.fillHits && token.fillHits.length) el.dataset.hasFillHits = '1';
    if (token.ner) el.dataset.hasNer = '1';
    if (token.ud && token.ud.id != null) el.dataset.udId = String(token.ud.id);
    applyMwtSurfaceMismatchMetadata(el, token);
    return el;
  }

  var ZERO_WIDTH_JOINER_RE = /[\u200C\u200D]/g;

  function normalizeVisibleComparisonText(raw) {
    var text = str(raw).replace(ZERO_WIDTH_JOINER_RE, '').trim();
    if (text.normalize) {
      try { text = text.normalize('NFKC'); } catch (_e) {}
    }
    return text.trim();
  }

  function hasSameVisibleComparisonText(left, right) {
    return normalizeVisibleComparisonText(left) === normalizeVisibleComparisonText(right);
  }

  function tokenUd(token) {
    if (!token || typeof token !== 'object') return null;
    if (token.ud && typeof token.ud === 'object') return token.ud;
    if (token.udTok && typeof token.udTok === 'object') return token.udTok;
    if (token.posData && token.posData.udTok && typeof token.posData.udTok === 'object') return token.posData.udTok;
    return null;
  }

  function surfaceAnchorFromToken(token) {
    var ud = tokenUd(token);
    var anchor = ud && ud.surface_anchor;
    if (!anchor && token && token.surface_anchor) anchor = token.surface_anchor;
    if (!anchor && token && token.surfaceAnchor) anchor = token.surfaceAnchor;
    if (!anchor && token && token.dictEntry && token.dictEntry.surface_anchor) anchor = token.dictEntry.surface_anchor;
    if (!anchor || typeof anchor !== 'object') return null;
    var text = str(anchor.text || anchor.surface || anchor.surfaceText || '').trim();
    if (!text) return null;
    return { text: text, raw: anchor };
  }

  function mwtChildTextFromToken(token) {
    var ud = tokenUd(token);
    var raw = token && (
      token.mwtChildText ||
      token.lookupText ||
      token.expandedText ||
      token.childText ||
      (ud && (ud.text || ud.form)) ||
      token.text ||
      token.segment
    );
    return str(raw).trim();
  }

  function mwtPartIndexFromToken(token) {
    var ud = tokenUd(token);
    var raw = token && (
      token.mwtPartIndex != null ? token.mwtPartIndex :
      token.mwt_part_index != null ? token.mwt_part_index :
      ud && ud.mwt_part_index != null ? ud.mwt_part_index :
      ud && ud.partIndex != null ? ud.partIndex :
      0
    );
    var idx = parseInt(raw, 10);
    return isFinite(idx) && idx >= 0 ? idx : 0;
  }

  function clearMwtSurfaceMismatchMetadata(el) {
    if (!el || !el.dataset) return;
    delete el.dataset.mwtAnchor;
    delete el.dataset.mwtPartIndex;
    delete el.dataset.mwtMismatch;
    delete el.dataset.mwtChildText;
    delete el.dataset.mwtSurfaceSlice;
    delete el.dataset.mwtPopupReason;
    if (el.classList) el.classList.remove('has-mwt-surface-mismatch');
  }

  function applyMwtSurfaceMismatchMetadata(el, token) {
    if (!el || !el.dataset || !token) return false;
    var anchor = surfaceAnchorFromToken(token);
    var childText = mwtChildTextFromToken(token);
    var surfaceText = anchor ? str(anchor.text).trim() : '';
    if (!surfaceText || !childText || hasSameVisibleComparisonText(surfaceText, childText)) {
      clearMwtSurfaceMismatchMetadata(el);
      return false;
    }
    el.dataset.mwtAnchor = '1';
    el.dataset.mwtPartIndex = String(mwtPartIndexFromToken(token));
    el.dataset.mwtMismatch = '1';
    el.dataset.mwtChildText = childText;
    el.dataset.mwtSurfaceSlice = surfaceText;
    el.dataset.mwtPopupReason = 'surface_anchor';
    if (el.classList) el.classList.add('has-mwt-surface-mismatch');
    return true;
  }

  function decorateTokenEl(el, token, opts) {
    el.className = tokenClass(token, opts);
    stampTokenMetadata(el, token);
    if (opts && typeof opts.decorateTokenEl === 'function') opts.decorateTokenEl(el, token);
    return el;
  }

  function fillHitsInsideToken(token) {
    var result = token && token.dictEntry;
    if (result && Array.isArray(result.dict_fill_surface_slices)) return result.dict_fill_surface_slices;
    if (result && Array.isArray(result.fillHits)) return result.fillHits;
    if (token && Array.isArray(token.fillHits)) return token.fillHits;
    return null;
  }

  function parseFillIndexes(slice) {
    var out = [];
    var seen = Object.create(null);
    if (!slice) return out;
    var raw = null;
    if (Array.isArray(slice.fillIndexes)) raw = slice.fillIndexes;
    else if (Array.isArray(slice.fill_indexes)) raw = slice.fill_indexes;
    else if (slice.fillIndex != null) raw = [slice.fillIndex];
    else if (slice.fill_index != null) raw = [slice.fill_index];
    else raw = [];
    for (var i = 0; i < raw.length; i++) {
      var n = parseInt(raw[i], 10);
      if (!isFinite(n) || n < 0 || seen[n]) continue;
      seen[n] = true;
      out.push(n);
    }
    return out;
  }

  function normalizeFillSlices(token) {
    var raw = fillHitsInsideToken(token);
    if (!raw || !raw.length) return null;
    var tokenText = str(token && (token.text || token.segment));
    var len = tokenText.length;
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var sl = raw[i] || {};
      var start = Number(sl.start != null ? sl.start : sl[0]);
      var end = Number(sl.end != null ? sl.end : sl[1]);
      if (!isFinite(start) || !isFinite(end)) continue;
      start = Math.max(0, Math.min(len, start));
      end = Math.max(start, Math.min(len, end));
      if (end <= start) continue;
      out.push({
        start: start,
        end: end,
        fillIndexes: parseFillIndexes(sl),
        raw: sl
      });
    }
    out.sort(function(a, b) {
      return a.start - b.start || a.end - b.end;
    });
    return out.length ? out : null;
  }

  function fillHeadForIndexes(token, indexes) {
    var dictFill = token && token.dictEntry && Array.isArray(token.dictEntry.dict_fill) ? token.dictEntry.dict_fill : [];
    var entry = indexes && indexes.length ? dictFill[indexes[0]] : null;
    return entry ? str(entry.head || entry.headword || entry.text || '') : '';
  }

  function setFillHitDataset(hit, token, slice, pieceText) {
    var indexes = Array.isArray(slice && slice.fillIndexes) ? slice.fillIndexes : [];
    hit.dataset.fillIndexes = indexes.join(',');
    if (indexes.length === 1) hit.dataset.fillIndex = String(indexes[0]);
    hit.dataset.fillText = str(token && (token.text || token.segment)).slice(slice.start, slice.end);
    hit.dataset.fillFragmentText = pieceText;
    hit.dataset.fillStart = String(slice.start);
    hit.dataset.fillEnd = String(slice.end);
    var head = fillHeadForIndexes(token, indexes);
    if (head) hit.dataset.fillHead = head;
    return hit;
  }

  function clearTokenChildren(el) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function appendProjectedFillHitContent(span, token, fragmentText, fragmentStart, fragmentEnd) {
    var slices = normalizeFillSlices(token);
    if (!slices || !slices.length) {
      span.textContent = fragmentText;
      return false;
    }
    clearTokenChildren(span);
    var cursor = 0;
    var renderedAny = false;
    for (var i = 0; i < slices.length; i++) {
      var sl = slices[i];
      var ovStart = Math.max(sl.start, fragmentStart);
      var ovEnd = Math.min(sl.end, fragmentEnd);
      if (ovEnd <= ovStart) continue;
      var localStart = Math.max(0, ovStart - fragmentStart);
      var localEnd = Math.max(localStart, ovEnd - fragmentStart);
      if (localStart > cursor) {
        span.appendChild(document.createTextNode(fragmentText.slice(cursor, localStart)));
      }
      var piece = fragmentText.slice(localStart, localEnd);
      var hit = createEl('span', 'reader-token-fill-hit');
      hit.textContent = piece;
      setFillHitDataset(hit, token, sl, piece);
      hit.dataset.fillFragmentStart = String(ovStart);
      hit.dataset.fillFragmentEnd = String(ovEnd);
      span.appendChild(hit);
      cursor = localEnd;
      renderedAny = true;
    }
    if (cursor < fragmentText.length) span.appendChild(document.createTextNode(fragmentText.slice(cursor)));
    if (renderedAny) span.dataset.hasFillHits = '1';
    return renderedAny;
  }

  function renderPlainToken(token, text, opts) {
    var span = createEl('span');
    span.textContent = text;
    decorateTokenEl(span, token, opts);
    return span;
  }

  function renderTokenWithFillHits(token, text, opts, ctx) {
    ctx = ctx || {};
    var tokenStart = num(token && token.start, 0);
    var fragmentStart = Math.max(0, num(ctx.segmentStart, tokenStart) - tokenStart);
    var fragmentEnd = fragmentStart + str(text).length;
    var slices = normalizeFillSlices(token);
    if (!slices || !slices.length) return renderPlainToken(token, text, opts);
    var span = createEl('span');
    decorateTokenEl(span, token, opts);
    appendProjectedFillHitContent(span, token, str(text), fragmentStart, fragmentEnd);
    return span;
  }

  function buildHostTokenElement(token, text, opts, ctx) {
    if (!opts || typeof opts.buildTokenElement !== 'function') return null;
    var built = opts.buildTokenElement(token, text, ctx || {});
    return built && built.nodeType ? built : (built && built.span && built.span.nodeType ? built.span : null);
  }

  function stampCanonicalFragment(el, token, fragmentText, ctx) {
    var tokenStart = num(token && token.start, 0);
    var globalStart = num(ctx && ctx.segmentStart, tokenStart);
    var globalEnd = num(ctx && ctx.segmentEnd, globalStart + str(fragmentText).length);
    var localStart = Math.max(0, globalStart - tokenStart);
    var localEnd = Math.max(localStart, globalEnd - tokenStart);
    if (!el.classList.contains('reader-token')) el.classList.add('reader-token');
    el.classList.add('canonical-token', 'canonical-token-fragment');
    stampTokenMetadata(el, token);
    el.dataset.canonicalFragmentStart = String(globalStart);
    el.dataset.canonicalFragmentEnd = String(globalEnd);
    el.dataset.tokenFragmentStart = String(localStart);
    el.dataset.tokenFragmentEnd = String(localEnd);
    el.dataset.tokenFragmentText = str(fragmentText);
    if (localStart === 0) el.dataset.tokenFragmentRole = 'first';
    else delete el.dataset.tokenFragmentRole;
    return { localStart: localStart, localEnd: localEnd };
  }

  function renderToken(token, text, opts, ctx) {
    opts = opts || {};
    ctx = ctx || {};
    var isWholeToken = ctx.segmentStart === token.start && ctx.segmentEnd === token.end;
    if (isWholeToken) {
      var el = buildHostTokenElement(token, text, opts, ctx);
      if (el) {
        // Preserve canonical metadata even when the host app supplies its own token span builder.
        el.classList.add('canonical-token');
        stampTokenMetadata(el, token);
        return el;
      }
      return renderTokenWithFillHits(token, text, opts, ctx);
    }

    var fullText = str(token && (token.text || token.segment));
    var fragmentEl = buildHostTokenElement(token, fullText, opts, Object.assign({}, ctx, {
      isTokenFragment: true,
      fragmentText: text
    }));
    if (!fragmentEl) fragmentEl = createEl('span');
    var fragmentInfo = stampCanonicalFragment(fragmentEl, token, text, ctx);
    appendProjectedFillHitContent(fragmentEl, token, str(text), fragmentInfo.localStart, fragmentInfo.localEnd);
    if (!fragmentEl.childNodes || !fragmentEl.childNodes.length) {
      fragmentEl.textContent = str(text);
    }
    return fragmentEl;
  }

  function tokensIntersecting(tokens, start, end) {
    var out = [];
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.end <= start || t.start >= end) continue;
      out.push(t);
    }
    out.sort(function(a, b) { return a.start - b.start || a.end - b.end; });
    return out;
  }

  function styleSegmentsForRun(run) {
    var raw = Array.isArray(run && run.styleSegments)
      ? run.styleSegments
      : (Array.isArray(run && run.source && run.source.styleSegments) ? run.source.styleSegments : []);
    var maxLen = str(run && run.text).length;
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var seg = raw[i] || {};
      var start = clamp(seg.start, 0, maxLen);
      var end = clamp(seg.end, start, maxLen);
      if (end <= start) continue;
      out.push({
        start: start,
        end: end,
        style: seg.style || {}
      });
    }
    out.sort(function(a, b) { return a.start - b.start || a.end - b.end; });
    return out;
  }

  function pieceStyleHasCss(style) {
    if (!style || !global.CanonicalStyle || typeof global.CanonicalStyle.styleToCssObject !== 'function') return false;
    var obj = global.CanonicalStyle.styleToCssObject(style);
    var keys = Object.keys(obj);
    for (var i = 0; i < keys.length; i++) {
      if (keys[i] !== 'whiteSpace' && obj[keys[i]]) return true;
    }
    return false;
  }

  function applyRunPieceStyleToElement(el, style) {
    if (!el || el.nodeType !== 1 || !pieceStyleHasCss(style)) return el;
    if (!global.CanonicalStyle || typeof global.CanonicalStyle.styleToCssObject !== 'function') return el;
    var obj = global.CanonicalStyle.styleToCssObject(style);
    Object.keys(obj).forEach(function(k) {
      if (k === 'whiteSpace') return;
      try { el.style[k] = obj[k]; } catch (_e) {}
    });
    return el;
  }

  function styledTextNode(text, style) {
    text = str(text);
    if (!text) return null;
    if (!pieceStyleHasCss(style)) return document.createTextNode(text);
    var span = createEl('span', 'canonical-run-style-piece');
    applyRunPieceStyleToElement(span, style);
    span.textContent = text;
    return span;
  }

  function appendRunRangeWithPieceStyles(parent, run, localStart, localEnd, buildNode) {
    var segments = styleSegmentsForRun(run);
    if (!segments.length) {
      var plain = buildNode(localStart, localEnd, null);
      if (plain) parent.appendChild(plain);
      return;
    }
    var cursor = localStart;
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      if (seg.end <= cursor || seg.start >= localEnd) continue;
      if (seg.start > cursor) {
        var gapEnd = Math.min(seg.start, localEnd);
        var gapNode = buildNode(cursor, gapEnd, null);
        if (gapNode) parent.appendChild(gapNode);
        cursor = gapEnd;
      }
      var s = Math.max(cursor, seg.start, localStart);
      var e = Math.min(localEnd, seg.end);
      if (e > s) {
        var node = buildNode(s, e, seg.style || {});
        if (node) parent.appendChild(node);
        cursor = e;
      }
      if (cursor >= localEnd) break;
    }
    if (cursor < localEnd) {
      var tail = buildNode(cursor, localEnd, null);
      if (tail) parent.appendChild(tail);
    }
  }

  function renderRun(run, page, opts) {
    var runSpan = createEl('span', 'canonical-run');
    global.CanonicalStyle.applyStyleToElement(runSpan, run.style || {});
    if (run.source && run.source.synthetic && /separator/i.test(String(run.source.kind || ''))) {
      runSpan.classList.add('canonical-hidden-separator');
      runSpan.setAttribute('aria-hidden', 'true');
    }
    if (run.layout && run.layout.mode === 'fixed') {
      runSpan.classList.add('canonical-run-fixed');
      if (run.layout.x != null) runSpan.style.left = Number(run.layout.x || 0) + 'px';
      if (run.layout.y != null) runSpan.style.top = Number(run.layout.y || 0) + 'px';
      if (run.layout.width != null) {
        var layoutWidth = Math.max(0, Number(run.layout.width || 0));
        runSpan.style.width = layoutWidth + 'px';
        runSpan.dataset.layoutWidth = String(layoutWidth);
      }
      if (run.layout.height != null) runSpan.style.height = Number(run.layout.height || 0) + 'px';
      if (run.layout.transform) {
        runSpan.style.transform = run.layout.transform;
        runSpan.dataset.baseTransform = run.layout.transform;
      }
      var skipFitWidth = !!(run.layout.skipFitWidth || run.source && run.source.skipFitWidth);
      if (!skipFitWidth && run.layout.fitWidth != null) {
        runSpan.dataset.fitWidth = String(Number(run.layout.fitWidth || 0));
      } else if (!skipFitWidth && isWebRectSlicePage(page) && run.layout.width != null) {
        runSpan.dataset.fitWidth = String(Math.max(1, Number(run.layout.width || 0)));
      }
      runSpan.style.position = 'absolute';
      runSpan.style.whiteSpace = 'pre';
      runSpan.style.overflowWrap = 'normal';
      runSpan.style.wordBreak = 'normal';
      runSpan.style.maxWidth = 'none';
    }
    var text = str(run.text);
    var tokens = tokensIntersecting(page.tokens || [], run.start, run.end);
    var localCursor = 0;
    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i];
      var s = Math.max(run.start, tok.start) - run.start;
      var e = Math.min(run.end, tok.end) - run.start;
      if (s > localCursor) {
        appendRunRangeWithPieceStyles(runSpan, run, localCursor, s, function(ps, pe, style) {
          return styledTextNode(text.slice(ps, pe), style);
        });
      }
      appendRunRangeWithPieceStyles(runSpan, run, s, e, function(ps, pe, style) {
        var tokText = text.slice(ps, pe);
        var tokEl = renderToken(tok, tokText, opts, {
          page: page,
          run: run,
          segmentStart: run.start + ps,
          segmentEnd: run.start + pe,
          localStart: ps,
          localEnd: pe
        });
        return applyRunPieceStyleToElement(tokEl, style);
      });
      localCursor = e;
    }
    if (localCursor < text.length) {
      appendRunRangeWithPieceStyles(runSpan, run, localCursor, text.length, function(ps, pe, style) {
        return styledTextNode(text.slice(ps, pe), style);
      });
    }
    return runSpan;
  }

  function blockClass(block) {
    return 'canonical-block canonical-block-' + String(block.type || 'paragraph').replace(/[^a-z0-9_-]+/gi, '-');
  }

  function applyBlockLayout(el, block) {
    var layout = block.layout || {};
    var style = block.style || {};
    if (layout.mode === 'fixed') {
      el.classList.add('canonical-block-fixed');
      el.style.position = 'absolute';
      if (layout.x != null) el.style.left = Number(layout.x || 0) + 'px';
      if (layout.y != null) el.style.top = Number(layout.y || 0) + 'px';
      if (layout.width != null) el.style.width = Number(layout.width || 0) + 'px';
      if (layout.height != null) el.style.height = Number(layout.height || 0) + 'px';
    }
    if (layout.textAlign || style.textAlign) el.style.textAlign = layout.textAlign || style.textAlign;
    if (layout.marginTop) el.style.marginTop = layout.marginTop;
    if (layout.marginBottom) el.style.marginBottom = layout.marginBottom;
    if (layout.marginLeft) el.style.marginLeft = layout.marginLeft;
    if (layout.marginRight) el.style.marginRight = layout.marginRight;
    if (layout.paddingLeft) el.style.paddingLeft = layout.paddingLeft;
    if (layout.textIndent) el.style.textIndent = layout.textIndent;
    if (layout.direction || style.direction) el.style.direction = layout.direction || style.direction;
    if (block.type === 'separator') el.classList.add('canonical-separator-block');
  }

  function renderBlock(block, page, opts) {
    var el = createEl('div', blockClass(block));
    el.dataset.blockId = block.id || '';
    el.dataset.canonicalStart = String(block.start || 0);
    el.dataset.canonicalEnd = String(block.end || 0);
    global.CanonicalStyle.applyStyleToElement(el, block.style || {});
    applyBlockLayout(el, block);
    var runs = block.runs || [];
    for (var i = 0; i < runs.length; i++) el.appendChild(renderRun(runs[i], page, opts));
    return el;
  }

  function targetWidth(target) {
    if (!target) return 0;
    var rect = target.getBoundingClientRect ? target.getBoundingClientRect() : null;
    return num(target.clientWidth, 0) || num(rect && rect.width, 0) || 0;
  }

  function isWebRectSlicePage(page) {
    return String(page && page.source && page.source.kind || '') === 'webSnapshotRectSlice';
  }

  function appendWebRectSlicePage(root, page, target, opts) {
    opts = opts || {};
    var layout = page.layout || {};
    var w = Math.max(1, num(layout.width, 0));
    var h = Math.max(1, num(layout.height, 0));

    target.classList.add('canonical-web-rect-slice-active');
    target.style.position = 'relative';

    root.classList.add('canonical-page-web-rect-slice');
    root.style.position = 'relative';
    root.style.left = '0';
    root.style.top = '0';
    root.style.width = w + 'px';
    root.style.minWidth = w + 'px';
    root.style.height = 'auto';
    root.style.minHeight = h + 'px';
    root.style.margin = '0';
    root.style.border = '0';
    root.style.outline = '0';
    root.style.boxShadow = 'none';
    root.style.background = 'transparent';
    root.style.transformOrigin = '0 0';
    root.style.transform = 'none';
    root.style.overflow = 'hidden';
    var pageDir = (opts.direction === 'rtl') ? 'rtl' : 'ltr';
    root.style.direction = pageDir;
    root.style.textAlign = (pageDir === 'rtl') ? 'right' : 'left';
    root.style.unicodeBidi = 'isolate';
    root.dataset.scale = '1';

    target.appendChild(root);
    return root;
  }

  function appendFixedPage(root, page, target, opts) {
    opts = opts || {};
    var layout = page.layout || {};
    var w = Math.max(1, num(layout.width, 0));
    var h = Math.max(1, num(layout.height, 0));
    var available = targetWidth(target);
    var scale = opts.fixedScale != null ? num(opts.fixedScale, 1) : (available > 0 ? available / w : 1);
    var sourceKind = String(page && page.source && page.source.kind || '');
    var defaultMaxScale = /webSnapshot/i.test(sourceKind) ? 1 : 4;
    scale = clamp(scale, opts.minFixedScale != null ? opts.minFixedScale : 0.2, opts.maxFixedScale != null ? opts.maxFixedScale : defaultMaxScale);
    var wrap = createEl('div', 'canonical-page-fixed-wrap');
    wrap.style.width = (w * scale) + 'px';
    wrap.style.height = (h * scale) + 'px';
    wrap.style.maxWidth = '100%';
    wrap.style.overflow = 'hidden';
    wrap.dataset.pageWidth = String(w);
    wrap.dataset.pageHeight = String(h);
    wrap.dataset.scale = String(scale);
    root.style.position = 'absolute';
    root.style.left = '0';
    root.style.top = '0';
    root.style.width = w + 'px';
    root.style.height = h + 'px';
    root.style.margin = '0';
    root.style.transformOrigin = '0 0';
    root.style.transform = 'scale(' + scale + ')';
    var pageDir = (opts.direction === 'rtl') ? 'rtl' : 'ltr';
    root.style.direction = pageDir;
    root.style.textAlign = (pageDir === 'rtl') ? 'right' : 'left';
    root.style.unicodeBidi = 'isolate';
    wrap.appendChild(root);
    target.appendChild(wrap);
    return wrap;
  }

  function measureNaturalRunWidth(span) {
    if (!span) return 0;
    var oldWidth = span.style.width;
    var oldTransform = span.style.transform;
    var oldWhiteSpace = span.style.whiteSpace;
    var oldOverflowWrap = span.style.overflowWrap;
    var oldWordBreak = span.style.wordBreak;
    var base = span.dataset.baseTransform || '';
    span.style.width = 'auto';
    span.style.transform = base;
    span.style.whiteSpace = 'pre';
    span.style.overflowWrap = 'normal';
    span.style.wordBreak = 'normal';
    var measured = num(span.scrollWidth, 0);
    if (!measured && span.getBoundingClientRect) measured = num(span.getBoundingClientRect().width, 0);
    span.style.width = oldWidth;
    span.style.transform = oldTransform;
    span.style.whiteSpace = oldWhiteSpace;
    span.style.overflowWrap = oldOverflowWrap;
    span.style.wordBreak = oldWordBreak;
    return measured;
  }

  function fitFixedTextRuns(root) {
    if (!root || !root.querySelectorAll) return;
    var spans = root.querySelectorAll('.canonical-run-fixed[data-fit-width]');
    for (var i = 0; i < spans.length; i++) {
      var span = spans[i];
      var target = num(span.dataset.fitWidth, 0);
      if (target <= 0) continue;
      var natural = measureNaturalRunWidth(span);
      if (!natural || natural <= 0) continue;
      var allowance = target;
      var base = span.dataset.baseTransform || '';
      span.style.transformOrigin = '0 0';
      if (natural <= allowance) {
        span.style.transform = base;
        span.style.width = Math.max(num(span.dataset.layoutWidth, target), target) + 'px';
        delete span.dataset.fitScaleX;
        continue;
      }
      var scaleX = allowance / natural;
      if (!isFinite(scaleX) || scaleX <= 0) continue;
      scaleX = clamp(scaleX, 0.1, 10);
      span.style.transform = (base ? (base + ' ') : '') + 'scaleX(' + scaleX + ')';
      span.dataset.fitScaleX = scaleX.toFixed(6);
    }
  }

  function renderPage(page, target, opts) {
    requireDeps();
    opts = opts || {};
    if (!page) throw new Error('renderPage requires a CanonicalPage');
    if (!target) throw new Error('renderPage requires a target element');
    global.CanonicalModel.assertPageInvariant(page, 'render page');
    target.innerHTML = '';
    target.classList.add('canonical-reader-active');
    target.classList.remove('plain-text-mode', 'docx-original-view', 'docrender-active');
    target.style.position = 'relative';
    target.style.overflow = 'visible';
    target.style.overflowX = 'visible';
    target.style.overflowY = 'visible';
    var root = createEl('div', 'canonical-page');
    root.dataset.pageIndex = String(page.index || 0);
    root.dataset.pageId = page.id || '';
    root.dataset.canonicalLength = String((page.text || '').length);
    if (page.layout && page.layout.mode === 'fixed') {
      root.classList.add('canonical-page-fixed');
      if (page.layout.width) root.style.width = Number(page.layout.width) + 'px';
      if (page.layout.height) root.style.height = Number(page.layout.height) + 'px';
    } else {
      root.classList.add('canonical-page-flow');
    }
    var blocks = page.blocks || [];
    for (var i = 0; i < blocks.length; i++) root.appendChild(renderBlock(blocks[i], page, opts));
    if (isWebRectSlicePage(page)) {
      appendWebRectSlicePage(root, page, target, opts);
      fitFixedTextRuns(root);
    } else if (page.layout && page.layout.mode === 'fixed') {
      target.classList.remove('canonical-web-rect-slice-active');
      appendFixedPage(root, page, target, opts);
      fitFixedTextRuns(root);
    } else {
      target.classList.remove('canonical-web-rect-slice-active');
      target.appendChild(root);
    }
    if (typeof opts.afterRender === 'function') opts.afterRender({ page: page, target: target, root: root });
    return root;
  }

  global.CanonicalRenderer = {
    renderPage: renderPage,
    renderBlock: renderBlock,
    renderRun: renderRun,
    fitFixedTextRuns: fitFixedTextRuns,
    decorateTokenEl: decorateTokenEl
  };
})(window);
