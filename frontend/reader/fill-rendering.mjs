import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { shouldInsertSpace } from './document-import.mjs';
import { isMyanmarPunctToken, needsDottedCircle } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  applyKoreanCompoundLemmaSpawnAttrs,
  applySurfaceAnchorMismatchAttrs,
  clearSurfaceAnchorMismatchAttrs,
  getKoreanCompoundLemmaSpawnParts,
  getUdTokenSurfaceAnchor,
  isSurfaceAnchorPopupOnlyToken
} from './entry-editing.mjs';
import {
  appendUniqueFillIndexes,
  buildDictFillSlicesForToken,
  buildForcedProjectedDictFillSlices,
  coalesceMarkOnlyFillSlices,
  getDictFillSurfaceText,
  isMarkOnlySliceText,
  parseFillHitIndexes
} from './fill-slices.mjs';
import { clearMwtPartAnchors, registerMwtPartAnchors } from './mwt-anchors.mjs';
import { getEntryDisplayHead, getGrammarColor, stripZeroWidthJoiners } from './presentation.mjs';
import { registerTokenSpan } from './token-fragments.mjs';
export function buildExactDictFillSlicesForToken(seg, dictFill, providedSlices) {
  if (!seg || !Array.isArray(dictFill) || dictFill.length < 2) return null;
  var slices = [];
  var lastEnd = 0;
  if (Array.isArray(providedSlices) && providedSlices.length) {
    for (var i = 0; i < providedSlices.length; i++) {
      var raw = providedSlices[i] || {};
      var start = parseInt(raw.start, 10);
      var end = parseInt(raw.end, 10);
      if (!isFinite(start) || !isFinite(end) || start < 0 || end > seg.length || end <= start) return null;
      if (start < lastEnd) return null;
      var indexes = parseFillHitIndexes(
        {
          dataset: {
            fillIndexes: Array.isArray(raw.fill_indexes)
              ? raw.fill_indexes.join(',')
              : String(raw.fill_indexes || '')
          }
        },
        dictFill.length
      );
      if (!indexes.length && raw.fill_index != null) {
        indexes = parseFillHitIndexes(
          {
            dataset: {
              fillIndex: String(raw.fill_index)
            }
          },
          dictFill.length
        );
      }
      if (!indexes.length) return null;
      slices.push({
        start: start,
        end: end,
        fillIndexes: indexes
      });
      lastEnd = end;
    }
    return coalesceMarkOnlyFillSlices(seg, slices);
  }
  var pendingLeading = [];
  var exactSlices = [];
  var cursor = 0;
  var segLower = seg.toLowerCase();
  for (var fi = 0; fi < dictFill.length; fi++) {
    var fillText = String((dictFill[fi] && (dictFill[fi].text || dictFill[fi].head)) || '');
    if (!fillText) continue;
    if (isMarkOnlySliceText(fillText)) {
      pendingLeading.push(fi);
      continue;
    }
    var idx = segLower.indexOf(fillText.toLowerCase(), cursor);
    if (idx < 0) return null;
    var nextSlice = {
      start: idx,
      end: idx + fillText.length,
      fillIndexes: [fi]
    };
    if (pendingLeading.length) {
      nextSlice.fillIndexes = appendUniqueFillIndexes(pendingLeading.slice(), nextSlice.fillIndexes);
      pendingLeading = [];
    }
    exactSlices.push(nextSlice);
    cursor = nextSlice.end;
  }
  if (pendingLeading.length) {
    if (exactSlices.length) {
      appendUniqueFillIndexes(exactSlices[exactSlices.length - 1].fillIndexes, pendingLeading);
    } else {
      return null;
    }
  }
  return exactSlices.length ? exactSlices : null;
}
export function buildAppendedFillHitParts(dictFill) {
  if (!Array.isArray(dictFill) || !dictFill.length) return [];
  var parts = [];
  var pendingZeroWidth = [];
  for (var i = 0; i < dictFill.length; i++) {
    var fillEntry = dictFill[i] || {};
    var rawText = String(getDictFillSurfaceText(fillEntry) || '');
    var displayText = stripZeroWidthJoiners(rawText);
    var visibleText = String(displayText || rawText || getEntryDisplayHead(fillEntry, '') || '');
    if (!visibleText && isMarkOnlySliceText(rawText)) {
      pendingZeroWidth.push(i);
      continue;
    }
    if (!visibleText) visibleText = String(getEntryDisplayHead(fillEntry, '') || '');
    if (!visibleText) visibleText = rawText;
    if (!visibleText) visibleText = '\u25CC';
    var fillIndexes = [i];
    if (pendingZeroWidth.length) {
      fillIndexes = appendUniqueFillIndexes(pendingZeroWidth.slice(), fillIndexes);
      pendingZeroWidth = [];
    }
    parts.push({
      text: visibleText,
      fillIndexes: fillIndexes,
      fillHead: String(fillEntry.head != null ? fillEntry.head : fillEntry.text != null ? fillEntry.text : '')
    });
  }
  if (pendingZeroWidth.length) {
    if (parts.length) {
      appendUniqueFillIndexes(parts[parts.length - 1].fillIndexes, pendingZeroWidth);
    } else {
      for (var zi = 0; zi < pendingZeroWidth.length; zi++) {
        parts.push({
          text: '\u25CC',
          fillIndexes: [pendingZeroWidth[zi]],
          fillHead: ''
        });
      }
    }
  }
  return parts;
}
export function applyInvisibleDictFillHitTargets(span, seg, dictFill, providedSlices) {
  if (!span) return false;
  var hasProvidedSlices = Array.isArray(providedSlices) && providedSlices.length > 0;
  var slices = buildDictFillSlicesForToken(seg, dictFill, providedSlices, {
    coalesceMarkOnly: true
  });
  if ((!slices || !slices.length) && hasProvidedSlices) {
    // The lookup pipeline already decided the spans. If those exact slices are
    // unavailable/invalid here, do not invent new placements downstream.
    return false;
  }
  // Fallback: case-insensitive sequential match of fill piece texts against surface
  if (!slices || !slices.length) {
    var fallbackSlices = [];
    var fallbackCursor = 0;
    var segLower = seg.toLowerCase();
    for (var fbi = 0; fbi < dictFill.length; fbi++) {
      var fbText = String((dictFill[fbi] && (dictFill[fbi].text || dictFill[fbi].head)) || '');
      if (!fbText) continue;
      var fbIdx = segLower.indexOf(fbText.toLowerCase(), fallbackCursor);
      if (fbIdx < 0) {
        fallbackSlices = [];
        break;
      }
      fallbackSlices.push({
        start: fbIdx,
        end: fbIdx + fbText.length,
        fillIndexes: [fbi]
      });
      fallbackCursor = fbIdx + fbText.length;
    }
    if (fallbackSlices.length) slices = fallbackSlices;
  }
  if ((!slices || !slices.length) && Array.isArray(dictFill) && dictFill.length >= 2) {
    slices = buildForcedProjectedDictFillSlices(seg, dictFill);
  }
  if (!slices || !slices.length) return false;
  var frag = document.createDocumentFragment();
  var cursor = 0;
  for (var i = 0; i < slices.length; i++) {
    var slice = slices[i];
    if (slice.start > cursor) {
      frag.appendChild(document.createTextNode(seg.slice(cursor, slice.start)));
    }
    var partText = seg.slice(slice.start, slice.end);
    var fillIndexes = Array.isArray(slice.fillIndexes) ? slice.fillIndexes.slice() : [];
    var fillEntry = fillIndexes.length ? dictFill[fillIndexes[0]] || {} : {};
    var hit = document.createElement('span');
    hit.className = 'reader-token-fill-hit';
    hit.dataset.fillIndexes = fillIndexes.join(',');
    if (fillIndexes.length === 1) hit.dataset.fillIndex = String(fillIndexes[0]);
    hit.dataset.fillText = partText;
    if (fillEntry.head != null) {
      hit.dataset.fillHead = String(fillEntry.head);
    } else if (fillEntry.text != null) {
      hit.dataset.fillHead = String(fillEntry.text);
    }
    hit.textContent = partText;
    frag.appendChild(hit);
    cursor = slice.end;
  }
  if (cursor < seg.length) {
    frag.appendChild(document.createTextNode(seg.slice(cursor)));
  }
  span.textContent = '';
  span.appendChild(frag);
  span.dataset.hasFillHits = '1';
  return true;
}
export function buildTokenSpan(i, seg, gramOverlay, resultsBySeg, udTokenMap, opts) {
  var span = document.createElement('span');
  span.className = 'reader-token';
  span.dataset.index = String(i);
  span.dataset.seg = seg;
  var options = opts || {};
  var lightweight = options.lightweight === true;
  var noMwtSideEffects = options.noMwtSideEffects === true;
  // Myanmar punctuation tokens (၊/။) are kept for UD sentence boundaries but are non-interactive.
  if (isMyanmarPunctToken(seg)) {
    span.textContent = seg;
    span.classList.add('reader-punct');
    span.dataset.punct = '1';
    return {
      span: span,
      hasGrammar: false,
      isUnknown: false
    };
  }
  var needsDotted = needsDottedCircle(seg);
  // Tokens without a base consonant (bare diacritics, or only stacked consonants)
  // still get a dotted circle for display, but we no longer force them unknown.
  if (needsDotted) {
    span.textContent = documentShellState.DOTTED_CIRCLE + seg;
    span.classList.add('damaged-token');
    span.dataset.damaged = '1';
    span.dataset.originalSeg = seg;
    // Continue so dict_fill can decide known/unknown.
  }
  var hasGrammar = false,
    isUnknown = false;
  var tInfo = gramOverlay[i] || {};
  var entries = Array.isArray(tInfo.grammar) ? tInfo.grammar : [];
  if (entries.length) {
    // Prefer a non-UNKNOWN entry if available
    var chosen =
      entries.find(function (e) {
        return e && e.type && e.type !== 'UNKNOWN';
      }) || entries[0];
    var type = chosen.type || chosen.category || 'MISC_FUNC';
    if (
      dependencyPopupState.displaySettings.grammarTypes &&
      dependencyPopupState.displaySettings.grammarTypes[type]
    ) {
      var color = getGrammarColor(type);
      span.classList.add('grammar-token');
      span.dataset.grammarType = type;
      span.style.borderBottom = '2px solid ' + color;
      span.style.paddingBottom = '2px';
      hasGrammar = true;
    }
  }
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
  var udTok =
    udTokenMap && udTokenMap[i]
      ? udTokenMap[i]
      : dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[i]
        ? dependencyState.latestUdTokenMap[i]
        : null;
  var res = resultsBySeg && resultsBySeg[i] ? resultsBySeg[i] : null;
  if (window.LE_READER_SHOWCASE_MODE && res && res._showcase_inert_punct) {
    span.textContent = seg;
    span.classList.add('reader-punct');
    span.dataset.punct = '1';
    if (!noMwtSideEffects) clearMwtPartAnchors(i);
    clearSurfaceAnchorMismatchAttrs(span);
    return {
      span: span,
      hasGrammar: false,
      isUnknown: false
    };
  }
  if (res) {
    var fillHasKnown = typeof res.dict_fill_has_known === 'boolean' ? res.dict_fill_has_known : false;
    var fillHasUnknown = typeof res.dict_fill_has_unknown === 'boolean' ? res.dict_fill_has_unknown : false;
    var dictFill = Array.isArray(res.dict_fill) ? res.dict_fill : [];
    // Back-compat: infer fill coverage if flags are missing
    if (
      (typeof res.dict_fill_has_known !== 'boolean' || typeof res.dict_fill_has_unknown !== 'boolean') &&
      dictFill.length
    ) {
      for (var pi = 0; pi < dictFill.length; pi++) {
        if (isUnknownEntry(dictFill[pi])) fillHasUnknown = true;
        else fillHasKnown = true;
      }
    }
    // Last-resort: old heuristic on the token itself
    if (!fillHasKnown && !fillHasUnknown) {
      var pos = (res.pos || '').toLowerCase();
      var senses = res.senses || [];
      var looksUnknown =
        pos.indexOf('unknown') >= 0 ||
        (senses.length === 1 &&
          typeof senses[0] === 'string' &&
          senses[0].toLowerCase().indexOf('no dictionary entry') >= 0);
      if (looksUnknown) fillHasUnknown = true;
      else fillHasKnown = true;
    }

    // Mark token unknown if any fill is unknown; visual rendering remains token-level.
    if (fillHasUnknown) isUnknown = true;
    var popupOnlySurfaceAnchor = isSurfaceAnchorPopupOnlyToken(seg, udTok);
    var popupOnlySurfaceText = popupOnlySurfaceAnchor
      ? String((getUdTokenSurfaceAnchor(udTok) || {}).text || '').trim()
      : '';
    var tokenDisplayText = popupOnlySurfaceText || seg;
    if (lightweight) {
      span.textContent =
        !popupOnlySurfaceText && needsDotted ? documentShellState.DOTTED_CIRCLE + seg : tokenDisplayText;
      if (!(udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length)) {
        if (!applySurfaceAnchorMismatchAttrs(span, seg, udTok)) {
          applyKoreanCompoundLemmaSpawnAttrs(span, seg, res, udTok);
        }
      }
      if (fillHasUnknown && !fillHasKnown) {
        span.classList.add('unknown-token');
      }
      return {
        span: span,
        hasGrammar: hasGrammar,
        isUnknown: isUnknown
      };
    }
    var koreanCompoundSpawnParts = getKoreanCompoundLemmaSpawnParts(seg, res, udTok);
    var hasKoreanCompoundSpawn = koreanCompoundSpawnParts.length > 0;

    // Keep token visuals unchanged, but add invisible per-fill hit targets for multi-fill tokens.
    var renderedWithFillHits = false;
    if (!hasKoreanCompoundSpawn && !needsDotted && dictFill.length > 1 && !popupOnlySurfaceAnchor) {
      var dictFillSurfaceSlices = Array.isArray(res.dict_fill_surface_slices)
        ? res.dict_fill_surface_slices
        : null;
      renderedWithFillHits = applyInvisibleDictFillHitTargets(span, seg, dictFill, dictFillSurfaceSlices);
    }
    if (!renderedWithFillHits) {
      span.textContent =
        !popupOnlySurfaceText && needsDotted ? documentShellState.DOTTED_CIRCLE + seg : tokenDisplayText;
    }
    if (!noMwtSideEffects && udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length) {
      registerMwtPartAnchors(i, span, res, udTok);
      delete span.dataset.koCompoundLemmaSpawn;
      delete span.dataset.koCompoundLemmaParts;
    } else {
      if (!noMwtSideEffects) clearMwtPartAnchors(i);
      if (!applySurfaceAnchorMismatchAttrs(span, seg, udTok)) {
        if (hasKoreanCompoundSpawn) {
          span.dataset.koCompoundLemmaSpawn = '1';
          span.dataset.koCompoundLemmaParts = JSON.stringify(koreanCompoundSpawnParts);
        } else {
          applyKoreanCompoundLemmaSpawnAttrs(span, seg, res, udTok);
        }
      }
    }
    if (fillHasUnknown && !fillHasKnown) {
      span.classList.add('unknown-token');
    }
  } else {
    if (!noMwtSideEffects) clearMwtPartAnchors(i);
    clearSurfaceAnchorMismatchAttrs(span);
    span.textContent = needsDotted ? documentShellState.DOTTED_CIRCLE + seg : seg;
    span.classList.add('unknown-token');
    isUnknown = true;
  }
  return {
    span: span,
    hasGrammar: hasGrammar,
    isUnknown: isUnknown
  };
}

