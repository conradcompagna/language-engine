import { loadFileViaDocRender } from './continuous-scroll.mjs';
import { refreshUiAfterCustomEntryMutation } from './custom-entry-state.mjs';
import { loadPdfInBrowser, updateRenderedOutputBackground } from './document-import.mjs';
import { loadEpubWithEpubJs } from './document-navigation.mjs';
import { leaveRawContinuousMode, showDocumentChrome } from './document-search.mjs';
import { revokePdfBrowserObjectUrl } from './document-shell.mjs';
import { documentShellState } from './document-shell.state.mjs';
import { cancelMovementLookupTimer, hideRawTextPill, resetCanonicalDocument } from './document-state.mjs';
import { documentState } from './document-state.state.mjs';
import { clonePanelEditSnapshot } from './entry-editing.mjs';
import { destroyEpubJs } from './foliate-viewport.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { orthographyState } from './orthography.state.mjs';
import { escapeHtml, handlePaidFeatureError } from './presentation.mjs';
import {
  buildEntryDeleteActionHtml,
  buildEntryDeletePanelHtml,
  buildGeminiSynthPosSelectHtml,
  closeEntryFormPanel,
  togglePanel
} from './settings-panels.mjs';
import { applyGlobalViewportClamp } from './viewport-clamping.mjs';
export // DEBUG MAP: synthetic/gemini edit form.
// Save-button state here is intended to be a single stable state machine:
// baseline snapshot -> current serialized form state -> canSave -> disabled flag.
function showEntryForm(opts) {
  opts = opts || {};
  var editMode = !!opts.editMode;
  var editContext = opts.editContext || null;
  var lang = opts.lang || documentShellState.currentLanguage || '';
  var source = opts.source || '';
  var entryId =
    opts.entry_id || (editContext && editContext.snapshot ? editContext.snapshot.entry_id : '') || '';
  var entryRowId =
    parseInt(
      opts.entry_row_id || (editContext && editContext.snapshot ? editContext.snapshot.entry_row_id : 0) || 0,
      10
    ) || 0;
  var storageKind = String(
    opts.storage_kind || (editContext && editContext.snapshot ? editContext.snapshot.storage_kind : '') || ''
  );
  var dbAlias = String(
    opts.db_alias || (editContext && editContext.snapshot ? editContext.snapshot.db_alias : '') || ''
  );
  var headword = opts.headword || '';
  var romanization = opts.romanization || '';
  var pos = opts.pos || '';
  var glosses = Array.isArray(opts.glosses) ? opts.glosses : [];
  var commentary = opts.commentary || '';
  var lemma = opts.lemma || '';
  togglePanel(true);
  var panelClass = editMode ? 'entry-form-panel entry-form-panel-edit' : 'entry-form-panel';
  var html =
    '<div class="' +
    panelClass +
    '">' +
    '<form id="entry-form" class="userdict-form">' +
    '  <div class="userdict-field">' +
    '    <label>Headword</label>' +
    '    <input type="text" id="ef-headword" class="userdict-input" value="' +
    escapeHtml(headword) +
    '" disabled>' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Pronunciation</label>' +
    '    <input type="text" id="ef-roman" class="userdict-input" value="' +
    escapeHtml(romanization) +
    '">' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Part of speech' +
    (editMode ? '' : ' *') +
    '</label>' +
    buildGeminiSynthPosSelectHtml(pos) +
    '  </div>' +
    '  <div class="userdict-field-full">' +
    '    <label>Glosses' +
    (editMode ? '' : ' *') +
    '</label>' +
    '    <div id="ef-glosses-list" class="ef-dynamic-list"></div>' +
    '    <button type="button" id="ef-add-gloss" class="ef-add-btn">+ Add gloss</button>' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Labels</label>' +
    '    <input type="text" id="ef-commentary" class="userdict-input" value="' +
    escapeHtml(commentary) +
    '" placeholder="e.g. past; plural; misspelling">' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Canonical Form</label>' +
    '    <input type="text" id="ef-lemma" class="userdict-input" value="' +
    escapeHtml(lemma) +
    '" placeholder="Leave empty if headword is canonical">' +
    '  </div>' +
    '  <div class="userdict-actions">' +
    '    <button type="submit" id="ef-save-btn" class="gemini-edit-save-btn" disabled>Save</button>' +
    '    <button type="button" id="ef-cancel-btn" class="gemini-edit-cancel-btn">Cancel</button>' +
    buildEntryDeleteActionHtml(editMode) +
    '  </div>' +
    '</form>' +
    buildEntryDeletePanelHtml(editMode) +
    '</div>';
  hoverLayoutState.panelContent.innerHTML = html;
  // Disable panel hover handlers while form is open � they cause save button winking
  hoverLayoutState.panelContent.onmousemove = null;
  hoverLayoutState.panelContent.onmouseleave = null;
  var entryFormEl = document.getElementById('entry-form');
  var saveBtn = document.getElementById('ef-save-btn');

  // --- Glosses dynamic list ---
  var glossesList = document.getElementById('ef-glosses-list');
  function addGlossRow(value) {
    var row = document.createElement('div');
    row.className = 'ef-row';
    row.innerHTML =
      '<input type="text" class="userdict-input ef-gloss-input" value="' +
      escapeHtml(value || '') +
      '" placeholder="e.g. run; dash">' +
      '<button type="button" class="ef-remove-btn" title="Remove">&times;</button>';
    row.querySelector('.ef-remove-btn').addEventListener('click', function () {
      row.remove();
      recomputeSaveState();
    });
    glossesList.appendChild(row);
  }
  if (glosses.length) {
    for (var gi = 0; gi < glosses.length; gi++) addGlossRow(glosses[gi]);
  } else {
    addGlossRow('');
  }
  document.getElementById('ef-add-gloss').addEventListener('click', function () {
    addGlossRow('');
    recomputeSaveState();
  });

  // DEBUG MAP: canonical serialized edit-state for the synthetic form.
  // If Save enables/disables incorrectly, compare this payload against baselineEntryState.
  function buildComparableEntryState() {
    var glossInputs = glossesList.querySelectorAll('.ef-gloss-input');
    var glossValues = [];
    for (var gi2 = 0; gi2 < glossInputs.length; gi2++) {
      var glossValue = String(glossInputs[gi2].value || '').trim();
      if (glossValue) glossValues.push(glossValue);
    }
    return {
      headword: String(headword || '').trim(),
      romanization: String((document.getElementById('ef-roman') || {}).value || '').trim(),
      pos: String((document.getElementById('ef-pos') || {}).value || '').trim(),
      commentary: String((document.getElementById('ef-commentary') || {}).value || '').trim(),
      lemma: String((document.getElementById('ef-lemma') || {}).value || '').trim(),
      glosses: glossValues
    };
  }
  var baselineEntryState = JSON.stringify(buildComparableEntryState());
  var formState = {
    saving: false,
    canSave: false
  };
  // DEBUG MAP: the only rule that decides whether Save should unlock.
  function canSaveCurrentState(currentState) {
    if (editMode) return !!currentState.pos && JSON.stringify(currentState) !== baselineEntryState;
    return !!(currentState.headword && currentState.pos && currentState.glosses.length);
  }
  // DEBUG MAP: actual DOM write for Save button state.
  function applySaveState() {
    if (!saveBtn) return;
    saveBtn.textContent = formState.saving ? 'Saving...' : 'Save';
    saveBtn.disabled = formState.saving || !formState.canSave;
  }
  // DEBUG MAP: recomputes Save from serialized current state only.
  function recomputeSaveState() {
    formState.canSave = canSaveCurrentState(buildComparableEntryState());
    applySaveState();
  }
  // DEBUG MAP: wiring for the synthetic form Save state.
  // All live unlock/lock behavior is supposed to come through these form-level listeners.
  if (entryFormEl) {
    entryFormEl.addEventListener('input', recomputeSaveState);
    entryFormEl.addEventListener('change', recomputeSaveState);
  }
  recomputeSaveState();

  // --- Save handler ---
  entryFormEl.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var hw = (document.getElementById('ef-headword').value || '').trim();
    if (!hw) {
      alert('Headword is required.');
      return;
    }
    var pron = (document.getElementById('ef-roman').value || '').trim();
    var posVal = (document.getElementById('ef-pos').value || '').trim();
    var commVal = (document.getElementById('ef-commentary').value || '').trim();
    var lemmaVal = (document.getElementById('ef-lemma').value || '').trim();

    // Collect glosses
    var glossInputs = glossesList.querySelectorAll('.ef-gloss-input');
    var glossArr = [];
    for (var i = 0; i < glossInputs.length; i++) {
      var v = (glossInputs[i].value || '').trim();
      if (v) glossArr.push(v);
    }
    formState.saving = true;
    applySaveState();
    var entryPayload = {
      entry_id: entryId,
      entry_row_id: entryRowId,
      storage_kind: storageKind,
      db_alias: dbAlias,
      headword: hw,
      romanization: pron,
      pos: posVal,
      glosses: glossArr,
      forms: [],
      commentary: commVal,
      lemma: lemmaVal,
      source: source || 'gemini'
    };
    var previousEntryForRefresh =
      editContext && editContext.liveEntry
        ? editContext.liveEntry
        : editContext && editContext.snapshot
          ? editContext.snapshot
          : null;
    var apiUrl = '/api/gemini_entry/update';
    var apiBody = Object.assign(
      {
        language: lang
      },
      entryPayload
    );
    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(apiBody)
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) {
          handlePaidFeatureError(data, 'Failed to save.');
          formState.saving = false;
          recomputeSaveState();
          return;
        }
        var updatedEntryPayload = data && data.entry ? data.entry : entryPayload;
        var updatePromise =
          window.DictionaryClient && typeof window.DictionaryClient.updateGeminiEntry === 'function'
            ? window.DictionaryClient.updateGeminiEntry(lang, updatedEntryPayload)
            : Promise.resolve();
        Promise.resolve(updatePromise)
          .then(function () {
            return refreshUiAfterCustomEntryMutation({
              previousEntry: previousEntryForRefresh,
              nextEntry: updatedEntryPayload,
              returnState: editContext && editContext.returnState,
              fallbackHeadword: hw,
              fallbackSurface:
                (editContext &&
                  editContext.returnState &&
                  editContext.returnState.fullData &&
                  editContext.returnState.fullData._panelTokenSurface) ||
                hw
            });
          })
          .catch(function () {});
      })
      .catch(function () {
        alert('Failed to save entry.');
        formState.saving = false;
        recomputeSaveState();
      });
  });

  // Cancel handler
  var cancelBtn = document.getElementById('ef-cancel-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      closeEntryFormPanel(headword, editContext && editContext.returnState);
    });
  }

  // Direct deletion for paid users (edit mode only)
  if (editMode) {
    _bindCustomEntryDelete(
      {
        entry_id: entryId,
        entry_row_id: entryRowId,
        storage_kind: storageKind,
        db_alias: dbAlias,
        headword: headword
      },
      lang
    );
  }
}

