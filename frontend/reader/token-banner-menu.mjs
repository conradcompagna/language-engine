import { applyFreshSegmentResult } from './custom-entry-state.mjs';
import {
  _buildGeminiEntryContext,
  _decompInlineEditorHtml,
  _decompPaidGate,
  _decompRelookup,
  _fetchDecompForBlock,
  _focusInlineDecompEditor,
  _generateAndShowDecomp,
  _getDecompCached,
  _hideDecompFloat,
  _renderDecompEditor,
  _renderDecompTooltip,
  _renderDecompView,
  _renderInlineDecompRows,
  _saveDecompFromEditor,
  _setDecompForBlock
} from './decomposition-editor.mjs';
import { dependencyState } from './dependency-state.state.mjs';
import { dictionaryPopupState } from './dictionary-popup.state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { getCanonicalTokenEntry } from './entry-editing.mjs';
import { flushCachedEntriesByStorageId } from './hover-interaction.mjs';
import { applyDictionaryHoverPopupClamp, setDictionaryPopupSignalFromMarkup } from './hover-layout.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import {
  buildHoverableAnnotatedLemmaHtml,
  buildTokenMapAnnotatedLemmaHtml,
  escapeHtml,
  hasDisplayText,
  hasSameVisibleComparisonText,
  showUpgradePrompt,
  summarizeUiRenderDebugLookupEntry,
  traceUiRenderEvent
} from './presentation.mjs';
import { showFormMetaPopupSimple, showKoGlossPopupSimple } from './pronunciation-panel.mjs';
import { _entryReferencesStorageId, flushLookupCachesForToken } from './segment-rendering.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
import { hidePopup, positionSidePanelPopup } from './side-panel.mjs';
import { sidePanelState } from './side-panel.state.mjs';
import { tokenBannerMenuState } from './token-banner-menu.state.mjs';
import { buildTokenMapLookupHtml, resolveTokenMapLookupEntry } from './token-map.mjs';
export function _deleteDecompFromEditor(block) {
  if (!block || sidePanelState._decompFloatBusy) return;
  if (!window.confirm('Are you sure you want to delete this decomposition?')) return;
  var lang = block.getAttribute('data-decomp-lang') || '';
  var surface = (block.getAttribute('data-decomp-surface-form') || '').trim();
  if (!surface) return;
  var alias = block.getAttribute('data-decomp-alias') || '';
  var rowId = block.getAttribute('data-decomp-rowid') || '';
  sidePanelState._decompFloatBusy = true;
  var delBody = {
    lang: lang,
    surface_form: surface
  };
  fetch('/api/entry_decomp/delete', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(delBody)
  })
    .then(function (r) {
      return r.json();
    })
    .then(function (d) {
      sidePanelState._decompFloatBusy = false;
      if (d.ok) {
        _setDecompForBlock(block, '');
        if (alias && rowId) {
          flushCachedEntriesByStorageId(alias, rowId);
        }
        _decompRelookup(surface, alias, rowId);
        _renderInlineDecompRows(block, '');
        _hideDecompFloat();
      }
    })
    .catch(function () {
      sidePanelState._decompFloatBusy = false;
    });
}

