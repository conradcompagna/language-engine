import { applyLanguageFormRules, getLanguageFormIndexTexts } from './entry-filters.mjs';
import { fuzzySearchState } from './fuzzy-search.state.mjs';
import { DictionaryEngine } from './model.mjs';
import { internMorphArray, lookupKey, lookupKeys } from './normalization.mjs';
import { normalizationState } from './normalization.state.mjs';
export function collectHydratedVariantTexts(entry) {
  var out = [];
  var seen = Object.create(null);
  function add(raw) {
    var text = String(raw || '').trim();
    if (!text || seen[text]) return;
    seen[text] = true;
    out.push(text);
  }
  var forms = entry && entry.forms && typeof entry.forms === 'object' ? entry.forms : {};
  var formKeys = ['kanji', 'readings', 'alt', 'hanja', 'hangeul', 'cjk'];
  for (var i = 0; i < formKeys.length; i++) {
    var values = forms[formKeys[i]];
    if (!Array.isArray(values)) continue;
    for (var j = 0; j < values.length; j++) add(values[j]);
  }
  var formsMeta = entry && entry.forms_meta && typeof entry.forms_meta === 'object' ? entry.forms_meta : {};
  var metaLists = ['kanji', 'readings'];
  for (var li = 0; li < metaLists.length; li++) {
    var rows = formsMeta[metaLists[li]];
    if (!Array.isArray(rows)) continue;
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      if (row && typeof row === 'object') add(row.form);
    }
  }
  var metaMaps = ['kanji_by_form', 'readings_by_form'];
  for (var mi = 0; mi < metaMaps.length; mi++) {
    var mapping = formsMeta[metaMaps[mi]];
    if (!mapping || typeof mapping !== 'object') continue;
    var mappingKeys = Object.keys(mapping);
    for (var mk = 0; mk < mappingKeys.length; mk++) add(mappingKeys[mk]);
  }
  return out;
}
export function collectHydratedFormRows(entry) {
  var out = [];
  var seen = Object.create(null);
  function add(formText, tagsStr, formRoman, displayText) {
    var text = String(formText || '').trim();
    var commentary = String(tagsStr || '').trim();
    var roman = String(formRoman || '').trim();
    var display = String(displayText || text).trim() || text;
    if (!text) return;
    var key = text + '\t' + commentary + '\t' + roman + '\t' + display;
    if (seen[key]) return;
    seen[key] = true;
    out.push({
      form_text: text,
      tags: commentary,
      form_roman: roman,
      display_text: display
    });
  }
  var forms = entry && entry.forms && typeof entry.forms === 'object' ? entry.forms : {};
  var rows = Array.isArray(forms.rows) ? forms.rows : [];
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    if (Array.isArray(row)) {
      add(row[0], row[1], row[2], row[0]);
    } else if (row && typeof row === 'object') {
      add(
        row.word || row.form || row.headword || row.form_text,
        row.commentary || row.tags,
        row.romanization || row.reading || row.form_roman,
        row.display_text || row.word || row.form || row.headword || row.form_text
      );
    }
  }
  var matchedForms = Array.isArray(entry && entry._matched_forms) ? entry._matched_forms : [];
  for (var j = 0; j < matchedForms.length; j++) {
    var matched = matchedForms[j];
    if (!matched || typeof matched !== 'object') continue;
    add(
      matched.form_text || matched.display_text,
      matched.tags,
      matched.form_roman,
      matched.display_text || matched.form_text
    );
  }
  return out;
}
export function initializeHydration() {
  DictionaryEngine.prototype._entry_to_fill = function (entry, text) {
    if (!this._compact_mode || !entry || !entry._winner_ref) {
      return fuzzySearchState._origEntryToFill.call(this, entry, text);
    }
    var surfaceText = String(text || '');
    return {
      text: surfaceText,
      head: surfaceText,
      roman: '',
      senses: normalizationState.EMPTY_ARRAY,
      pos: '',
      source: 'KAIKKI',
      _winner_ref: entry // full ref stub; extracted by client after hydration
    };
  };
  DictionaryEngine.prototype._index_hydrated_forms = function (entry, word, foldKey, byWord, formIndex) {
    var variantTexts = collectHydratedVariantTexts(entry);
    for (var vi = 0; vi < variantTexts.length; vi++) {
      var variant = variantTexts[vi];
      if (!variant || variant === word) continue;
      var variantKeys = lookupKeys(variant, this._lang_code);
      for (var vki = 0; vki < variantKeys.length; vki++) {
        var variantKey = variantKeys[vki];
        if (!variantKey || variantKey === foldKey) continue;
        if (!byWord[variantKey]) byWord[variantKey] = [];
        byWord[variantKey].push(entry);
      }
    }
    var formRows = collectHydratedFormRows(entry);
    for (var i = 0; i < formRows.length; i++) {
      var row = formRows[i];
      var formText = String(row.form_text || '').trim();
      if (!formText || formText === word) continue;
      var tagsStr = String(row.tags || '').trim();
      var formRoman = String(row.form_roman || '').trim();
      var tags = tagsStr ? tagsStr.split(';').filter(Boolean) : [];
      applyLanguageFormRules(this._lang_code, entry, formText, tags);
      var internedMorph = internMorphArray(tags);
      var formTexts = getLanguageFormIndexTexts(this._lang_code, formText, tags);
      for (var ft = 0; ft < formTexts.length; ft++) {
        var indexFormText = String(formTexts[ft] || '').trim();
        if (!indexFormText || indexFormText === word) continue;
        var formKeys = lookupKeys(indexFormText, this._lang_code);
        for (var fki = 0; fki < formKeys.length; fki++) {
          var formKey = formKeys[fki];
          if (!formKey || formKey === foldKey) continue;
          if (!formIndex[formKey]) formIndex[formKey] = [];
          var formHit = {
            lemma: word,
            form_text: indexFormText,
            morph: internedMorph,
            entry_ref: entry
          };
          var displayText = String(row.display_text || formText || indexFormText).trim();
          if (displayText && displayText !== indexFormText) formHit.form_display_text = displayText;
          if (formRoman) formHit.form_roman = formRoman;
          formIndex[formKey].push(formHit);
        }
      }
    }
  };

  /**
   * Legacy hydrated relookup substrate. The active hybrid flow no longer calls
   * this; keep it only for disconnected old paths.
   */
  DictionaryEngine.prototype.beginHydratedLookup = function (entryStore) {
    if (!this._compact_mode) return;
    this._compact_mode = false;
    this._saved_by_word = this._by_word;
    this._saved_form_index = this._form_index;
    var byWord = Object.create(null);
    var formIndex = Object.create(null);
    var keys = Object.keys(entryStore || {});
    for (var i = 0; i < keys.length; i++) {
      var entry = entryStore[keys[i]];
      if (!entry || typeof entry !== 'object') continue;
      var hw = String(entry.headword || entry.head || '').trim();
      if (!hw) continue;
      var foldKey = lookupKey(hw, this._lang_code);
      var nkeys = lookupKeys(hw, this._lang_code);
      for (var ki = 0; ki < nkeys.length; ki++) {
        var nk = nkeys[ki];
        if (!byWord[nk]) byWord[nk] = [];
        byWord[nk].push(entry);
      }
      // Also index by surface_form if different
      var sf = String(entry.surface_form || '').trim();
      if (sf && sf !== hw) {
        var sfkeys = lookupKeys(sf, this._lang_code);
        for (var si = 0; si < sfkeys.length; si++) {
          if (!byWord[sfkeys[si]]) byWord[sfkeys[si]] = [];
          byWord[sfkeys[si]].push(entry);
        }
      }
      this._index_hydrated_forms(entry, hw, foldKey, byWord, formIndex);
    }
    this._by_word = byWord;
    this._form_index = formIndex;
  };
  DictionaryEngine.prototype.endHydratedLookup = function () {
    if (this._saved_by_word) {
      this._by_word = this._saved_by_word;
      this._form_index = this._saved_form_index;
      this._saved_by_word = null;
      this._saved_form_index = null;
      this._compact_mode = true;
    }
  };
  window.DictionaryEngine = DictionaryEngine;
  return true;
}
