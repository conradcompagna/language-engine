import { getSentenceSpansFromSegments } from './dependency-geometry.mjs';
import { getDepTreeExperimentSentenceSpans, normalizeUdSentenceSpans } from './dependency-state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { autoResizeTextarea } from './document-import.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { documentState } from './document-state.state.mjs';
import {
  getDictionaryRuntimeApi,
  getLookupEntryFills,
  getOrderedCompoundLemmaTexts,
  getRenderableLlmGlossRows,
  pushLookupResolverPayload
} from './entry-editing.mjs';
import { getLlmGlossEntryForSeg } from './gloss-entries.mjs';
import { filterFeatsForLang, normalizeDepLabel, normalizeGrammarMetaValue } from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { filterRenderableFillEntries, hasSameVisibleComparisonText } from './presentation.mjs';
import { renderSegments } from './segment-rendering.mjs';
export function _buildExpandedCtxForSeg(segIdx, fallback) {
  if (!hoverLayoutState.latestSegments || !hoverLayoutState.latestSegments.length || segIdx < 0)
    return fallback || '';
  // Find sentence boundaries for segIdx
  var ctxS = 0,
    ctxE = hoverLayoutState.latestSegments.length;
  var sentences = normalizeUdSentenceSpans(
    (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.sentences) || []
  );
  if (!sentences.length) {
    var fbSpans = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
    for (var fi = 0; fi < fbSpans.length; fi++) sentences.push([fbSpans[fi].start, fbSpans[fi].end]);
  }
  for (var si = 0; si < sentences.length; si++) {
    if (segIdx >= sentences[si][0] && segIdx < sentences[si][1]) {
      ctxS = sentences[si][0];
      ctxE = sentences[si][1];
      break;
    }
  }
  var parts = [];
  for (var i = ctxS; i < ctxE; i++) {
    var seg = hoverLayoutState.latestSegments[i];
    var udTok = dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[i];
    var res =
      hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)
        ? hoverLayoutState.latestData.results_by_seg[i] || null
        : null;
    var mwtP = udTok && Array.isArray(udTok.mwt_parts) && udTok.mwt_parts.length > 1 ? udTok.mwt_parts : null;
    if (mwtP) {
      for (var mi = 0; mi < mwtP.length; mi++) {
        var pt = typeof mwtP[mi] === 'string' ? mwtP[mi] : mwtP[mi].text || mwtP[mi].form || String(mwtP[mi]);
        if (pt) parts.push(pt);
      }
    } else {
      var lps = getOrderedCompoundLemmaTexts(seg, {
        entry: res,
        udTok: udTok
      });
      if (lps && lps.length > 1) {
        for (var li = 0; li < lps.length; li++) {
          var lp = String(lps[li] || '').trim();
          if (lp) parts.push(lp);
        }
      } else {
        parts.push(seg);
      }
    }
  }
  return parts.join(' ');
}