// User entry form � for creating/editing user-created entries.
// Headword is editable on create, disabled on edit.  Has full forms
// paradigm support (word + tags + pronunciation rows) like Wiktionary.
// opts: { headword, romanization, pos, glosses:[], forms:[], lang, source, editMode }
// ---------------------------------------------------------------------------
// DEBUG MAP: user-entry create/edit form.
// This uses the same Save-button model as showEntryForm, but the validity rule differs.
export function showUserEntryForm(opts) {
  opts = opts || {};
  var editMode = !!opts.editMode;
  var editContext = opts.editContext || null;
  var lang = opts.lang || documentShellState.currentLanguage || '';
  var source = opts.source || 'user_created';
  var entryId =
    opts.entry_id || (editContext && editContext.snapshot ? editContext.snapshot.entry_id : '') || '';
  var entryRowId =
    parseInt(
      opts.entry_row_id || (editContext && editContext.snapshot ? editContext.snapshot.entry_row_id : 0) || 0,
      10
    ) || 0;
  var storageKind = String(
    opts.storage_kind || (editContext && editContext.snapshot ? editContext.snapshot.storage_kind : '') || ''
  );
  var dbAlias = String(
    opts.db_alias || (editContext && editContext.snapshot ? editContext.snapshot.db_alias : '') || ''
  );
  var headword = opts.headword || '';
  var romanization = opts.romanization || '';
  var pos = opts.pos || '';
  var glosses = Array.isArray(opts.glosses) ? opts.glosses : [];
  var forms = Array.isArray(opts.forms) ? opts.forms : [];
  togglePanel(true);
  var panelClass = editMode ? 'entry-form-panel entry-form-panel-edit' : 'entry-form-panel';
  var html =
    '<div class="' +
    panelClass +
    '">' +
    '<form id="entry-form" class="userdict-form">' +
    '  <div class="userdict-field">' +
    '    <label>Headword *</label>' +
    '    <input type="text" id="ef-headword" class="userdict-input" value="' +
    escapeHtml(headword) +
    '"' +
    (editMode ? ' disabled' : ' required') +
    '>' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Pronunciation</label>' +
    '    <input type="text" id="ef-roman" class="userdict-input" value="' +
    escapeHtml(romanization) +
    '">' +
    '  </div>' +
    '  <div class="userdict-field">' +
    '    <label>Part of speech' +
    (editMode ? '' : ' *') +
    '</label>' +
    '    <input type="text" id="ef-pos" class="userdict-input" value="' +
    escapeHtml(pos) +
    '"' +
    (editMode ? '' : ' required') +
    '>' +
    '  </div>' +
    '  <div class="userdict-field-full">' +
    '    <label>Glosses' +
    (editMode ? '' : ' *') +
    '</label>' +
    '    <div id="ef-glosses-list" class="ef-dynamic-list"></div>' +
    '    <button type="button" id="ef-add-gloss" class="ef-add-btn">+ Add gloss</button>' +
    '  </div>' +
    '  <div class="userdict-field-full">' +
    '    <label>Forms</label>' +
    '    <div id="ef-forms-list" class="ef-dynamic-list"></div>' +
    '    <button type="button" id="ef-add-form" class="ef-add-btn">+ Add form</button>' +
    '  </div>' +
    '  <div class="userdict-actions">' +
    '    <button type="submit" id="ef-save-btn" class="gemini-edit-save-btn" disabled>Save</button>' +
    '    <button type="button" id="ef-cancel-btn" class="gemini-edit-cancel-btn">Cancel</button>' +
    buildEntryDeleteActionHtml(editMode) +
    '  </div>' +
    '</form>' +
    buildEntryDeletePanelHtml(editMode) +
    '</div>';
  hoverLayoutState.panelContent.innerHTML = html;
  // Disable panel hover handlers while form is open � they cause save button winking
  hoverLayoutState.panelContent.onmousemove = null;
  hoverLayoutState.panelContent.onmouseleave = null;
  var entryFormEl = document.getElementById('entry-form');
  var saveBtn = document.getElementById('ef-save-btn');

  // --- Glosses dynamic list ---
  var glossesList = document.getElementById('ef-glosses-list');
  function addGlossRow(value) {
    var row = document.createElement('div');
    row.className = 'ef-row';
    row.innerHTML =
      '<input type="text" class="userdict-input ef-gloss-input" value="' +
      escapeHtml(value || '') +
      '" placeholder="e.g. run; dash">' +
      '<button type="button" class="ef-remove-btn" title="Remove">&times;</button>';
    row.querySelector('.ef-remove-btn').addEventListener('click', function () {
      row.remove();
      recomputeSaveState();
    });
    glossesList.appendChild(row);
  }
  if (glosses.length) {
    for (var gi = 0; gi < glosses.length; gi++) addGlossRow(glosses[gi]);
  } else {
    addGlossRow('');
  }
  document.getElementById('ef-add-gloss').addEventListener('click', function () {
    addGlossRow('');
    recomputeSaveState();
  });

  // --- Forms dynamic list ---
  var formsList = document.getElementById('ef-forms-list');
  function addFormRow(word, tags, pron) {
    var row = document.createElement('div');
    row.className = 'ef-row ef-form-row';
    row.innerHTML =
      '<input type="text" class="userdict-input ef-form-word" value="' +
      escapeHtml(word || '') +
      '" placeholder="Form">' +
      '<input type="text" class="userdict-input ef-form-commentary" value="' +
      escapeHtml(tags || '') +
      '" placeholder="Tags">' +
      '<input type="text" class="userdict-input ef-form-pron" value="' +
      escapeHtml(pron || '') +
      '" placeholder="Roman">' +
      '<button type="button" class="ef-remove-btn" title="Remove">&times;</button>';
    row.querySelector('.ef-remove-btn').addEventListener('click', function () {
      row.remove();
      recomputeSaveState();
    });
    formsList.appendChild(row);
  }
  for (var fi = 0; fi < forms.length; fi++) {
    var f = forms[fi];
    if (Array.isArray(f)) addFormRow(f[0] || '', f[1] || '', f[2] || '');
  }
  document.getElementById('ef-add-form').addEventListener('click', function () {
    addFormRow('', '', '');
    recomputeSaveState();
  });

  // DEBUG MAP: canonical serialized state for the user-entry form.
  function buildComparableUserEntryState() {
    var glossInputs = glossesList.querySelectorAll('.ef-gloss-input');
    var glossValues = [];
    for (var gi2 = 0; gi2 < glossInputs.length; gi2++) {
      var glossValue = String(glossInputs[gi2].value || '').trim();
      if (glossValue) glossValues.push(glossValue);
    }
    var formRows = formsList.querySelectorAll('.ef-form-row');
    var formValues = [];
    for (var fri = 0; fri < formRows.length; fri++) {
      var formWord = String((formRows[fri].querySelector('.ef-form-word') || {}).value || '').trim();
      var formTags = String((formRows[fri].querySelector('.ef-form-commentary') || {}).value || '').trim();
      var formRoman = String((formRows[fri].querySelector('.ef-form-pron') || {}).value || '').trim();
      if (formWord) {
        formValues.push([formWord, formTags, formRoman]);
      }
    }
    return {
      headword: String((document.getElementById('ef-headword') || {}).value || '').trim(),
      romanization: String((document.getElementById('ef-roman') || {}).value || '').trim(),
      pos: String((document.getElementById('ef-pos') || {}).value || '').trim(),
      glosses: glossValues,
      forms: formValues
    };
  }
  var baselineUserEntryState = JSON.stringify(buildComparableUserEntryState());
  var formState = {
    saving: false,
    canSave: false
  };
  // DEBUG MAP: the only rule that decides whether Save should unlock.
  function canSaveCurrentState(currentState) {
    if (editMode) return JSON.stringify(currentState) !== baselineUserEntryState;
    return !!(currentState.headword && currentState.pos && currentState.glosses.length);
  }
  // DEBUG MAP: actual DOM write for Save button state.
  function applySaveState() {
    if (!saveBtn) return;
    saveBtn.textContent = formState.saving ? 'Saving...' : 'Save';
    saveBtn.disabled = formState.saving || !formState.canSave;
  }
  // DEBUG MAP: recomputes Save from serialized current state only.
  function recomputeSaveState() {
    formState.canSave = canSaveCurrentState(buildComparableUserEntryState());
    applySaveState();
  }
  // DEBUG MAP: wiring for the user-entry form Save state.
  // All live unlock/lock behavior is supposed to come through these form-level listeners.
  if (entryFormEl) {
    entryFormEl.addEventListener('input', recomputeSaveState);
    entryFormEl.addEventListener('change', recomputeSaveState);
  }
  recomputeSaveState();

  // Focus
  var headEl = document.getElementById('ef-headword');
  if (!editMode && headEl) headEl.focus();

  // --- Save handler ---
  entryFormEl.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var hw = (document.getElementById('ef-headword').value || '').trim();
    if (!hw) {
      alert('Headword is required.');
      return;
    }
    var pron = (document.getElementById('ef-roman').value || '').trim();
    var posVal = (document.getElementById('ef-pos').value || '').trim();
    if (!posVal) {
      alert('Part of speech is required.');
      return;
    }

    // Collect glosses
    var glossInputs = glossesList.querySelectorAll('.ef-gloss-input');
    var glossArr = [];
    for (var i = 0; i < glossInputs.length; i++) {
      var v = (glossInputs[i].value || '').trim();
      if (v) glossArr.push(v);
    }
    if (!glossArr.length) {
      alert('At least one gloss is required.');
      return;
    }

    // Collect forms
    var formRows = formsList.querySelectorAll('.ef-form-row');
    var formArr = [];
    for (var j = 0; j < formRows.length; j++) {
      var fw = (formRows[j].querySelector('.ef-form-word').value || '').trim();
      var fc = (formRows[j].querySelector('.ef-form-commentary').value || '').trim();
      var fp = (formRows[j].querySelector('.ef-form-pron').value || '').trim();
      if (fw) formArr.push([fw, fc, fp]);
    }
    formState.saving = true;
    applySaveState();
    var entryPayload = {
      entry_id: entryId,
      entry_row_id: entryRowId,
      storage_kind: storageKind,
      db_alias: dbAlias,
      headword: hw,
      romanization: pron,
      pos: posVal,
      glosses: glossArr,
      forms: formArr,
      source: source || 'user_created'
    };
    var previousEntryForRefresh =
      editContext && editContext.liveEntry
        ? editContext.liveEntry
        : editContext && editContext.snapshot
          ? editContext.snapshot
          : null;
    var apiUrl = editMode ? '/api/gemini_entry/update' : '/api/user_dict/add';
    var apiBody = Object.assign(
      {
        language: lang
      },
      entryPayload
    );
    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(apiBody)
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) {
          handlePaidFeatureError(data, 'Failed to save.');
          formState.saving = false;
          recomputeSaveState();
          return;
        }
        var savedEntryPayload = data && data.entry ? data.entry : entryPayload;
        var syncPromise = Promise.resolve();
        if (window.DictionaryClient) {
          if (editMode && typeof window.DictionaryClient.updateGeminiEntry === 'function') {
            syncPromise = window.DictionaryClient.updateGeminiEntry(lang, savedEntryPayload);
          } else if (!editMode && typeof window.DictionaryClient.injectGeminiEntry === 'function') {
            syncPromise = window.DictionaryClient.injectGeminiEntry(lang, savedEntryPayload);
          }
        }
        if (editMode) {
          Promise.resolve(syncPromise)
            .then(function () {
              return refreshUiAfterCustomEntryMutation({
                previousEntry: previousEntryForRefresh,
                nextEntry: savedEntryPayload,
                returnState: editContext && editContext.returnState,
                fallbackHeadword: hw,
                fallbackSurface:
                  (editContext &&
                    editContext.returnState &&
                    editContext.returnState.fullData &&
                    editContext.returnState.fullData._panelTokenSurface) ||
                  hw
              });
            })
            .catch(function () {});
          return;
        }
        Promise.resolve(syncPromise)
          .then(function () {
            return refreshUiAfterCustomEntryMutation({
              nextEntry: savedEntryPayload,
              fallbackHeadword: hw,
              fallbackSurface: hw
            });
          })
          .catch(function () {});
      })
      .catch(function () {
        alert('Failed to save entry.');
        formState.saving = false;
        recomputeSaveState();
      });
  });

  // Cancel handler
  var cancelBtn = document.getElementById('ef-cancel-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function () {
      closeEntryFormPanel(headword, editContext && editContext.returnState);
    });
  }

  // Direct deletion for paid users (edit mode only)
  if (editMode) {
    _bindCustomEntryDelete(
      {
        entry_id: entryId,
        entry_row_id: entryRowId,
        storage_kind: storageKind,
        db_alias: dbAlias,
        headword: headword
      },
      lang
    );
  }
}

