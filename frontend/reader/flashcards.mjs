import { renderSenseLines } from './annotations.mjs';
import { getDocRenderPageSize, setDocRenderPages } from './continuous-scroll.mjs';
import { dependencyPopupState } from './dependency-popup.state.mjs';
import { hideSeparateGrammarPopup } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { documentState } from './document-state.state.mjs';
import { getLookupPayloadPrimaryResult, pushLookupResolverPayload } from './entry-editing.mjs';
import { triggerUpdate } from './fill-slices.mjs';
import { flashcardsState } from './flashcards.state.mjs';
import { isActiveWebSnapshotDocument, performWebSnapshotLookup } from './foliate-viewport.mjs';
import { loadXposDescriptionsForLanguage } from './grammar-popup.mjs';
import {
  applyDictionaryHoverPopupClamp,
  clearDictionaryHoverPopupClamp,
  fetchLangConfigAndApply,
  setDictionaryPopupSignalFromMarkup
} from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  _resetSentenceTabletGlossOverrides,
  buildLookupPostRequest,
  decorateLookupFetchResponse,
  renderInitialExampleDemoIfAvailable,
  showInitialInputGuidanceIfEmpty
} from './lookup-progress.mjs';
import { lookupProgressState } from './lookup-progress.state.mjs';
import {
  _formatOrthCodePointLabel,
  _isOrthCombiningCodePoint,
  _isOrthInvisibleCodePoint,
  buildLookupUrl,
  setDepTreeSourceMode
} from './orthography.mjs';
import { escapeHtml, formatPopupRoman, normalizeVisibleComparisonText } from './presentation.mjs';
import { _buildPronunciationPopupModel, getCachedSidePanelLookupEntry } from './pronunciation-panel.mjs';
import { renderSegments } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { togglePanel } from './settings-panels.mjs';
import {
  displayDictEntry,
  hidePopup,
  lookupAndDisplay,
  positionSidePanelPopup,
  renderDictTemplate
} from './side-panel.mjs';
export function normalizeG2PMiniBoundaryText(raw) {
  return normalizeVisibleComparisonText(String(raw || '')).replace(/\s+/g, '');
}
export function matchG2PMiniGroupBoundaries(syllables, groupTexts) {
  if (
    !Array.isArray(syllables) ||
    syllables.length < 2 ||
    !Array.isArray(groupTexts) ||
    groupTexts.length < 2
  )
    return null;
  var targets = [];
  for (var i = 0; i < groupTexts.length; i++) {
    var target = normalizeG2PMiniBoundaryText(groupTexts[i]);
    if (target) targets.push(target);
  }
  if (targets.length < 2) return null;
  var boundaries = [];
  var syllableIndex = 0;
  for (var g = 0; g < targets.length; g++) {
    var targetText = targets[g];
    var acc = '';
    var matchedAny = false;
    while (syllableIndex < syllables.length) {
      var syll = syllables[syllableIndex] || {};
      var orthText = normalizeG2PMiniBoundaryText(syll.orth || syll.cluster || syll.text || '');
      if (!orthText) {
        syllableIndex++;
        continue;
      }
      var nextAcc = acc + orthText;
      if (targetText.indexOf(nextAcc) !== 0) return null;
      acc = nextAcc;
      matchedAny = true;
      syllableIndex++;
      if (acc === targetText) {
        if (g < targets.length - 1) boundaries.push(syllableIndex - 1);
        break;
      }
    }
    if (!matchedAny || acc !== targetText) return null;
  }
  for (; syllableIndex < syllables.length; syllableIndex++) {
    var trailing = syllables[syllableIndex] || {};
    if (normalizeG2PMiniBoundaryText(trailing.orth || trailing.cluster || trailing.text || '')) return null;
  }
  return boundaries.length ? boundaries : null;
}
export function resolveG2PMiniGroupBoundaries(model, groupTextSets) {
  var syllables = model && Array.isArray(model.syllables) ? model.syllables : [];
  var sets = Array.isArray(groupTextSets) ? groupTextSets : [];
  if (syllables.length < 2 || !sets.length) return null;
  for (var i = 0; i < sets.length; i++) {
    var boundaries = matchG2PMiniGroupBoundaries(syllables, sets[i]);
    if (boundaries && boundaries.length) return boundaries;
  }
  return null;
}
export function buildG2PMiniSeparatorHtml() {
  return '<span class="g2p-mini-separator" aria-hidden="true"></span>';
}
export function joinG2PMiniCells(cells, boundaryEnds) {
  if (!Array.isArray(cells) || !cells.length) return '';
  var boundaryMap = Object.create(null);
  var ends = Array.isArray(boundaryEnds) ? boundaryEnds : [];
  for (var i = 0; i < ends.length; i++) {
    var endIndex = Number(ends[i]);
    if (isFinite(endIndex) && endIndex >= 0) boundaryMap[String(endIndex)] = true;
  }
  var html = [];
  for (var cellIndex = 0; cellIndex < cells.length; cellIndex++) {
    html.push(cells[cellIndex]);
    if (boundaryMap[String(cellIndex)] && cellIndex < cells.length - 1) {
      html.push(buildG2PMiniSeparatorHtml());
    }
  }
  return html.join('');
}
export function setG2PPopup(rawText, rawLang, g2pData) {
  if (!hoverLayoutState.g2pPopup) return;
  if (!dependencyPopupState.displaySettings.pronunciation) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
    return;
  }
  var html = renderG2PBlock(g2pData, false, rawText, rawLang);
  if (html) {
    hoverLayoutState.g2pPopup.innerHTML = html;
    hoverLayoutState.g2pPopup.style.display = 'block';
  } else {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
}
export function buildG2PMiniRows(rawText, rawLang, g2pData, options) {
  var model = _buildPronunciationPopupModel(rawText, rawLang, g2pData);
  if (!model || !Array.isArray(model.syllables) || !model.syllables.length) return null;
  var opts = options || {};
  function splitSlashParts(value) {
    if (!value || typeof value !== 'string') return [];
    return value
      .split('/')
      .map(function (part) {
        return part.trim();
      })
      .filter(function (part) {
        return !!part;
      });
  }
  function dedupeParts(parts) {
    var seen = Object.create(null);
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var part = parts[i];
      var key = String(part || '').toLowerCase();
      if (!key || seen[key]) continue;
      seen[key] = true;
      out.push(part);
    }
    return out;
  }
  function normalizeRomanText(value) {
    return dedupeParts(splitSlashParts(formatPopupRoman(String(value || '')))).join(' / ');
  }
  function buildPronunciationBreakdown(parts) {
    void parts;
    return '';
  }
  function renderG2PClusterText(text, allowAnchors) {
    var raw = String(text || '');
    if (!raw) return '';
    // Standalone grapheme clusters stay raw; dotted-circle anchors are only
    // for decomposition views that expand a cluster into multiple code points.
    if (allowAnchors === false) return escapeHtml(raw);
    return Array.from(raw)
      .map(function (ch) {
        if (_isOrthInvisibleCodePoint(ch)) {
          return (
            '<span class="g2p-mini-zero-width" title="' +
            escapeHtml(_formatOrthCodePointLabel(ch)) +
            '">&#9676;</span>'
          );
        }
        if (_isOrthCombiningCodePoint(ch)) {
          return (
            '<span class="g2p-mini-zero-width g2p-mini-zero-width-mark" title="' +
            escapeHtml(_formatOrthCodePointLabel(ch)) +
            '">&#9676;' +
            escapeHtml(ch) +
            '</span>'
          );
        }
        return escapeHtml(ch);
      })
      .join('');
  }
  function buildCodepointBreakdownHtml(parts, orthCodepoints) {
    void parts;
    void orthCodepoints;
    return '';
  }
  function buildCell(mainHtml, breakdownText, className, breakdownIsHtml) {
    var html = '<div class="' + className + '"><div class="g2p-mini-main">' + mainHtml + '</div>';
    if (breakdownText)
      html +=
        '<div class="g2p-mini-breakdown">' +
        (breakdownIsHtml ? breakdownText : escapeHtml(breakdownText)) +
        '</div>';
    html += '</div>';
    return html;
  }
  function isWhitespaceOnlyText(value) {
    var text = String(value || '');
    return !!text && !text.trim();
  }
  var pronCells = [];
  var graphemeCells = [];
  for (var sIdx = 0; sIdx < model.syllables.length; sIdx++) {
    var s = model.syllables[sIdx] || {};
    var orthRaw = String(s.orth || s.cluster || s.text || '');
    if (!orthRaw) continue;
    var orth = orthRaw;
    var whitespaceOnly = isWhitespaceOnlyText(orth);
    var complex = false;
    var pron = normalizeRomanText(s.roman || s.sound || s.pronunciation || '');
    var pronBreakdown = '';
    var codepointBreakdown = '';
    var pronMainHtml = whitespaceOnly
      ? '<span class="g2p-mini-space-gap" aria-hidden="true">&nbsp;</span>'
      : pron
        ? escapeHtml(pron)
        : '<span class="g2p-mini-empty">∅</span>';
    var orthMainHtml = whitespaceOnly
      ? '<span class="g2p-mini-space" title="space" aria-label="space">_</span>'
      : '<span dir="auto">' + renderG2PClusterText(orth, false) + '</span>';
    pronCells.push(
      buildCell(
        pronMainHtml,
        pronBreakdown,
        'g2p-mini-cell g2p-mini-cell--pron' + (complex ? ' g2p-mini-cell--complex' : '')
      )
    );
    // Render the surface grapheme only; internal codepoint breakdown is
    // intentionally suppressed in the active popup.
    graphemeCells.push(
      buildCell(
        orthMainHtml,
        codepointBreakdown,
        'g2p-mini-cell g2p-mini-cell--graph' + (complex ? ' g2p-mini-cell--complex' : ''),
        true
      )
    );
  }
  if (!pronCells.length && !graphemeCells.length) return null;
  var groupBoundaries = resolveG2PMiniGroupBoundaries(model, opts.groupTextSets);
  return {
    pronCellsHtml: joinG2PMiniCells(pronCells, groupBoundaries),
    orthCellsHtml: joinG2PMiniCells(graphemeCells, groupBoundaries)
  };
}
export function buildG2PMiniRowHtml(kind, cellsHtml, extraClass) {
  if (!cellsHtml) return '';
  var className = 'g2p-mini-row g2p-mini-row--' + String(kind || '').trim();
  if (extraClass) className += ' ' + String(extraClass);
  return '<div class="' + className + '">' + cellsHtml + '</div>';
}
export function buildGrammarPopupPronunciationRows(rawText, rawLang, g2pData, options) {
  var miniRows = buildG2PMiniRows(rawText, rawLang, g2pData, options);
  if (!miniRows) return [];
  return [
    '<tr class="gp-g2p-row"><td class="gp-label">ORTH</td><td class="gp-g2p-cell">' +
      buildG2PMiniRowHtml('graph', miniRows.orthCellsHtml) +
      '</td></tr>',
    '<tr class="gp-g2p-row"><td class="gp-label">ROM</td><td class="gp-g2p-cell">' +
      buildG2PMiniRowHtml('pron', miniRows.pronCellsHtml) +
      '</td></tr>'
  ];
}
export function renderG2PBlock(g2pData, showTitle, rawText, rawLang) {
  var miniRows = buildG2PMiniRows(rawText, rawLang, g2pData);
  if (!miniRows) return '';
  return (
    '<div class="g2p-mini">' +
    buildG2PMiniRowHtml('pron', miniRows.pronCellsHtml) +
    buildG2PMiniRowHtml('graph', miniRows.orthCellsHtml) +
    '</div>'
  );
}
export function renderUnknownPopup(seg) {
  var requestLang = String(documentShellState.currentLanguage || '');
  hideSeparateGrammarPopup();
  // Disable G2P pronunciation popup in side panel (pronunciation only in main window)
  if (hoverLayoutState.g2pPopup) {
    hoverLayoutState.g2pPopup.style.display = 'none';
    hoverLayoutState.g2pPopup.innerHTML = '';
  }
  if (!dependencyPopupState.displaySettings.dictPopup) {
    hoverLayoutState.hoverPopup.style.display = 'none';
    hoverLayoutState.hoverPopupContainer.style.display = 'none';
    clearDictionaryHoverPopupClamp();
    return;
  }
  // Render through the shared dictionary template path.
  var cached = getCachedSidePanelLookupEntry(seg, requestLang);
  if (cached) {
    var html = renderDictTemplate(cached, seg, {
      showHead: false,
      showRomanUnknown: true,
      showSensesKnown: false
    }).html;
    // Append synthetic badge if it's an MT entry
    if (cached.synthetic) {
      html += '<span class="dict-entry-synthetic-badge">MT</span>';
    }
    hoverLayoutState.hoverPopup.innerHTML = html;
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html);
    // Render annotation UI and community entries for known synthetic
    _appendUnknownExtras(hoverLayoutState.hoverPopup, seg, requestLang, cached);
  } else {
    var initialHtml = renderDictTemplate(
      {
        head: seg
      },
      seg,
      {
        showHead: false,
        showRomanUnknown: false,
        showSensesKnown: false
      }
    ).html;
    hoverLayoutState.hoverPopup.innerHTML = initialHtml;
    setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, initialHtml);
    _appendUnknownExtras(hoverLayoutState.hoverPopup, seg, requestLang, null);
  }
  hoverLayoutState.hoverPopup.style.display = 'block';
  hoverLayoutState.hoverPopupContainer.style.display = 'flex';
  applyDictionaryHoverPopupClamp();
  positionSidePanelPopup(
    hoverLayoutState.hoverPopupContainer,
    segmentRenderingState.lastMouseX,
    segmentRenderingState.lastMouseY
  );
}

