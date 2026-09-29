import {
  expandHighlightSetForCollapsedSpans,
  getCanonicalSegIdx,
  getConnectedIslandGroup,
  getIslandSpanForSeg
} from './dependency-geometry.mjs';
import {
  clearBottomUpCascadeCache,
  clearBottomUpChunkCache,
  clearContextWindowCache,
  drawUdLinesForToken,
  getActiveBottomUpTokens,
  getContextWindowTokens,
  normalizeUdPartIndex
} from './dependency-hover.mjs';
import { ensureLmWeightsInitialized } from './dependency-popup.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getOrderedCompoundLemmaTexts } from './entry-editing.mjs';
import {
  _surfaceHasGlossableChar,
  buildCompoundLlmGlossEntry,
  mergeLlmGlossEntries
} from './gloss-entries.mjs';
import { glossRequestsState } from './gloss-requests.state.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { getLiveHoveredMwtPartIdx, getMwtPartsForSeg } from './mwt-context.mjs';
import { _refreshLlmGlossUI, ensureFuzzySettingsInitialized } from './orthography.mjs';
import { getHighlightTargetsForSeg, getNerLabelForSeg, nerLabelToUpos } from './token-fragments.mjs';
import { getTokenMapLemmaPartTexts } from './token-map.mjs';
export // Get chunk color based on POS
function getChunkColor(pos) {
  return dependencyPopupState.CHUNK_POS_COLORS[pos] || dependencyPopupState.CHUNK_POS_COLORS['DEFAULT'];
}
export function uposColorForTag(upos) {
  var key = (upos || '').toUpperCase();
  return dependencyPopupState.CHUNK_POS_COLORS[key] && dependencyPopupState.CHUNK_POS_COLORS[key].bg
    ? dependencyPopupState.CHUNK_POS_COLORS[key].bg
    : '#e5e7eb';
}

// Get all chunks a token belongs to (sorted by depth, shallowest first)
export function getChunksForToken(seg) {
  if (!dependencyPopupState.latestChunks) return [];
  var list = dependencyPopupState.latestChunks.tokenToChunks.get(seg) || [];
  return list.slice().sort(function (a, b) {
    return a.depth - b.depth;
  });
}

// Check if a token is a chunk head
export function isChunkHead(seg) {
  if (!dependencyPopupState.latestChunks) return null;
  for (var i = 0; i < dependencyPopupState.latestChunks.chunks.length; i++) {
    if (dependencyPopupState.latestChunks.chunks[i].headSeg === seg) {
      return dependencyPopupState.latestChunks.chunks[i];
    }
  }
  return null;
}

// Container for chunk POS tag elements
export // Clear all chunk highlighting
function clearChunkHighlight() {
  // Clear context window cache
  clearContextWindowCache();
  // Clear bottom-up chunk cache
  clearBottomUpChunkCache();
  clearBottomUpCascadeCache();
  // Remove POS tag elements
  for (var pi = 0; pi < glossRequestsState.chunkPosTags.length; pi++) {
    var el = glossRequestsState.chunkPosTags[pi];
    if (el.parentNode) el.parentNode.removeChild(el);
  }
  glossRequestsState.chunkPosTags = [];

  // Remove highlight styles from cached token elements (avoid querySelectorAll)
  for (var i = 0; i < glossRequestsState.highlightedTokenElements.length; i++) {
    var el = glossRequestsState.highlightedTokenElements[i];
    el.classList.remove('chunk-active', 'chunk-head-active', 'hovered-token');
    // Restore original backgroundColor if saved, otherwise clear
    if (el.dataset.originalBgColor) {
      el.style.backgroundColor = el.dataset.originalBgColor;
    } else {
      el.style.backgroundColor = '';
    }
    el.style.boxShadow = '';
    el.style.backgroundImage = '';
    el.style.backgroundSize = '';
    el.style.backgroundPosition = '';
    el.style.backgroundRepeat = '';
    el.style.borderRadius = '';
    el.style.outline = '';
    el.style.outlineOffset = '';
    el.style.position = ''; // Reset position from chunk head styling
  }
  glossRequestsState.highlightedTokenElements = [];
  glossRequestsState.currentChunkHighlightTokens = null;
  glossRequestsState.currentChunkHighlightState = null;
  glossRequestsState.cachedClauseHead = null;
  glossRequestsState.cachedTokenRectCache = null;
  glossRequestsState.cachedContainerRect = null;
}

