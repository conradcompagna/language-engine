import {
  applyLanguageFormRules,
  getLanguageFormIndexTexts,
  isKoreanHanjaDropdownEntry,
  splitMorphTags
} from './entry-filters.mjs';
import { DictionaryEngine, ensureHydrated, entryIdentityKey, hydrateAll, parseTsvRow } from './model.mjs';
import { annotateLookupEntries, internMorphArray, lookupKey, lookupKeys } from './normalization.mjs';
import { normalizationState } from './normalization.state.mjs';
export function initializeIndexLoading() {
  DictionaryEngine.prototype.load_tsv_entries = function (rows) {
    return this.loadFromRows(rows || []);
  };

  /** Load a single pre-parsed TSV row — avoids array allocation in streaming path. */
  DictionaryEngine.prototype._loadOneRow = function (row) {
    var entry = parseTsvRow(row);
    if (!entry) return false;
    var word = entry.headword;
    var foldKey = lookupKey(word, this._lang_code);
    if (!foldKey) return false;
    if (!this._by_word[foldKey]) this._by_word[foldKey] = [];
    this._by_word[foldKey].push(entry);
    this._index_tsv_forms(entry, word, foldKey);
    return true;
  };
  DictionaryEngine.prototype._index_tsv_forms = function (entry, word, foldKey) {
    var formsJson = entry._forms_json;
    delete entry._forms_json;
    var forms = [];
    if (formsJson) {
      try {
        var parsed = JSON.parse(formsJson);
        if (Array.isArray(parsed)) forms = parsed;
      } catch (_e) {}
    }
    for (var i = 0; i < forms.length; i++) {
      var f = forms[i];
      if (!Array.isArray(f) || f.length < 2) continue;
      var formText = String(f[0] || '').trim();
      if (!formText || formText === word) continue;
      var tagsStr = String(f[1] || '');
      var formRoman = String(f.length >= 3 ? f[2] || '' : '').trim();
      var tags = tagsStr ? tagsStr.split(';').filter(Boolean) : [];
      applyLanguageFormRules(this._lang_code, entry, formText, tags);
      var internedMorph = internMorphArray(tags);
      var formTexts = getLanguageFormIndexTexts(this._lang_code, formText, tags);
      for (var ft = 0; ft < formTexts.length; ft++) {
        var indexFormText = String(formTexts[ft] || '').trim();
        if (!indexFormText || indexFormText === word) continue;
        var formKey = lookupKey(indexFormText, this._lang_code);
        if (!formKey || formKey === foldKey) continue;
        if (!this._form_index[formKey]) this._form_index[formKey] = [];
        // Compacted form hit: dropped entry_identity (use entry_ref object identity),
        // dropped lemma_key (derive from entry_ref.headword on demand),
        // dropped form_display_text when identical to form_text,
        // dropped form_roman when empty.
        var formHit = {
          lemma: word,
          form_text: indexFormText,
          morph: internedMorph,
          entry_ref: entry
        };
        if (formText !== indexFormText) formHit.form_display_text = formText;
        if (formRoman) formHit.form_roman = formRoman;
        this._form_index[formKey].push(formHit);
      }
    }

    // Korean infinitive stem indexing:
    // add "<lemma without final -da>" as a synthetic form with Morph: stem.
    var lang = String(this._lang_code || '')
      .trim()
      .toLowerCase();
    var isKorean = lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0;
    var posRaw = String((entry && entry.pos_raw) || '')
      .trim()
      .toLowerCase();
    var canStem = posRaw === 'verb' || posRaw === 'adj';
    var endsWithKoreanDa = word.length > 1 && word.charCodeAt(word.length - 1) === 0xb2e4;
    if (isKorean && canStem && endsWithKoreanDa) {
      var stemText = String(word.slice(0, -1) || '').trim();
      if (stemText && stemText !== word) {
        var stemKey = lookupKey(stemText, this._lang_code);
        if (stemKey && stemKey !== foldKey) {
          if (!this._form_index[stemKey]) this._form_index[stemKey] = [];
          this._form_index[stemKey].push({
            lemma: word,
            form_text: stemText,
            morph: internMorphArray(['stem']),
            entry_ref: entry
          });
        }
      }
    }
  };
  DictionaryEngine.prototype.lookup = function (word) {
    var entries = this.lookup_all(word);
    return entries.length ? entries[0] : null;
  };
  DictionaryEngine.prototype._split_matchable_display_entries = function (entries) {
    var src = Array.isArray(entries) ? entries : [];
    if (!src.length)
      return {
        matchable: [],
        display_only: []
      };
    var lang = String(this._lang_code || '')
      .trim()
      .toLowerCase();
    if (!(lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0)) {
      return {
        matchable: src.slice(),
        display_only: []
      };
    }
    var matchable = [];
    var displayOnly = [];
    for (var i = 0; i < src.length; i++) {
      if (isKoreanHanjaDropdownEntry(src[i])) displayOnly.push(src[i]);
      else matchable.push(src[i]);
    }
    return {
      matchable: matchable,
      display_only: displayOnly
    };
  };
  DictionaryEngine.prototype._lookup_all_raw = function (word) {
    var keys = lookupKeys(word, this._lang_code);
    var direct = [];
    var seenDirect = Object.create(null);
    for (var ki = 0; ki < keys.length; ki++) {
      var bucket = this._by_word[keys[ki]];
      if (!bucket) continue;
      for (var bi = 0; bi < bucket.length; bi++) {
        var eid = keys[ki] + ':' + bi;
        if (seenDirect[eid]) continue;
        seenDirect[eid] = true;
        direct.push(bucket[bi]);
      }
    }
    var formEntries = this.lookup_via_forms(word);
    if (!direct.length) {
      if (!formEntries.length) return [];
      hydrateAll(formEntries);
      for (var _fti = 0; _fti < formEntries.length; _fti++) {
        if (formEntries[_fti]) formEntries[_fti]._match_source = 'form';
      }
      return annotateLookupEntries(formEntries, word, this._lang_code);
    }
    hydrateAll(direct);
    for (var _dti = 0; _dti < direct.length; _dti++) {
      if (direct[_dti]) direct[_dti]._match_source = 'headword';
    }
    if (!formEntries.length) return annotateLookupEntries(direct, word, this._lang_code);
    var merged = direct.slice();
    var seenKeys = Object.create(null);
    for (var mi = 0; mi < merged.length; mi++) {
      seenKeys[entryIdentityKey(merged[mi])] = true;
    }
    for (var fi = 0; fi < formEntries.length; fi++) {
      ensureHydrated(formEntries[fi]);
      var k = entryIdentityKey(formEntries[fi]);
      if (seenKeys[k]) continue;
      seenKeys[k] = true;
      formEntries[fi]._match_source = 'form';
      merged.push(formEntries[fi]);
    }
    return annotateLookupEntries(merged, word, this._lang_code);
  };
  DictionaryEngine.prototype.lookup_all = function (word) {
    return this._lookup_all_raw(word);
  };
  DictionaryEngine.prototype.lookupAll = function (word) {
    return this.lookup_all(word);
  };
  DictionaryEngine.prototype.lookup_display_only = function (word) {
    void word;
    return [];
  };
  DictionaryEngine.prototype.lookupDisplayOnly = function (word) {
    return this.lookup_display_only(word);
  };
  DictionaryEngine.prototype.lookup_via_forms = function (word) {
    function hasMorphTag(rawMorph, tagText) {
      var target = String(tagText || '')
        .trim()
        .toLowerCase();
      if (!target) return false;
      var src = Array.isArray(rawMorph) ? rawMorph : rawMorph ? [rawMorph] : [];
      for (var i = 0; i < src.length; i++) {
        var one = String(src[i] || '')
          .trim()
          .toLowerCase();
        if (!one) continue;
        if (one === target) return true;
      }
      return false;
    }
    var keys = lookupKeys(word, this._lang_code);
    var formHits = [];
    for (var ki = 0; ki < keys.length; ki++) {
      var hits = this._form_index[keys[ki]];
      if (!hits) continue;
      for (var h = 0; h < hits.length; h++) formHits.push(hits[h]);
    }
    if (!formHits.length) return [];
    // Use a tag-on-object approach for dedup by entry_ref identity
    // (avoids building entryIdentityKey strings for every form hit).
    var dedupTag = '_fld_' + Math.random().toString(36).slice(2, 8);
    var taggedObjects = [];
    var resultsByIdx = [];
    var resultCount = 0;
    function registerSurfaceForm(rec, rawSurface) {
      if (!rec || !rec.entry) return;
      var surface = String(rawSurface || '').trim();
      if (!surface) return;
      if (!rec.surfaceSeen[surface]) {
        rec.surfaceSeen[surface] = true;
        rec.surfaceForms.push(surface);
      }
      // Prefer the queried surface if present; otherwise keep first seen.
      if (!rec.entry.surface_form || surface === String(word || '').trim()) {
        rec.entry.surface_form = surface;
      }
    }
    for (var i = 0; i < formHits.length; i++) {
      var hit = formHits[i];
      var lemma = hit.lemma || '';
      var morph = hit.morph;
      var formRoman = String(hit.form_roman || '').trim();
      var formDisplayText = String(hit.form_display_text || hit.form_text || '').trim();
      var isEumhun = hasMorphTag(morph, 'eumhun');
      var baseEntries = null;
      if (hit.entry_ref && typeof hit.entry_ref === 'object') {
        baseEntries = [hit.entry_ref];
      } else {
        // Strict fallback: only resolve to exact lemma headword rows, never to
        // every entry sharing the normalized lookup key.
        var lemmaKey = lookupKey(lemma || '', this._lang_code);
        var bucket = this._by_word[lemmaKey] || [];
        var exactLemma = String(lemma || '');
        baseEntries = [];
        for (var bi = 0; bi < bucket.length; bi++) {
          var candidate = bucket[bi] || {};
          if (String(candidate.headword || '') === exactLemma) {
            baseEntries.push(candidate);
          }
        }
      }
      if (!baseEntries) continue;
      for (var b = 0; b < baseEntries.length; b++) {
        var base = baseEntries[b];
        if (!base || typeof base !== 'object') continue;
        // Hydrate entry before cloning properties
        ensureHydrated(base);
        // Dedup by object identity using tag-on-object pattern
        var recIdx = base[dedupTag];
        var morphKey = '';
        if (Array.isArray(morph)) {
          var parts = [];
          for (var mi = 0; mi < morph.length; mi++) {
            var part = String(morph[mi] || '').trim();
            if (part) parts.push(part);
          }
          morphKey = parts.join(';');
        } else {
          morphKey = String(morph || '').trim();
        }
        var rec;
        if (recIdx === undefined) {
          var enriched = {};
          for (var k in base) {
            if (Object.prototype.hasOwnProperty.call(base, k) && k !== dedupTag) enriched[k] = base[k];
          }
          if (lemma) enriched.morph_base = lemma;
          // Seed morph_info from any existing tags on the base entry, then
          // form-hit tags will be appended below.  Without this the base
          // entry's own morph data (e.g. the morph tags on 不要 itself) was
          // silently wiped when 不要 appeared only via the forms index.
          var _existingMorphTags = splitMorphTags(base.morph_info);
          enriched.morph_info = _existingMorphTags.slice();
          var _initMorphSeen = Object.create(null);
          for (var _emi = 0; _emi < _existingMorphTags.length; _emi++) {
            _initMorphSeen[_existingMorphTags[_emi]] = true;
          }
          rec = {
            entry: enriched,
            morphSeen: _initMorphSeen,
            form_roman: formRoman,
            form_display_text: formDisplayText,
            has_eumhun: isEumhun,
            surfaceSeen: Object.create(null),
            surfaceForms: []
          };
          base[dedupTag] = resultCount;
          taggedObjects.push(base);
          resultsByIdx.push(rec);
          resultCount++;
        } else {
          rec = resultsByIdx[recIdx];
          if (formRoman) {
            // Prefer fuller eumhun readings when several form hits map to one entry.
            if (
              !rec.form_roman ||
              ((rec.has_eumhun || isEumhun) && formRoman.length > String(rec.form_roman || '').length)
            ) {
              rec.form_roman = formRoman;
            }
          }
          if (!rec.form_display_text && formDisplayText) rec.form_display_text = formDisplayText;
          if (isEumhun) rec.has_eumhun = true;
          if (!rec.entry.morph_base && lemma) rec.entry.morph_base = lemma;
        }
        registerSurfaceForm(rec, hit.form_display_text || hit.form_text || word || '');
        if (morphKey && !rec.morphSeen[morphKey]) {
          rec.morphSeen[morphKey] = true;
          rec.entry.morph_info.push(morphKey);
        }
      }
    }
    // Cleanup dedup tags
    for (var ci = 0; ci < taggedObjects.length; ci++) {
      delete taggedObjects[ci][dedupTag];
    }
    var results = [];
    for (var ri = 0; ri < resultsByIdx.length; ri++) {
      var recOut = resultsByIdx[ri];
      var row = recOut.entry;
      if (recOut.form_roman) {
        row.reading = recOut.form_roman;
      } else if (recOut.has_eumhun && recOut.form_display_text) {
        // Keep the full eumhun reading text for display while lookup still uses
        // the indexed final character.
        row.reading = recOut.form_display_text;
      }
      if (!row.morph_info || !row.morph_info.length) delete row.morph_info;
      if (recOut.surfaceForms && recOut.surfaceForms.length > 1) {
        row.surface_forms = recOut.surfaceForms.slice();
      }
      results.push(row);
    }
    return annotateLookupEntries(results, word, this._lang_code);
  };
  DictionaryEngine.prototype.lookupViaForms = function (word) {
    return this.lookup_via_forms(word);
  };
  DictionaryEngine.prototype._filter_entries_for_greedy = function (entries) {
    var src = Array.isArray(entries) ? entries : [];
    if (!src.length) return [];
    return src.slice();
  };
  DictionaryEngine.prototype._entry_to_fill = function (entry, text) {
    ensureHydrated(entry);
    var surfaceText = String(text || '');
    var lemmaHead = String(entry.headword || '');
    var displayHead = surfaceText || lemmaHead;
    var fill = {
      text: surfaceText,
      head: displayHead,
      headword: lemmaHead || displayHead,
      roman: entry.reading || '',
      reading: entry.reading || '',
      senses: entry.senses || normalizationState.EMPTY_ARRAY,
      pos: entry.pos || '',
      pos_raw: entry.pos_raw || entry.pos || '',
      source: entry._source || entry.source || 'KAIKKI',
      etymology: entry.etymology || '',
      senses_full: entry.senses_full || normalizationState.EMPTY_ARRAY,
      ipa_variants: entry.ipa_variants || normalizationState.EMPTY_ARRAY
    };
    var passthroughKeys = [
      'entry_id',
      '_source',
      '_glosses_raw',
      '_forms_raw',
      '_forms_json',
      '_commentary',
      '_lemma',
      'forms',
      'forms_meta',
      'spelling_header'
    ];
    for (var pk = 0; pk < passthroughKeys.length; pk++) {
      var key = passthroughKeys[pk];
      if (entry[key]) fill[key] = entry[key];
    }
    if (entry.morph_info) fill.morph_info = entry.morph_info;
    if (entry.morph_base) fill.morph_base = entry.morph_base;
    if (entry.grammar) fill.grammar = entry.grammar;
    if (lemmaHead && lemmaHead !== displayHead) {
      fill.surface_form = displayHead;
      fill.lemma_form = lemmaHead;
      if (!fill.morph_base) fill.morph_base = lemmaHead;
    }
    return fill;
  };
  return true;
}