// Shared direct-delete binding for both form types
export function _bindCustomEntryDelete(entryRef, lang) {
  var entryId = '';
  var entryRowId = 0;
  var storageKind = '';
  var dbAlias = '';
  var headword = '';
  if (entryRef && typeof entryRef === 'object') {
    entryId = String(entryRef.entry_id || '').trim();
    entryRowId = parseInt(entryRef.entry_row_id || 0, 10) || 0;
    storageKind = String(entryRef.storage_kind || '').trim();
    dbAlias = String(entryRef.db_alias || '').trim();
    headword = String(entryRef.headword || '').trim();
  } else {
    headword = String(entryRef || '').trim();
  }
  var deleteBtn = document.getElementById('ef-delete-btn');
  if (!deleteBtn) return;
  deleteBtn.addEventListener('click', function () {
    if (!window.confirm('Are you sure you want to delete this entry?')) return;
    deleteBtn.disabled = true;
    deleteBtn.textContent = 'Deleting...';
    var previousEntryForRefresh =
      hoverLayoutState.currentPanelDisplayState && hoverLayoutState.currentPanelDisplayState.res
        ? hoverLayoutState.currentPanelDisplayState.res
        : {
            entry_id: entryId,
            entry_row_id: entryRowId,
            headword: headword
          };
    fetch('/api/gemini_entry/delete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        entry_id: entryId,
        entry_row_id: entryRowId,
        storage_kind: storageKind,
        db_alias: dbAlias,
        headword: headword,
        language: lang
      })
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (resp) {
        if (!resp || !resp.ok) {
          handlePaidFeatureError(resp, 'Failed to delete.');
          deleteBtn.disabled = false;
          deleteBtn.textContent = 'Delete';
          return;
        }
        var removePromise =
          window.DictionaryClient && typeof window.DictionaryClient.removeGeminiEntry === 'function'
            ? window.DictionaryClient.removeGeminiEntry(lang, {
                headword: headword,
                entry_row_id: entryRowId,
                storage_kind: storageKind,
                db_alias: dbAlias
              })
            : Promise.resolve();
        Promise.resolve(removePromise)
          .then(function () {
            return refreshUiAfterCustomEntryMutation({
              previousEntry: previousEntryForRefresh,
              returnState: hoverLayoutState.currentPanelDisplayState,
              fallbackHeadword: headword,
              fallbackSurface:
                (hoverLayoutState.currentPanelDisplayState &&
                  hoverLayoutState.currentPanelDisplayState.fullData &&
                  hoverLayoutState.currentPanelDisplayState.fullData._panelTokenSurface) ||
                headword
            });
          })
          .catch(function () {});
      })
      .catch(function () {
        alert('Failed to delete entry.');
        deleteBtn.disabled = false;
        deleteBtn.textContent = 'Delete';
      });
  });
}