// Apply chunk highlighting when hovering on a token
// Uses STABLE canonical colors - each token always gets the same color
export function applyChunkHighlight(segIdx, hoveredPartIdx) {
  clearChunkHighlight();
  if (!dependencyPopupState.latestChunks || !dependencyPopupState.displaySettings.chunkHighlight) return;

  // Collect ALL tokens that should light up.
  // When clause splitting is enabled, highlight by clause group; otherwise use chunk membership.
  var allTokensToHighlight = new Set();
  var highlightState = null;
  var canonicalSegIdx = getCanonicalSegIdx(segIdx);
  var hoveredPart = normalizeUdPartIndex(hoveredPartIdx);
  if (hoveredPart === null && getMwtPartsForSeg(canonicalSegIdx).length) {
    hoveredPart = getLiveHoveredMwtPartIdx(canonicalSegIdx);
  }
  var useContextWindow = dependencyPopupState.displaySettings.contextWindow;
  var useBottomUpChunk = dependencyPopupState.displaySettings.bottomUpChunk;
  var useIslandGroup =
    dependencyPopupState.displaySettings.islandDepTree ||
    dependencyPopupState.displaySettings.connectedIslands;
  var useClauseGroup =
    dependencyPopupState.latestChunks.clauseGroup && dependencyPopupState.displaySettings.linearClauseSplit;
  if (useBottomUpChunk) {
    // Use bottom-up chunk algorithm (cached for sync with drawUdLinesForBottomUpChunk)
    highlightState = getActiveBottomUpTokens(canonicalSegIdx, hoveredPart);
    allTokensToHighlight =
      highlightState && highlightState.segSet ? new Set(highlightState.segSet) : new Set();
  } else if (useContextWindow) {
    // Use context window algorithm (cached for sync with drawUdLinesForContextWindow)
    allTokensToHighlight = getContextWindowTokens(canonicalSegIdx);
  } else if (useIslandGroup) {
    if (dependencyPopupState.displaySettings.connectedIslands) {
      // Use connected island group
      var connectedSpans = getConnectedIslandGroup(canonicalSegIdx);
      if (connectedSpans && connectedSpans.length > 0) {
        connectedSpans.forEach(function (span) {
          for (var i = span[0]; i < span[1]; i++) {
            allTokensToHighlight.add(i);
          }
        });
      } else {
        allTokensToHighlight.add(canonicalSegIdx);
      }
    } else {
      // Use single island
      var span = getIslandSpanForSeg(canonicalSegIdx);
      if (span) {
        for (var i = span[0]; i < span[1]; i++) {
          allTokensToHighlight.add(i);
        }
      } else {
        allTokensToHighlight.add(canonicalSegIdx);
      }
    }
  } else if (useClauseGroup) {
    var clauseGroup = dependencyPopupState.latestChunks.clauseGroup;
    var targetGroup = clauseGroup.get(canonicalSegIdx);
    if (targetGroup !== undefined && targetGroup !== 0) {
      dependencyPopupState.latestChunks.tokenMap.forEach(function (_, seg) {
        if (clauseGroup.get(seg) === targetGroup) {
          allTokensToHighlight.add(seg);
        }
      });
    } else {
      allTokensToHighlight.add(canonicalSegIdx);
    }
  } else {
    var chunks = getChunksForToken(canonicalSegIdx);
    // Always include the hovered token itself (even if it's an orphaned singleton not in any chunk)
    allTokensToHighlight.add(canonicalSegIdx);
    chunks.forEach(function (item) {
      var chunk = item.chunk;
      if (!chunk) return;
      if (chunk.members) {
        chunk.members.forEach(function (m) {
          allTokensToHighlight.add(m);
        });
      }
      if (!chunk.isRootPhrase && Array.isArray(chunk.extraMembers)) {
        chunk.extraMembers.forEach(function (m) {
          allTokensToHighlight.add(m);
        });
      }
    });
  }
  allTokensToHighlight.add(segIdx);
  allTokensToHighlight.add(canonicalSegIdx);
  allTokensToHighlight = expandHighlightSetForCollapsedSpans(allTokensToHighlight);

  // Find ALL chunk heads within the highlighted tokens (not just chunks the hovered token belongs to)
  // This ensures we show POS tags for every chunk head in the highlighted area
  var chunkHeadToChunk = new Map();
  dependencyPopupState.latestChunks.chunks.forEach(function (chunk) {
    // If this chunk's head is in the highlighted area, track it
    if (allTokensToHighlight.has(chunk.headSeg)) {
      chunkHeadToChunk.set(chunk.headSeg, chunk);
    }
  });
  var containerRect = hoverLayoutState.renderedText.getBoundingClientRect();
  var tokenRectCache = {}; // Shared cache for phrase boundaries and UD arrows - measure each token only once

  // Apply highlighting to each token using its CANONICAL color (stable, never changes)
  allTokensToHighlight.forEach(function (tokenSeg) {
    var highlightTargets = getHighlightTargetsForSeg(tokenSeg);
    var activePartSet =
      highlightState && highlightState.partsBySeg ? highlightState.partsBySeg.get(tokenSeg) || null : null;
    if (getMwtPartsForSeg(tokenSeg).length) {
      if (!activePartSet || !activePartSet.size) return;
      highlightTargets = highlightTargets.filter(function (targetInfo) {
        return !!(targetInfo && activePartSet.has(normalizeUdPartIndex(targetInfo.partIndex)));
      });
    }
    if (!highlightTargets.length) return;

    // Color by the token's own POS, not the chunk head
    var tokenData =
      dependencyPopupState.latestChunks.tokenMap &&
      typeof dependencyPopupState.latestChunks.tokenMap.get === 'function'
        ? dependencyPopupState.latestChunks.tokenMap.get(tokenSeg)
        : null;
    var tokenPos = tokenData && tokenData.upos ? tokenData.upos : null;
    var isRootToken = false;
    if (tokenData) {
      if (tokenData.head === tokenData.i) isRootToken = true;
      var depVal = (tokenData.dep || '').toLowerCase();
      if (depVal === 'root') isRootToken = true;
    }
    if (
      !isRootToken &&
      dependencyState.latestUdOverlay &&
      Array.isArray(dependencyState.latestUdOverlay.roots)
    ) {
      if (dependencyState.latestUdOverlay.roots.indexOf(tokenSeg) !== -1) isRootToken = true;
    }
    if (!isRootToken && (!tokenPos || tokenPos === 'DEFAULT')) {
      var nerLabel = getNerLabelForSeg(tokenSeg);
      var nerPos = nerLabelToUpos(nerLabel);
      if (nerPos) tokenPos = nerPos;
    }
    if (isRootToken) tokenPos = 'ROOT';
    if (!tokenPos) {
      var canonChunk = dependencyPopupState.latestChunks.canonicalChunk.get(tokenSeg);
      tokenPos = canonChunk ? canonChunk.pos : 'DEFAULT';
    }
    highlightTargets.forEach(function (targetInfo) {
      var span = targetInfo && targetInfo.el ? targetInfo.el : null;
      var spanList =
        targetInfo && Array.isArray(targetInfo.elements) && targetInfo.elements.length
          ? targetInfo.elements
          : span
            ? [span]
            : [];
      if (!spanList.length) return;
      var hasPartMeta = !!(targetInfo && targetInfo.part);
      var partUpos =
        targetInfo && targetInfo.part && targetInfo.part.upos
          ? String(targetInfo.part.upos || '').trim()
          : '';
      var partDep =
        targetInfo && targetInfo.part && targetInfo.part.dep
          ? String(targetInfo.part.dep || '')
              .trim()
              .toLowerCase()
          : '';
      // MWT anchors color by their own child metadata. Only the specific
      // child whose dep tag is root gets the ROOT orange; sibling children
      // keep their own per-part POS coloring even when the collapsed token
      // as a whole is the sentence root.
      var colorKey = hasPartMeta ? (partDep === 'root' ? 'ROOT' : partUpos || 'DEFAULT') : tokenPos;
      var color = getChunkColor(colorKey);
      for (var sti = 0; sti < spanList.length; sti++) {
        var targetSpan = spanList[sti];
        if (!targetSpan) continue;
        // Save original backgroundColor before overwriting (for spacy POS overlay preservation)
        if (!targetSpan.dataset.originalBgColor && targetSpan.style.backgroundColor) {
          targetSpan.dataset.originalBgColor = targetSpan.style.backgroundColor;
        }

        // Apply styling to the token fragment span
        // Only use properties that don't affect box model to avoid subpixel shifts
        targetSpan.classList.add('chunk-active');
        targetSpan.style.backgroundColor = color.bg;
        targetSpan.style.outline = '1px solid rgba(0, 0, 0, 0.15)';
        targetSpan.style.outlineOffset = '-1px';

        // Track this element for fast clearing (avoid querySelectorAll)
        glossRequestsState.highlightedTokenElements.push(targetSpan);

        // If this is a chunk head, keep the head styling but skip the POS tag chip
        if (chunkHeadToChunk.get(tokenSeg)) {
          targetSpan.classList.add('chunk-head-active');
          targetSpan.style.position = 'relative';
        }

        // Mark the actively hovered token with a subtle glow effect via CSS class
        var targetPartIdx = normalizeUdPartIndex(targetInfo ? targetInfo.partIndex : null);
        var isHoveredTarget = false;
        if (tokenSeg === segIdx) {
          if (hoveredPart === null) isHoveredTarget = true;
          else if (targetPartIdx === hoveredPart) isHoveredTarget = true;
        }
        if (isHoveredTarget) {
          targetSpan.classList.add('hovered-token');
        }
      }
    });
    // Cache rect measurement for UD arrows using the first fragment
    if (dependencyPopupState.displaySettings.udOverlay) {
      var anchor =
        highlightTargets[0] && highlightTargets[0].el
          ? highlightTargets[0].el
          : dependencyState.udTokenIndex.get(tokenSeg) || null;
      if (anchor) tokenRectCache[tokenSeg] = anchor.getBoundingClientRect();
    }
  });
  glossRequestsState.currentChunkHighlightTokens = allTokensToHighlight;
  glossRequestsState.currentChunkHighlightState = highlightState;
  // Draw UD arrows in the same pass using cached measurements
  if (dependencyPopupState.displaySettings.udOverlay) {
    drawUdLinesForToken(segIdx, hoveredPart);
  }
  var canonChunk = dependencyPopupState.latestChunks
    ? dependencyPopupState.latestChunks.canonicalChunk.get(segIdx)
    : null;
  glossRequestsState.cachedClauseHead = canonChunk ? canonChunk.headSeg : null;
  glossRequestsState.cachedTokenRectCache = tokenRectCache;
  glossRequestsState.cachedContainerRect = containerRect;

  // Note: External chunk highlighting removed - dep tree arrows are sufficient
  // to show connections to chunks outside the current clause
}
// ===================== END CHUNK HIGHLIGHTING =====================
// Load saved settings from localStorage
export function loadDisplaySettings() {
  try {
    var saved = localStorage.getItem('burmeseReaderDisplaySettings');
    if (saved) {
      var parsed = JSON.parse(saved);
      // Backward compat: legacy grammarOverlay bool turns everything on/off
      var legacyGrammarAll = parsed.hasOwnProperty('grammarOverlay') ? !!parsed.grammarOverlay : false;
      dependencyPopupState.displaySettings.grammarTypes = parsed.grammarTypes || {};
      dependencyPopupState.GRAMMAR_TYPES.forEach(function (t) {
        if (dependencyPopupState.displaySettings.grammarTypes[t] === undefined) {
          dependencyPopupState.displaySettings.grammarTypes[t] = legacyGrammarAll;
        }
      });
      dependencyPopupState.displaySettings.udOverlay =
        parsed.udOverlay !== undefined ? parsed.udOverlay : dependencyPopupState.displaySettings.udOverlay;
      dependencyPopupState.displaySettings.chunkHighlight =
        parsed.chunkHighlight !== undefined
          ? parsed.chunkHighlight
          : dependencyPopupState.displaySettings.chunkHighlight;
      dependencyPopupState.displaySettings.nerOverlay =
        parsed.nerOverlay !== undefined ? parsed.nerOverlay : dependencyPopupState.displaySettings.nerOverlay;
      dependencyPopupState.displaySettings.islandDepTree =
        parsed.islandDepTree !== undefined
          ? parsed.islandDepTree
          : dependencyPopupState.displaySettings.islandDepTree;
      dependencyPopupState.displaySettings.connectedIslands =
        parsed.connectedIslands !== undefined
          ? parsed.connectedIslands
          : dependencyPopupState.displaySettings.connectedIslands;
      dependencyPopupState.displaySettings.connectedIslandsAclGate =
        parsed.connectedIslandsAclGate !== undefined
          ? parsed.connectedIslandsAclGate
          : dependencyPopupState.displaySettings.connectedIslandsAclGate;
      dependencyPopupState.displaySettings.contextWindow =
        parsed.contextWindow !== undefined
          ? parsed.contextWindow
          : dependencyPopupState.displaySettings.contextWindow;
      if (parsed.contextWindowSize !== undefined) {
        dependencyPopupState.displaySettings.contextWindowSize = parsed.contextWindowSize;
      }
      dependencyPopupState.displaySettings.bottomUpChunk =
        parsed.bottomUpChunk !== undefined
          ? parsed.bottomUpChunk
          : dependencyPopupState.displaySettings.bottomUpChunk;
      dependencyPopupState.displaySettings.bottomUpCascade =
        parsed.bottomUpCascade !== undefined
          ? parsed.bottomUpCascade
          : dependencyPopupState.displaySettings.bottomUpCascade;
      if (parsed.bottomUpChunkThreshold !== undefined) {
        var chunkThreshold = parseInt(parsed.bottomUpChunkThreshold, 10);
        if (isNaN(chunkThreshold)) chunkThreshold = 5;
        if (chunkThreshold < 1) chunkThreshold = 1;
        if (chunkThreshold > 10) chunkThreshold = 10;
        dependencyPopupState.displaySettings.bottomUpChunkThreshold = chunkThreshold;
      }
      dependencyPopupState.displaySettings.linearClauseSplit =
        parsed.linearClauseSplit !== undefined
          ? parsed.linearClauseSplit
          : dependencyPopupState.displaySettings.linearClauseSplit;
      if (parsed.branchDepthMin !== undefined) {
        dependencyPopupState.displaySettings.branchDepthMin = parsed.branchDepthMin;
      }
      if (parsed.clauseDepthDrop !== undefined) {
        dependencyPopupState.displaySettings.clauseDepthDrop = parsed.clauseDepthDrop;
      }
      dependencyPopupState.displaySettings.depTreeView =
        parsed.depTreeView !== undefined
          ? parsed.depTreeView
          : dependencyPopupState.displaySettings.depTreeView;
      dependencyPopupState.displaySettings.udPopup =
        parsed.udPopup !== undefined ? parsed.udPopup : dependencyPopupState.displaySettings.udPopup;
      dependencyPopupState.displaySettings.pronunciation =
        parsed.pronunciation !== undefined
          ? parsed.pronunciation
          : dependencyPopupState.displaySettings.pronunciation;
      dependencyPopupState.displaySettings.grammarPopup =
        parsed.grammarPopup !== undefined
          ? parsed.grammarPopup
          : dependencyPopupState.displaySettings.grammarPopup;
      dependencyPopupState.displaySettings.llmGloss =
        parsed.llmGloss !== undefined ? parsed.llmGloss : dependencyPopupState.displaySettings.llmGloss;
      dependencyPopupState.displaySettings.llmDecomp =
        parsed.llmDecomp !== undefined ? parsed.llmDecomp : dependencyPopupState.displaySettings.llmDecomp;
      dependencyPopupState.displaySettings.orthBreakdown =
        parsed.orthBreakdown !== undefined
          ? parsed.orthBreakdown
          : dependencyPopupState.displaySettings.orthBreakdown;
      dependencyPopupState.displaySettings.geminiNer =
        parsed.geminiNer !== undefined ? parsed.geminiNer : dependencyPopupState.displaySettings.geminiNer;
      dependencyPopupState.displaySettings.dictPopup =
        parsed.dictPopup !== undefined ? parsed.dictPopup : dependencyPopupState.displaySettings.dictPopup;
      dependencyPopupState.displaySettings.comments =
        parsed.comments !== undefined ? parsed.comments : dependencyPopupState.displaySettings.comments;
      dependencyPopupState.displaySettings.debugCapture =
        parsed.debugCapture !== undefined
          ? parsed.debugCapture
          : dependencyPopupState.displaySettings.debugCapture;
      dependencyPopupState.displaySettings.stripPunctuation =
        parsed.stripPunctuation !== undefined
          ? parsed.stripPunctuation
          : dependencyPopupState.displaySettings.stripPunctuation;
      dependencyPopupState.displaySettings.manualSentenceSegmentation =
        parsed.manualSentenceSegmentation !== undefined
          ? parsed.manualSentenceSegmentation
          : dependencyPopupState.displaySettings.manualSentenceSegmentation;
      dependencyPopupState.displaySettings.pdfOcrCleanup =
        parsed.pdfOcrCleanup !== undefined
          ? parsed.pdfOcrCleanup
          : dependencyPopupState.displaySettings.pdfOcrCleanup;
      if (parsed.fuzzyMaxEditDistance !== undefined) {
        var fuzzyVal = parseInt(parsed.fuzzyMaxEditDistance, 10);
        if (!isNaN(fuzzyVal)) {
          dependencyPopupState.displaySettings.fuzzyMaxEditDistance = fuzzyVal;
        }
      }
      dependencyPopupState.displaySettings.mergeGreedy =
        parsed.mergeGreedy !== undefined
          ? parsed.mergeGreedy
          : dependencyPopupState.displaySettings.mergeGreedy;
      dependencyPopupState.displaySettings.splitDictFill =
        parsed.splitDictFill !== undefined
          ? parsed.splitDictFill
          : dependencyPopupState.displaySettings.splitDictFill;
      // posOverride, stanzaNer, collapseNerUd, dpResegment are now hardcoded to true
      if (parsed.lmWeights !== undefined) {
        dependencyPopupState.displaySettings.lmWeights = parsed.lmWeights;
      }
      dependencyPopupState.displaySettings.bottomUpChunk = true;
      dependencyPopupState.displaySettings.bottomUpCascade = true;
      dependencyPopupState.displaySettings.geminiNer = false;
      dependencyPopupState.displaySettings.pronunciation = false;
      dependencyPopupState.displaySettings.llmDecomp = false;
      dependencyPopupState.displaySettings.orthBreakdown = false;
      dependencyPopupState.displaySettings.stripPunctuation = false;
      dependencyPopupState.displaySettings.debugCapture =
        dependencyPopupState.DEBUG_CAPTURE_PROTOTYPE_ENABLED;
      ensureLmWeightsInitialized();
      ensureFuzzySettingsInitialized();
    }
  } catch (e) {
    console.error('Failed to load display settings:', e);
  }
  dependencyPopupState.displaySettings.bottomUpChunk = true;
  dependencyPopupState.displaySettings.bottomUpCascade = true;
  dependencyPopupState.displaySettings.geminiNer = false;
  dependencyPopupState.displaySettings.pronunciation = false;
  dependencyPopupState.displaySettings.llmDecomp = false;
  dependencyPopupState.displaySettings.orthBreakdown = false;
  dependencyPopupState.displaySettings.stripPunctuation = false;
  dependencyPopupState.displaySettings.debugCapture = dependencyPopupState.DEBUG_CAPTURE_PROTOTYPE_ENABLED;
  ensureLmWeightsInitialized();
  ensureFuzzySettingsInitialized();
}
// Save settings to localStorage
export function saveDisplaySettings() {
  try {
    localStorage.setItem(
      'burmeseReaderDisplaySettings',
      JSON.stringify(dependencyPopupState.displaySettings)
    );
  } catch (e) {
    console.error('Failed to save display settings:', e);
  }
}
// -- LLM gloss request helper --
// Builds a per-sentence token list (segment indices + filtered token texts).
// Sentences come from ud_overlay.sentences + doc2seg, mirroring the fluent
// translation logic. Each sentence carries its own segment indices so the
// cache can key on the exact sentence token stream.
export function isKoreanCurrentLanguageForGloss() {
  var lang = String(documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  return lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0 || lang.indexOf('korean-') === 0;
}
export function getLlmGlossTokenText(token) {
  if (token && typeof token === 'object') return String(token.text || '').trim();
  return String(token || '').trim();
}
export function getLlmGlossServerToken(token) {
  if (token && typeof token === 'object') {
    var out = {
      text: String(token.text || '').trim()
    };
    if (Array.isArray(token.lemmas) && token.lemmas.length) out.lemmas = token.lemmas.slice();
    return out;
  }
  return {
    text: String(token || '').trim()
  };
}
export function getKoreanGlossLemmaParts(segText, udTok, resultEntry) {
  if (!isKoreanCurrentLanguageForGloss()) return [];
  var compoundParts = getOrderedCompoundLemmaTexts(segText, {
    entry: resultEntry,
    udTok: udTok
  });
  if (compoundParts.length > 1) return compoundParts;
  var rawLemma = String(
    (udTok && (udTok.lemma_raw || udTok.lemma)) ||
      (resultEntry && (resultEntry.lemma_raw || resultEntry.lemma_form || resultEntry.lemma)) ||
      ''
  ).trim();
  if (!rawLemma || !/[+\uFF0B]/.test(rawLemma)) return [];
  var parts = getTokenMapLemmaPartTexts(rawLemma);
  return parts.length > 1 ? parts : [];
}
// Expand one segment into its sub-part texts:
//   1. MWT: use mwt_parts surface texts (e.g. Italian "del" → ["di","il"])
//   2. Compound lemma without MWT (e.g. Korean): use lemma.split('+') parts
//   3. Otherwise: just the surface text itself
// Returns an array of strings or {text, lemmas} token objects (length >= 1).
export function _glossSubTexts(segText, udTok, resultEntry) {
  var mwtParts =
    udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length > 1 ? udTok.mwt_parts : null;
  if (mwtParts) {
    var out = [];
    for (var mi = 0; mi < mwtParts.length; mi++) {
      var p =
        typeof mwtParts[mi] === 'string'
          ? mwtParts[mi]
          : (mwtParts[mi] && (mwtParts[mi].text || mwtParts[mi].form)) || '';
      if (p && _surfaceHasGlossableChar(p)) out.push(p);
    }
    if (out.length) return out;
  }
  var koreanLemmaParts = getKoreanGlossLemmaParts(segText, udTok, resultEntry);
  if (koreanLemmaParts.length) {
    var koLemmas = [];
    for (var ki = 0; ki < koreanLemmaParts.length; ki++) {
      var kp = String(koreanLemmaParts[ki] || '').trim();
      if (kp && _surfaceHasGlossableChar(kp)) koLemmas.push(kp);
    }
    if (koLemmas.length > 1) return koLemmas;
    if (koLemmas.length) return [koLemmas[0]];
  }
  var lemmaParts = getOrderedCompoundLemmaTexts(segText, {
    entry: resultEntry,
    udTok: udTok
  });
  if (lemmaParts.length > 1) {
    var out2 = [];
    for (var li = 0; li < lemmaParts.length; li++) {
      var lp = String(lemmaParts[li] || '').trim();
      if (lp && _surfaceHasGlossableChar(lp)) out2.push(lp);
    }
    if (out2.length) return out2;
  }
  return [segText];
}
export function _buildLlmGlossSentences(data) {
  var segments = data.segments || [];
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udOverlay = data.ud_overlay || {};
  var udTokens = udOverlay.tokens && Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  var sents = udOverlay.sentences && Array.isArray(udOverlay.sentences) ? udOverlay.sentences : null;
  var doc2seg = udOverlay.doc2seg && Array.isArray(udOverlay.doc2seg) ? udOverlay.doc2seg : null;

  // Build a segIdx → udTok map for fast lookup
  var udTokMap = {};
  for (var ui = 0; ui < udTokens.length; ui++) {
    if (udTokens[ui] && udTokens[ui].i != null) udTokMap[udTokens[ui].i] = udTokens[ui];
  }

  // Expand a single segIdx into sub-part tokens+indices entries.
  // tokens: flat sub-part text strings; indices: parent segIdx repeated per sub-part.
  function expandSeg(idx) {
    var text = segments[idx];
    if (text == null || !_surfaceHasGlossableChar(text)) return null;
    var udTok = udTokMap[idx] || null;
    var resultEntry = idx >= 0 && idx < resultsBySeg.length ? resultsBySeg[idx] || null : null;
    var subTexts = _glossSubTexts(text, udTok, resultEntry);
    var toks = [],
      idxs = [];
    for (var si = 0; si < subTexts.length; si++) {
      toks.push(subTexts[si]);
      idxs.push(idx);
    }
    return {
      tokens: toks,
      indices: idxs
    };
  }
  var out = [];
  if (sents && sents.length && doc2seg) {
    for (var si = 0; si < sents.length; si++) {
      var rng = sents[si];
      if (!Array.isArray(rng) || rng.length < 2) continue;
      var docStart = rng[0] | 0,
        docEnd = rng[1] | 0;
      var segSet = {};
      for (var j = docStart; j < docEnd && j < udTokens.length; j++) {
        var seg = j < doc2seg.length ? doc2seg[j] | 0 : -1;
        if (seg >= 0) segSet[seg] = true;
      }
      var tokens = [],
        indices = [];
      var segIdxs = Object.keys(segSet)
        .map(function (k) {
          return parseInt(k, 10);
        })
        .sort(function (a, b) {
          return a - b;
        });
      for (var k = 0; k < segIdxs.length; k++) {
        var exp = expandSeg(segIdxs[k]);
        if (!exp) continue;
        for (var ei = 0; ei < exp.tokens.length; ei++) {
          tokens.push(exp.tokens[ei]);
          indices.push(exp.indices[ei]);
        }
      }
      if (tokens.length)
        out.push({
          tokens: tokens,
          indices: indices
        });
    }
    return out;
  }
  // Fallback: whole segment array as one sentence.
  var tokensAll = [],
    indicesAll = [];
  for (var ti = 0; ti < segments.length; ti++) {
    var exp2 = expandSeg(ti);
    if (!exp2) continue;
    for (var ei2 = 0; ei2 < exp2.tokens.length; ei2++) {
      tokensAll.push(exp2.tokens[ei2]);
      indicesAll.push(exp2.indices[ei2]);
    }
  }
  if (tokensAll.length)
    out.push({
      tokens: tokensAll,
      indices: indicesAll
    });
  return out;
}

// Pack sentences into chunks of ~CHUNK_SIZE tokens. A chunk may slightly
// exceed CHUNK_SIZE to keep a sentence intact; small sentences are combined.
// Each chunk carries its member sentences so caching remains per-sentence.
export function _buildLlmGlossChunks(data) {
  var CHUNK_SIZE = 100;
  var sentences = _buildLlmGlossSentences(data);
  var chunks = [];
  var curTokens = [],
    curIndices = [],
    curSents = [],
    curCount = 0;
  function flush() {
    if (!curTokens.length) return;
    chunks.push({
      tokens: curTokens.map(getLlmGlossServerToken),
      indices: curIndices,
      sentences: curSents,
      context: curTokens.map(getLlmGlossTokenText).join(' / ')
    });
    curTokens = [];
    curIndices = [];
    curSents = [];
    curCount = 0;
  }
  for (var si = 0; si < sentences.length; si++) {
    var s = sentences[si];
    if (!s.tokens.length) continue;
    // If adding this sentence would push us past CHUNK_SIZE and we already
    // have content, flush first — unless the sentence alone is huge, in
    // which case it still goes in its own chunk.
    if (curCount > 0 && curCount + s.tokens.length > CHUNK_SIZE) flush();
    for (var k = 0; k < s.tokens.length; k++) {
      curTokens.push(s.tokens[k]);
      curIndices.push(s.indices[k]);
    }
    curSents.push({
      tokens: s.tokens.slice(),
      indices: s.indices.slice()
    });
    curCount += s.tokens.length;
    if (curCount >= CHUNK_SIZE) flush();
  }
  flush();
  return chunks;
}

// Per-sentence LLM gloss cache in sessionStorage.
// Each entry maps sentenceKey -> array of glosses aligned with that
// sentence's token indices.
// sentenceKey = lang + '\u0001' + JSON.stringify(sentence.tokens)
// Exact 1:1 token-stream match required — no normalization.
export function _llmGlossLoadCache() {
  try {
    var raw = sessionStorage.getItem(glossRequestsState._LLM_GLOSS_SS_KEY);
    if (!raw) return Object.create(null);
    var obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : Object.create(null);
  } catch (e) {
    return Object.create(null);
  }
}
export function _llmGlossSaveCache(cache) {
  try {
    sessionStorage.setItem(glossRequestsState._LLM_GLOSS_SS_KEY, JSON.stringify(cache));
  } catch (e) {
    // quota exceeded — drop ~20% of keys and retry once
    try {
      var keys = Object.keys(cache);
      var drop = Math.max(1, Math.floor(keys.length * 0.2));
      for (var i = 0; i < drop; i++) delete cache[keys[i]];
      sessionStorage.setItem(glossRequestsState._LLM_GLOSS_SS_KEY, JSON.stringify(cache));
    } catch (e2) {}
  }
}
export function _llmGlossSentKey(lang, tokens) {
  try {
    return lang + '\u0001' + JSON.stringify(tokens);
  } catch (e) {
    return null;
  }
}
export function sameLlmGlossIndexSequence(left, right) {
  var a = Array.isArray(left) ? left : [];
  var b = Array.isArray(right) ? right : [];
  if (a.length !== b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (String(a[i]) !== String(b[i])) return false;
  }
  return true;
}
export function getLlmGlossTextValue(glossEntry) {
  if (glossEntry && typeof glossEntry === 'object') return String(glossEntry.gloss || '').trim();
  return String(glossEntry || '').trim();
}
export function getKoreanCompoundPartsForSeg(segIdx, segments, resultsBySeg, udTokMap) {
  if (!isKoreanCurrentLanguageForGloss()) return [];
  var idx = Number(segIdx);
  if (!isFinite(idx) || idx < 0) return [];
  return getKoreanGlossLemmaParts(
    (segments && segments[idx]) || '',
    (udTokMap && udTokMap[idx]) || null,
    (resultsBySeg && resultsBySeg[idx]) || null
  );
}
export function applyLlmGlossEntries(indices, glosses, segments, resultsBySeg, udTokMap) {
  if (!Array.isArray(indices) || !Array.isArray(glosses)) return;
  var koreanGroups = Object.create(null);
  var handled = Object.create(null);
  if (isKoreanCurrentLanguageForGloss()) {
    for (var gi = 0; gi < indices.length; gi++) {
      var segKey = String(indices[gi]);
      var parts = getKoreanCompoundPartsForSeg(indices[gi], segments, resultsBySeg, udTokMap);
      if (parts.length < 2) continue;
      if (!koreanGroups[segKey]) {
        koreanGroups[segKey] = {
          segIdx: indices[gi],
          parts: parts,
          glosses: []
        };
      }
      var glossText = getLlmGlossTextValue(glosses[gi]);
      if (glossText) koreanGroups[segKey].glosses.push(glossText);
      handled[segKey] = true;
    }
  }
  for (var mi = 0; mi < indices.length; mi++) {
    var segHandledKey = String(indices[mi]);
    if (handled[segHandledKey]) continue;
    var segIdx = indices[mi];
    var glossEntry = glosses[mi];
    if (glossEntry == null) continue;
    var existing = hoverLayoutState.latestLlmGlosses[segIdx];
    hoverLayoutState.latestLlmGlosses[segIdx] = mergeLlmGlossEntries(
      existing,
      glossEntry,
      (segments && segments[segIdx]) || '',
      {
        entry: resultsBySeg[segIdx] || null,
        udTok: udTokMap[segIdx] || null
      }
    );
  }
  var keys = Object.keys(koreanGroups);
  for (var ki = 0; ki < keys.length; ki++) {
    var group = koreanGroups[keys[ki]];
    var combined = buildCompoundLlmGlossEntry(group.parts, group.glosses.slice(0, group.parts.length));
    if (!combined) continue;
    combined._korean_compound_gloss = true;
    hoverLayoutState.latestLlmGlosses[group.segIdx] = combined;
  }
}
export function _fireLlmGlossRequest(data) {
  if (!dependencyPopupState.displaySettings.llmGloss) {
    hoverLayoutState.latestLlmGlossUpgradeRequired = false;
    return;
  }
  hoverLayoutState.latestLlmGlossUpgradeRequired = false;
  var segments = data.segments || [];
  if (!segments.length) return;
  var resultsBySeg = Array.isArray(data.results_by_seg) ? data.results_by_seg : [];
  var udOverlay = data.ud_overlay || {};
  var udTokens = udOverlay.tokens && Array.isArray(udOverlay.tokens) ? udOverlay.tokens : [];
  var udTokMap = {};
  for (var _ui = 0; _ui < udTokens.length; _ui++) {
    if (udTokens[_ui] && udTokens[_ui].i != null) udTokMap[udTokens[_ui].i] = udTokens[_ui];
  }
  var allChunks = _buildLlmGlossChunks(data);
  if (!allChunks.length) return;
  var lang = documentShellState.currentLanguage || '';
  var seq = ++hoverLayoutState.latestLlmGlossSeq;
  hoverLayoutState.latestLlmGlosses = new Array(segments.length).fill(null);
  var cache = _llmGlossLoadCache();

  // For each chunk, check each sentence. Sentences with exact token-stream
  // matches are filled from cache. Remaining sentences form a rebuilt chunk
  // to send to the server.
  var chunksToSend = [];
  var cacheHits = [];
  for (var ci = 0; ci < allChunks.length; ci++) {
    var ch = allChunks[ci];
    var missSents = [];
    for (var sj = 0; sj < ch.sentences.length; sj++) {
      var sent = ch.sentences[sj];
      var key = _llmGlossSentKey(lang, sent.tokens);
      var cached = key ? cache[key] : null;
      if (cached && Array.isArray(cached) && cached.length === sent.indices.length) {
        applyLlmGlossEntries(sent.indices, cached, segments, resultsBySeg, udTokMap);
        cacheHits.push({
          tokens: sent.tokens.slice()
        });
      } else {
        missSents.push(sent);
      }
    }
    if (missSents.length) {
      var newTokens = [],
        newIndices = [];
      for (var m = 0; m < missSents.length; m++) {
        for (var n = 0; n < missSents[m].tokens.length; n++) {
          newTokens.push(missSents[m].tokens[n]);
          newIndices.push(missSents[m].indices[n]);
        }
      }
      chunksToSend.push({
        tokens: newTokens.map(getLlmGlossServerToken),
        indices: newIndices,
        sentences: missSents,
        context: newTokens.map(getLlmGlossTokenText).join(' / '),
        _cacheGlosses: null
      });
    }
  }
  _refreshLlmGlossUI();
  if (!chunksToSend.length) return;

  // Strip the server-facing payload down to what the endpoint expects.
  // Include per-sentence token groupings so the server can label them
  // ("sentence 1:", "sentence 2:", ...) and reset token numbering per sentence.
  var serverChunks = chunksToSend.map(function (c) {
    var sents = (c.sentences || []).map(function (s) {
      return {
        tokens: s.tokens.slice()
      };
    });
    return {
      tokens: c.tokens,
      indices: c.indices,
      context: c.context,
      sentences: sents
    };
  });
  fetch('/api/llm_glosses', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      chunks: serverChunks,
      lang: lang
    })
  })
    .then(function (r) {
      if (!r.ok) {
        return r
          .json()
          .catch(function () {
            return null;
          })
          .then(function (errData) {
            if (errData && (errData.upgrade_required || errData.upgrade)) {
              hoverLayoutState.latestLlmGlossUpgradeRequired = true;
              _refreshLlmGlossUI();
              return;
            }
            throw new Error('HTTP ' + r.status);
          });
      }
      hoverLayoutState.latestLlmGlossUpgradeRequired = false;
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      function rememberReturnedGlossesForCache(indices, glosses) {
        if (!Array.isArray(indices) || !Array.isArray(glosses) || indices.length !== glosses.length) return;
        for (var ck = 0; ck < chunksToSend.length; ck++) {
          var ch = chunksToSend[ck];
          if (!ch || ch._cacheGlosses) continue;
          if (sameLlmGlossIndexSequence(ch.indices, indices)) {
            ch._cacheGlosses = glosses.slice();
            return;
          }
        }
      }
      function persistOnce() {
        // Walk the sent chunks and store each sentence's glosses individually.
        var cur = _llmGlossLoadCache();
        var changed = false;
        for (var ck = 0; ck < chunksToSend.length; ck++) {
          var sentChunk = chunksToSend[ck] || {};
          var snts = sentChunk.sentences || [];
          var directGlosses = Array.isArray(sentChunk._cacheGlosses) ? sentChunk._cacheGlosses : null;
          var cursor = 0;
          for (var ss = 0; ss < snts.length; ss++) {
            var sent = snts[ss];
            var key = _llmGlossSentKey(lang, sent.tokens);
            if (!key) {
              cursor += (sent.indices || []).length;
              continue;
            }
            var arr = new Array(sent.indices.length).fill(null);
            var any = false;
            for (var ii = 0; ii < sent.indices.length; ii++) {
              var _si = sent.indices[ii];
              var g = directGlosses ? directGlosses[cursor + ii] : hoverLayoutState.latestLlmGlosses[_si];
              if (g != null) {
                arr[ii] = g;
                any = true;
              }
            }
            if (any) {
              cur[key] = arr;
              changed = true;
            }
            cursor += sent.indices.length;
          }
        }
        if (changed) _llmGlossSaveCache(cur);
      }
      function pump() {
        return reader.read().then(function (chunk) {
          if (seq !== hoverLayoutState.latestLlmGlossSeq) {
            // Preempted — persist whatever glosses arrived before bailing.
            try {
              persistOnce();
            } catch (e) {}
            reader.cancel();
            return;
          }
          if (chunk.done) {
            try {
              persistOnce();
            } catch (e) {}
            return;
          }
          buf += decoder.decode(chunk.value, {
            stream: true
          });
          var lines = buf.split('\n');
          buf = lines.pop(); // keep incomplete last line
          for (var li = 0; li < lines.length; li++) {
            var line = lines[li].trim();
            if (!line || line.indexOf('data: ') !== 0) continue;
            try {
              var msg = JSON.parse(line.slice(6));
              if (msg.done) {
                try {
                  persistOnce();
                } catch (e) {}
                return;
              }
              if (msg.error) {
                console.warn('LLM gloss error:', msg.error);
                return;
              }
              if (Array.isArray(msg.indices) && Array.isArray(msg.glosses)) {
                rememberReturnedGlossesForCache(msg.indices, msg.glosses);
                applyLlmGlossEntries(msg.indices, msg.glosses, segments, resultsBySeg, udTokMap);
                _refreshLlmGlossUI();
              }
            } catch (e) {}
          }
          return pump();
        });
      }
      return pump();
    })
    .catch(function (err) {
      console.warn('LLM gloss request failed:', err);
    });
}
export function initializeGlossRequests() {
  glossRequestsState.chunkPosTags = [];
  glossRequestsState.currentChunkHighlightTokens = null;
  glossRequestsState.currentChunkHighlightState = null;
  glossRequestsState.cachedClauseHead = null;
  glossRequestsState.cachedTokenRectCache = null;
  glossRequestsState.cachedContainerRect = null;
  glossRequestsState.lastUdHoverKey = '';
  // Performance: cache references to highlighted elements to avoid querySelectorAll
  glossRequestsState.highlightedTokenElements = [];
  glossRequestsState._LLM_GLOSS_SS_KEY = 'llmGlossSentCache:v6';
  window._fireLlmGlossRequest = _fireLlmGlossRequest;

  // -- LLM inflectional decomposition request helper --
  return true;
}