// Global click handler — promotes view → edit on second click of same
// headword, handles editor button clicks, and dismisses on outside click.
export function _decompHandleHover(target) {
  if (!target || !target.closest) return false;
  var block = target.closest('.entry-headword-block');
  if (!block) return false;
  // Inline Gemini blocks render their own visible rows — suppress the redundant floating tooltip/view.
  if (block.getAttribute && block.getAttribute('data-decomp-inline') === '1') return false;
  if (sidePanelState._decompFloatState === 'edit') return true; // don't disturb edit mode
  // If view is already showing on this block, keep it visible
  if (sidePanelState._decompFloatState === 'view' && sidePanelState._decompFloatBlock === block) return true;
  var cached = _getDecompCached(block);
  if (cached) {
    // Decomp exists: show view directly (no click needed)
    _renderDecompView(block, cached);
    return true;
  } else {
    // No decomp yet: show floating "+decomp" badge and fetch in background
    if (sidePanelState._decompFloatBlock === block && sidePanelState._decompFloatState === 'tooltip')
      return true; // already showing
    _renderDecompTooltip(block);
    return true;
  }
}
export function _decompHandleHoverLeave(targetIfAny) {
  // Hide decomp popup (tooltip/view) when cursor leaves headword, unless over the float itself
  if (sidePanelState._decompFloatState === 'tooltip' || sidePanelState._decompFloatState === 'view') {
    // If mouse is over the decomp float itself, don't hide it
    if (sidePanelState._decompFloat && targetIfAny && sidePanelState._decompFloat.contains(targetIfAny)) {
      return;
    }
    _hideDecompFloat();
    return;
  }
}
export function attachPanelHandlers() {
  hoverLayoutState.panelContent.onmousemove = function (ev) {
    // Decomp hover takes precedence over generic panel hover, but never
    // when a persistent (view/edit) popup is already showing.
    if (_decompHandleHover(ev.target)) return;
    _decompHandleHoverLeave(ev.target);
    segmentRenderingState.lastMouseX = ev.clientX;
    segmentRenderingState.lastMouseY = ev.clientY;
    // Skip hover logic when an entry edit/create form is open
    if (document.getElementById('entry-form')) return;
    // Metadata chips inside JMdict form headers: show metadata popup, not dictionary lookup.
    var metaEl = ev.target && ev.target.closest('.headword-meta-component');
    if (metaEl) {
      if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
      var metaKey = String(metaEl.getAttribute('data-form-meta') || '');
      if (!metaKey) {
        metaKey =
          String(metaEl.getAttribute('data-meta-kind') || '') +
          '|' +
          String(metaEl.getAttribute('data-meta-form') || '');
      }
      dictionaryPopupState.lastHoveredElement = metaEl;
      if (metaKey && metaKey !== segmentRenderingState.panelHoverToken) {
        segmentRenderingState.panelHoverToken = metaKey;
        segmentRenderingState.panelHoverType = 'headword-meta';
        showFormMetaPopupSimple(metaEl);
      }
      positionSidePanelPopup(
        hoverLayoutState.hoverPopupContainer,
        segmentRenderingState.lastMouseX,
        segmentRenderingState.lastMouseY
      );
      return;
    }
    // Korean detailed-gloss markers: show app popup (not native title tooltip).
    var koGlossEl = ev.target && ev.target.closest('.ko-gloss-hover');
    if (koGlossEl) {
      if (ev.stopImmediatePropagation) ev.stopImmediatePropagation();
      var glossKeyRaw = String(koGlossEl.getAttribute('data-ko-gloss') || '').trim();
      if (!glossKeyRaw) glossKeyRaw = String(koGlossEl.textContent || '').trim();
      var glossHoverKey = glossKeyRaw ? 'ko-gloss|' + glossKeyRaw : '';
      dictionaryPopupState.lastHoveredElement = koGlossEl;
      if (glossHoverKey && glossHoverKey !== segmentRenderingState.panelHoverToken) {
        segmentRenderingState.panelHoverToken = glossHoverKey;
        segmentRenderingState.panelHoverType = 'ko-gloss';
        showKoGlossPopupSimple(koGlossEl);
      }
      positionSidePanelPopup(
        hoverLayoutState.hoverPopupContainer,
        segmentRenderingState.lastMouseX,
        segmentRenderingState.lastMouseY
      );
      return;
    }
    var psrApi = window.PanelSegmentRenderer || null;
    if (psrApi && typeof psrApi.hasLookupTarget === 'function' && psrApi.hasLookupTarget(ev.target)) {
      return;
    }
    // Panel definition body text stays non-interactive.
    // PanelSegmentRenderer owns side-panel token/headword hover targets.
    segmentRenderingState.panelHoverToken = null;
    segmentRenderingState.panelHoverType = null;
    dictionaryPopupState.lastHoveredElement = null;
    hidePopup();
  };
  hoverLayoutState.panelContent.onmouseleave = function () {
    // Hide tooltip immediately when leaving the panel
    _decompHandleHoverLeave(null);
    if (document.getElementById('entry-form')) return;
    segmentRenderingState.panelHoverToken = null;
    segmentRenderingState.panelHoverType = null;
    dictionaryPopupState.lastHoveredElement = null;
    hidePopup();
  };
  hoverLayoutState.panelContent.onclick = function (ev) {
    // Morph toggle
    var morphToggle = ev.target && ev.target.closest ? ev.target.closest('.dict-morph-inline-toggle') : null;
    if (morphToggle) {
      ev.preventDefault();
      ev.stopPropagation();
      var expanded = String(morphToggle.getAttribute('data-morph-expanded') || '') === '1';
      var collapsedText = String(morphToggle.getAttribute('data-morph-collapsed') || '').trim();
      var fullText = String(morphToggle.getAttribute('data-morph-full') || collapsedText).trim();
      var nextExpanded = !expanded;
      morphToggle.textContent = nextExpanded ? fullText : collapsedText;
      morphToggle.setAttribute('data-morph-expanded', nextExpanded ? '1' : '0');
      morphToggle.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
      morphToggle.removeAttribute('title');
      return;
    }

    // --- Inline AI morphology handlers ---
    var decompLine = ev.target && ev.target.closest ? ev.target.closest('.entry-decomp-line') : null;
    if (decompLine) {
      var decompValue = ev.target.closest('.entry-decomp-value');
      var decompAutoBtn = ev.target.closest('.entry-decomp-auto-btn');
      var decompSaveBtn = ev.target.closest('.entry-decomp-save-btn');
      var decompDeleteBtn = ev.target.closest('.entry-decomp-delete-btn');
      var decompCancelBtn = ev.target.closest('.entry-decomp-cancel-btn');
      var dLang = decompLine.getAttribute('data-decomp-lang') || '';
      var dAlias = decompLine.getAttribute('data-decomp-alias') || '';
      var dRowId = decompLine.getAttribute('data-decomp-rowid') || '';
      var dHeadword = decompLine.getAttribute('data-decomp-headword') || '';
      var dPos = decompLine.getAttribute('data-decomp-pos') || '';
      var dSurface = String(decompLine.getAttribute('data-decomp-surface-form') || '').trim();
      function _showInlineDecompEditor(prefillRaw) {
        decompLine.setAttribute('data-decomp-before-edit', String(prefillRaw || ''));
        decompLine.innerHTML = _decompInlineEditorHtml(prefillRaw || '');
        _focusInlineDecompEditor(decompLine);
      }
      function _rebuildInlineDecompLine(rawText) {
        decompLine.removeAttribute('data-decomp-before-edit');
        _renderInlineDecompRows(decompLine, rawText || '');
      }
      ev.preventDefault();
      ev.stopPropagation();
      if (decompCancelBtn) {
        _rebuildInlineDecompLine(decompLine.getAttribute('data-decomp-before-edit') || '');
        return;
      }
      if (decompDeleteBtn) {
        if (!dSurface) return;
        if (!window.confirm('Are you sure you want to delete this decomposition?')) return;
        decompDeleteBtn.textContent = '...';
        decompDeleteBtn.style.pointerEvents = 'none';
        fetch('/api/entry_decomp/delete', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            lang: dLang,
            surface_form: dSurface
          })
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (d.ok) {
              _setDecompForBlock(decompLine, '');
              if (dAlias && dRowId) {
                flushCachedEntriesByStorageId(dAlias, dRowId);
              }
              _decompRelookup(dSurface, dAlias, dRowId);
              _rebuildInlineDecompLine('');
            } else {
              decompDeleteBtn.textContent = '\ud83d\uddd1';
              decompDeleteBtn.style.pointerEvents = '';
              if (d && d.error) alert(d.error);
            }
          })
          .catch(function () {
            decompDeleteBtn.textContent = '\ud83d\uddd1';
            decompDeleteBtn.style.pointerEvents = '';
          });
        return;
      }
      if (decompSaveBtn) {
        if (!dSurface) return;
        var decompD = decompLine.querySelector('.decomp-edit-d');
        var decompA = decompLine.querySelector('.decomp-edit-a');
        var decompB = decompLine.querySelector('.decomp-edit-b');
        var dText = decompD ? (decompD.textContent || '').trim() : '';
        var aText = decompA ? (decompA.textContent || '').trim() : '';
        var bText = decompB ? (decompB.textContent || '').trim() : '';
        if (!dText && !aText && !bText) {
          _rebuildInlineDecompLine(decompLine.getAttribute('data-decomp-before-edit') || '');
          return;
        }
        if (!dText) {
          alert('Decomposition is required.');
          _focusInlineDecompEditor(decompLine);
          return;
        }
        decompSaveBtn.textContent = '...';
        decompSaveBtn.style.pointerEvents = 'none';
        var combined = JSON.stringify({
          decomposition: dText,
          analysis: aText,
          breakdown: bText
        });
        fetch('/api/entry_decomp/save', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            lang: dLang,
            surface_form: dSurface,
            decomp: combined
          })
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (d.ok) {
              _setDecompForBlock(decompLine, combined);
              if (dAlias && dRowId) {
                flushCachedEntriesByStorageId(dAlias, dRowId);
              }
              _decompRelookup(dSurface, dAlias, dRowId);
              _rebuildInlineDecompLine(combined);
            } else {
              decompSaveBtn.textContent = '\u2713';
              decompSaveBtn.style.pointerEvents = '';
              if (d && d.error) alert(d.error);
            }
          })
          .catch(function () {
            decompSaveBtn.textContent = '\u2713';
            decompSaveBtn.style.pointerEvents = '';
          });
        return;
      }
      if (decompValue) {
        if (!_decompPaidGate()) return;
        var currentDecomp = String(decompLine.getAttribute('data-decomp-value') || '');
        if (currentDecomp) {
          _showInlineDecompEditor(currentDecomp);
          return;
        }
        _fetchDecompForBlock(decompLine, function (existing) {
          _showInlineDecompEditor(existing || '');
        });
        return;
      }
      if (decompAutoBtn) {
        if (!_decompPaidGate()) return;
        if (!dSurface) return;
        decompAutoBtn.textContent = '...';
        decompAutoBtn.style.pointerEvents = 'none';
        var _decompCtx2 = _buildGeminiEntryContext(dAlias, parseInt(dRowId, 10), dSurface);
        fetch('/api/entry_decomp/generate', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            lang: dLang,
            surface_form: dSurface,
            headword: dHeadword || dSurface,
            pos: dPos,
            trankit: _decompCtx2.trankit
          })
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (d.ok && d.decomp) {
              _setDecompForBlock(decompLine, d.decomp);
              if (dAlias && dRowId) {
                flushCachedEntriesByStorageId(dAlias, dRowId);
              }
              _decompRelookup(dSurface, dAlias, dRowId);
              _rebuildInlineDecompLine(d.decomp);
            } else {
              decompAutoBtn.textContent = '+ decomp';
              decompAutoBtn.style.pointerEvents = '';
              if (d && d.error) alert(d.error);
            }
          })
          .catch(function () {
            decompAutoBtn.textContent = '+ decomp';
            decompAutoBtn.style.pointerEvents = '';
          });
        return;
      }
    }

    // --- Entry note handlers ---
    var noteLine = ev.target && ev.target.closest ? ev.target.closest('.entry-note-line') : null;
    if (!noteLine) return;
    var noteToggle = ev.target.closest('.entry-note-toggle');
    var noteEditBtn = ev.target.closest('.entry-note-edit-btn');
    var noteAddBtn = ev.target.closest('.entry-note-add-btn');
    var noteAutoBtn = ev.target.closest('.entry-note-auto-btn');
    var noteSaveBtn = ev.target.closest('.entry-note-save-btn');
    var noteDeleteBtn = ev.target.closest('.entry-note-delete-btn');
    var noteCancelBtn = ev.target.closest('.entry-note-cancel-btn');
    var lang = noteLine.getAttribute('data-note-lang') || '';
    var alias = noteLine.getAttribute('data-note-alias') || '';
    var rowId = noteLine.getAttribute('data-note-rowid') || '';
    var headword = noteLine.getAttribute('data-note-headword') || '';
    var pos = noteLine.getAttribute('data-note-pos') || '';
    function _paidGate() {
      if (window.__LE_SUBSCRIBED) return true;
      showUpgradePrompt();
      return false;
    }

    // Re-lookup all live segments that reference (alias, rowId) so fresh
    // hydration from the server picks up the saved/deleted note.
    function _relookupAffectedSegments() {
      var nAlias = String(alias || '').trim();
      var nRowId = parseInt(rowId || 0, 10) || 0;
      if (!nAlias || !nRowId) return;
      if (
        !hoverLayoutState.latestData ||
        !Array.isArray(hoverLayoutState.latestData.results_by_seg) ||
        !hoverLayoutState.latestSegments
      )
        return;
      var dc = window.DictionaryClient;
      if (!dc || typeof dc.relookupOneSegment !== 'function') return;
      var rlang = String(documentShellState.currentLanguage || '').toLowerCase();
      var rbs = hoverLayoutState.latestData.results_by_seg;
      for (var ri = 0; ri < rbs.length; ri++) {
        var seg = rbs[ri];
        if (!seg || !_entryReferencesStorageId(seg, nAlias, nRowId)) continue;
        var surface = String(hoverLayoutState.latestSegments[ri] || '').trim();
        if (!surface) continue;
        (function (segIdx, segSurface, existing) {
          flushLookupCachesForToken(segSurface);
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
          dc.relookupOneSegment(rlang, segSurface, seededExisting)
            .then(function (fresh) {
              applyFreshSegmentResult(fresh || existing, segIdx, segSurface);
            })
            .catch(function () {});
        })(ri, surface, seg);
      }
    }
    function _rebuildNoteLine(noteText) {
      var nText = String(noteText || '').trim();
      var NOTE_COLOR = '#2d8659';
      var MAX = 96;
      var html = '';
      if (nText) {
        var truncated = nText.length > MAX;
        var preview = truncated
          ? nText
              .slice(0, Math.max(nText.lastIndexOf(' ', MAX - 4), Math.floor(MAX * 0.55)))
              .replace(/[,\s|;]+$/g, '')
              .trim() + '...'
          : nText;
        if (truncated) {
          html +=
            '<span class="entry-note-toggle" role="button" tabindex="0"' +
            ' data-note-expanded="0"' +
            ' data-note-collapsed="' +
            _escAttr(preview) +
            '"' +
            ' data-note-full="' +
            _escAttr(nText) +
            '"' +
            ' style="cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px;">' +
            _escHtml(preview) +
            '</span>';
        } else {
          html +=
            '<span class="entry-note-toggle" role="button" tabindex="0"' +
            ' data-note-expanded="1"' +
            ' data-note-collapsed="' +
            _escAttr(nText) +
            '"' +
            ' data-note-full="' +
            _escAttr(nText) +
            '"' +
            ' style="text-decoration:underline dotted;text-underline-offset:2px;">' +
            _escHtml(nText) +
            '</span>';
        }
        html +=
          ' <span class="entry-note-edit-btn" role="button" tabindex="0" data-native-tooltip title="Click to generate or edit a note"' +
          ' style="cursor:pointer;font-size:10px;">&#9998;</span>';
      } else {
        html +=
          '<span class="entry-note-auto-btn" role="button" tabindex="0" data-native-tooltip title="Click to generate or edit a note"' +
          ' style="cursor:pointer;font-size:10px;opacity:0.7;">+ note</span>';
      }
      noteLine.innerHTML = html;
    }
    function _escHtml(s) {
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function _escAttr(s) {
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
    function _showEditor(prefill) {
      noteLine.setAttribute('data-note-before-edit', prefill || '');
      var NOTE_COLOR = '#2d8659';
      noteLine.innerHTML =
        '' +
        '<span class="entry-note-textarea" contenteditable="true" style="display:inline;outline:none;color:' +
        NOTE_COLOR +
        ';font-size:11px;white-space:pre-wrap;word-break:break-word;">' +
        _escHtml(prefill || '') +
        '</span>' +
        ' <span class="entry-note-edit-btn" role="button" tabindex="0" data-editing="1"' +
        ' style="cursor:pointer;font-size:11px;color:' +
        NOTE_COLOR +
        ';font-weight:bold;">&#10003;</span>' +
        ' <span class="entry-note-cancel-btn" role="button" tabindex="0"' +
        ' style="cursor:pointer;font-size:11px;color:#888;">&#10007;</span>' +
        ' <span class="entry-note-delete-btn" role="button" tabindex="0" title="Delete"' +
        ' style="cursor:pointer;font-size:11px;color:#dc2626;">&#128465;</span>';
      var ce = noteLine.querySelector('.entry-note-textarea');
      if (ce) {
        ce.focus();
        var range = document.createRange();
        var sel = window.getSelection();
        range.selectNodeContents(ce);
        range.collapse(false);
        sel.removeAllRanges();
        sel.addRange(range);
      }
    }
    ev.preventDefault();
    ev.stopPropagation();

    // Toggle expand/collapse
    if (
      noteToggle &&
      !noteEditBtn &&
      !noteAddBtn &&
      !noteAutoBtn &&
      !noteSaveBtn &&
      !noteDeleteBtn &&
      !noteCancelBtn
    ) {
      var exp = String(noteToggle.getAttribute('data-note-expanded') || '') === '1';
      var col = String(noteToggle.getAttribute('data-note-collapsed') || '').trim();
      var full = String(noteToggle.getAttribute('data-note-full') || col).trim();
      var next = !exp;
      noteToggle.textContent = next ? full : col;
      noteToggle.setAttribute('data-note-expanded', next ? '1' : '0');
      noteToggle.removeAttribute('title');
      return;
    }

    // Edit btn � either enter edit mode or save (if already editing)
    if (noteEditBtn) {
      if (noteEditBtn.getAttribute('data-editing') === '1') {
        // Save
        var ta2 = noteLine.querySelector('.entry-note-textarea');
        var val2 = ta2 ? (ta2.textContent || '').trim() : '';
        if (!val2) {
          // treat empty save as cancel
          var beforeEdit2 = noteLine.getAttribute('data-note-before-edit') || '';
          _rebuildNoteLine(beforeEdit2);
          return;
        }
        noteEditBtn.textContent = '...';
        noteEditBtn.style.pointerEvents = 'none';
        fetch('/api/entry_note/save', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            lang: lang,
            db_alias: alias,
            entry_row_id: parseInt(rowId, 10),
            note: val2
          })
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (d) {
            if (d.ok) {
              flushCachedEntriesByStorageId(alias, rowId);
              _relookupAffectedSegments();
              _rebuildNoteLine(val2);
            } else {
              noteEditBtn.textContent = '\u2713';
              noteEditBtn.style.pointerEvents = '';
              if (d && (d.upgrade_required || d.upgrade)) showUpgradePrompt();
              else if (d.error) alert(d.error);
            }
          })
          .catch(function () {
            noteEditBtn.textContent = '\u2713';
            noteEditBtn.style.pointerEvents = '';
          });
      } else {
        if (!_paidGate()) return;
        var currentFull = '';
        var toggle = noteLine.querySelector('.entry-note-toggle');
        if (toggle) currentFull = toggle.getAttribute('data-note-full') || toggle.textContent || '';
        _showEditor(currentFull);
      }
      return;
    }

    // Add
    if (noteAddBtn) {
      if (!_paidGate()) return;
      _showEditor('');
      return;
    }

    // Auto-generate
    if (noteAutoBtn) {
      if (!_paidGate()) return;
      noteAutoBtn.textContent = '...';
      noteAutoBtn.style.pointerEvents = 'none';
      var _noteCtx = _buildGeminiEntryContext(alias, parseInt(rowId, 10), headword);
      fetch('/api/entry_note/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          lang: lang,
          db_alias: alias,
          entry_row_id: parseInt(rowId, 10),
          headword: headword,
          pos: pos,
          sentence_tokens: _noteCtx.sentence_tokens,
          fills: _noteCtx.fills
        })
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.ok && d.note) {
            flushCachedEntriesByStorageId(alias, rowId);
            _relookupAffectedSegments();
            _rebuildNoteLine(d.note);
          } else {
            noteAutoBtn.textContent = '\u2726 auto';
            noteAutoBtn.style.pointerEvents = '';
            if (d && (d.upgrade_required || d.upgrade)) showUpgradePrompt();
            else if (d.error) alert(d.error);
          }
        })
        .catch(function () {
          noteAutoBtn.textContent = '\u2726 auto';
          noteAutoBtn.style.pointerEvents = '';
        });
      return;
    }

    // Save
    if (noteSaveBtn) {
      var ta = noteLine.querySelector('.entry-note-textarea');
      var val = ta ? (ta.value !== undefined ? ta.value.trim() : (ta.textContent || '').trim()) : '';
      if (!val) return;
      noteSaveBtn.textContent = '...';
      noteSaveBtn.disabled = true;
      fetch('/api/entry_note/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          lang: lang,
          db_alias: alias,
          entry_row_id: parseInt(rowId, 10),
          note: val
        })
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.ok) {
            flushCachedEntriesByStorageId(alias, rowId);
            _relookupAffectedSegments();
            _rebuildNoteLine(val);
          } else {
            noteSaveBtn.textContent = 'Save';
            noteSaveBtn.disabled = false;
            if (d && (d.upgrade_required || d.upgrade)) showUpgradePrompt();
            else if (d.error) alert(d.error);
          }
        })
        .catch(function () {
          noteSaveBtn.textContent = 'Save';
          noteSaveBtn.disabled = false;
        });
      return;
    }

    // Delete (confirm first — same UX as synthetic dict entry deletion)
    if (noteDeleteBtn) {
      if (!window.confirm('Are you sure you want to delete this note?')) return;
      noteDeleteBtn.textContent = '...';
      noteDeleteBtn.disabled = true;
      fetch('/api/entry_note/delete', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          lang: lang,
          db_alias: alias,
          entry_row_id: parseInt(rowId, 10)
        })
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (d) {
          if (d.ok) {
            flushCachedEntriesByStorageId(alias, rowId);
            _relookupAffectedSegments();
            _rebuildNoteLine('');
          } else {
            noteDeleteBtn.textContent = 'Delete';
            noteDeleteBtn.disabled = false;
            if (d && (d.upgrade_required || d.upgrade)) showUpgradePrompt();
          }
        })
        .catch(function () {
          noteDeleteBtn.textContent = 'Delete';
          noteDeleteBtn.disabled = false;
        });
      return;
    }

    // Cancel
    if (noteCancelBtn) {
      var beforeEdit = noteLine.getAttribute('data-note-before-edit') || '';
      _rebuildNoteLine(beforeEdit);
      return;
    }
  };
  hoverLayoutState.panelContent.onkeydown = function (ev) {
    var key = String((ev && ev.key) || '');
    if (key !== 'Enter' && key !== ' ') return;
    var decompAction =
      ev.target && ev.target.closest
        ? ev.target.closest(
            '.entry-decomp-value, .entry-decomp-auto-btn, .entry-decomp-save-btn, .entry-decomp-cancel-btn, .entry-decomp-delete-btn'
          )
        : null;
    if (decompAction) {
      ev.preventDefault();
      decompAction.click();
      return;
    }
    var morphToggle = ev.target && ev.target.closest ? ev.target.closest('.dict-morph-inline-toggle') : null;
    if (!morphToggle) return;
    ev.preventDefault();
    morphToggle.click();
  };
}
// -- Token Banner: compact segmentation/grammar banner above dictionary panel --
export // track which fill entry is active in banner