// Convenience wrappers
export function showGeminiEditPanel(editContext) {
  var ctx = editContext && typeof editContext === 'object' ? editContext : null;
  var snapshot = clonePanelEditSnapshot(ctx && ctx.snapshot);
  if (!snapshot) return;
  var resolvedSource =
    String(snapshot.source || '')
      .trim()
      .toLowerCase() || 'gemini';
  if (resolvedSource === 'user_created') {
    showUserEntryForm({
      entry_id: snapshot.entry_id,
      entry_row_id: snapshot.entry_row_id,
      storage_kind: snapshot.storage_kind,
      db_alias: snapshot.db_alias,
      headword: snapshot.headword,
      romanization: snapshot.romanization,
      pos: snapshot.pos,
      glosses: snapshot.glosses,
      forms: snapshot.forms,
      lang: snapshot.lang,
      source: resolvedSource,
      editMode: true,
      editContext: ctx
    });
    return;
  }
  showEntryForm({
    entry_id: snapshot.entry_id,
    entry_row_id: snapshot.entry_row_id,
    storage_kind: snapshot.storage_kind,
    db_alias: snapshot.db_alias,
    headword: snapshot.headword,
    romanization: snapshot.romanization,
    pos: snapshot.pos,
    glosses: snapshot.glosses,
    commentary: snapshot.commentary,
    lemma: snapshot.lemma,
    lang: snapshot.lang,
    source: resolvedSource,
    editMode: true,
    editContext: ctx
  });
}

