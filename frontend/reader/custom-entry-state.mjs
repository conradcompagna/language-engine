import { dependencyPopupState } from './dependency-popup.state.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  getLookupEntryFillMode,
  getLookupEntryFills,
  getLookupEntryResolvedVia,
  mergeLookupResolverPayload,
  pushLookupEntryStore
} from './entry-editing.mjs';
import { buildTokenSpan } from './fill-rendering.mjs';
import {
  _surfaceHasGlossableChar,
  clearSyntheticEntryBarState,
  ensureSyntheticEntryBarState,
  getSyntheticEntryBarKey,
  getTokenBannerLemmaInfo,
  setExpandableBannerExpanded,
  wireExpandableBannerToggle
} from './gloss-entries.mjs';
import { applyChunkHighlight } from './gloss-requests.mjs';
import { invalidateRowBandCache } from './hover-interaction.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _buildExpandedCtxForSeg } from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import { getMwtPartsForSeg } from './mwt-context.mjs';
import {
  escapeHtml,
  getEntryDisplayHead,
  hasSameVisibleComparisonText,
  showUpgradePrompt
} from './presentation.mjs';
import { flushLookupCachesForToken, normalizeLookupKey } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { displayDictEntry, lookupAndDisplay } from './side-panel.mjs';
import {
  cacheSidePanelLookupEntry,
  getTokenMapSurfaceLookupEntry,
  isLiveTokenMapStateMatch,
  renderTokenBanner
} from './token-banner.mjs';
import { invalidateUdRectCache, invalidateUiRectCache, registerTokenSpan } from './token-fragments.mjs';
import {
  buildTokenMapGroupedFillEntry,
  getRenderableTokenMapDisplaySliceItems,
  getTokenMapDictFill
} from './token-map.mjs';
export function getSyntheticEntryChooserSelectedTexts(state) {
  var out = [];
  var seen = Object.create(null);
  if (!state || !Array.isArray(state.choices)) return out;
  for (var i = 0; i < state.choices.length; i++) {
    var choice = state.choices[i] || {};
    var choiceText = String(choice.text || choice.value || choice.label || choice || '').trim();
    var choiceLabel = String(choice.label || choiceText || '').trim();
    var selectedKey = choiceText || choiceLabel;
    var selected =
      state.selected &&
      (state.selected[selectedKey] || state.selected[choiceText] || state.selected[choiceLabel]);
    if (!choiceText || seen[choiceText] || !selected) continue;
    seen[choiceText] = true;
    out.push(choiceText);
  }
  return out;
}
export function buildSyntheticEntryChooserHtml(state) {
  var choices = Array.isArray(state && state.choices) ? state.choices : [];
  var html = '<div class="seb-chooser">';
  html += '<div class="seb-chooser-head">';
  html += '<div class="seb-chooser-hint">Select one item</div>';
  html += '</div>';
  html += '<div class="seb-chooser-list">';
  var radioName = 'seb-choice-group';
  for (var i = 0; i < choices.length; i++) {
    var choice = choices[i] || {};
    var choiceText = String(choice.text || choice.value || choice.label || choice || '').trim();
    if (!choiceText) continue;
    var choiceLabel = String(choice.label || choiceText).trim() || choiceText;
    var checked = !!(state && state.selected && (state.selected[choiceText] || state.selected[choiceLabel]));
    var choiceId = 'seb-choice-' + i;
    html +=
      '<label class="seb-chooser-item" for="' +
      choiceId +
      '">' +
      '<input type="radio" name="' +
      radioName +
      '" id="' +
      choiceId +
      '" data-seb-choice="' +
      escapeHtml(choiceText) +
      '"' +
      (checked ? ' checked' : '') +
      '>' +
      '<span class="seb-chooser-item-label">' +
      escapeHtml(choiceLabel) +
      '</span>' +
      '</label>';
  }
  html += '</div>';
  html +=
    '<div class="seb-chooser-actions">' +
    '<button type="button" id="seb-chooser-send" class="seb-chooser-send" disabled>Send</button>' +
    '<button type="button" id="seb-chooser-cancel" class="seb-chooser-cancel">Cancel</button>' +
    '</div>';
  html += '</div>';
  return html;
}
export function buildSyntheticEntryBarHtml(state) {
  var isSending = !!(state && state.mode === 'sending');
  var statusText = String((state && state.status) || 'Sending...').trim() || 'Sending...';
  var hasExpandableRows = !!(!isSending && state && Array.isArray(state.choices) && state.choices.length);
  var barExpanded = !!(hasExpandableRows && state && state.expanded);
  var titleText = isSending ? statusText : 'Create Synthetic Entry';
  var toggleAttrs = hasExpandableRows
    ? ' id="seb-banner-toggle" role="button" tabindex="0" aria-expanded="' +
      (barExpanded ? 'true' : 'false') +
      '" aria-label="Toggle synthetic entry options"'
    : '';
  var html =
    '<div class="tb-strip seb-strip' +
    (hasExpandableRows ? ' tb-strip-expandable' : '') +
    (isSending ? ' seb-strip-sending' : '') +
    '">';
  html += '<div class="tb-stack">';
  html +=
    '<div class="tb-header seb-header" data-native-tooltip title="Click to create an LLM-generated entry"' +
    toggleAttrs +
    '>';
  html += '<div class="tb-info-row seb-info-row">';
  html += '<span class="tb-slot-value seb-slot-value">' + escapeHtml(titleText) + '</span>';
  html += '</div>';
  html += '</div>';
  if (hasExpandableRows) {
    html += '<div class="tb-expand-rows">';
    html += buildSyntheticEntryChooserHtml(state);
    html += '</div>';
  }
  html += '</div>';
  html += '</div>';
  return html;
}
export function renderSyntheticEntryBar(data, surfaceText) {
  var synthBar = document.getElementById('synth-entry-bar');
  if (!synthBar) return;
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  var key = getSyntheticEntryBarKey(data, surface);
  if (hoverLayoutState._syntheticEntryBarState && hoverLayoutState._syntheticEntryBarState.key !== key) {
    clearSyntheticEntryBarState();
  }
  if (!surface || !_surfaceHasGlossableChar(surface)) {
    synthBar.innerHTML = '';
    synthBar.style.display = 'none';
    return;
  }
  synthBar.style.display = '';
  var state = ensureSyntheticEntryBarState(data, surface);
  synthBar.innerHTML = buildSyntheticEntryBarHtml(state);
  setExpandableBannerExpanded(
    synthBar,
    'seb-banner-toggle',
    !!(state && state.mode !== 'sending' && state.expanded)
  );
  wireSyntheticEntryBarEvents(data, surface);
}
export function beginSyntheticEntrySend(data, surfaceText) {
  var surface = String(surfaceText || (data && data.surface) || '').trim();
  var state = hoverLayoutState._syntheticEntryBarState;
  if (!state || state.mode === 'sending') return;
  var selectedTexts = getSyntheticEntryChooserSelectedTexts(state);
  if (!selectedTexts.length) return;
  state.mode = 'sending';
  state.expanded = false;
  state.status = 'Sending entry...';
  state.pendingTexts = selectedTexts.slice();
  renderSyntheticEntryBar(data, surface);
  sendSyntheticEntries(data, surface, selectedTexts);
}
export function wireSyntheticEntryBarEvents(data, surfaceText) {
  var synthBar = document.getElementById('synth-entry-bar');
  if (!synthBar) return;
  var state = ensureSyntheticEntryBarState(data, surfaceText);
  if (!state) return;
  wireExpandableBannerToggle(synthBar, 'seb-banner-toggle', function () {
    if (state.mode === 'sending') return;
    state.expanded = !synthBar.classList.contains('expanded');
    setExpandableBannerExpanded(synthBar, 'seb-banner-toggle', state.expanded);
  });
  if (state.mode === 'sending') return;
  var sendBtn = document.getElementById('seb-chooser-send');
  var cancelBtn = document.getElementById('seb-chooser-cancel');
  var chooserInputs = synthBar.querySelectorAll('.seb-chooser-item input[type="radio"]');
  function updateSendState() {
    if (!sendBtn) return;
    var hasSelection = getSyntheticEntryChooserSelectedTexts(state).length > 0;
    sendBtn.disabled = !hasSelection;
  }
  for (var i = 0; i < chooserInputs.length; i++) {
    (function (input) {
      input.addEventListener('change', function () {
        var choiceText = String(input.getAttribute('data-seb-choice') || '').trim();
        if (!choiceText) return;
        state.selected = Object.create(null);
        if (input.checked) state.selected[choiceText] = true;
        updateSendState();
      });
    })(chooserInputs[i]);
  }
  if (sendBtn) {
    sendBtn.addEventListener('click', function (ev) {
      ev.stopPropagation();
      beginSyntheticEntrySend(data, surfaceText);
    });
    updateSendState();
  }
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function (ev) {
      ev.stopPropagation();
      clearSyntheticEntryBarState();
      renderSyntheticEntryBar(data, surfaceText);
    });
  }
}
export function buildGeneratedSyntheticPanelEntry(entryPayload) {
  if (!entryPayload || typeof entryPayload !== 'object') return null;
  var headword = String(entryPayload.headword || '').trim();
  if (!headword) return null;
  var glosses = Array.isArray(entryPayload.glosses) ? entryPayload.glosses : [];
  var senses = [];
  for (var i = 0; i < glosses.length; i++) {
    var gloss = String(glosses[i] || '').trim();
    if (gloss)
      senses.push({
        glosses: [gloss]
      });
  }
  var forms = Array.isArray(entryPayload.forms) ? entryPayload.forms : [];
  var entryRowId = parseInt(entryPayload.entry_row_id || entryPayload.id || 0, 10) || 0;
  var dbAlias = String(entryPayload.db_alias || 'customdb').trim() || 'customdb';
  var sourceTag =
    String(entryPayload.source || 'gemini')
      .trim()
      .toLowerCase() || 'gemini';
  var syntheticEntryRef = {
    entry_id: String(entryPayload.entry_id || '').trim(),
    entry_row_id: entryRowId,
    db_alias: dbAlias,
    _storage_kind: 'custom',
    _storage_db_alias: dbAlias,
    _storage_row_id: entryRowId,
    headword: headword,
    head: headword,
    text: headword,
    surface_form: headword,
    display_headword: headword,
    reading: String(entryPayload.romanization || '').trim(),
    roman: String(entryPayload.romanization || '').trim(),
    pos_raw: String(entryPayload.pos || '').trim(),
    pos: String(entryPayload.pos || '').trim(),
    senses: senses.slice(),
    senses_full: senses.slice(),
    senses_hover: senses.slice(),
    source: sourceTag,
    _source: sourceTag,
    _glosses_raw: JSON.stringify(senses),
    _forms_raw: JSON.stringify(forms),
    _forms_json: JSON.stringify(forms),
    forms: forms.slice(),
    _commentary: String(entryPayload.commentary || '').trim(),
    _lemma: String(entryPayload.lemma || '').trim()
  };
  if (syntheticEntryRef._commentary) syntheticEntryRef.morph_info = [syntheticEntryRef._commentary];
  if (syntheticEntryRef._lemma) syntheticEntryRef.morph_base = syntheticEntryRef._lemma;
  var panelEntry = Object.assign({}, syntheticEntryRef);
  var posLabel = String(panelEntry.pos_raw || panelEntry.pos || '').trim();
  var posGroup = {
    headword: headword,
    reading: panelEntry.reading,
    pos: posLabel,
    senses: senses.slice(),
    _entryRef: syntheticEntryRef
  };
  if (syntheticEntryRef.morph_info) posGroup.morph_info = syntheticEntryRef.morph_info.slice();
  if (syntheticEntryRef.morph_base) posGroup.morph_base = syntheticEntryRef.morph_base;
  var entryGroup = {
    headword: headword,
    reading: panelEntry.reading,
    pos_groups: [posGroup],
    _entryRef: syntheticEntryRef
  };
  panelEntry.entry_groups = [entryGroup];
  panelEntry.entry_groups_hover = [entryGroup];
  return panelEntry;
}
export function displayGeneratedSyntheticPanelEntry(entryPayload, surface, returnState) {
  var panelEntry = buildGeneratedSyntheticPanelEntry(entryPayload);
  if (!panelEntry) return false;
  var fullData = returnState && returnState.fullData ? Object.assign({}, returnState.fullData) : {};
  fullData._lookupLang = String(documentShellState.currentLanguage || '').toLowerCase();
  fullData._panelTokenSurface = String(
    fullData._panelTokenSurface || surface || panelEntry.headword || ''
  ).trim();
  fullData._panelTokenLemma = String(fullData._panelTokenLemma || panelEntry._lemma || '').trim();
  fullData._panelTokenLemmaRaw = String(fullData._panelTokenLemmaRaw || panelEntry._lemma || '').trim();
  fullData._skipBannerRender = true;
  displayDictEntry(panelEntry, panelEntry.headword, fullData);
  return true;
}
export function sendSyntheticEntries(d, surface, tokensToGenerate) {
  var lang = String(documentShellState.currentLanguage || '').toLowerCase();
  var dc = window.DictionaryClient;
  var selectedTokens = Array.isArray(tokensToGenerate) ? tokensToGenerate.slice() : [];
  var chosenSurface = String(surface || (d && d.surface) || '').trim();
  var lemmaInfo = getTokenBannerLemmaInfo(d);
  var lemmaStr = String(lemmaInfo.lemma || '').trim();
  var lemmaRawStr = String(lemmaInfo.raw || lemmaInfo.lemma || '').trim();
  var segIdx = d && typeof d.segIdx === 'number' ? d.segIdx : -1;
  var sentenceCtx = _buildExpandedCtxForSeg(segIdx, chosenSurface);
  var trankitDep = String((d.posData && d.posData.dep) || (d.udTok && d.udTok.dep) || '').trim();
  var trankitUpos = String((d.posData && d.posData.upos) || (d.udTok && d.udTok.upos) || '').trim();
  var trankitXpos = String(
    (d.posData && (d.posData.tag || d.posData.xpos)) || (d.udTok && (d.udTok.tag || d.udTok.xpos)) || ''
  ).trim();
  var trankitFeats = String((d.posData && d.posData.feats) || (d.udTok && d.udTok.feats) || '').trim();

  // Get MWT parts for per-token UPOS lookup
  var mwtParts = [];
  if (d && Array.isArray(d.mwt_parts) && d.mwt_parts.length) {
    mwtParts = d.mwt_parts;
  } else if (d && d.udTok && Array.isArray(d.udTok.mwt_parts) && d.udTok.mwt_parts.length) {
    mwtParts = d.udTok.mwt_parts;
  } else if (isFinite(segIdx)) {
    mwtParts = getMwtPartsForSeg(segIdx);
  }

  // Function to look up UPOS for a specific token from MWT parts
  function getTokenUpos(tokenText) {
    if (!mwtParts.length) return trankitUpos;
    for (var i = 0; i < mwtParts.length; i++) {
      var part = mwtParts[i];
      if (part && String(part.text || part || '').trim() === String(tokenText || '').trim()) {
        return String(part.upos || (part.posData && part.posData.upos) || trankitUpos || '').trim();
      }
    }
    return trankitUpos;
  }
  if (!selectedTokens.length) {
    clearSyntheticEntryBarState();
    renderSyntheticEntryBar(d, surface);
    return;
  }
  var generatedCount = 0;
  var generatedEntries = [];
  function finishSend() {
    clearSyntheticEntryBarState();
    renderSyntheticEntryBar(d, surface);
  }
  function onAllGenerated() {
    finishSend();
    var generatedEntry = generatedEntries[0] || null;
    var returnState = hoverLayoutState.currentPanelDisplayState;
    refreshUiAfterCustomEntryMutation({
      nextEntry: generatedEntries,
      extraLookupTexts: [chosenSurface, lemmaStr, lemmaRawStr],
      fallbackHeadword: chosenSurface,
      fallbackSurface: chosenSurface,
      returnState: returnState
    })
      .then(function () {
        displayGeneratedSyntheticPanelEntry(generatedEntry, chosenSurface, returnState);
      })
      .catch(function () {
        displayGeneratedSyntheticPanelEntry(generatedEntry, chosenSurface, returnState);
      });
  }
  function generateNext(idx) {
    if (idx >= selectedTokens.length) {
      if (generatedCount === 0) {
        finishSend();
        return;
      }
      onAllGenerated();
      return;
    }
    var currentTok = selectedTokens[idx];
    var state = hoverLayoutState._syntheticEntryBarState;
    if (state && state.mode === 'sending') {
      state.status =
        selectedTokens.length > 1
          ? 'Sending ' + (idx + 1) + '/' + selectedTokens.length + '...'
          : 'Sending entry...';
      renderSyntheticEntryBar(d, surface);
    }

    // Look up UPOS for this specific token (handles MWT children with per-token UPOS)
    var tokenUpos = getTokenUpos(currentTok);
    fetch('/api/mt_gloss', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        token: currentTok,
        surface_form: chosenSurface,
        target_word: currentTok,
        language: lang,
        sentence: sentenceCtx,
        lemma: lemmaRawStr,
        upos: tokenUpos,
        xpos: trankitXpos,
        feats: trankitFeats,
        dep: trankitDep
      })
    })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data && data.ok && data.entry) {
          generatedCount++;
          generatedEntries.push(data.entry);
          var injectP = dc ? dc.injectGeminiEntry(lang, data.entry) : Promise.resolve();
          return injectP.then(function () {
            generateNext(idx + 1);
          });
        } else if (data && data.upgrade_required) {
          showUpgradePrompt();
          finishSend();
        } else {
          generateNext(idx + 1);
        }
      })
      .catch(function () {
        generateNext(idx + 1);
      });
  }
  generateNext(0);
}
export function addLookupTextCandidate(store, rawText) {
  var text = String(rawText || '').trim();
  if (!text) return;
  var key = normalizeLookupKey(text);
  if (!key || store[key]) return;
  store[key] = text;
}
export function collectLookupTextCandidatesFromForms(formsValue, store) {
  var forms = [];
  if (formsValue && typeof formsValue === 'object' && !Array.isArray(formsValue)) {
    if (Array.isArray(formsValue.rows)) {
      forms = formsValue.rows.slice();
    } else {
      var buckets = ['kanji', 'readings', 'alt', 'hanja', 'hangeul', 'cjk'];
      for (var bi = 0; bi < buckets.length; bi++) {
        var bucket = formsValue[buckets[bi]];
        if (!Array.isArray(bucket)) continue;
        for (var bj = 0; bj < bucket.length; bj++) {
          addLookupTextCandidate(store, bucket[bj]);
        }
      }
    }
  } else if (Array.isArray(formsValue)) {
    forms = formsValue;
  } else if (typeof formsValue === 'string' && formsValue) {
    try {
      var parsed = JSON.parse(formsValue);
      if (Array.isArray(parsed)) forms = parsed;
    } catch (_e) {}
  }
  for (var i = 0; i < forms.length; i++) {
    var formRow = forms[i];
    if (Array.isArray(formRow)) {
      addLookupTextCandidate(store, formRow[0]);
    } else if (formRow && typeof formRow === 'object') {
      addLookupTextCandidate(store, formRow.form || formRow.word || formRow.headword || '');
    }
  }
}
export function collectLookupTextCandidates(entryLike, store) {
  if (!entryLike) return;
  if (Array.isArray(entryLike)) {
    for (var ai = 0; ai < entryLike.length; ai++) collectLookupTextCandidates(entryLike[ai], store);
    return;
  }
  var entry = entryLike.snapshot && typeof entryLike.snapshot === 'object' ? entryLike.snapshot : entryLike;
  if (!entry || typeof entry !== 'object') return;
  addLookupTextCandidate(store, entry.headword);
  addLookupTextCandidate(store, entry.head);
  addLookupTextCandidate(store, entry.text);
  addLookupTextCandidate(store, entry.surface_form);
  addLookupTextCandidate(store, entry.lemma);
  addLookupTextCandidate(store, entry._lemma);
  addLookupTextCandidate(store, entry.lemma_form);
  addLookupTextCandidate(store, entry.morph_base);
  collectLookupTextCandidatesFromForms(entry.forms, store);
  collectLookupTextCandidatesFromForms(entry._forms_raw, store);
  collectLookupTextCandidatesFromForms(entry._forms_json, store);
  var fill = getLookupEntryFills(entry);
  for (var i = 0; i < fill.length; i++) collectLookupTextCandidates(fill[i], store);
  var koChildren = Array.isArray(entry.ko_compound_lemma_children) ? entry.ko_compound_lemma_children : [];
  for (var ki = 0; ki < koChildren.length; ki++) {
    var child = koChildren[ki] || {};
    addLookupTextCandidate(store, child.text);
    addLookupTextCandidate(store, child.source_text);
    collectLookupTextCandidates(child.lookup, store);
  }
}
export function buildAffectedLookupTexts(previousEntry, nextEntry, extraTexts) {
  var store = Object.create(null);
  collectLookupTextCandidates(previousEntry, store);
  collectLookupTextCandidates(nextEntry, store);
  if (Array.isArray(extraTexts)) {
    for (var i = 0; i < extraTexts.length; i++) addLookupTextCandidate(store, extraTexts[i]);
  }
  return Object.keys(store).map(function (key) {
    return store[key];
  });
}
export function liveResultTouchesLookupTexts(entry, lookupTextMap) {
  if (!entry || !lookupTextMap) return false;
  function formsTouchLookupTexts(formsValue) {
    var forms = [];
    if (Array.isArray(formsValue)) {
      forms = formsValue;
    } else if (typeof formsValue === 'string' && formsValue) {
      try {
        var parsed = JSON.parse(formsValue);
        if (Array.isArray(parsed)) forms = parsed;
      } catch (_e) {}
    }
    for (var fi = 0; fi < forms.length; fi++) {
      var formRow = forms[fi];
      var formText = '';
      if (Array.isArray(formRow)) formText = String(formRow[0] || '').trim();
      else if (formRow && typeof formRow === 'object')
        formText = String(formRow.form || formRow.word || formRow.headword || '').trim();
      var formKey = normalizeLookupKey(formText);
      if (formKey && lookupTextMap[formKey]) return true;
    }
    return false;
  }
  var stack = [entry];
  while (stack.length) {
    var current = stack.pop();
    if (!current || typeof current !== 'object') continue;
    var candidates = [
      current.headword,
      current.head,
      current.text,
      current.surface_form,
      current.lemma,
      current._lemma,
      current.lemma_form,
      current.morph_base
    ];
    for (var i = 0; i < candidates.length; i++) {
      var normalized = normalizeLookupKey(candidates[i]);
      if (normalized && lookupTextMap[normalized]) return true;
    }
    var currentFills = getLookupEntryFills(current);
    if (currentFills.length) {
      for (var fi = 0; fi < currentFills.length; fi++) stack.push(currentFills[fi]);
    }
    if (
      formsTouchLookupTexts(current.forms) ||
      formsTouchLookupTexts(current._forms_raw) ||
      formsTouchLookupTexts(current._forms_json)
    ) {
      return true;
    }
    var koChildren = Array.isArray(current.ko_compound_lemma_children)
      ? current.ko_compound_lemma_children
      : [];
    for (var ki = 0; ki < koChildren.length; ki++) {
      var child = koChildren[ki] || {};
      var childTextKey = normalizeLookupKey(child.text || child.source_text || '');
      if (childTextKey && lookupTextMap[childTextKey]) return true;
      if (child.lookup) stack.push(child.lookup);
    }
  }
  return false;
}
export function buildLookupTextKeyMap(lookupTexts) {
  var out = Object.create(null);
  var texts = Array.isArray(lookupTexts) ? lookupTexts : [];
  for (var i = 0; i < texts.length; i++) {
    var key = normalizeLookupKey(texts[i]);
    if (key) out[key] = true;
  }
  return out;
}
export function findAffectedLiveSegmentIndexes(lookupTexts) {
  var out = [];
  var seen = Object.create(null);
  var keyMap = buildLookupTextKeyMap(lookupTexts);
  var results =
    hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)
      ? hoverLayoutState.latestData.results_by_seg
      : [];
  var segments = Array.isArray(hoverLayoutState.latestSegments) ? hoverLayoutState.latestSegments : [];
  for (var i = 0; i < segments.length; i++) {
    var segText = String(segments[i] || '').trim();
    var segKey = normalizeLookupKey(segText);
    if (segKey && keyMap[segKey]) {
      seen[i] = true;
      out.push(i);
      continue;
    }
    var result = results[i] || null;
    if (result && liveResultTouchesLookupTexts(result, keyMap)) {
      seen[i] = true;
      out.push(i);
      continue;
    }
    var udTok =
      dependencyState.latestUdOverlay && Array.isArray(dependencyState.latestUdOverlay.tokens)
        ? dependencyState.latestUdOverlay.tokens[i] || null
        : null;
    if (udTok) {
      var lemmaKey = normalizeLookupKey(udTok.lemma || udTok.lemma_raw || '');
      if (lemmaKey && keyMap[lemmaKey] && !seen[i]) {
        seen[i] = true;
        out.push(i);
      }
    }
    // Check MWT part texts — a synth entry created for a word that appears as
    // an expanded MWT sub-token (e.g. "ballistic" inside "ballistic+article")
    // must cause the MWT parent segment to be re-looked-up.
    if (!seen[i]) {
      var mwtTok = dependencyState.latestUdTokenMap && dependencyState.latestUdTokenMap[i];
      var mwtParts = mwtTok && Array.isArray(mwtTok.mwt_parts) ? mwtTok.mwt_parts : [];
      for (var mi = 0; mi < mwtParts.length; mi++) {
        var mwtPartText = String((mwtParts[mi] && mwtParts[mi].text) || '').trim();
        var mwtPartKey = normalizeLookupKey(mwtPartText);
        if (mwtPartKey && keyMap[mwtPartKey]) {
          seen[i] = true;
          out.push(i);
          break;
        }
      }
    }
  }
  if (
    hoverLayoutState.tokenMapData &&
    typeof hoverLayoutState.tokenMapData.segIdx === 'number' &&
    isFinite(hoverLayoutState.tokenMapData.segIdx)
  ) {
    var tmIdx = hoverLayoutState.tokenMapData.segIdx;
    if (
      !seen[tmIdx] &&
      liveResultTouchesLookupTexts(
        hoverLayoutState.tokenMapData.tokenEntry || hoverLayoutState.tokenMapData.entry,
        keyMap
      )
    ) {
      out.push(tmIdx);
    }
  }
  return out;
}
export function invalidateLookupTextList(lookupTexts) {
  var texts = Array.isArray(lookupTexts) ? lookupTexts : [];
  for (var i = 0; i < texts.length; i++) {
    flushLookupCachesForToken(texts[i], documentShellState.currentLanguage || '');
  }
}
export function resetTokenMapDerivedLookups(data, freshResult) {
  if (!data) return;
  data.entry = freshResult;
  data.tokenEntry = freshResult;
  data.dictFill = getLookupEntryFills(freshResult).slice();
  data.tokenDictFill = data.dictFill;
  data.fillMode = getLookupEntryFillMode(freshResult);
  data.tokenFillMode = data.fillMode;
  data.resolvedVia = getLookupEntryResolvedVia(freshResult);
  data.tokenResolvedVia = data.resolvedVia;
  data.panelEntry = null;
  data.headDecompByForm = null;
  data.surfaceLookup = null;
  data.surfaceLookupPromise = null;
  data.lemmaLookup = null;
  data.lemmaLookupPromise = null;
  data.lemmaPartLookups = null;
  data.lemmaPartLookupsByIndex = null;
  data.lemmaPartLookupPromises = null;
  data.lemmaPartLookupPromisesByIndex = null;
}
export function unpackFreshSegmentRefreshPayload(payloadOrResult) {
  if (!payloadOrResult || typeof payloadOrResult !== 'object') {
    return {
      result: payloadOrResult || null,
      entryStore: null,
      refToKey: null,
      formOverlays: null
    };
  }
  if (Array.isArray(payloadOrResult.results_by_seg)) {
    return {
      result: payloadOrResult.results_by_seg[0] || null,
      entryStore:
        payloadOrResult.entry_store && typeof payloadOrResult.entry_store === 'object'
          ? payloadOrResult.entry_store
          : null,
      refToKey:
        payloadOrResult.ref_to_key && typeof payloadOrResult.ref_to_key === 'object'
          ? payloadOrResult.ref_to_key
          : null,
      formOverlays:
        payloadOrResult.form_overlays && typeof payloadOrResult.form_overlays === 'object'
          ? payloadOrResult.form_overlays
          : null
    };
  }
  return {
    result: payloadOrResult,
    entryStore:
      payloadOrResult.entry_store && typeof payloadOrResult.entry_store === 'object'
        ? payloadOrResult.entry_store
        : null,
    refToKey:
      payloadOrResult.ref_to_key && typeof payloadOrResult.ref_to_key === 'object'
        ? payloadOrResult.ref_to_key
        : null,
    formOverlays:
      payloadOrResult.form_overlays && typeof payloadOrResult.form_overlays === 'object'
        ? payloadOrResult.form_overlays
        : null
  };
}
export function applyFreshSegmentResult(freshPayloadOrResult, targetIdx, targetSurface) {
  var refreshData = unpackFreshSegmentRefreshPayload(freshPayloadOrResult);
  var freshResult = refreshData.result;
  if (hoverLayoutState.latestData && typeof hoverLayoutState.latestData === 'object') {
    mergeLookupResolverPayload(hoverLayoutState.latestData, {
      entry_store: refreshData.entryStore,
      ref_to_key: refreshData.refToKey,
      form_overlays: refreshData.formOverlays
    });
  }
  pushLookupEntryStore(refreshData.entryStore, refreshData.refToKey, refreshData.formOverlays);
  if (!freshResult) return;
  flushLookupCachesForToken(targetSurface);
  if (hoverLayoutState.latestData && Array.isArray(hoverLayoutState.latestData.results_by_seg)) {
    hoverLayoutState.latestData.results_by_seg[targetIdx] = freshResult;
  }
  if (lookupProgressState.latestFillsDict) {
    lookupProgressState.latestFillsDict[targetIdx] = freshResult.dict_fill || [];
  }
  cacheSidePanelLookupEntry(freshResult, targetSurface, documentShellState.currentLanguage || '');
  var oldSpan = hoverLayoutState.renderedText
    ? hoverLayoutState.renderedText.querySelector('.reader-token[data-index="' + targetIdx + '"]')
    : null;
  if (oldSpan && hoverLayoutState.latestData) {
    var gramOverlay =
      hoverLayoutState.latestData.grammar_overlay &&
      Array.isArray(hoverLayoutState.latestData.grammar_overlay.tokens)
        ? hoverLayoutState.latestData.grammar_overlay.tokens
        : [];
    var udTokenMap = dependencyState.latestUdTokenMap || {};
    var built = buildTokenSpan(
      targetIdx,
      targetSurface,
      gramOverlay,
      hoverLayoutState.latestData.results_by_seg,
      udTokenMap,
      {}
    );
    if (built && built.span) {
      var wasCurrentHover = segmentRenderingState.currentSpan === oldSpan;
      oldSpan.parentNode.replaceChild(built.span, oldSpan);
      registerTokenSpan(targetIdx, built.span);
      invalidateUdRectCache();
      invalidateRowBandCache();
      invalidateUiRectCache();
      if (wasCurrentHover) {
        segmentRenderingState.currentSpan = built.span;
        segmentRenderingState.currentFillHit = null;
        segmentRenderingState.currentPopupAnchorEl = built.span;
        if (dependencyPopupState.displaySettings.chunkHighlight) {
          applyChunkHighlight(targetIdx);
        }
      }
    }
  }
  if (
    hoverLayoutState.tokenMapData &&
    isLiveTokenMapStateMatch(hoverLayoutState.tokenMapData, targetSurface, targetIdx)
  ) {
    resetTokenMapDerivedLookups(hoverLayoutState.tokenMapData, freshResult);
  }
}
export function restorePanelFromTokenMapState(returnState) {
  var state = returnState && returnState.res ? returnState : hoverLayoutState.currentPanelDisplayState;
  if (!state || !state.fullData || state.fullData._panelManualSearch) return false;
  if (!hoverLayoutState.tokenMapData) return false;
  var tokenSurface = String(state.fullData._panelTokenSurface || state.originalToken || '').trim();
  if (!tokenSurface) return false;
  if (!hasSameVisibleComparisonText(String(hoverLayoutState.tokenMapData.surface || ''), tokenSurface))
    return false;
  var fillKey = String(state.fullData._panelBannerFillKey || '').trim();
  var signature = String(state.fullData._panelEntrySignature || '').trim();
  var dictFill = getTokenMapDictFill(hoverLayoutState.tokenMapData);
  var entrySliceItems = getRenderableTokenMapDisplaySliceItems(hoverLayoutState.tokenMapData);
  if (fillKey) {
    for (var i = 0; i < entrySliceItems.length; i++) {
      var item = entrySliceItems[i] || {};
      var itemFill = Array.isArray(item.dictFill) ? item.dictFill : dictFill;
      var itemIndexes = Array.isArray(item.fillIndexes) ? item.fillIndexes.slice() : [];
      var itemFillKey = i + ':' + itemIndexes.join(',');
      if (itemFillKey !== fillKey || !itemIndexes.length) continue;
      if (itemIndexes.length === 1) {
        var idx = itemIndexes[0];
        var fillEntry = itemFill[idx];
        var fillHead = getEntryDisplayHead(fillEntry, '');
        if (!fillEntry || !fillHead) break;
        displayDictEntry(fillEntry, fillHead, {
          _lookupLang: String(documentShellState.currentLanguage || ''),
          _panelTokenSurface: hoverLayoutState.tokenMapData.surface,
          _panelTokenLemma: hoverLayoutState.tokenMapData.lemma,
          _panelTokenLemmaRaw: hoverLayoutState.tokenMapData.lemma_raw || hoverLayoutState.tokenMapData.lemma,
          _panelBannerFillKey: fillKey,
          _panelEntrySignature: signature || 'single|' + String(idx) + '|' + fillHead,
          _skipBannerRender: true
        });
        return true;
      }
      var groupedEntry = buildTokenMapGroupedFillEntry(
        item.lookupEntry || getTokenMapSurfaceLookupEntry(hoverLayoutState.tokenMapData),
        itemIndexes,
        item.text || tokenSurface,
        itemFill
      );
      if (!groupedEntry) break;
      displayDictEntry(groupedEntry, item.text || tokenSurface, {
        _lookupLang: String(documentShellState.currentLanguage || ''),
        _panelTokenSurface: hoverLayoutState.tokenMapData.surface,
        _panelTokenLemma: hoverLayoutState.tokenMapData.lemma,
        _panelTokenLemmaRaw: hoverLayoutState.tokenMapData.lemma_raw || hoverLayoutState.tokenMapData.lemma,
        _panelBannerFillKey: fillKey,
        _panelEntrySignature:
          signature || 'group|' + itemIndexes.join(',') + '|' + (item.text || tokenSurface),
        _skipBannerRender: true
      });
      return true;
    }
  }
  var baseEntry = hoverLayoutState.tokenMapData.tokenEntry || hoverLayoutState.tokenMapData.entry;
  if (!baseEntry) return false;
  displayDictEntry(baseEntry, tokenSurface, {
    _lookupLang: String(documentShellState.currentLanguage || ''),
    _panelTokenSurface: hoverLayoutState.tokenMapData.surface,
    _panelTokenLemma: hoverLayoutState.tokenMapData.lemma,
    _panelTokenLemmaRaw: hoverLayoutState.tokenMapData.lemma_raw || hoverLayoutState.tokenMapData.lemma,
    _skipBannerRender: true
  });
  return true;
}
export function refreshUiAfterCustomEntryMutation(options) {
  var opts = options || {};
  var extraLookupTexts = Array.isArray(opts.extraLookupTexts) ? opts.extraLookupTexts.slice() : [];
  var returnState =
    opts.returnState && opts.returnState.res ? opts.returnState : hoverLayoutState.currentPanelDisplayState;
  if (opts.fallbackSurface) extraLookupTexts.push(opts.fallbackSurface);
  if (returnState && returnState.fullData && returnState.fullData._panelTokenSurface) {
    extraLookupTexts.push(returnState.fullData._panelTokenSurface);
  }
  var lookupTexts = buildAffectedLookupTexts(opts.previousEntry, opts.nextEntry, extraLookupTexts);
  invalidateLookupTextList(lookupTexts);
  var affectedIndexes = findAffectedLiveSegmentIndexes(lookupTexts);
  var dc = window.DictionaryClient;
  var lang = String(documentShellState.currentLanguage || '').toLowerCase();
  var refreshJobs = [];
  for (var i = 0; i < affectedIndexes.length; i++) {
    (function (segIdx) {
      if (
        !hoverLayoutState.latestSegments ||
        !hoverLayoutState.latestData ||
        !Array.isArray(hoverLayoutState.latestData.results_by_seg)
      )
        return;
      var surface = String(hoverLayoutState.latestSegments[segIdx] || '').trim();
      var existing = hoverLayoutState.latestData.results_by_seg[segIdx] || null;
      if (!surface || !existing || !dc || typeof dc.relookupOneSegment !== 'function') return;
      var seededExisting = existing;
      if (
        (!seededExisting.mwt_parts ||
          !Array.isArray(seededExisting.mwt_parts) ||
          !seededExisting.mwt_parts.length) &&
        dependencyState.latestUdTokenMap &&
        dependencyState.latestUdTokenMap[segIdx] &&
        Array.isArray(dependencyState.latestUdTokenMap[segIdx].mwt_parts) &&
        dependencyState.latestUdTokenMap[segIdx].mwt_parts.length
      ) {
        seededExisting = Object.assign({}, existing, {
          mwt_parts: dependencyState.latestUdTokenMap[segIdx].mwt_parts.slice()
        });
      }
      refreshJobs.push(
        dc
          .relookupOneSegment(lang, surface, seededExisting)
          .then(function (freshResult) {
            applyFreshSegmentResult(freshResult || existing, segIdx, surface);
            return true;
          })
          .catch(function () {
            return false;
          })
      );
    })(affectedIndexes[i]);
  }
  return Promise.all(refreshJobs).then(function (results) {
    var hadSuccessfulRefresh =
      Array.isArray(results) &&
      results.some(function (item) {
        return !!item;
      });
    if (hoverLayoutState.tokenMapData) renderTokenBanner();
    if (hadSuccessfulRefresh && restorePanelFromTokenMapState(returnState)) return true;
    var fallbackToken = '';
    if (returnState && returnState.fullData && returnState.fullData._panelTokenSurface) {
      fallbackToken = String(returnState.fullData._panelTokenSurface || '').trim();
    }
    if (!fallbackToken) fallbackToken = String(opts.fallbackSurface || opts.fallbackHeadword || '').trim();
    if (fallbackToken) {
      lookupAndDisplay(fallbackToken, {
        raw: true,
        exact: true,
        allowFuzzy: false,
        noIsland: true,
        forceWholeToken: true,
        manualPanelSearch: !!(returnState && returnState.fullData && returnState.fullData._panelManualSearch),
        lemma: (returnState && returnState.fullData && returnState.fullData._panelTokenLemma) || '',
        lemmaRaw: (returnState && returnState.fullData && returnState.fullData._panelTokenLemmaRaw) || ''
      });
    }
    return true;
  });
}