function buildTokenBannerSurfaceHtml(data, surfaceText) {
  var surface = String(surfaceText || '').trim();
  if (!surface) return '';
  var lookupEntry = resolveTokenMapLookupEntry('surface', data, surface);
  traceUiRenderEvent(
    'banner_surface_lookup',
    {
      surface: surface,
      lookup_entry: summarizeUiRenderDebugLookupEntry(lookupEntry),
      token_entry: summarizeUiRenderDebugLookupEntry(getCanonicalTokenEntry(data))
    },
    {
      scope: 'banner-surface'
    }
  );
  return buildTokenMapLookupHtml(lookupEntry, surface, 'surface', {
    tokenMapData: data,
    forceTokenMapFallback: true
  });
}
export function buildTokenBannerLemmaHtml(data, lemmaValue, lemmaRawValue) {
  if (!hasDisplayText(lemmaValue) && !hasDisplayText(lemmaRawValue)) return '';
  traceUiRenderEvent(
    'banner_lemma_lookup',
    {
      lemma: String(lemmaValue || ''),
      lemma_raw: String(lemmaRawValue || ''),
      lemma_lookup: summarizeUiRenderDebugLookupEntry(data && data.lemmaLookup)
    },
    {
      scope: 'banner-lemma'
    }
  );
  if (data) return buildTokenMapAnnotatedLemmaHtml(lemmaValue, lemmaRawValue, data.lemmaLookup || null, data);
  return buildHoverableAnnotatedLemmaHtml(
    lemmaValue,
    lemmaRawValue,
    null,
    documentShellState.currentLanguage || ''
  );
}
export function buildTokenBannerMwtLookupHtml(data, childText, partIndex) {
  var text = String(childText || '').trim();
  if (!text) return '';
  return buildTokenMapLookupHtml(
    resolveTokenMapLookupEntry('surface', data, text, partIndex),
    text,
    'surface',
    {
      tokenMapData: data,
      tokenMapPartIndex: isFinite(Number(partIndex)) ? Number(partIndex) : null,
      forceTokenMapFallback: true
    }
  );
}
// Returns joined hoverable HTML for MWT child texts, or '' if children equal the surface.
export function buildTokenBannerMwtChildrenHtml(data, udTok, surfaceText) {
  var parts = udTok && Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
  if (parts.length < 2) return '';
  var childTexts = [];
  for (var i = 0; i < parts.length; i++) {
    var p = parts[i] || {};
    var t = String(p.text || '').trim();
    if (!t || t === '_') t = String(p.lemma || '').trim();
    childTexts.push(t);
  }
  // Only show when joined child texts differ visibly from the surface.
  var joined = childTexts.join('');
  var surface = String(surfaceText || '').trim();
  if (joined && hasSameVisibleComparisonText(joined, surface)) return '';
  var html = '';
  for (var j = 0; j < childTexts.length; j++) {
    var ct = childTexts[j];
    if (!ct) continue;
    if (j > 0) html += '<span aria-hidden="true" style="opacity:0.5;pointer-events:none;"> + </span>';
    html += buildTokenBannerMwtLookupHtml(data, ct, j);
  }
  return html;
}
export function showTokenBannerInfoPopup(titleText, bodyText) {
  if (!hoverLayoutState.hoverPopup || !hoverLayoutState.hoverPopupContainer) return false;
  var title = String(titleText || '').trim();
  var body = String(bodyText || '').trim();
  if (!title && !body) return false;
  var html = '<div class="tb-help-popup">';
  if (title) html += '<div class="tb-help-popup-title">' + escapeHtml(title) + '</div>';
  if (body) html += '<div class="tb-help-popup-body">' + escapeHtml(body) + '</div>';
  html += '</div>';
  hoverLayoutState.hoverPopup.innerHTML = html;
  setDictionaryPopupSignalFromMarkup(hoverLayoutState.hoverPopup, html, {
    disableClamp: true
  });
  hoverLayoutState.hoverPopup.style.display = 'block';
  hoverLayoutState.hoverPopupContainer.style.display = 'flex';
  applyDictionaryHoverPopupClamp();
  positionSidePanelPopup(
    hoverLayoutState.hoverPopupContainer,
    segmentRenderingState.lastMouseX,
    segmentRenderingState.lastMouseY
  );
  return true;
}
export function initializeTokenBannerMenu() {
  document.addEventListener(
    'click',
    function (ev) {
      if (sidePanelState._decompFloat && sidePanelState._decompFloat.contains(ev.target)) {
        var saveBtn = ev.target.closest && ev.target.closest('.decomp-save-btn');
        var cancelBtn = ev.target.closest && ev.target.closest('.decomp-cancel-btn');
        var deleteBtn = ev.target.closest && ev.target.closest('.decomp-delete-btn');
        if (saveBtn) {
          ev.preventDefault();
          ev.stopPropagation();
          _saveDecompFromEditor(sidePanelState._decompFloatBlock);
          return;
        }
        if (cancelBtn) {
          ev.preventDefault();
          ev.stopPropagation();
          _hideDecompFloat();
          return;
        }
        if (deleteBtn) {
          ev.preventDefault();
          ev.stopPropagation();
          _deleteDecompFromEditor(sidePanelState._decompFloatBlock);
          return;
        }
        return;
      }
      if (sidePanelState._decompFloat && sidePanelState._decompFloat.contains && false) {
        /* no-op guard kept for clarity */
      }
      var block = ev.target.closest && ev.target.closest('.entry-headword-block');
      if (!block) {
        if (
          sidePanelState._decompFloatState === 'view' ||
          sidePanelState._decompFloatState === 'edit' ||
          sidePanelState._decompFloatState === 'tooltip'
        ) {
          _hideDecompFloat();
        }
        return;
      }
      ev.preventDefault();
      ev.stopPropagation();
      var prevBlock = sidePanelState._decompFloatBlock;
      _fetchDecompForBlock(block, function (existing) {
        if (existing) {
          // Decomp exists: open editor directly on click (view already visible from hover)
          _renderDecompEditor(block, existing);
        } else {
          // No decomp yet: generate and show view
          _generateAndShowDecomp(block);
        }
      });
    },
    true
  );
  tokenBannerMenuState._bannerActiveFillKey = null;
  return true;
}