// Show the paid-entry prompt for unknown tokens.
export function _appendUnknownExtras(container, seg, lang, entry) {
  var UC = window.UnknownEntryPrompt;
  if (!UC) return;
  // Legacy Google Translate synthetic-entry annotation UI disabled.

  if (!entry || !entry.senses || !entry.senses.length) {
    UC.renderUpgradeNudge(container);
  }
}
// ---------------- Flashcard UI (reading SRS) ----------------
export function openFlashcardMode() {
  if (!flashcardsState.flashcardOverlay) return;
  flashcardsState.flashcardOverlay.style.display = 'flex';
  resetFlashcardUI();
  loadNextFlashcard();
}
export function resetFlashcardUI() {
  flashcardsState.flashcardMessage.textContent = '';
  if (flashcardsState.flashcardStats) flashcardsState.flashcardStats.textContent = '';
  if (flashcardsState.flashcardWord) flashcardsState.flashcardWord.style.display = 'block';
  if (flashcardsState.flashcardShowAnswerBtn) flashcardsState.flashcardShowAnswerBtn.style.display = 'block';
  if (flashcardsState.flashcardAnswer) flashcardsState.flashcardAnswer.style.display = 'none';
  if (flashcardsState.flashcardGradeButtons) flashcardsState.flashcardGradeButtons.style.display = 'none';
  if (flashcardsState.flashcardPronunciation) flashcardsState.flashcardPronunciation.innerHTML = '';
  if (flashcardsState.flashcardDictionary) flashcardsState.flashcardDictionary.innerHTML = '';
  if (flashcardsState.flashcardGrammar) flashcardsState.flashcardGrammar.innerHTML = '';
  if (flashcardsState.flashcardAnnotation) flashcardsState.flashcardAnnotation.value = '';
}
export function closeFlashcardMode() {
  if (!flashcardsState.flashcardOverlay) return;
  flashcardsState.flashcardOverlay.style.display = 'none';
  flashcardsState.flashcardCurrent = null;
}
export function loadNextFlashcard() {
  if (flashcardsState.flashcardIsLoading) return;
  flashcardsState.flashcardIsLoading = true;
  if (!flashcardsState.flashcardOverlay) return;
  resetFlashcardUI();
  flashcardsState.flashcardWord.textContent = '...';
  if (flashcardsState.flashcardShowAnswerBtn) flashcardsState.flashcardShowAnswerBtn.disabled = true;
  fetch('/api/reading_srs/next_card')
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      flashcardsState.flashcardIsLoading = false;
      if (!data || !data.ok || !data.card) {
        flashcardsState.flashcardCurrent = null;
        flashcardsState.flashcardWord.textContent = 'No cards available';
        if (flashcardsState.flashcardShowAnswerBtn)
          flashcardsState.flashcardShowAnswerBtn.style.display = 'none';
        var msg =
          (data && data.error) || 'Paste and analyze some text first so the reader can collect known words.';
        flashcardsState.flashcardMessage.textContent = msg;
        return;
      }
      var card = data.card;
      flashcardsState.flashcardCurrent = card;
      var head = card.head || '';
      var display = card.display || head;
      flashcardsState.flashcardWord.textContent = display || head || '...';
      flashcardsState.flashcardMessage.textContent = card.is_new ? 'New word' : 'Review';
      var stats = card.stats || {};
      var review = card.review || {};
      var seen = stats.total_seen || 0;
      var reps = review.repetitions || 0;
      if (flashcardsState.flashcardStats)
        flashcardsState.flashcardStats.textContent = 'Seen ' + seen + 'x / Repetitions ' + reps;
      if (flashcardsState.flashcardShowAnswerBtn) flashcardsState.flashcardShowAnswerBtn.disabled = false;
    })
    .catch(function (err) {
      console.error('reading_srs next_card error', err);
      flashcardsState.flashcardIsLoading = false;
      flashcardsState.flashcardWord.textContent = 'Error';
      flashcardsState.flashcardMessage.textContent = 'Failed to load next card.';
      if (flashcardsState.flashcardShowAnswerBtn)
        flashcardsState.flashcardShowAnswerBtn.style.display = 'none';
    });
}
export function showFlashcardAnswer() {
  if (!flashcardsState.flashcardCurrent) return;
  var head = flashcardsState.flashcardCurrent.head || flashcardsState.flashcardCurrent.display || '';
  if (!head) return;
  if (flashcardsState.flashcardWord) flashcardsState.flashcardWord.style.display = 'none';
  if (flashcardsState.flashcardShowAnswerBtn) flashcardsState.flashcardShowAnswerBtn.style.display = 'none';
  if (flashcardsState.flashcardAnswer) flashcardsState.flashcardAnswer.style.display = 'flex';
  if (flashcardsState.flashcardGradeButtons) flashcardsState.flashcardGradeButtons.style.display = 'flex';
  if (flashcardsState.flashcardKnowBtn) flashcardsState.flashcardKnowBtn.disabled = false;
  if (flashcardsState.flashcardDontKnowBtn) flashcardsState.flashcardDontKnowBtn.disabled = false;
  loadFlashcardContent(head);
}
export function gradeFlashcard(knew) {
  if (!flashcardsState.flashcardCurrent || flashcardsState.flashcardIsLoading) return;
  var head = flashcardsState.flashcardCurrent.head || flashcardsState.flashcardCurrent.display || '';
  if (!head) return;
  if (flashcardsState.flashcardKnowBtn) flashcardsState.flashcardKnowBtn.disabled = true;
  if (flashcardsState.flashcardDontKnowBtn) flashcardsState.flashcardDontKnowBtn.disabled = true;
  fetch('/api/reading_srs/grade', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      head: head,
      knew: !!knew
    })
  })
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      if (!data || !data.ok) {
        flashcardsState.flashcardMessage.textContent = 'Failed to update card.';
        if (flashcardsState.flashcardKnowBtn) flashcardsState.flashcardKnowBtn.disabled = false;
        if (flashcardsState.flashcardDontKnowBtn) flashcardsState.flashcardDontKnowBtn.disabled = false;
        return;
      }
      loadNextFlashcard();
    })
    .catch(function (err) {
      console.error('reading_srs grade error', err);
      flashcardsState.flashcardMessage.textContent = 'Failed to update card.';
      if (flashcardsState.flashcardKnowBtn) flashcardsState.flashcardKnowBtn.disabled = false;
      if (flashcardsState.flashcardDontKnowBtn) flashcardsState.flashcardDontKnowBtn.disabled = false;
    });
}
export function loadFlashcardContent(head) {
  if (!head) return;
  if (flashcardsState.flashcardPronunciation)
    flashcardsState.flashcardPronunciation.innerHTML = '<div class="flashcard-loading">Loading...</div>';
  if (flashcardsState.flashcardDictionary)
    flashcardsState.flashcardDictionary.innerHTML = '<div class="flashcard-loading">Loading...</div>';
  if (flashcardsState.flashcardGrammar) flashcardsState.flashcardGrammar.innerHTML = '';
  // Fetch dictionary data (includes g2p and grammar_overlay)
  var lookupUrl = buildLookupUrl(head);
  var lookupRequest = buildLookupPostRequest(lookupUrl);
  fetch(lookupRequest.url, lookupRequest.init)
    .then(function (r) {
      return decorateLookupFetchResponse(r, lookupRequest.decoratorUrl || lookupUrl);
    })
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      var primaryResult = getLookupPayloadPrimaryResult(data);
      // Pronunciation
      if (flashcardsState.flashcardPronunciation) {
        var g2pData = (primaryResult && primaryResult.g2p) || (data && data.g2p);
        var g2pContent = '';
        if (g2pData) {
          if (typeof renderG2PBlock === 'function') {
            g2pContent = renderG2PBlock(g2pData, true, head, documentShellState.currentLanguage);
          } else if (typeof g2pData === 'string' && g2pData.trim()) {
            g2pContent = '<div class="pronunciation-legacy-fallback">' + escapeHtml(g2pData) + '</div>';
          }
        }
        if (g2pContent) {
          flashcardsState.flashcardPronunciation.innerHTML = g2pContent;
        } else {
          flashcardsState.flashcardPronunciation.innerHTML = '';
        }
      }
      // Dictionary
      if (flashcardsState.flashcardDictionary) {
        if (data && data.ok && primaryResult) {
          var main = primaryResult;
          var senses = main.senses || [];
          var dictHtml = '<div class="flashcard-section-title">Dictionary</div>';
          if (senses.length && typeof renderSenseLines === 'function') {
            dictHtml += renderSenseLines(senses, head);
          } else {
            dictHtml += '<div class="popup-empty">[no senses found]</div>';
          }
          flashcardsState.flashcardDictionary.innerHTML = dictHtml;
        } else {
          flashcardsState.flashcardDictionary.innerHTML = '';
        }
      }
      // Grammar overlay senses (from /lookup response)
      if (flashcardsState.flashcardGrammar && data && data.grammar_overlay) {
        var gramOverlay = data.grammar_overlay;
        if (gramOverlay && gramOverlay.tokens && gramOverlay.tokens.length) {
          var token = gramOverlay.tokens[0];
          var grammarEntries = token.grammar || [];
          if (grammarEntries.length) {
            var gramHtml = '<div class="flashcard-section-title">Grammar</div>';
            for (var i = 0; i < grammarEntries.length; i++) {
              var entry = grammarEntries[i];
              gramHtml += '<div class="flashcard-grammar-entry">';
              gramHtml +=
                '<div class="flashcard-grammar-category">' +
                escapeHtml(entry.category || entry.type || '') +
                '</div>';
              gramHtml += '<div class="flashcard-grammar-gloss">' + escapeHtml(entry.gloss || '') + '</div>';
              gramHtml += '</div>';
            }
            flashcardsState.flashcardGrammar.innerHTML = gramHtml;
          }
        }
      }
      // Load existing annotation
      fetch('/annotation?head=' + encodeURIComponent(head))
        .then(function (resp) {
          return resp.json();
        })
        .then(function (aData) {
          if (aData && aData.ok && typeof aData.note === 'string' && flashcardsState.flashcardAnnotation) {
            flashcardsState.flashcardAnnotation.value = aData.note;
          }
        })
        .catch(function (err) {
          console.error('annotation load error', err);
        });
    })
    .catch(function (err) {
      console.error('flashcard content load error', err);
      if (flashcardsState.flashcardPronunciation)
        flashcardsState.flashcardPronunciation.innerHTML =
          '<div class="flashcard-error">Failed to load.</div>';
      if (flashcardsState.flashcardDictionary)
        flashcardsState.flashcardDictionary.innerHTML = '<div class="flashcard-error">Failed to load.</div>';
    });
}
export function saveFlashcardAnnotation() {
  if (!flashcardsState.flashcardCurrent || !flashcardsState.flashcardAnnotation) return;
  var head = flashcardsState.flashcardCurrent.head || flashcardsState.flashcardCurrent.display || '';
  if (!head) return;
  var note = flashcardsState.flashcardAnnotation.value;
  fetch('/annotation', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      head: head,
      note: note
    })
  }).catch(function (err) {
    console.error('annotation autosave error', err);
  });
}
export function initializeFlashcards() {
  flashcardsState.flashcardOverlay = document.getElementById('flashcardOverlay');
  flashcardsState.flashcardWord = document.getElementById('flashcardWord');
  flashcardsState.flashcardMessage = document.getElementById('flashcardMessage');
  flashcardsState.flashcardStats = document.getElementById('flashcardStats');
  flashcardsState.flashcardShowAnswerBtn = document.getElementById('flashcardShowAnswerBtn');
  flashcardsState.flashcardAnswer = document.getElementById('flashcardAnswer');
  flashcardsState.flashcardGradeButtons = document.getElementById('flashcardGradeButtons');
  flashcardsState.flashcardPronunciation = document.getElementById('flashcardPronunciation');
  flashcardsState.flashcardDictionary = document.getElementById('flashcardDictionary');
  flashcardsState.flashcardGrammar = document.getElementById('flashcardGrammar');
  flashcardsState.flashcardAnnotation = document.getElementById('flashcardAnnotation');
  flashcardsState.flashcardKnowBtn = document.getElementById('flashcardKnowBtn');
  flashcardsState.flashcardDontKnowBtn = document.getElementById('flashcardDontKnowBtn');
  flashcardsState.flashcardCloseBtn = document.getElementById('flashcardCloseBtn');
  flashcardsState.flashcardModeBtn = document.getElementById('flashcardModeBtn');
  flashcardsState.flashcardCurrent = null;
  flashcardsState.flashcardIsLoading = false;
  flashcardsState.flashcardAnnotationSaveTimeout = null;
  if (flashcardsState.flashcardModeBtn) {
    flashcardsState.flashcardModeBtn.addEventListener('click', function () {
      openFlashcardMode();
    });
  }
  if (flashcardsState.flashcardCloseBtn) {
    flashcardsState.flashcardCloseBtn.addEventListener('click', function () {
      closeFlashcardMode();
    });
  }
  if (flashcardsState.flashcardShowAnswerBtn) {
    flashcardsState.flashcardShowAnswerBtn.addEventListener('click', function () {
      showFlashcardAnswer();
    });
  }
  if (flashcardsState.flashcardKnowBtn) {
    flashcardsState.flashcardKnowBtn.addEventListener('click', function () {
      gradeFlashcard(true);
    });
  }
  if (flashcardsState.flashcardDontKnowBtn) {
    flashcardsState.flashcardDontKnowBtn.addEventListener('click', function () {
      gradeFlashcard(false);
    });
  }
  // Autosave annotation with debounce
  if (flashcardsState.flashcardAnnotation) {
    flashcardsState.flashcardAnnotation.addEventListener('input', function () {
      if (flashcardsState.flashcardAnnotationSaveTimeout) {
        clearTimeout(flashcardsState.flashcardAnnotationSaveTimeout);
      }
      flashcardsState.flashcardAnnotationSaveTimeout = setTimeout(function () {
        saveFlashcardAnnotation();
      }, 1000);
    });
  }

  // ===================== LEFT SIDEBAR MENU =====================
  flashcardsState.leftMenu = document.getElementById('left-menu');
  flashcardsState.menuToggle = document.getElementById('menu-toggle');
  flashcardsState.menuSections = document.querySelectorAll('.menu-section');
  flashcardsState.thresholdSlider = document.getElementById('bottomUpChunkThreshold');
  flashcardsState.thresholdValue = document.querySelector('.menu-slider-value');

  // Menu toggle (collapse/expand sidebar) - mirrors panel-toggle behavior
  if (flashcardsState.menuToggle && flashcardsState.leftMenu) {
    flashcardsState.menuToggle.addEventListener('click', function () {
      var isOpen = flashcardsState.menuToggle.classList.contains('menu-open');
      if (isOpen) {
        // Close the menu
        flashcardsState.leftMenu.classList.add('collapsed');
        flashcardsState.menuToggle.classList.remove('menu-open');
      } else {
        // Open the menu
        flashcardsState.leftMenu.classList.remove('collapsed');
        flashcardsState.menuToggle.classList.add('menu-open');
      }
    });
  }

  // Toggle behavior for menu sections (multiple can be open at once)
  flashcardsState.menuSections.forEach(function (section) {
    var header = section.querySelector('.menu-section-header');
    if (header) {
      header.addEventListener('click', function () {
        section.classList.toggle('open');
      });
    }
  });

  // Slider value display update
  if (flashcardsState.thresholdSlider && flashcardsState.thresholdValue) {
    flashcardsState.thresholdSlider.addEventListener('input', function () {
      flashcardsState.thresholdValue.textContent = this.value;
    });
    // Sync initial value
    flashcardsState.thresholdValue.textContent = flashcardsState.thresholdSlider.value;
  }
  window.LEReaderShowcaseApi = {
    renderPayload: function (payload, options) {
      var opts = options || {};
      var data = payload && typeof payload === 'object' ? payload : null;
      if (!data || !data.ok) return Promise.resolve(false);
      if (opts.renderedText) hoverLayoutState.renderedText = opts.renderedText;
      if (opts.hoverPopupContainer) hoverLayoutState.hoverPopupContainer = opts.hoverPopupContainer;
      if (opts.hoverPopup) hoverLayoutState.hoverPopup = opts.hoverPopup;
      if (opts.grammarPopup) hoverLayoutState.grammarPopup = opts.grammarPopup;
      if (opts.udPopup) hoverLayoutState.udPopup = opts.udPopup;
      if (opts.g2pPopup) hoverLayoutState.g2pPopup = opts.g2pPopup;
      if (opts.notePopup) hoverLayoutState.notePopup = opts.notePopup;
      if (opts.subsegmentPopupsContainer)
        hoverLayoutState.subsegmentPopupsContainer = opts.subsegmentPopupsContainer;
      if (opts.statusText) hoverLayoutState.statusText = opts.statusText;
      if (opts.statusCounts) hoverLayoutState.statusCounts = opts.statusCounts;
      var lang = String(opts.lang || data.language || '')
        .trim()
        .toLowerCase();
      if (lang) {
        documentShellState.currentLanguage = lang;
        loadXposDescriptionsForLanguage(lang);
      }
      documentState.inputMode = 'raw';
      lookupProgressState.rawTextDocActive = false;
      documentState.currentFileType = 'text';
      hoverLayoutState.latestData = data;
      _resetSentenceTabletGlossOverrides();
      hoverLayoutState.latestLlmGlosses = Array.isArray(data.llm_glosses)
        ? data.llm_glosses.map(function (entry) {
            return entry && typeof entry === 'object' ? Object.assign({}, entry) : null;
          })
        : null;
      pushLookupResolverPayload(data);
      var text = String(opts.text || data.display_text || data.q || '');
      var configPromise = lang ? fetchLangConfigAndApply(lang) : Promise.resolve(false);
      return configPromise
        .catch(function () {
          return false;
        })
        .then(function () {
          renderSegments(data, text);
          return true;
        });
    },
    hidePopup: hidePopup,
    renderSegments: renderSegments
  };

  // Expose dictionary popup helpers for the reader interface.
  window.togglePanel = togglePanel;
  window.displayDictEntry = displayDictEntry;
  window.lookupAndDisplay = lookupAndDisplay;
  window.getSyntheticLookupText = function () {
    var idx = documentState.activePageIndex || 0;
    if (documentState.pageLookupTextByIndex && documentState.pageLookupTextByIndex[idx] != null) {
      return String(documentState.pageLookupTextByIndex[idx] || '');
    }
    return String(lookupProgressState.latestOriginalText || '');
  };
  window.getSyntheticLookupTextDebug = function () {
    var t = window.getSyntheticLookupText();
    return t.replace(/ /g, '[SP]').replace(/\n/g, '\\n\n');
  };
  window.setDepTreeSourceMode = setDepTreeSourceMode;
  Object.defineProperty(window, 'latestData', {
    get: function () {
      return hoverLayoutState.latestData;
    },
    set: function (v) {
      hoverLayoutState.latestData = v;
    },
    configurable: true
  });

  // On page load, show English guidance in the input and a one-time cached demo in output.
  if (!window.LE_READER_SHOWCASE_MODE) {
    setTimeout(function () {
      showInitialInputGuidanceIfEmpty();
      renderInitialExampleDemoIfAvailable();
    }, 100);
  }

  // Dictionary lookup decoration/runtime now lives in dictionary_client_hybrid.js.
  if (
    !window.LE_READER_SHOWCASE_MODE &&
    window.DictionaryClient &&
    typeof window.DictionaryClient.init === 'function'
  ) {
    window.DictionaryClient.init();
    // SQLite mode is always on
  }

  // ---- DocRender public bridge ----
  window.__LE_getDocRenderPageSize = getDocRenderPageSize;
  window.__LE_openDocRenderPages = function (pages, meta, options) {
    setDocRenderPages(pages || [], meta || {}, options || {});
  };
  window.__LE_isDocRenderActive = function () {
    return !!documentState.docrenderActive;
  };

  // ---- Web snapshot lookup keyboard shortcut: Ctrl+Enter ----
  document.addEventListener('keydown', function (ev) {
    if (ev.ctrlKey && ev.key === 'Enter' && isActiveWebSnapshotDocument()) {
      ev.preventDefault();
      performWebSnapshotLookup();
    }
  });

  // ---- Language Engine: expose triggerUpdate for lookup_gate.js ----
  window.__LE_triggerUpdate = triggerUpdate;

  // ---- Web snapshot lookup helper ----
  window.__LE_performWebSnapshotLookup = performWebSnapshotLookup;
  return true;
}