// Merge consecutive pdf-text-item text nodes with no pdf-sep (whitespace separator) between them
// into a single text node so that applyOffsetsAsTokenSpansOnDom can create whole-word token spans
// instead of per-character fragments (which happens for Arabic/Persian glyph-level PDF items).
export function rebuildPdfWordSpansFromTextRuns(root, textRuns) {
  if (!root || !textRuns || !textRuns.length) return textRuns;
  if (!root.querySelector || !root.querySelector('.pdf-text-item')) return textRuns;
  var newRuns = [];
  var i = 0;
  while (i < textRuns.length) {
    var run = textRuns[i];
    if (!run || !run.node) {
      newRuns.push(run);
      i++;
      continue;
    }
    var parentEl = run.node.parentNode;
    if (!parentEl || !parentEl.classList || !parentEl.classList.contains('pdf-text-item')) {
      newRuns.push(run);
      i++;
      continue;
    }
    var groupStart = run.start;
    var groupEnd = run.end;
    var groupText = run.node.nodeValue || '';
    var lastParent = parentEl;
    var j = i + 1;
    while (j < textRuns.length) {
      var nextRun = textRuns[j];
      if (!nextRun || !nextRun.node) break;
      var nextParent = nextRun.node.parentNode;
      if (!nextParent || !nextParent.classList || !nextParent.classList.contains('pdf-text-item')) break;

      // Walk siblings from lastParent to nextParent; any pdf-sep between them means a word boundary
      var hasSep = false;
      var sib = lastParent.nextSibling;
      while (sib && sib !== nextParent) {
        if (sib.nodeType === 1 && sib.classList && sib.classList.contains('pdf-sep')) {
          hasSep = true;
          break;
        }
        sib = sib.nextSibling;
      }
      if (hasSep || sib !== nextParent) break;
      groupEnd = nextRun.end;
      groupText += nextRun.node.nodeValue || '';
      lastParent = nextParent;
      j++;
    }
    if (j === i + 1) {
      newRuns.push(run);
      i++;
      continue;
    }

    // Merge: put all text in the first node, empty the rest
    run.node.nodeValue = groupText;
    for (var k = i + 1; k < j; k++) {
      if (textRuns[k] && textRuns[k].node) textRuns[k].node.nodeValue = '';
    }
    newRuns.push({
      node: run.node,
      start: groupStart,
      end: groupEnd
    });
    i = j;
  }
  return newRuns;
}

