import {
  buildDebugFillPreview,
  languageUsesXposFilter,
  normalizeFilterXposTag,
  splitCompoundTags
} from './alignment-inputs.mjs';
import { getCurrentLanguage, normalizeVisibleComparisonText, splitCompoundLemma } from './core.mjs';
import { coreState } from './core.state.mjs';
import { getEntryDisplayReading, getStableRuntimeEntryId } from './entry-adapters.mjs';
import { _ensureEntryHydrated } from './hydration.mjs';
import { resolveExactThenGreedy } from './winner-references.mjs';
export function mergeLookupResults(results, mode) {
  var mergedEntries = [];
  var mergedFills = [];
  var hasKnown = false;
  var hasUnknown = false;
  var mergedDpDebugParts = [];
  for (var i = 0; i < (results || []).length; i++) {
    var result = results[i];
    if (!result || typeof result !== 'object') continue;
    var ents = result.entries || [];
    for (var e = 0; e < ents.length; e++) mergedEntries.push(ents[e]);
    var fill = result.fill || {};
    var fills = fill.fills || [];
    for (var f = 0; f < fills.length; f++) mergedFills.push(fills[f]);
    hasKnown = hasKnown || !!fill.has_known;
    hasUnknown = hasUnknown || !!fill.has_unknown;
    if (fill.dp_debug && typeof fill.dp_debug === 'object') {
      mergedDpDebugParts.push({
        index: i,
        mode: String(fill.mode || ''),
        fills: buildDebugFillPreview(fill),
        dp_debug: fill.dp_debug
      });
    }
  }
  if (!mergedEntries.length) return null;
  var mergedFill = {
    mode: mode,
    fills: mergedFills,
    has_known: hasKnown || !!mergedEntries.length,
    has_unknown: hasUnknown
  };
  if (mergedDpDebugParts.length) {
    mergedFill.dp_debug = {
      kind: 'merged',
      mode: mode,
      parts: mergedDpDebugParts
    };
  }
  return {
    entries: mergedEntries,
    fill: mergedFill
  };
}
export function resultMatchCount(result) {
  if (!result || typeof result !== 'object') return 0;
  var fill = result.fill || {};
  var fills = Array.isArray(fill.fills) ? fill.fills : [];
  if (fills.length) return fills.length;
  return Array.isArray(result.entries) ? result.entries.length : 0;
}
export function resolveLemmaOverride(surface, lemmaText, engine, upos, xpos, options) {
  options = options || {};
  var lemmaValue = String(lemmaText || '').trim();
  if (!lemmaValue) return null;
  var parts = splitCompoundLemma(lemmaValue);
  var lookupTarget = parts.length ? parts.join('') : lemmaValue;
  if (!lookupTarget) return null;
  var resolved = resolveExactThenGreedy(
    surface,
    lookupTarget,
    engine,
    upos || '',
    'lemma_override',
    'lemma_greedy',
    lemmaValue,
    String(xpos || '')
      .trim()
      .toLowerCase(),
    options
  );
  return resolved;
}
export function wiktLookup(word, lemma, engine, xpos, upos, options) {
  options = options || {};
  var includeDebugTrace = !!options.debug_trace;
  var surface = String(word || '').trim();
  var lemmaText = String(lemma || '').trim();
  if (!surface) return null;
  var lemmaResult = null;
  var debugLookupEvents = includeDebugTrace
    ? {
        surface: [],
        lemma: []
      }
    : null;
  function makeLookupOptions(pathLabel) {
    if (!includeDebugTrace) return options;
    var out = {};
    for (var key in options) {
      if (Object.prototype.hasOwnProperty.call(options, key)) out[key] = options[key];
    }
    out._debug_lookup_events = debugLookupEvents;
    out._debug_lookup_label = String(pathLabel || '');
    return out;
  }
  var surfaceLookupOptions = makeLookupOptions('surface');
  var lemmaLookupOptions = makeLookupOptions('lemma');
  function finishLookupResult(result, chosenPath, reason) {
    if (includeDebugTrace && result && typeof result === 'object') {
      result._debug_lookup_scoring = {
        token: surface,
        lemma_text: lemmaText,
        chosen_path: String(chosenPath || ''),
        selection_reason: String(reason || ''),
        surface_exact_events:
          debugLookupEvents && Array.isArray(debugLookupEvents.surface)
            ? debugLookupEvents.surface.slice()
            : [],
        lemma_exact_events:
          debugLookupEvents && Array.isArray(debugLookupEvents.lemma) ? debugLookupEvents.lemma.slice() : []
      };
    }
    if (result && typeof result === 'object') {
      result.resolved_via = String(chosenPath || '');
    }
    return result;
  }
  var surfaceResult = options.surface_result || null;
  if (!surfaceResult) {
    surfaceResult = resolveExactThenGreedy(
      surface,
      surface,
      engine,
      upos || '',
      'exact',
      'greedy',
      lemmaText || surface,
      xpos || '',
      surfaceLookupOptions
    );
  }
  if (!lemmaText || normalizeVisibleComparisonText(lemmaText) === normalizeVisibleComparisonText(surface)) {
    return finishLookupResult(surfaceResult, 'surface', 'lemma_same_as_surface');
  }
  lemmaResult = resolveLemmaOverride(surface, lemmaText, engine, upos || '', xpos || '', lemmaLookupOptions);
  if (lemmaResult == null) return finishLookupResult(surfaceResult, 'surface', 'lemma_unresolved');
  if (surfaceResult == null) return finishLookupResult(lemmaResult, 'lemma', 'surface_unresolved');
  var surfaceHasUnknown = !!(surfaceResult.fill && surfaceResult.fill.has_unknown);
  var lemmaHasUnknown = !!(lemmaResult.fill && lemmaResult.fill.has_unknown);
  if (surfaceHasUnknown !== lemmaHasUnknown) {
    if (surfaceHasUnknown) return finishLookupResult(lemmaResult, 'lemma', 'surface_has_unknown');
    return finishLookupResult(surfaceResult, 'surface', 'lemma_has_unknown');
  }
  var lemmaCount = resultMatchCount(lemmaResult);
  var surfaceCount = resultMatchCount(surfaceResult);
  if (lemmaCount < surfaceCount) {
    return finishLookupResult(lemmaResult, 'lemma', 'lemma_has_fewer_matches');
  }
  if (lemmaCount === surfaceCount) {
    var surfaceMode = String((surfaceResult.fill && surfaceResult.fill.mode) || '').toLowerCase();
    // If surface is an exact match, preserve it on ties.
    if (surfaceMode === 'exact')
      return finishLookupResult(surfaceResult, 'surface', 'tie_prefers_surface_exact');
    // Otherwise (greedy surface path), lemma wins ties.
    return finishLookupResult(lemmaResult, 'lemma', 'tie_prefers_lemma');
  }
  return finishLookupResult(surfaceResult, 'surface', 'surface_has_fewer_matches');
}
export function dedupeMergedSenseLines(lines) {
  var out = [];
  var seen = Object.create(null);
  var seenSenseSegments = Object.create(null);
  var seenSenseTexts = Object.create(null);
  for (var i = 0; i < (lines || []).length; i++) {
    var line = String(lines[i] || '');
    if (!line) continue;
    if (line.charAt(0) === '\x1E') {
      seenSenseSegments = Object.create(null);
      seenSenseTexts = Object.create(null);
      out.push(line);
      continue;
    }
    var senseText = '';
    var prefix = '';
    var resetOverlap = line.charAt(0) !== '\t';
    var parts = line.split('\t');
    if (parts.length > 1) {
      senseText = String(parts[parts.length - 1] || '').trim();
      prefix = line.slice(0, line.length - String(parts[parts.length - 1] || '').length);
    }
    if (resetOverlap) {
      seenSenseSegments = Object.create(null);
      seenSenseTexts = Object.create(null);
    }
    if (senseText) {
      if (seenSenseTexts[senseText]) continue;
      var trimmedSenseText = trimSeenGlossOverlap(senseText, seenSenseSegments);
      if (!trimmedSenseText) continue;
      line = prefix + trimmedSenseText;
    }
    if (seen[line]) continue;
    seen[line] = true;
    out.push(line);
    if (senseText) {
      var emittedSenseText = String(line.slice(prefix.length) || '').trim();
      if (emittedSenseText) seenSenseTexts[emittedSenseText] = true;
      seenSenseTexts[senseText] = true;
      var visibleSegments = splitGlossDedupeSegments(emittedSenseText);
      for (var ssi = 0; ssi < visibleSegments.length; ssi++) {
        seenSenseSegments[visibleSegments[ssi]] = true;
      }
    }
  }
  return out;
}
export function splitGlossDedupeSegments(text) {
  return String(text || '')
    .split(';')
    .map(function (part) {
      return String(part || '').trim();
    })
    .filter(Boolean);
}