// ---------------------------------------------------------------------------
// Language Assistant context builders. Produce plain-text blocks intended
// as LLM prompt context AND preview text for the assistant side panel.
// ---------------------------------------------------------------------------
export function _assistantFormatFeats(feats) {
  if (!feats) return '';
  if (typeof feats === 'string') return feats;
  if (Array.isArray(feats)) return feats.join('|');
  if (typeof feats === 'object') {
    var parts = [];
    Object.keys(feats).forEach(function (k) {
      var v = feats[k];
      if (v == null || v === '') return;
      parts.push(k + '=' + v);
    });
    return parts.join('|');
  }
  return String(feats || '');
}
export function _assistantMwtPartTexts(udTok) {
  if (!udTok || !Array.isArray(udTok.mwt_parts) || udTok.mwt_parts.length <= 1) return [];
  var out = [];
  for (var i = 0; i < udTok.mwt_parts.length; i++) {
    var p = udTok.mwt_parts[i];
    var txt = typeof p === 'string' ? p : (p && (p.text || p.form || p.surface)) || '';
    if (txt) out.push(String(txt));
  }
  return out;
}
export function _assistantEntrySenseLines(entry, maxSenses) {
  if (!entry || typeof entry !== 'object') return [];
  var lines = [];
  var limit = Math.max(0, Number(maxSenses) || 0) || 999;
  var sourceSenses = [];
  if (Array.isArray(entry.senses_hover) && entry.senses_hover.length) {
    sourceSenses = entry.senses_hover;
  } else if (Array.isArray(entry.senses_full) && entry.senses_full.length) {
    sourceSenses = entry.senses_full;
  } else if (Array.isArray(entry.senses) && entry.senses.length) {
    sourceSenses = entry.senses;
  }
  for (var i = 0; i < sourceSenses.length && lines.length < limit; i++) {
    var sf = sourceSenses[i];
    if (!sf) continue;
    var gloss = '';
    if (typeof sf === 'string') gloss = sf;
    else if (typeof sf === 'object') gloss = String(sf.gloss || sf.text || sf.def || '');
    gloss = gloss.trim();
    if (gloss) lines.push(lines.length + 1 + '. ' + gloss);
  }
  return lines;
}
export function _assistantSliceMwtValue(rawValue, partIdx) {
  var raw = String(rawValue || '').trim();
  if (partIdx == null || partIdx < 0 || !raw || raw.indexOf('+') === -1) return raw;
  var parts = raw.split('+');
  if (partIdx >= parts.length) return raw;
  return String(parts[partIdx] || '').trim();
}
export function _assistantParseFeatPairs(rawFeats) {
  var raw = String(rawFeats || '').trim();
  if (!raw) return [];
  var out = [];
  var parts = raw.split('|');
  for (var i = 0; i < parts.length; i++) {
    var part = String(parts[i] || '').trim();
    if (!part) continue;
    var eq = part.indexOf('=');
    if (eq > 0) out.push([part.slice(0, eq), part.slice(eq + 1)]);
    else out.push([part, '']);
  }
  return out;
}
export function _assistantGetHeadInfo(udTok) {
  if (!udTok || typeof udTok !== 'object') return null;
  var dep = String(udTok.dep || udTok.deprel || '')
    .trim()
    .toLowerCase();
  var selfIdx = isFinite(Number(udTok.i)) ? Number(udTok.i) : -1;
  var headIdxRaw = Array.isArray(udTok.heads) ? udTok.heads[0] : udTok.head;
  var headIdx = isFinite(Number(headIdxRaw)) ? Number(headIdxRaw) : -1;
  if (dep === 'root' || headIdx < 0 || headIdx === selfIdx) {
    return {
      idx: headIdx,
      surface: 'ROOT'
    };
  }
  var surface = '';
  if (
    dependencyState.latestUdOverlay &&
    Array.isArray(dependencyState.latestUdOverlay.tokens) &&
    headIdx < dependencyState.latestUdOverlay.tokens.length
  ) {
    var headTok = dependencyState.latestUdOverlay.tokens[headIdx] || null;
    surface = String((headTok && (headTok.text || headTok.form)) || '').trim();
    if (
      !surface &&
      Array.isArray(dependencyState.latestUdOverlay.doc2seg) &&
      headIdx < dependencyState.latestUdOverlay.doc2seg.length
    ) {
      var seg = dependencyState.latestUdOverlay.doc2seg[headIdx] | 0;
      surface = String(
        (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[seg]) || ''
      ).trim();
    }
  }
  if (!surface) surface = 'Token ' + headIdx;
  return {
    idx: headIdx,
    surface: surface
  };
}
export function _assistantGetGlossRows(segIdx, surface, entry, posData, udTok, partIdx, childLemma) {
  var glossEntry = getLlmGlossEntryForSeg(segIdx);
  if (!glossEntry) return [];
  try {
    return getRenderableLlmGlossRows(
      glossEntry,
      surface,
      {
        entry: entry || null,
        udTok: udTok || null,
        posData: posData || {},
        lemma: String((posData && posData.lemma) || (entry && entry.lemma) || ''),
        lemma_raw: String(
          (posData && posData.lemma_raw) || (entry && entry.lemma_raw) || (entry && entry.lemma) || ''
        )
      },
      {
        isMwtChild: partIdx >= 0,
        partIndex: partIdx,
        childLemma: String(childLemma || '')
      }
    );
  } catch (_e) {
    return [];
  }
}
export function _assistantBuildVisibleEntryCards(entry) {
  if (!entry || typeof entry !== 'object') return [];
  var fills = filterRenderableFillEntries(getLookupEntryFills(entry));
  var out = [];
  if (fills.length) {
    for (var i = 0; i < fills.length; i++) {
      var fillCard = _assistantEntryStruct(fills[i], 6);
      if (fillCard) out.push(fillCard);
    }
    return out;
  }
  var mainCard = _assistantEntryStruct(entry, 8);
  return mainCard ? [mainCard] : [];
}
export function _assistantEntryBlockFromStruct(entryStruct, index) {
  if (!entryStruct || typeof entryStruct !== 'object') return '';
  var header = (index > 0 ? 'Entry ' + index + ': ' : 'Entry: ') + (entryStruct.head || '(entry)');
  if (entryStruct.pos) header += ' [' + entryStruct.pos + ']';
  if (entryStruct.rom) header += ' /' + entryStruct.rom + '/';
  if (entryStruct.lemma && entryStruct.lemma !== entryStruct.head) header += ' lemma=' + entryStruct.lemma;
  if (entryStruct.upos) header += ' upos=' + entryStruct.upos;
  if (entryStruct.xpos) header += ' xpos=' + entryStruct.xpos;
  var lines = [header];
  if (Array.isArray(entryStruct.morphTags) && entryStruct.morphTags.length) {
    lines.push('  morph: ' + entryStruct.morphTags.join(' | '));
  }
  for (var i = 0; i < entryStruct.senses.length; i++) {
    lines.push('  ' + (i + 1) + '. ' + entryStruct.senses[i]);
  }
  return lines.join('\n');
}
export function _assistantBuildTokenText(obj) {
  if (!obj || typeof obj !== 'object') return '';
  var lines = ['=== Token context ==='];
  if (obj.surface) lines.push('Surface: ' + obj.surface);
  if (obj.lookupText && (!obj.surface || !hasSameVisibleComparisonText(obj.lookupText, obj.surface))) {
    lines.push('Lookup: ' + obj.lookupText);
  }
  if (obj.lemma) {
    var lemmaLine = 'Lemma: ' + obj.lemma;
    if (obj.lemmaRaw && obj.lemmaRaw !== obj.lemma) lemmaLine += ' (' + obj.lemmaRaw + ')';
    lines.push(lemmaLine);
  }
  if (obj.upos) lines.push('UPOS: ' + obj.upos);
  if (obj.xpos) lines.push('XPOS: ' + obj.xpos);
  if (Array.isArray(obj.feats) && obj.feats.length) {
    var featParts = [];
    for (var fi = 0; fi < obj.feats.length; fi++) {
      featParts.push(obj.feats[fi][1] ? obj.feats[fi][0] + '=' + obj.feats[fi][1] : obj.feats[fi][0]);
    }
    lines.push('Features: ' + featParts.join(' | '));
  }
  if (Array.isArray(obj.mwtParts) && obj.mwtParts.length) lines.push('MWT: ' + obj.mwtParts.join(' + '));
  if (Array.isArray(obj.glossRows) && obj.glossRows.length) {
    lines.push('Gloss:');
    for (var gi = 0; gi < obj.glossRows.length; gi++) {
      var gRow = obj.glossRows[gi] || {};
      var gLine = String(gRow.gloss || '').trim();
      if (!gLine) continue;
      if (gRow.lemma) gLine = gRow.lemma + ': ' + gLine;
      lines.push('  - ' + gLine);
    }
  }
  if (Array.isArray(obj.entries) && obj.entries.length) {
    var block = _assistantEntryBlockFromStruct(obj.entries[0], 0);
    if (block) {
      lines.push('Dictionary entry:');
      lines.push(block);
    }
  }
  return lines.join('\n');
}
export function _assistantEntryBlock(entry, depthLabel) {
  if (!entry || typeof entry !== 'object') return '';
  var entryStruct = _assistantEntryStruct(entry, 8);
  if (!entryStruct) return '';
  var header = (depthLabel ? depthLabel + ' ' : '') + (entryStruct.head || '(entry)');
  if (entryStruct.pos) header += '  [' + entryStruct.pos + ']';
  if (entryStruct.rom) header += '  /' + entryStruct.rom + '/';
  if (entryStruct.lemma && entryStruct.lemma !== entryStruct.head) header += '  lemma=' + entryStruct.lemma;
  if (entryStruct.upos) header += '  upos=' + entryStruct.upos;
  if (entryStruct.xpos) header += '  xpos=' + entryStruct.xpos;
  var lines = [header];
  if (Array.isArray(entryStruct.morphTags) && entryStruct.morphTags.length) {
    lines.push('  morph: ' + entryStruct.morphTags.join(' | '));
  }
  for (var si = 0; si < entryStruct.senses.length; si++)
    lines.push('  ' + (si + 1) + '. ' + entryStruct.senses[si]);
  return lines.join('\n');
}
export function _assistantEntryStruct(entry, maxSenses) {
  if (!entry || typeof entry !== 'object') return null;
  var head = String(entry.head || entry.lemma_form || entry.lemma || '').trim();
  var pos = String(entry.pos || entry.upos || entry.tag || '').trim();
  var lemma = String(entry._lemma || entry.lemma || entry.morph_base || entry.lemma_form || '').trim();
  var rom = String(entry.romanization || entry.pinyin || entry.pron || '').trim();
  var upos = String(entry.upos || '').trim();
  var xpos = String(entry.xpos || entry.tag || '').trim();
  var morphTags = [];
  if (Array.isArray(entry.morph_info)) {
    for (var mi = 0; mi < entry.morph_info.length; mi++) {
      var mt = String(entry.morph_info[mi] || '').trim();
      if (mt && morphTags.indexOf(mt) === -1) morphTags.push(mt);
    }
  } else if (entry.morph_info != null) {
    var singleMorph = String(entry.morph_info || '').trim();
    if (singleMorph) morphTags.push(singleMorph);
  }
  var grammarText = String(entry.grammar || entry._commentary || entry.commentary || '').trim();
  if (grammarText && morphTags.indexOf(grammarText) === -1) morphTags.push(grammarText);
  var limit = Math.max(0, Number(maxSenses) || 0) || 999;
  var sourceSenses = [];
  if (Array.isArray(entry.senses_hover) && entry.senses_hover.length) {
    sourceSenses = entry.senses_hover;
  } else if (Array.isArray(entry.senses_full) && entry.senses_full.length) {
    sourceSenses = entry.senses_full;
  } else if (Array.isArray(entry.senses) && entry.senses.length) {
    sourceSenses = entry.senses;
  }
  var senses = [];
  for (var i = 0; i < sourceSenses.length && senses.length < limit; i++) {
    var sf = sourceSenses[i];
    if (!sf) continue;
    var gloss = '';
    if (typeof sf === 'string') gloss = sf;
    else if (sf && typeof sf === 'object') gloss = String(sf.gloss || sf.text || sf.def || '');
    gloss = gloss.trim();
    if (gloss) senses.push(gloss);
  }
  return {
    head: head,
    pos: pos,
    lemma: lemma,
    rom: rom,
    upos: upos,
    xpos: xpos,
    morphTags: morphTags,
    senses: senses
  };
}
export function _buildAssistantTokenCtx(clickContext, panelEntry, panelSurface) {
  var ctx = clickContext && typeof clickContext === 'object' ? clickContext : {};
  var bannerCtx = ctx.bannerContext && typeof ctx.bannerContext === 'object' ? ctx.bannerContext : ctx;
  var segIdx = isFinite(Number(ctx.segIdx))
    ? Number(ctx.segIdx)
    : isFinite(Number(bannerCtx.segIdx))
      ? Number(bannerCtx.segIdx)
      : -1;
  var partIdx = isFinite(Number(ctx.mwtPartIndex))
    ? Number(ctx.mwtPartIndex)
    : isFinite(Number(bannerCtx.mwtPartIndex))
      ? Number(bannerCtx.mwtPartIndex)
      : -1;
  var udTok = bannerCtx.udTok && typeof bannerCtx.udTok === 'object' ? bannerCtx.udTok : null;
  var posData = bannerCtx.posData && typeof bannerCtx.posData === 'object' ? bannerCtx.posData : {};
  var entry =
    panelEntry && typeof panelEntry === 'object'
      ? panelEntry
      : ctx.entry && typeof ctx.entry === 'object'
        ? ctx.entry
        : bannerCtx.entry && typeof bannerCtx.entry === 'object'
          ? bannerCtx.entry
          : null;
  var anchorText = String(
    ctx.anchorText ||
      ctx.mwtSurfaceSlice ||
      bannerCtx.anchorText ||
      bannerCtx.mwtSurfaceSlice ||
      panelSurface ||
      ctx.surface ||
      bannerCtx.surface ||
      (entry && entry.surface_form) ||
      ''
  ).trim();
  var lookupText = String(
    ctx.lookupText ||
      bannerCtx.lookupText ||
      ctx.mwtChildText ||
      bannerCtx.mwtChildText ||
      (entry && entry.text) ||
      anchorText ||
      ''
  ).trim();
  var surface = anchorText || lookupText;
  var child = null;
  if (udTok && Array.isArray(udTok.mwt_parts) && partIdx >= 0 && partIdx < udTok.mwt_parts.length) {
    child = udTok.mwt_parts[partIdx] || null;
  }
  var lemma = String(
    (child && child.lemma) || bannerCtx.lemma || posData.lemma || (entry && entry.lemma) || ''
  ).trim();
  var lemmaRaw = String(
    bannerCtx.lemma_raw || posData.lemma_raw || (entry && entry.lemma_raw) || lemma
  ).trim();
  var upos = _assistantSliceMwtValue(
    posData.upos_label || posData.upos || (udTok && udTok.upos) || '',
    partIdx
  );
  if (child && child.upos) upos = String(child.upos);
  var xpos = _assistantSliceMwtValue(posData.tag || posData.xpos || (udTok && udTok.xpos) || '', partIdx);
  if (child && (child.tag || child.xpos)) xpos = String(child.tag || child.xpos);
  var dep = _assistantSliceMwtValue(
    posData.dep_label || posData.dep || (udTok && (udTok.dep || udTok.deprel)) || '',
    partIdx
  );
  if (child && child.dep) dep = String(child.dep);
  dep = normalizeDepLabel(dep);
  var featsRaw = _assistantSliceMwtValue(
    filterFeatsForLang(normalizeGrammarMetaValue(posData.feats || '' || (udTok && udTok.feats) || '')),
    partIdx
  );
  var mwtParts = _assistantMwtPartTexts(udTok);
  var head = _assistantGetHeadInfo(udTok);
  var glossRows = _assistantGetGlossRows(
    segIdx,
    lookupText || surface,
    entry,
    posData,
    udTok,
    partIdx,
    child && child.lemma
  );
  var entries = _assistantBuildVisibleEntryCards(entry);
  var out = {
    type: 'token',
    surface: surface,
    lookupText: lookupText || surface,
    segIdx: segIdx,
    lemma: lemma,
    lemmaRaw: lemmaRaw,
    upos: String(upos || '').trim(),
    xpos: String(xpos || '').trim(),
    dep: String(dep || '').trim(),
    head: head,
    feats: _assistantParseFeatPairs(featsRaw),
    mwtParts: mwtParts,
    glossRows: Array.isArray(glossRows) ? glossRows : [],
    entries: entries
  };
  out.text = _assistantBuildTokenText(out);
  return out;
}
export function _serializeAssistantToken(obj) {
  if (!obj || !obj.text) return '';
  return obj.text;
}
export function _buildAssistantSentenceCtx(segIdx) {
  var tokens = [];
  var text = '';
  var clickedIdx = isFinite(Number(segIdx)) && segIdx >= 0 ? Number(segIdx) : null;
  if (
    !dependencyState.latestUdOverlay ||
    !Array.isArray(dependencyState.latestUdOverlay.tokens) ||
    !dependencyState.latestUdOverlay.tokens.length
  ) {
    // Fallback — use segments only
    var ctxS = 0,
      ctxE = (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments.length) || 0;
    if (ctxE === 0)
      return {
        type: 'sentence',
        text: '',
        tokens: [],
        clickedSeg: clickedIdx
      };
    var spans = normalizeUdSentenceSpans(
      (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.sentences) || []
    );
    if (!spans.length) {
      var fbSpans = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
      for (var fi = 0; fi < fbSpans.length; fi++) spans.push([fbSpans[fi].start, fbSpans[fi].end]);
    }
    for (var si = 0; si < spans.length; si++) {
      if (segIdx >= spans[si][0] && segIdx < spans[si][1]) {
        ctxS = spans[si][0];
        ctxE = spans[si][1];
        break;
      }
    }
    for (var i = ctxS; i < ctxE; i++) {
      tokens.push({
        n: i - ctxS + 1,
        seg: i,
        surface: String(hoverLayoutState.latestSegments[i] || ''),
        lemma: '',
        upos: '',
        xpos: '',
        dep: '',
        head: null,
        feats: [],
        isClicked: clickedIdx === i
      });
    }
    text = hoverLayoutState.latestSegments
      .slice(ctxS, ctxE)
      .join(' ')
      .replace(/\s+([,.;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])/g, '$1')
      .trim();
    return {
      type: 'sentence',
      text: text,
      tokens: tokens,
      clickedSeg: clickedIdx
    };
  }
  var udTokens = dependencyState.latestUdOverlay.tokens;
  var sents = normalizeUdSentenceSpans(dependencyState.latestUdOverlay.sentences || []);
  var doc2seg = Array.isArray(dependencyState.latestUdOverlay.doc2seg)
    ? dependencyState.latestUdOverlay.doc2seg
    : null;
  var sentStart = 0,
    sentEnd = udTokens.length;
  if (sents.length && doc2seg) {
    for (var s = 0; s < sents.length; s++) {
      var rng = sents[s];
      var docS = rng[0] | 0,
        docE = rng[1] | 0;
      var segMatch = false;
      for (var d = docS; d < docE && d < doc2seg.length; d++) {
        if ((doc2seg[d] | 0) === (segIdx | 0)) {
          segMatch = true;
          break;
        }
      }
      if (segMatch) {
        sentStart = docS;
        sentEnd = docE;
        break;
      }
    }
  } else if (sents.length) {
    for (var s2 = 0; s2 < sents.length; s2++) {
      var r2 = sents[s2];
      if (segIdx >= r2[0] && segIdx < r2[1]) {
        sentStart = r2[0];
        sentEnd = r2[1];
        break;
      }
    }
  }
  var textParts = [];
  var n = 0;
  for (var ti = sentStart; ti < sentEnd && ti < udTokens.length; ti++) {
    var t = udTokens[ti] || {};
    n += 1;
    var tSurf = String(t.text || t.form || '');
    if (tSurf) textParts.push(tSurf);
    var tHead = Array.isArray(t.heads) ? t.heads[0] : t.head;
    var seg = doc2seg && ti < doc2seg.length ? doc2seg[ti] | 0 : t.i != null ? t.i : -1;
    var featsArr = [];
    if (t.feats) {
      if (typeof t.feats === 'object' && !Array.isArray(t.feats)) {
        Object.keys(t.feats).forEach(function (k) {
          var v = t.feats[k];
          if (v == null || v === '') return;
          featsArr.push([k, String(v)]);
        });
      } else {
        var fstr = _assistantFormatFeats(t.feats);
        if (fstr)
          fstr.split('|').forEach(function (p) {
            var ix = p.indexOf('=');
            if (ix > 0) featsArr.push([p.slice(0, ix), p.slice(ix + 1)]);
          });
      }
    }
    tokens.push({
      n: n,
      docIdx: ti,
      seg: seg,
      surface: tSurf,
      lemma: String(t.lemma || ''),
      upos: String(t.upos || ''),
      xpos: String(t.xpos || ''),
      dep: String(t.dep || t.deprel || ''),
      head: tHead != null ? tHead : null,
      feats: featsArr,
      isClicked: clickedIdx != null && seg === clickedIdx
    });
  }
  text = textParts
    .join(' ')
    .replace(/\s+([,.;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])/g, '$1')
    .trim();
  return {
    type: 'sentence',
    text: text,
    tokens: tokens,
    clickedSeg: clickedIdx
  };
}
export function _serializeAssistantSentence(obj) {
  if (!obj || !obj.text) return '';
  var out = '=== Sentence context ===\n' + obj.text;
  if (Array.isArray(obj.tokens) && obj.tokens.length) {
    // Build docIdx → sentence-n reverse map
    var docIdxToN = {};
    for (var j = 0; j < obj.tokens.length; j++) {
      var tk = obj.tokens[j];
      if (tk.docIdx != null) docIdxToN[tk.docIdx] = tk.n;
    }
    var depLines = [];
    for (var i = 0; i < obj.tokens.length; i++) {
      var t = obj.tokens[i];
      var dep = String(t.dep || '').trim();
      if (!dep) continue;
      var headN = t.head != null && docIdxToN[t.head] != null ? docIdxToN[t.head] : null;
      var headStr = dep.toLowerCase() === 'root' ? 'ROOT' : headN != null ? String(headN) : '?';
      depLines.push(t.n + '\t' + t.surface + '\t' + dep + '\t' + headStr);
    }
    if (depLines.length) out += '\nDep tree (n  surface  dep  head):\n' + depLines.join('\n');
  }
  return out;
}
export function _buildAssistantReaderCtx() {
  var text = '';
  var tokenCount = 0;
  var sentCount = 0;
  if (Array.isArray(hoverLayoutState.latestSegments) && hoverLayoutState.latestSegments.length) {
    text = hoverLayoutState.latestSegments
      .join(' ')
      .replace(/\s+([,.;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])/g, '$1')
      .trim();
    tokenCount = hoverLayoutState.latestSegments.length;
    var spans = normalizeUdSentenceSpans(
      (dependencyState.latestUdOverlay && dependencyState.latestUdOverlay.sentences) || []
    );
    sentCount = spans.length;
    if (!sentCount) {
      var fbS = getSentenceSpansFromSegments(hoverLayoutState.latestSegments);
      sentCount = fbS.length;
    }
  } else {
    var rt = document.getElementById('renderedText');
    text = rt ? rt.innerText || rt.textContent || '' : '';
  }
  return {
    type: 'reader',
    text: text,
    tokenCount: tokenCount,
    sentCount: sentCount
  };
}
export function _serializeAssistantReader(obj) {
  if (!obj || !obj.text) return '';
  return '=== Reader context ===\n' + obj.text;
}
export function _buildSentenceTabletTextFromTokens(tokens) {
  var parts = [];
  var src = Array.isArray(tokens) ? tokens : [];
  for (var i = 0; i < src.length; i++) {
    var text = String(src[i] == null ? '' : src[i]).trim();
    if (text) parts.push(text);
  }
  return parts
    .join(' ')
    .replace(/\s+([,.;:!?\u3002\uff0c\u3001\uff1b\uff1a\uff01\uff1f])/g, '$1')
    .trim();
}
export function _buildSentenceTabletDataForSeg(segIdx) {
  var idx = Number(segIdx);
  if (
    !isFinite(idx) ||
    idx < 0 ||
    !Array.isArray(hoverLayoutState.latestSegments) ||
    !hoverLayoutState.latestSegments.length
  ) {
    return {
      ok: false,
      error: 'No active lookup.'
    };
  }
  var spans = getDepTreeExperimentSentenceSpans();
  var span = null;
  for (var si = 0; si < spans.length; si++) {
    var cur = spans[si];
    if (idx >= cur.start && idx < cur.end) {
      span = cur;
      break;
    }
  }
  if (!span) {
    return {
      ok: false,
      error: 'Sentence not found.'
    };
  }
  var tokens = [];
  for (var i = span.start; i < span.end; i++) {
    var tokenText = String(
      (hoverLayoutState.latestSegments && hoverLayoutState.latestSegments[i]) || ''
    ).trim();
    tokens.push({
      segIdx: i,
      token: tokenText
    });
  }
  var tokenTexts = tokens.map(function (tok) {
    return String(tok.token || '');
  });
  return {
    ok: true,
    lang: String(documentShellState.currentLanguage || ''),
    segStart: span.start,
    segEnd: span.end,
    key: String(documentShellState.currentLanguage || '') + '\u0001' + JSON.stringify(tokenTexts),
    sentenceText: _buildSentenceTabletTextFromTokens(tokenTexts),
    tokens: tokens
  };
}
export function _resetSentenceTabletGlossOverrides() {
  hoverLayoutState.latestLlmGlossOverrides = Object.create(null);
}
export function showInitialInputGuidanceIfEmpty() {
  if (!hoverLayoutState.sourceText) return;
  if ((hoverLayoutState.sourceText.value || '').trim()) return;
  hoverLayoutState.sourceText.value = lookupProgressState.initialInputGuidance;
  lookupProgressState.initialInputGuidanceActive = true;
  autoResizeTextarea();
}
export function clearInitialInputGuidanceIfNeeded() {
  if (!hoverLayoutState.sourceText || !lookupProgressState.initialInputGuidanceActive) return;
  if ((hoverLayoutState.sourceText.value || '') === lookupProgressState.initialInputGuidance) {
    hoverLayoutState.sourceText.value = '';
  }
  lookupProgressState.initialInputGuidanceActive = false;
}
export function isShowingInitialInputGuidance() {
  return (
    !!hoverLayoutState.sourceText &&
    lookupProgressState.initialInputGuidanceActive &&
    (hoverLayoutState.sourceText.value || '') === lookupProgressState.initialInputGuidance
  );
}
export function dismissInitialExampleDemo() {
  if (!lookupProgressState.initialExampleDemoActive) return;
  lookupProgressState.initialExampleDemoActive = false;
  hoverLayoutState.latestData = null;
  _resetSentenceTabletGlossOverrides();
  hoverLayoutState.latestSegments = [];
  lookupProgressState.latestOriginalText = '';
  if (hoverLayoutState.renderedText) hoverLayoutState.renderedText.innerHTML = '';
  if (
    !lookupProgressState.depTreeUseConllu &&
    lookupProgressState.depTreeController &&
    typeof lookupProgressState.depTreeController.setData === 'function'
  ) {
    lookupProgressState.depTreeController.setData({
      segments: [],
      udOverlay: null
    });
  }
}
export function renderInitialExampleDemoIfAvailable() {
  if (!hoverLayoutState.renderedText) return;
  if (documentState.currentFile) return;
  if (documentState.inputMode !== 'raw') return;
  if ((hoverLayoutState.renderedText.textContent || '').trim()) return;
  if (typeof INITIAL_EXAMPLE_CACHE === 'undefined' || !INITIAL_EXAMPLE_CACHE || !INITIAL_EXAMPLE_CACHE.ok)
    return;
  var cachedData = INITIAL_EXAMPLE_CACHE;
  var exampleText = cachedData.display_text || '';
  hoverLayoutState.latestData = cachedData;
  _resetSentenceTabletGlossOverrides();
  pushLookupResolverPayload(cachedData);
  hoverLayoutState.latestSegments = Array.isArray(cachedData.segments) ? cachedData.segments : [];
  lookupProgressState.initialExampleDemoActive = true;
  renderSegments(cachedData, exampleText);
}
export function buildLookupPostRequest(url, init) {
  var rawUrl = String(url || '');
  var fetchInit = Object.assign({}, init || {});
  try {
    var parsed = new URL(rawUrl, window.location.origin);
    if (parsed.pathname !== '/lookup' || !parsed.searchParams.has('q')) {
      return {
        url: url,
        init: fetchInit,
        decoratorUrl: rawUrl
      };
    }
    var q = String(parsed.searchParams.get('q') || '');
    parsed.searchParams.delete('q');
    var body = {};
    if (fetchInit.body) {
      try {
        var parsedBody = JSON.parse(String(fetchInit.body || '{}'));
        if (parsedBody && typeof parsedBody === 'object' && !Array.isArray(parsedBody)) {
          body = parsedBody;
        }
      } catch (_e) {}
    }
    body.q = q;
    if (!body.lang && parsed.searchParams.get('lang')) {
      body.lang = String(parsed.searchParams.get('lang') || '');
    }
    var headers = {};
    if (fetchInit.headers instanceof Headers) {
      fetchInit.headers.forEach(function (value, key) {
        headers[key] = value;
      });
    } else if (Array.isArray(fetchInit.headers)) {
      fetchInit.headers.forEach(function (pair) {
        if (pair && pair.length >= 2) headers[String(pair[0])] = String(pair[1]);
      });
    } else if (fetchInit.headers && typeof fetchInit.headers === 'object') {
      headers = Object.assign({}, fetchInit.headers);
    }
    if (!headers['Content-Type'] && !headers['content-type']) {
      headers['Content-Type'] = 'application/json';
    }
    fetchInit.method = 'POST';
    fetchInit.headers = headers;
    fetchInit.body = JSON.stringify(body);
    return {
      url: parsed.pathname + parsed.search + parsed.hash,
      init: fetchInit,
      decoratorUrl: rawUrl
    };
  } catch (_err) {
    return {
      url: url,
      init: fetchInit,
      decoratorUrl: rawUrl
    };
  }
}
export function startSegmentLookupFetch(url, init) {
  dismissInitialExampleDemo();
  reportLookupProgress('Sending text');
  if (hoverLayoutState.segmentLookupAbort) hoverLayoutState.segmentLookupAbort.abort();
  hoverLayoutState.segmentLookupAbort = new AbortController();
  var fetchInit = Object.assign({}, init || {});
  fetchInit.signal = hoverLayoutState.segmentLookupAbort.signal;
  var request = buildLookupPostRequest(url, fetchInit);
  return fetch(request.url, request.init).then(function (resp) {
    return decorateLookupFetchResponse(resp, request.decoratorUrl || url);
  });
}
export function decorateLookupFetchResponse(resp, rawUrl) {
  var api = getDictionaryRuntimeApi();
  if (!api || typeof api.maybeDecorateJsonResponse !== 'function') {
    return Promise.resolve(resp);
  }
  try {
    return api.maybeDecorateJsonResponse(resp, new URL(String(rawUrl || ''), window.location.origin));
  } catch (_e) {
    return Promise.resolve(resp);
  }
}
export function reportLookupProgress(message) {
  try {
    if (window.__LE_lookupProgress && window.__LE_LOOKUP_ACTIVE) {
      window.__LE_lookupProgress(message);
    } else if (typeof document !== 'undefined') {
      document.dispatchEvent(
        new CustomEvent('le:lookup-progress', {
          detail: {
            message: String(message || '')
          }
        })
      );
    }
  } catch (_e) {}
}
export function completeLookupProgress() {
  try {
    if (window.__LE_lookupComplete && window.__LE_LOOKUP_ACTIVE) {
      window.__LE_lookupComplete();
    } else if (typeof document !== 'undefined') {
      document.dispatchEvent(new CustomEvent('le:lookup-complete'));
    }
  } catch (_e) {}
}
export function initializeLookupProgress() {
  lookupProgressState.DEP_TREE_INLINE_PREF_WIDTH_WIDE = 1180;
  lookupProgressState.DEP_TREE_INLINE_PREF_HEIGHT = 720;
  try {
    window.LEReaderAssistantBridge = window.LEReaderAssistantBridge || {};
    window.LEReaderAssistantBridge.getReaderCtx = _buildAssistantReaderCtx;
    window.LEReaderAssistantBridge.serializeReader = _serializeAssistantReader;
    window.LEReaderAssistantBridge.getSentenceTabletDataForSeg = _buildSentenceTabletDataForSeg;
    // Return sentence-tablet data for every sentence in the current lookup.
    // Used by the LLM assistant to batch-translate all sentences in one Gemini
    // call so the model has full discourse context.
    window.LEReaderAssistantBridge.getAllSentenceTabletData = function () {
      if (!Array.isArray(hoverLayoutState.latestSegments) || !hoverLayoutState.latestSegments.length)
        return [];
      var spans = getDepTreeExperimentSentenceSpans();
      var out = [];
      for (var i = 0; i < spans.length; i++) {
        var s = spans[i];
        if (!s || typeof s.start !== 'number') continue;
        var d = _buildSentenceTabletDataForSeg(s.start);
        if (d && d.ok) out.push(d);
      }
      return out;
    };
  } catch (_e) {}
  lookupProgressState.latestRawWordSpans = []; // Raw PDF word spans for annotation
  lookupProgressState.latestRawPageData = null; // Page data for annotation
  lookupProgressState.latestOriginalText = '';
  lookupProgressState.latestFillsDict = null;
  lookupProgressState.panelOpen = false;
  lookupProgressState.depTreeController = null;
  lookupProgressState.depTreeUseConllu = false;
  lookupProgressState.depTreeConlluUrl = '/myudtree.sentence?i=';
  lookupProgressState.depTreeConlluMetaUrl = '/myudtree.meta';
  lookupProgressState.rawTextDocActive = false;
  lookupProgressState.embeddedFontRegistry = {};
  lookupProgressState.initialInputGuidance = '';
  lookupProgressState.initialInputGuidanceActive = false;
  lookupProgressState.initialExampleDemoActive = false;
  return true;
}