// Annotate raw PDF word spans with segment/NLP data
export function annotateRawWordSpans(
  wordSpans,
  pdfWords,
  segments,
  segmentOffsets,
  resultsBySeg,
  gramOverlay,
  udTokenMap,
  pageData
) {
  if (!wordSpans || !segments || !segmentOffsets) return;

  // Build word offsets using SAME iteration order as buildLayoutTextFromWords()
  // This must match exactly for character-level mapping to work
  var wordOffsets = [];
  var charPos = 0;
  var structuredBlocks =
    pageData && Array.isArray(pageData.structured_blocks) ? pageData.structured_blocks : null;
  var words = pageData && Array.isArray(pageData.words) ? pageData.words : pdfWords;
  if (structuredBlocks && structuredBlocks.length > 0) {
    // Sort blocks by Y position - MUST match buildLayoutTextFromWords and render loop
    var sortedBlocks = structuredBlocks.slice().sort(function (a, b) {
      return (a.min_y || 0) - (b.min_y || 0);
    });
    var spanIdx = 0;
    for (var bi = 0; bi < sortedBlocks.length; bi++) {
      if (bi > 0) charPos += 2; // '\n\n' paragraph break
      var block = sortedBlocks[bi];
      var lines = block.lines || [];
      for (var li = 0; li < lines.length; li++) {
        if (li > 0) charPos += 1; // '\n' line break
        var lineWords = lines[li].words || [];
        // Sort words by X within line - MUST match buildLayoutTextFromWords
        var sortedWords = lineWords.slice().sort(function (a, b) {
          return (a.x || 0) - (b.x || 0);
        });
        for (var wi = 0; wi < sortedWords.length; wi++) {
          var w = sortedWords[wi];
          if (!w || !w.text) {
            wordOffsets.push(null);
            spanIdx++;
            continue;
          }
          if (shouldInsertSpace(w, wi)) charPos += 1; // space between words
          var wtext = String(w.text);
          wordOffsets.push([charPos, charPos + wtext.length]);
          charPos += wtext.length;
          spanIdx++;
        }
      }
    }
  } else if (words && words.length > 0) {
    // Fallback: group words by Y, sort by X within each line
    // Compute median height
    var medianH = 12;
    var allHeights = [];
    for (var wi = 0; wi < words.length; wi++) {
      if (words[wi] && words[wi].h > 0) allHeights.push(words[wi].h);
    }
    if (allHeights.length) {
      allHeights.sort(function (a, b) {
        return a - b;
      });
      var mid = Math.floor(allHeights.length / 2);
      medianH = allHeights.length % 2 ? allHeights[mid] : (allHeights[mid - 1] + allHeights[mid]) / 2;
    }

    // Group words into lines by Y
    var lineGroups = [];
    var currentLineY = -999;
    var currentLineWords = [];
    for (var wi = 0; wi < words.length; wi++) {
      var w = words[wi];
      if (!w || !w.text) continue;
      var y = typeof w.y === 'number' ? w.y : 0;
      var h = typeof w.h === 'number' && w.h > 0 ? w.h : medianH;
      if (currentLineY >= 0 && Math.abs(y - currentLineY) > h * 0.5) {
        if (currentLineWords.length > 0) {
          lineGroups.push({
            y: currentLineY,
            words: currentLineWords
          });
        }
        currentLineWords = [];
      }
      currentLineWords.push(w);
      currentLineY = y;
    }
    if (currentLineWords.length > 0) {
      lineGroups.push({
        y: currentLineY,
        words: currentLineWords
      });
    }

    // Sort lines by Y
    lineGroups.sort(function (a, b) {
      return a.y - b.y;
    });

    // Build offsets: lines separated by \n, words sorted by X and separated by space
    for (var li = 0; li < lineGroups.length; li++) {
      if (li > 0) charPos += 1; // '\n' line break
      var lineWords = lineGroups[li].words;
      // Sort words by X within line
      lineWords.sort(function (a, b) {
        return (a.x || 0) - (b.x || 0);
      });
      for (var wi = 0; wi < lineWords.length; wi++) {
        var w = lineWords[wi];
        if (shouldInsertSpace(w, wi)) charPos += 1; // space between words
        var wtext = String(w.text);
        wordOffsets.push([charPos, charPos + wtext.length]);
        charPos += wtext.length;
      }
    }
  }

  // For each segment, find which word(s) it overlaps and apply annotations
  for (var si = 0; si < segments.length; si++) {
    var off = segmentOffsets[si];
    if (!off || off.length < 2) continue;
    var segStart = Number(off[0]);
    var segEnd = Number(off[1]);
    if (!isFinite(segStart) || !isFinite(segEnd)) continue;

    // Find all words this segment overlaps
    for (var wi = 0; wi < wordOffsets.length; wi++) {
      var woff = wordOffsets[wi];
      if (!woff) continue;
      var wStart = Number(woff[0]);
      var wEnd = Number(woff[1]);

      // Check overlap
      if (segStart < wEnd && segEnd > wStart) {
        var segText = String(segments[si] || '');
        var wordSpan = wordSpans[wi];
        if (!wordSpan) continue;

        // Persist the word's character-offset span in the synthetic layout text.
        // This is critical for mapping multiple Burmese segments back onto a single PDF "word" span.
        if (wordSpan.dataset.wordStart == null) wordSpan.dataset.wordStart = String(wStart);
        if (wordSpan.dataset.wordEnd == null) wordSpan.dataset.wordEnd = String(wEnd);

        // Apply grammar overlay if present
        if (gramOverlay && Array.isArray(gramOverlay)) {
          for (var gi = 0; gi < gramOverlay.length; gi++) {
            var gramToken = gramOverlay[gi];
            if (gramToken && gramToken.seg_i === si) {
              var posTag = gramToken.pos || '';
              if (posTag) {
                wordSpan.classList.add('pos-' + posTag);
                wordSpan.dataset.pos = posTag;
              }
            }
          }
        }

        // Apply known/unknown status from dictionary results
        if (resultsBySeg && resultsBySeg[si]) {
          var res = resultsBySeg[si];
          var hasKnown = typeof res.dict_fill_has_known === 'boolean' ? res.dict_fill_has_known : false;
          var dictFill = Array.isArray(res.dict_fill) ? res.dict_fill : [];
          if (!hasKnown && dictFill.length) hasKnown = true;
          if (hasKnown) {
            wordSpan.classList.add('seg-known');
          } else {
            wordSpan.classList.add('seg-unknown');
          }
        }

        // Make raw PDF span participate in the normal token UI by giving it the same hooks
        // the hover/click/overlay code expects.
        wordSpan.classList.add('reader-token');
        wordSpan.style.cursor = 'pointer';

        // Choose a canonical segment index for this span (used as a fallback when we can't resolve
        // which sub-segment within an island the pointer is on).
        if (!wordSpan.dataset.index || Number(si) < Number(wordSpan.dataset.index)) {
          wordSpan.dataset.index = String(si);
          wordSpan.dataset.seg = String(segments[si] || '');
        }

        // Ensure UD overlay / NER / dependency line rendering can locate an element for EACH segment.
        // In original PDF view, multiple segments may map to the same DOM span; that's fine.
        if (!dependencyState.udTokenIndex.has(si)) {
          registerTokenSpan(si, wordSpan);
        }

        // Store segment reference on the word span
        if (!wordSpan.dataset.segments) {
          wordSpan.dataset.segments = '';
        }
        if (!wordSpan.dataset.segments.includes(String(si))) {
          wordSpan.dataset.segments += (wordSpan.dataset.segments ? ',' : '') + String(si);
        }
      }
    }
  }

  // Second pass: split each absolute-positioned PDF word span into multiple interactive segment spans.
  // This is the key step that makes hover popups and overlays work properly when Burmese "islands" contain
  // multiple segmentation tokens.
  for (var wi2 = 0; wi2 < wordSpans.length; wi2++) {
    var ws = wordSpans[wi2];
    if (!ws) continue;
    var segCsv = ws.dataset.segments || '';
    if (!segCsv) continue;
    var wStart2 = parseInt(ws.dataset.wordStart || 'NaN', 10);
    var wEnd2 = parseInt(ws.dataset.wordEnd || 'NaN', 10);
    if (!isFinite(wStart2) || !isFinite(wEnd2) || wEnd2 <= wStart2) continue;
    var wText = ws.textContent || '';
    if (!wText) continue;
    var segList2 = segCsv
      .split(',')
      .map(function (x) {
        return parseInt(x, 10);
      })
      .filter(function (n) {
        return isFinite(n) && n >= 0;
      });
    if (!segList2.length) continue;

    // Sort by segment start offset
    segList2.sort(function (a, b) {
      var oa = segmentOffsets[a] || [0, 0];
      var ob = segmentOffsets[b] || [0, 0];
      return Number(oa[0]) - Number(ob[0]);
    });

    // Rebuild the content as a mixture of plain text nodes and interactive token spans
    var frag2 = document.createDocumentFragment();
    var cursor2 = 0;
    for (var si3 = 0; si3 < segList2.length; si3++) {
      var sIdx = segList2[si3];
      var off3 = segmentOffsets[sIdx];
      if (!off3 || off3.length < 2) continue;
      var s0 = Number(off3[0]);
      var s1 = Number(off3[1]);
      if (!isFinite(s0) || !isFinite(s1)) continue;

      // Local indices within this word's text
      var local0 = s0 - wStart2;
      var local1 = s1 - wStart2;
      if (local1 <= 0 || local0 >= wText.length) continue;
      if (local0 < 0) local0 = 0;
      if (local1 > wText.length) local1 = wText.length;

      // Fill any gap between previous piece and this segment
      if (local0 > cursor2) {
        frag2.appendChild(document.createTextNode(wText.slice(cursor2, local0)));
      }

      // Only build a full token span when the substring matches the segment text.
      // If it doesn't match (rare, usually due to synthetic whitespace/newlines), fall back to plain text.
      var piece = wText.slice(local0, local1);
      var segText = String(segments[sIdx] || '');
      var canBuildFullToken = piece && segText && piece === segText;
      if (canBuildFullToken) {
        var built = buildTokenSpan(sIdx, segText, gramOverlay || [], resultsBySeg || [], udTokenMap || {});
        frag2.appendChild(built.span);
        registerTokenSpan(sIdx, built.span);
      } else {
        var fallback = document.createElement('span');
        fallback.className = 'reader-token';
        fallback.dataset.index = String(sIdx);
        fallback.dataset.seg = segText || piece;
        fallback.textContent = piece;
        frag2.appendChild(fallback);
        registerTokenSpan(sIdx, fallback);
      }
      cursor2 = local1;
    }
    if (cursor2 < wText.length) {
      frag2.appendChild(document.createTextNode(wText.slice(cursor2)));
    }

    // The outer span is only a positioned container now; the real interactive spans are children.
    ws.classList.remove('reader-token');
    ws.style.cursor = 'default';
    ws.textContent = '';
    ws.appendChild(frag2);
  }
}
export function annotatePdfJsTextLayerSpans(
  wordSpans,
  segments,
  segmentOffsets,
  resultsBySeg,
  gramOverlay,
  udTokenMap
) {
  if (!wordSpans || !wordSpans.length || !segments || !segmentOffsets) return;

  // Merge consecutive glyph-level spans that contain no whitespace into word-level spans.
  // This prevents Arabic/Persian/other scripts from getting per-character token fragments.
  var spanArray = Array.prototype.slice.call(wordSpans);
  var mergedSpans = [];
  var mi = 0;
  while (mi < spanArray.length) {
    var msp = spanArray[mi];
    var mTxt = msp ? msp.textContent || '' : '';
    if (!mTxt || /\s/.test(mTxt) || !msp) {
      if (msp) mergedSpans.push(msp);
      mi++;
      continue;
    }
    var group = [msp];
    var gi = mi + 1;
    while (gi < spanArray.length) {
      var nsp = spanArray[gi];
      var nTxt = nsp ? nsp.textContent || '' : '';
      if (!nTxt || /\s/.test(nTxt)) break;
      group.push(nsp);
      gi++;
    }
    if (group.length > 1) {
      var combined = group
        .map(function (s) {
          return s.textContent || '';
        })
        .join('');
      msp.textContent = combined;
      for (var gk = 1; gk < group.length; gk++) group[gk].textContent = '';
    }
    mergedSpans.push(msp);
    mi = gi;
  }
  wordSpans = mergedSpans;
  var spanOffsets = [];
  var charPos = 0;
  for (var wi = 0; wi < wordSpans.length; wi++) {
    var ws = wordSpans[wi];
    if (!ws) continue;
    var txt = ws.textContent || '';
    var start = charPos;
    charPos += txt.length;
    spanOffsets.push([start, charPos]);
    ws.dataset.wordStart = String(start);
    ws.dataset.wordEnd = String(charPos);
    ws.dataset.segments = '';
  }
  for (var si = 0; si < segments.length; si++) {
    var off = segmentOffsets[si];
    if (!off || off.length < 2) continue;
    var segStart = Number(off[0]);
    var segEnd = Number(off[1]);
    if (!isFinite(segStart) || !isFinite(segEnd)) continue;
    var segText = String(segments[si] || '');
    for (var wi2 = 0; wi2 < wordSpans.length; wi2++) {
      var spanOff = spanOffsets[wi2];
      if (!spanOff) continue;
      var wStart = spanOff[0];
      var wEnd = spanOff[1];
      if (!(segStart < wEnd && segEnd > wStart)) continue;
      var wordSpan = wordSpans[wi2];
      if (!wordSpan) continue;
      if (!wordSpan.dataset.index || Number(si) < Number(wordSpan.dataset.index)) {
        wordSpan.dataset.index = String(si);
        wordSpan.dataset.seg = segText;
      }
      if (!wordSpan.dataset.segments) wordSpan.dataset.segments = '';
      if (!wordSpan.dataset.segments.includes(String(si))) {
        wordSpan.dataset.segments += (wordSpan.dataset.segments ? ',' : '') + String(si);
      }
      wordSpan.classList.add('reader-token');
      if (!dependencyState.udTokenIndex.has(si)) registerTokenSpan(si, wordSpan);
    }
  }
  for (var wi3 = 0; wi3 < wordSpans.length; wi3++) {
    var ws2 = wordSpans[wi3];
    if (!ws2) continue;
    var segCsv = ws2.dataset.segments || '';
    if (!segCsv) continue;
    var wStart2 = parseInt(ws2.dataset.wordStart || 'NaN', 10);
    var wEnd2 = parseInt(ws2.dataset.wordEnd || 'NaN', 10);
    if (!isFinite(wStart2) || !isFinite(wEnd2) || wEnd2 <= wStart2) continue;
    var wText = ws2.textContent || '';
    if (!wText) continue;
    var segList = segCsv
      .split(',')
      .map(function (x) {
        return parseInt(x, 10);
      })
      .filter(function (n) {
        return isFinite(n) && n >= 0;
      });
    if (!segList.length) continue;
    segList.sort(function (a, b) {
      var oa = segmentOffsets[a] || [0, 0];
      var ob = segmentOffsets[b] || [0, 0];
      return Number(oa[0]) - Number(ob[0]);
    });
    var frag = document.createDocumentFragment();
    var cursor = 0;
    for (var si2 = 0; si2 < segList.length; si2++) {
      var sIdx = segList[si2];
      var off2 = segmentOffsets[sIdx];
      if (!off2 || off2.length < 2) continue;
      var s0 = Number(off2[0]);
      var s1 = Number(off2[1]);
      if (!isFinite(s0) || !isFinite(s1)) continue;
      var local0 = s0 - wStart2;
      var local1 = s1 - wStart2;
      if (local1 <= 0 || local0 >= wText.length) continue;
      if (local0 < 0) local0 = 0;
      if (local1 > wText.length) local1 = wText.length;
      if (local0 > cursor) frag.appendChild(document.createTextNode(wText.slice(cursor, local0)));
      var piece = wText.slice(local0, local1);
      var segText2 = String(segments[sIdx] || '');
      var canBuildFullToken = piece && segText2 && piece === segText2;
      if (canBuildFullToken) {
        var built = buildTokenSpan(sIdx, segText2, gramOverlay || [], resultsBySeg || [], udTokenMap || {});
        frag.appendChild(built.span);
        registerTokenSpan(sIdx, built.span);
      } else {
        var fallback = document.createElement('span');
        fallback.className = 'reader-token';
        fallback.dataset.index = String(sIdx);
        fallback.dataset.seg = segText2 || piece;
        fallback.textContent = piece;
        frag.appendChild(fallback);
        registerTokenSpan(sIdx, fallback);
      }
      cursor = local1;
    }
    if (cursor < wText.length) frag.appendChild(document.createTextNode(wText.slice(cursor)));
    ws2.classList.remove('reader-token');
    ws2.textContent = '';
    ws2.appendChild(frag);
  }
}