// File handling
export function setLoadedFileName(name) {
  if (!hoverLayoutState.fileNamePill || !hoverLayoutState.fileNameText) return;
  var label = (name || '').toString();
  if (!label) {
    hoverLayoutState.fileNamePill.style.display = 'none';
    hoverLayoutState.fileNameText.textContent = '';
    return;
  }
  hoverLayoutState.fileNameText.textContent = label;
  hoverLayoutState.fileNamePill.style.display = 'inline-flex';
}
export function clearLoadedFile() {
  cancelMovementLookupTimer();
  leaveRawContinuousMode();
  documentShellState.pdfJsSessionId += 1;
  documentShellState.pdfJsIframe = null;
  revokePdfBrowserObjectUrl();
  documentShellState.pdfOriginal.renderSeq += 1;
  documentState.pdfCacheId = null;
  // Destroy PDF.js document
  if (documentShellState.pdfOriginal.doc) {
    documentShellState.pdfOriginal.doc.destroy();
    documentShellState.pdfOriginal.doc = null;
  }
  documentShellState.pdfOriginal.fileToken = null;
  documentShellState.pdfOriginal.docPromise = null;
  // Reset DOCX original-view cache/cancellation state.
  documentShellState.docxOriginal.renderSeq += 1;
  documentShellState.docxOriginal.buf = null;
  documentShellState.docxOriginal.fileToken = null;
  documentShellState.docxOriginal.rendered = false;
  destroyEpubJs();
  // Clean up observer
  if (documentShellState.pdfJsObserver) {
    documentShellState.pdfJsObserver.disconnect();
    documentShellState.pdfJsObserver = null;
  }
  documentShellState.pdfJsRenderedPages = {};
  documentState.inputMode = 'raw';
  documentState.docText = '';
  documentState.docPagerIsPaged = false;
  documentState.docPages = [];
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.pdfRawPageTextLoaded = {};
  documentState.pdfCanonicalPageFetches = {};
  documentState.docrenderPdfRichHtml = [];
  documentState.docrenderPdfText = [];
  documentState.docrenderPdfTextMap = [];
  documentState.docrenderActive = false;
  documentState.webSnapshotCanonicalSeq += 1;
  documentState.webSnapshotInspectorEnabled = false;
  documentState.webSnapshotSelectedText = '';
  documentState.docSourcePages = [];
  documentState.docPageRichHtml = [];
  documentState.docPageTextMaps = [];
  documentState.docrenderPageHeightPx = 0;
  documentState.docrenderPageWidthPx = 0;
  hideRawTextPill();
  // Reset original view state
  documentState.currentFile = null;
  documentState.currentFileType = null;
  documentState.pdfCacheId = null;
  documentShellState.pdfPageDimensions = [];
  documentShellState.pdfAveragePageDimensions = null;
  documentState.isOriginalView = false;
  documentState.originalLayoutCache = {};
  if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
  if (documentState.origViewCheckbox) documentState.origViewCheckbox.checked = false;
  if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.classList.remove('orig-view-mode');
    hoverLayoutState.sourcePager.classList.remove(
      'pdfjs-native-mode',
      'docrender-docx-continuous-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.style.display = 'none';
    hoverLayoutState.sourcePager.innerHTML = '';
  }
  showDocumentChrome(false);
  if (hoverLayoutState.sourceText) {
    hoverLayoutState.sourceText.style.display = '';
    hoverLayoutState.sourceText.value = '';
  }
  if (hoverLayoutState.fileNamePill) hoverLayoutState.fileNamePill.style.display = 'none';
  if (hoverLayoutState.fileNameText) hoverLayoutState.fileNameText.textContent = '';
  if (hoverLayoutState.rawTextPill) hoverLayoutState.rawTextPill.style.display = 'none';
  if (hoverLayoutState.rawTextText) hoverLayoutState.rawTextText.textContent = '';
  if (hoverLayoutState.fileInput) hoverLayoutState.fileInput.value = '';
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.innerHTML = '';
  }
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Ready.';
  if (hoverLayoutState.statusCounts) hoverLayoutState.statusCounts.textContent = '';
  applyGlobalViewportClamp(true);
  updateRenderedOutputBackground();
}
export function loadFile(file) {
  if (!file) return;
  cancelMovementLookupTimer();
  leaveRawContinuousMode();
  documentShellState.pdfJsSessionId += 1;
  documentShellState.pdfJsIframe = null;
  revokePdfBrowserObjectUrl();
  documentShellState.pdfOriginal.renderSeq += 1;
  setLoadedFileName(file.name || 'document');
  var name = (file.name || '').toLowerCase();

  // Clean up previous PDF.js state
  hideRawTextPill();
  documentState.pdfCacheId = null;
  if (documentShellState.pdfOriginal.doc) {
    documentShellState.pdfOriginal.doc.destroy();
    documentShellState.pdfOriginal.doc = null;
  }
  documentShellState.pdfOriginal.fileToken = null;
  documentShellState.pdfOriginal.docPromise = null;
  if (documentShellState.pdfJsObserver) {
    documentShellState.pdfJsObserver.disconnect();
    documentShellState.pdfJsObserver = null;
  }
  // Invalidate DOCX original-view state from the previous file.
  documentShellState.docxOriginal.renderSeq += 1;
  documentShellState.docxOriginal.buf = null;
  documentShellState.docxOriginal.fileToken = null;
  documentShellState.docxOriginal.rendered = false;
  documentShellState.pdfJsRenderedPages = {};
  documentState.currentFile = file;
  documentState.pdfCacheId = null;
  documentShellState.pdfPageDimensions = [];
  documentShellState.pdfAveragePageDimensions = null;
  documentState.isOriginalView = false;
  documentState.originalLayoutCache = {};
  documentState.rawTextFoliateLoadSeq += 1;
  documentState.activePageIndex = 0;
  documentState.lastLookupPageIndex = -1;
  documentState.pendingPdfLookupPageIndex = -1;
  documentState.pageLookupTextByIndex = {};
  documentState.pdfRawPageTextLoaded = {};
  documentState.pdfCanonicalPageFetches = {};
  documentState.docrenderPdfRichHtml = [];
  documentState.docrenderPdfText = [];
  documentState.docrenderPdfTextMap = [];
  resetCanonicalDocument();
  destroyEpubJs();
  if (documentState.origViewCheckbox) documentState.origViewCheckbox.checked = false;
  if (hoverLayoutState.sourcePager) {
    hoverLayoutState.sourcePager.classList.remove('orig-view-mode');
    hoverLayoutState.sourcePager.classList.remove(
      'pdfjs-native-mode',
      'docrender-docx-continuous-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.classList.remove(
      'docrender-source-active',
      'docrender-websnapshot-active',
      'docrender-epub-foliate-active',
      'docrender-foliate-flow-active'
    );
    hoverLayoutState.sourcePager.innerHTML = '';
  }
  showDocumentChrome(false);

  // EPUB, MOBI, KF8/AZW3, FB2, and FBZ are all handled by Foliate.
  if (
    name.endsWith('.epub') ||
    name.endsWith('.mobi') ||
    name.endsWith('.azw3') ||
    name.endsWith('.fb2') ||
    name.endsWith('.fb2.zip') ||
    name.endsWith('.fbz')
  ) {
    documentState.currentFileType = 'epub';
    if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
    if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
    loadEpubWithEpubJs(file);
    return;
  }
  if (loadFileViaDocRender(file)) {
    return;
  }
  if (name.endsWith('.pdf')) {
    documentState.currentFileType = 'pdf';
    // PDFs stay entirely client-side: PDF.js renders the source pane and
    // CanonicalPdfExtractor builds the bottom-pane document from PDF.js text.
    if (documentState.origViewToggle) documentState.origViewToggle.style.display = 'none';
    if (orthographyState.pdfTextSourceGroup) orthographyState.pdfTextSourceGroup.style.display = 'none';
    documentState.isOriginalView = true;
    loadPdfInBrowser(file);
    return;
  }
  documentState.currentFileType = '';
  if (hoverLayoutState.statusText) hoverLayoutState.statusText.textContent = 'Unsupported file type.';
  if (hoverLayoutState.renderedText) {
    hoverLayoutState.renderedText.innerHTML =
      '<div class="reader-output-placeholder">Unsupported file type. Use PDF, ebook, TXT, DOCX, or frozen Chrome-extension HTML.</div>';
  }
}
export function initializeEntryForms() {
  if (hoverLayoutState.clearFileBtn) {
    hoverLayoutState.clearFileBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      clearLoadedFile();
    });
  }
  if (hoverLayoutState.clearRawTextBtn) {
    hoverLayoutState.clearRawTextBtn.addEventListener('click', function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      clearLoadedFile();
    });
  }
  hoverLayoutState.fileButton.addEventListener('click', function () {
    hoverLayoutState.fileInput.click();
  });
  hoverLayoutState.fileInput.addEventListener('change', function (ev) {
    var file = ev.target.files && ev.target.files[0];
    if (file) loadFile(file);
  });
  return true;
}