// Strip previously shown semicolon-delimited gloss parts from later sense rows.
export function trimSeenGlossOverlap(text, seenSegments) {
  var original = String(text || '').trim();
  if (!original) return '';
  var segments = splitGlossDedupeSegments(original);
  if (!segments.length) return '';
  if (!seenSegments || typeof seenSegments !== 'object') return original;
  var kept = [];
  for (var i = 0; i < segments.length; i++) {
    if (seenSegments[segments[i]]) continue;
    kept.push(segments[i]);
  }
  return kept.join('; ').trim();
}
export function listTexts(raw) {
  var out = [];
  if (Array.isArray(raw)) {
    for (var i = 0; i < raw.length; i++) {
      var txt = String(raw[i] || '').trim();
      if (txt) out.push(txt);
    }
  } else {
    var one = String(raw || '').trim();
    if (one) out.push(one);
  }
  return out;
}
export function buildEntrySpellingsHead(entry) {
  var direct = String((entry && entry.spelling_header) || '').trim();
  if (direct) return direct;
  var forms = entry && entry.forms && typeof entry.forms === 'object' ? entry.forms : {};
  var kanjiForms = Array.isArray(forms.kanji) ? forms.kanji : entry && entry.kanji ? entry.kanji : [];
  var readings = Array.isArray(forms.readings)
    ? forms.readings
    : entry && entry.readings
      ? entry.readings
      : [];
  if (kanjiForms && kanjiForms.length) {
    var header = kanjiForms.join('\u30fb');
    if (readings && readings.length) header += '\u3010' + readings.join('\u30fb') + '\u3011';
    return header;
  }
  return readings && readings.length ? readings.join('\u30fb') : '';
}
export function abbreviatePos(posText) {
  if (!posText) return '';
  var lower = String(posText).toLowerCase().trim();
  if (Object.prototype.hasOwnProperty.call(coreState.POS_ABBREV, lower)) return coreState.POS_ABBREV[lower];
  for (var full in coreState.POS_ABBREV) {
    if (!Object.prototype.hasOwnProperty.call(coreState.POS_ABBREV, full)) continue;
    if (String(full).toLowerCase() === lower) return coreState.POS_ABBREV[full];
  }
  var fallback = String(posText || '').trim();
  if (fallback.length > 6) fallback = fallback.slice(0, 6);
  return fallback.trim().replace(/,+$/, '');
}
export function formatStructuredSenses(senses) {
  if (!senses || !senses.length) return [];
  var dictSenses = [];
  for (var i = 0; i < senses.length; i++) {
    if (senses[i] && typeof senses[i] === 'object' && senses[i].glosses) dictSenses.push(senses[i]);
  }
  var commonMisc = Object.create(null);
  if (dictSenses.length) {
    var firstMisc = dictSenses[0].misc || [];
    for (var fm = 0; fm < firstMisc.length; fm++) commonMisc[String(firstMisc[fm] || '')] = true;
    for (var ds = 1; ds < dictSenses.length; ds++) {
      var set = Object.create(null);
      var cur = dictSenses[ds].misc || [];
      for (var cm = 0; cm < cur.length; cm++) set[String(cur[cm] || '')] = true;
      var nextCommon = Object.create(null);
      for (var key in commonMisc) {
        if (Object.prototype.hasOwnProperty.call(commonMisc, key) && set[key]) nextCommon[key] = true;
      }
      commonMisc = nextCommon;
    }
  }
  var formatted = [];
  var prevPosKey = '';
  for (var si = 0; si < senses.length; si++) {
    var sense = senses[si];
    if (!sense || typeof sense !== 'object') {
      formatted.push('\t' + String(sense || ''));
      continue;
    }
    var glosses = Array.isArray(sense.glosses) ? sense.glosses : [];
    if (!glosses.length) continue;
    var posList = Array.isArray(sense.pos) ? sense.pos : [];
    var misc = Array.isArray(sense.misc) ? sense.misc : [];
    var sInf = String(sense.s_inf || '');
    var field = Array.isArray(sense.field) ? sense.field : [];
    var stagk = Array.isArray(sense.stagk) ? sense.stagk : [];
    var stagr = Array.isArray(sense.stagr) ? sense.stagr : [];
    var xref = Array.isArray(sense.xref) ? sense.xref : [];
    var ant = Array.isArray(sense.ant) ? sense.ant : [];
    var dial = Array.isArray(sense.dial) ? sense.dial : [];
    var lsource = Array.isArray(sense.lsource) ? sense.lsource : [];
    var posParts = [];
    for (var p = 0; p < posList.length; p++) {
      var part = abbreviatePos(posList[p]);
      part = part.split(/\s+/).join(' ').trim().replace(/,+$/, '');
      if (part) posParts.push(part);
    }
    var posLabel = posParts.join(', ');
    var posKey = posList.join('|');
    var senseText = glosses.join('; ');
    var annotations = [];
    for (var m = 0; m < misc.length; m++) {
      var mv = String(misc[m] || '');
      if (!mv || commonMisc[mv]) continue;
      annotations.push(mv);
    }
    for (var f = 0; f < field.length; f++) annotations.push(String(field[f] || ''));
    for (var d = 0; d < dial.length; d++) annotations.push(String(dial[d] || ''));
    if (stagk.length) annotations.push('kanji: ' + stagk.join(', '));
    if (stagr.length) annotations.push('reading: ' + stagr.join(', '));
    if (lsource.length) annotations.push('source: ' + lsource.join(', '));
    if (annotations.length) senseText += ' [' + annotations.join('; ') + ']';
    if (xref.length) senseText += ' [cf. ' + xref.join(', ') + ']';
    if (ant.length) senseText += ' [ant. ' + ant.join(', ') + ']';
    if (sInf) senseText += '\x1F(' + sInf + ')';
    if (!formatted.length || (posKey !== prevPosKey && posLabel)) {
      formatted.push('\t\t' + posLabel + '\t' + senseText);
    } else {
      formatted.push('\t' + senseText);
    }
    if (posKey) prevPosKey = posKey;
  }
  var commonMiscKeys = Object.keys(commonMisc).sort();
  if (commonMiscKeys.length) {
    formatted.push('\t[' + commonMiscKeys.join('; ') + ']');
  }
  return formatted;
}
export function formatSenses(head, roman, rawSenses, pos) {
  if (!rawSenses || !rawSenses.length) return [];
  var formatted = [];
  for (var i = 0; i < rawSenses.length; i++) {
    var sense = rawSenses[i];
    if (i === 0)
      formatted.push(
        String(head || '') +
          '\t' +
          String(roman || '') +
          '\t' +
          String(pos || '') +
          '\t' +
          String(sense || '')
      );
    else formatted.push('\t\t\t' + String(sense || ''));
  }
  return formatted;
}
export function mergeAllEntries(head, entries) {
  var formatted = [];
  for (var i = 0; i < (entries || []).length; i++) {
    var entry = entries[i] || {};
    _ensureEntryHydrated(entry);
    var roman = getEntryDisplayReading(entry);
    var pos = entry.pos || '';
    var sensesFull = Array.isArray(entry.senses_full) ? entry.senses_full : [];
    var senses = Array.isArray(entry.senses) ? entry.senses : [];
    if (sensesFull.length || (senses.length && typeof senses[0] === 'object')) {
      var entryHead = buildEntrySpellingsHead(entry);
      if (entryHead) formatted.push('\x1E' + entryHead);
      var structured = formatStructuredSenses(sensesFull.length ? sensesFull : senses);
      for (var s = 0; s < structured.length; s++) formatted.push(structured[s]);
    } else {
      var displayHead = String(entry.headword || head || '');
      var lines = formatSenses(displayHead, roman, senses, pos);
      for (var l = 0; l < lines.length; l++) formatted.push(lines[l]);
    }
  }
  return dedupeMergedSenseLines(formatted);
}
export function computeMetaSpecTag(tags) {
  var rawTags = listTexts(tags);
  var tagSet = Object.create(null);
  for (var i = 0; i < rawTags.length; i++) tagSet[rawTags[i]] = true;
  if (tagSet.spec1) return 'spec1';
  if (tagSet.spec2) return 'spec2';
  return '';
}
export function metaNfPercent(nfBand) {
  var band = Math.max(1, Math.min(48, Number(nfBand) || 1));
  var pct = ((49 - band) / 48.0) * 100.0;
  if (pct < 0.0) return 0.0;
  if (pct > 100.0) return 100.0;
  return pct;
}
export function computeMetaPriScoreDetails(tags) {
  var rawTags = listTexts(tags);
  var bestNf = null;
  for (var i = 0; i < rawTags.length; i++) {
    var m = coreState.META_NF_RE.exec(rawTags[i]);
    if (!m) continue;
    var nfBand = parseInt(m[1], 10);
    if (!isFinite(nfBand)) continue;
    if (bestNf == null || nfBand < bestNf) bestNf = nfBand;
  }
  if (bestNf != null) return [metaNfPercent(bestNf), 'nf' + String(bestNf).padStart(2, '0')];
  var bestScore = 0.0;
  var bestTag = '';
  for (var j = 0; j < rawTags.length; j++) {
    var pct = coreState.META_PRI_TAG_PERCENT[rawTags[j]];
    if (pct == null) continue;
    if (pct > bestScore) {
      bestScore = pct;
      bestTag = rawTags[j];
    }
  }
  if (bestScore < 0.0) bestScore = 0.0;
  if (bestScore > 100.0) bestScore = 100.0;
  return [bestScore, bestTag];
}
export function buildJmdictFormsMetaBundle(entry) {
  if (!entry || typeof entry !== 'object') return {};
  if (entry.forms_meta && typeof entry.forms_meta === 'object') {
    return Object.assign({}, entry.forms_meta);
  }
  var kanjiInfo = entry.kanji_info || {};
  var kanjiPri = entry.kanji_pri || {};
  var readingInfo = entry.reading_info || {};
  var readingPri = entry.reading_pri || {};
  var readingRestr = entry.reading_restr || {};
  var readingNokanji = entry.reading_nokanji || {};
  var kanjiRows = [];
  var kanjiByForm = {};
  var kanjiList = listTexts(entry.kanji || []);
  for (var i = 0; i < kanjiList.length; i++) {
    var kForm = kanjiList[i];
    var kPriTags = listTexts(kanjiPri[kForm] || []);
    var kInfoTags = listTexts(kanjiInfo[kForm] || []);
    var kScore = computeMetaPriScoreDetails(kPriTags);
    var kSpecTag = computeMetaSpecTag(kPriTags);
    var kRow = {
      form: kForm,
      kind: 'kanji',
      info_tags: kInfoTags,
      priority_tags: kPriTags,
      priority_score: kScore[0],
      priority_basis_tag: kScore[1],
      spec_priority_tag: kSpecTag
    };
    kanjiRows.push(kRow);
    kanjiByForm[kForm] = Object.assign({}, kRow);
  }
  var readingRows = [];
  var readingByForm = {};
  var readingList = listTexts(entry.readings || []);
  for (var j = 0; j < readingList.length; j++) {
    var rForm = readingList[j];
    var rPriTags = listTexts(readingPri[rForm] || []);
    var rInfoTags = listTexts(readingInfo[rForm] || []);
    var restricted = listTexts(readingRestr[rForm] || []);
    var noKanji = !!readingNokanji[rForm];
    var rScore = computeMetaPriScoreDetails(rPriTags);
    var rSpecTag = computeMetaSpecTag(rPriTags);
    var rRow = {
      form: rForm,
      kind: 'reading',
      info_tags: rInfoTags,
      priority_tags: rPriTags,
      priority_score: rScore[0],
      priority_basis_tag: rScore[1],
      spec_priority_tag: rSpecTag,
      no_kanji: noKanji,
      restricted_to_kanji: restricted,
      is_restricted: !!restricted.length
    };
    readingRows.push(rRow);
    readingByForm[rForm] = Object.assign({}, rRow);
  }
  return {
    kanji: kanjiRows,
    readings: readingRows,
    kanji_by_form: kanjiByForm,
    readings_by_form: readingByForm
  };
}
export function buildJmdictFormsMetaByHeader(entries) {
  var out = {};
  for (var i = 0; i < (entries || []).length; i++) {
    var entry = entries[i];
    if (!entry || typeof entry !== 'object') continue;
    var header = buildEntrySpellingsHead(entry);
    if (!header || out[header]) continue;
    var bundle = buildJmdictFormsMetaBundle(entry);
    if (!bundle || !Object.keys(bundle).length) continue;
    bundle.header = header;
    out[header] = bundle;
  }
  return out;
}
export function splitEntriesForHover(entries, upos, engine, xpos, filterKwargs) {
  var baseEntries = Array.isArray(entries) ? entries.slice() : [];
  if (!baseEntries.length) return [baseEntries, []];
  var callKw = Object.assign({}, filterKwargs || {});
  var strictLemmaEntries = Array.isArray(callKw.strict_exact_lemma_entries)
    ? callKw.strict_exact_lemma_entries.slice()
    : [];
  if (Object.prototype.hasOwnProperty.call(callKw, 'strict_exact_lemma_entries')) {
    delete callKw.strict_exact_lemma_entries;
  }
  function splitStrictLemmaEntries(inputEntries) {
    var sourceEntries = Array.isArray(inputEntries) ? inputEntries.slice() : [];
    if (!sourceEntries.length || !strictLemmaEntries.length) return null;
    var strictEntryIds = Object.create(null);
    var strictFallback = [];
    for (var sei = 0; sei < strictLemmaEntries.length; sei++) {
      var strictEntry = strictLemmaEntries[sei];
      var strictEntryId = getStableRuntimeEntryId(strictEntry);
      if (strictEntryId) strictEntryIds[strictEntryId] = true;
      else strictFallback.push(strictEntry);
    }
    var strictPrimary = [];
    var strictAlternate = [];
    for (var sbi = 0; sbi < sourceEntries.length; sbi++) {
      var baseEntry = sourceEntries[sbi];
      var baseEntryId = getStableRuntimeEntryId(baseEntry);
      var isStrict = !!(baseEntryId && strictEntryIds[baseEntryId]);
      if (!isStrict && !baseEntryId && strictFallback.indexOf(baseEntry) >= 0) isStrict = true;
      if (isStrict) strictPrimary.push(baseEntry);
      else strictAlternate.push(baseEntry);
    }
    return strictPrimary.length ? [strictPrimary, strictAlternate] : null;
  }
  var explicitAlternate = [];
  var posFilterInput = [];
  for (var bei = 0; bei < baseEntries.length; bei++) {
    var baseEntry = baseEntries[bei];
    if (baseEntry && baseEntry.is_alternate_match) explicitAlternate.push(baseEntry);
    else posFilterInput.push(baseEntry);
  }
  if (!posFilterInput.length) {
    return [baseEntries.slice(), []];
  }
  var strictLemmaSplit = splitStrictLemmaEntries(posFilterInput);
  var lemmaFilterInput = strictLemmaSplit ? strictLemmaSplit[0] : null;
  var nonLemmaEntries = strictLemmaSplit ? strictLemmaSplit[1] : [];
  function runCorePosFilter(inputEntries) {
    var filterInput = Array.isArray(inputEntries) ? inputEntries.slice() : [];
    if (!filterInput.length) return [[], []];
    var result;
    try {
      var activeLang = getCurrentLanguage();
      if (
        languageUsesXposFilter(activeLang) &&
        engine &&
        typeof engine.filter_entries_by_xpos === 'function'
      ) {
        result = engine.filter_entries_by_xpos(
          filterInput,
          splitCompoundTags(xpos)
            .map(function (t) {
              return normalizeFilterXposTag(t, activeLang);
            })
            .filter(Boolean)
        );
      } else if (engine && typeof engine.filter_entries_by_upos === 'function') {
        var filterKw = Object.assign({}, callKw);
        if (xpos && !Object.prototype.hasOwnProperty.call(filterKw, 'xpos')) {
          filterKw.xpos = xpos;
        }
        result = engine.filter_entries_by_upos(filterInput, upos, filterKw);
      } else {
        result = [filterInput, []];
      }
    } catch (_e) {
      result = [filterInput, []];
    }
    if (Array.isArray(result) && result.length === 2) {
      return [Array.isArray(result[0]) ? result[0] : [], Array.isArray(result[1]) ? result[1] : []];
    }
    var filtered = Array.isArray(result) ? result.slice() : [];
    var alternate = [];
    for (var j = 0; j < filterInput.length; j++) {
      if (filtered.indexOf(filterInput[j]) < 0) alternate.push(filterInput[j]);
    }
    return [filtered, alternate];
  }
  function appendExplicitAlternate(alternate) {
    var alt = Array.isArray(alternate) ? alternate.slice() : [];
    for (var i = 0; i < explicitAlternate.length; i++) {
      if (alt.indexOf(explicitAlternate[i]) < 0) alt.push(explicitAlternate[i]);
    }
    return alt;
  }

  // Try to run POS filter on explicitAlternate entries so we can promote them
  // when no non-alt entries survive POS filtering.
  function posFilterAlternates() {
    if (!explicitAlternate.length) return null;
    try {
      var altResult = runCorePosFilter(explicitAlternate);
      return altResult[0].length ? altResult : null;
    } catch (_e2) {
      return null;
    }
  }
  if (lemmaFilterInput && lemmaFilterInput.length) {
    var lemmaResult = runCorePosFilter(lemmaFilterInput);
    var lemmaPrimary = Array.isArray(lemmaResult[0]) ? lemmaResult[0] : [];
    var lemmaAlternate = Array.isArray(lemmaResult[1]) ? lemmaResult[1] : [];
    if (lemmaPrimary.length) {
      var lemmaCombinedAlternate = nonLemmaEntries.slice();
      for (var lai = 0; lai < lemmaAlternate.length; lai++) {
        if (lemmaCombinedAlternate.indexOf(lemmaAlternate[lai]) < 0)
          lemmaCombinedAlternate.push(lemmaAlternate[lai]);
      }
      return [lemmaPrimary, appendExplicitAlternate(lemmaCombinedAlternate)];
    }
    return [lemmaFilterInput.slice(), appendExplicitAlternate(nonLemmaEntries)];
  }
  var result = runCorePosFilter(posFilterInput);
  if (Array.isArray(result) && result.length === 2) {
    var primary = Array.isArray(result[0]) ? result[0] : [];
    var alternate = Array.isArray(result[1]) ? result[1] : [];
    var combinedAlternate = appendExplicitAlternate(alternate);
    if (!primary.length && combinedAlternate.length) {
      // No non-alt entry survived POS filtering. Try promoting alt entries that
      // actually match the POS tag rather than blindly returning everything.
      var altFiltered = posFilterAlternates();
      if (altFiltered) {
        // At least one alt matches — promote the matching alts to primary.
        var altPrimary = Array.isArray(altFiltered[0]) ? altFiltered[0] : [];
        var altSecondary = Array.isArray(altFiltered[1]) ? altFiltered[1] : [];
        // Non-alt entries that failed POS filter go to secondary as well.
        var nonAltFailed = alternate.slice(); // these already failed POS filter
        var secondaryMerged = altSecondary.slice();
        for (var k = 0; k < nonAltFailed.length; k++) {
          if (secondaryMerged.indexOf(nonAltFailed[k]) < 0) secondaryMerged.push(nonAltFailed[k]);
        }
        return [altPrimary, secondaryMerged];
      }
      // No alt matches POS either — fall back to showing everything as primary.
      return [baseEntries.slice(), []];
    }
    if (!primary.length && !combinedAlternate.length)
      return [posFilterInput.slice(), explicitAlternate.slice()];
    return [primary, combinedAlternate];
  }
  var filtered = Array.isArray(result) ? result.slice() : [];
  if (!filtered.length) return [baseEntries.slice(), []];
  var alternateFlat = [];
  for (var j = 0; j < posFilterInput.length; j++) {
    if (filtered.indexOf(posFilterInput[j]) < 0) alternateFlat.push(posFilterInput[j]);
  }
  return [filtered, appendExplicitAlternate(alternateFlat)];
}
export function toDebugLineNo(raw) {
  var n = parseInt(raw || 0, 10);
  if (!isFinite(n) || n <= 0) return 0;
  return n;
}
export function entryDebugIdentity(entry) {
  var e = entry || {};
  var head = String(e.headword || '').trim();
  var posRaw = String(e.pos_raw || e.pos || '').trim();
  var etymNum = parseInt(e.etymology_number || 0, 10);
  if (!isFinite(etymNum) || etymNum < 0) etymNum = 0;
  var etymText = String(e.etymology || '');
  var eid = getStableRuntimeEntryId(e);
  return head + '\t' + posRaw + '\t' + etymNum + '\t' + etymText + '\t' + eid;
}
export function buildDebugEntryRef(entry) {
  var e = entry || {};
  var lineNo = toDebugLineNo(e.__line_no);
  var morphInfo = Array.isArray(e.morph_info)
    ? e.morph_info
        .slice()
        .map(function (v) {
          return String(v || '').trim();
        })
        .filter(Boolean)
    : [];
  return {
    line_no: lineNo || null,
    headword: String(e.headword || '').trim(),
    pos_raw: String(e.pos_raw || e.pos || '').trim(),
    reading: getEntryDisplayReading(e),
    etymology_number: (function () {
      var n = parseInt(e.etymology_number || 0, 10);
      return isFinite(n) && n > 0 ? n : 0;
    })(),
    etymology: String(e.etymology || ''),
    identity: entryDebugIdentity(e),
    morph_base: String(e.morph_base || '').trim(),
    morph_info: morphInfo
  };
}
export function buildDebugEntryRefs(entries) {
  var out = [];
  var seen = Object.create(null);
  var list = Array.isArray(entries) ? entries : [];
  for (var i = 0; i < list.length; i++) {
    var ref = buildDebugEntryRef(list[i]);
    var key = String(ref.line_no || '') + '\t' + String(ref.identity || '');
    if (!key.trim() || seen[key]) continue;
    seen[key] = true;
    out.push(ref);
  }
  return out;
}
