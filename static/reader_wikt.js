(function() {
  // UNIVERSAL WIKTIONARY frontend adapter.
  // Shared by all languages routed through wiktionary_general pipeline.

  var WIKT_LANGS = {
    'zh': true, 'zh-hant': true, 'chinese': true, 'traditional-chinese': true,
    'lzh': true, 'classical': true, 'classical-chinese': true,
    'ja': true, 'japanese': true,
    'ko': true, 'korean': true,
    'vi': true, 'vietnamese': true,
    'ar': true, 'arabic': true,
    'fa': true, 'persian': true,
    'hi': true, 'hindi': true,
    'id': true, 'indonesian': true,
    'ta': true, 'tamil': true,
    'th': true, 'thai': true,
    'tr': true, 'turkish': true,
    'ur': true, 'urdu': true,
    'sa': true, 'sanskrit': true,
    'ga': true, 'irish': true,
    'ang': true, 'oldenglish': true, 'old-english': true, 'old english': true,
    'fr': true, 'french': true,
    'it': true, 'italian': true,
    'ru': true, 'russian': true,
    'es': true, 'spanish': true,
    'de': true, 'german': true,
    'nl': true, 'dutch': true,
    'pt': true, 'portuguese': true,
    'la': true, 'latin': true,
    'el': true, 'greek': true,
    'hy': true, 'armenian': true,
    'grc': true, 'ancient-greek': true, 'ancientgreek': true,
    'he': true, 'hebrew': true,
    'hbo': true, 'ancient-hebrew': true, 'ancienthebrew': true, 'biblical-hebrew': true,
    'tl': true, 'tagalog': true, 'filipino': true,
    'sw': true, 'swahili': true, 'kiswahili': true,
    'bn': true, 'bengali': true, 'bangla': true,
    'pa': true, 'punjabi': true, 'panjabi': true
  };

  function isWiktLanguage(rawLang) {
    var lang = String(rawLang || '').toLowerCase();
    return !!WIKT_LANGS[lang];
  }

  // ---- Entry store resolver for ref-key based payload ----
  var _entryStoreRef = null;
  var _entryRefToKeyRef = null;
  var _entryFormOverlaysRef = null;
  function cloneResolvedEntry(entry) {
    var src = (entry && typeof entry === 'object') ? entry : {};
    var out = {};
    for (var key in src) {
      if (!Object.prototype.hasOwnProperty.call(src, key)) continue;
      out[key] = src[key];
    }
    if (Array.isArray(src.morph_info)) out.morph_info = src.morph_info.slice();
    if (Array.isArray(src._matched_forms)) {
      out._matched_forms = src._matched_forms.map(function(row) {
        var raw = (row && typeof row === 'object') ? row : {};
        var copy = {};
        for (var rowKey in raw) {
          if (!Object.prototype.hasOwnProperty.call(raw, rowKey)) continue;
          copy[rowKey] = Array.isArray(raw[rowKey]) ? raw[rowKey].slice() : raw[rowKey];
        }
        return copy;
      });
    }
    return out;
  }
  function applyResolvedFormOverlay(baseEntry, refKey, overlay) {
    var ov = (overlay && typeof overlay === 'object') ? overlay : null;
    if (!ov) return baseEntry;
    var resolved = cloneResolvedEntry(baseEntry);
    resolved.ref_key = String(refKey || resolved.ref_key || '').trim();
    if (ov.display_headword) {
      resolved.display_headword = ov.display_headword;
      resolved.headword = ov.display_headword;
      resolved.surface_form = ov.display_headword;
      resolved.head = ov.display_headword;
    }
    if (ov.display_reading !== undefined) {
      resolved.display_reading = ov.display_reading;
      resolved.reading = ov.display_reading;
      resolved.roman = ov.display_reading;
    }
    if (ov.match_kind) resolved.match_kind = String(ov.match_kind || '').trim().toLowerCase();
    if (ov._match_kind) resolved._match_kind = String(ov._match_kind || '').trim().toLowerCase();
    else if (resolved.match_kind) resolved._match_kind = resolved.match_kind;
    if (ov._match_source) resolved._match_source = String(ov._match_source || '').trim().toLowerCase();
    else if (resolved._match_kind) resolved._match_source = resolved._match_kind;
    if (ov.morph_info) resolved.morph_info = Array.isArray(ov.morph_info) ? ov.morph_info.slice() : [String(ov.morph_info || '')];
    if (ov.morph_base) resolved.morph_base = String(ov.morph_base || '').trim();
    if (ov.is_alternate_match !== undefined) resolved.is_alternate_match = !!ov.is_alternate_match;
    if (ov.matched_form) {
      resolved.matched_form = ov.matched_form;
      resolved._matched_forms = [ov.matched_form];
    }
    if (ov._storage_form_row_id) resolved._storage_form_row_id = ov._storage_form_row_id;
    return resolved;
  }
  function setEntryStore(store, refToKey, formOverlays) {
    if (!_entryStoreRef || typeof _entryStoreRef !== 'object') {
      _entryStoreRef = Object.create(null);
    }
    if (!_entryRefToKeyRef || typeof _entryRefToKeyRef !== 'object') {
      _entryRefToKeyRef = Object.create(null);
    }
    if (!_entryFormOverlaysRef || typeof _entryFormOverlaysRef !== 'object') {
      _entryFormOverlaysRef = Object.create(null);
    }
    if (store && typeof store === 'object') {
      var keys = Object.keys(store);
      for (var i = 0; i < keys.length; i++) {
        _entryStoreRef[keys[i]] = store[keys[i]];
      }
    }
    if (refToKey && typeof refToKey === 'object') {
      var refKeys = Object.keys(refToKey);
      for (var j = 0; j < refKeys.length; j++) {
        _entryRefToKeyRef[refKeys[j]] = refToKey[refKeys[j]];
      }
    }
    if (formOverlays && typeof formOverlays === 'object') {
      var overlayKeys = Object.keys(formOverlays);
      for (var k = 0; k < overlayKeys.length; k++) {
        _entryFormOverlaysRef[overlayKeys[k]] = formOverlays[overlayKeys[k]];
      }
    }
  }
  function resolveEntryRef(refOrObj) {
    if (!refOrObj) return null;
    if (typeof refOrObj === 'string') {
      var direct = (_entryStoreRef && _entryStoreRef[refOrObj]) || null;
      var baseKey = direct ? refOrObj : ((_entryRefToKeyRef && _entryRefToKeyRef[refOrObj]) || refOrObj);
      var baseEntry = direct || ((_entryStoreRef && _entryStoreRef[baseKey]) || null);
      if (!baseEntry) return null;
      var overlay = (_entryFormOverlaysRef && _entryFormOverlaysRef[refOrObj]) || null;
      return overlay ? applyResolvedFormOverlay(baseEntry, refOrObj, overlay) : baseEntry;
    }
    return refOrObj;
  }
  function resolveEntryRefs(arr) {
    if (!Array.isArray(arr)) return [];
    var out = [];
    for (var i = 0; i < arr.length; i++) {
      var resolved = resolveEntryRef(arr[i]);
      if (resolved) out.push(resolved);
    }
    return out;
  }
  // Expose so reader.js can set the store
  window._wiktSetEntryStore = setEntryStore;

  function esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function isKrdictSource(rawSource) {
    var source = String(rawSource || '').trim().toLowerCase();
    return source === 'krdict' || source === 'ko-krdict' || /(?:^|-)krdict$/.test(source);
  }

  function splitKrdictGloss(glossText, rawSource) {
    if (!isKrdictSource(rawSource)) return null;
    var text = String(glossText || '').trim();
    if (!text) return null;
    var idx = text.indexOf(' - ');
    if (idx <= 0) return null;
    var lead = text.slice(0, idx).trim();
    var body = text.slice(idx + 3).trim();
    if (!lead || !body) return null;
    return { lead: lead, body: body };
  }

  function renderGlossText(glossText, options) {
    var text = String(glossText || '');
    var opts = options || {};
    var split = splitKrdictGloss(text, opts.source);
    if (!split) return esc(text);
    return '<span class="krdict-gloss-lead">' + esc(split.lead) + '</span>' +
      '<span class="krdict-gloss-divider" aria-hidden="true">&#183;</span>' +
      '<span class="krdict-gloss-body">' + esc(split.body) + '</span>';
  }
  function traceUiRenderDebug(type, details) {
    var api = window.ReaderUiDebug;
    if (!api || typeof api.trace !== 'function') return;
    api.trace(type, details, { scope: 'panel-wikt' });
  }

  function wrapSenseHeadInline(mainHtml, entryMetaHtml) {
    var main = String(mainHtml || '');
    var meta = String(entryMetaHtml || '');
    if (!main) return '';
    if (!meta) return main;
    // Entry meta (edit button) is a sibling of main, not nested inside
    return '<span class="sense-head-inline">' + main + meta + '</span>';
  }

  // Row-level metadata: each entry row gets its own badge via _buildEntryMetaForRow
  // (side panel path) or inherits entryMetaHtml directly (popup path). No
  // representative-entry selection — every row is treated identically.

  // ---------------------------------------------------------------------------
  // Headword forms
  // ---------------------------------------------------------------------------

  function getSurfaceLemmaInfo(entry, fallbackHead) {
    var surface = '';
    if (entry && entry.text) surface = String(entry.text);
    if (!surface) surface = String(fallbackHead || '');
    if (!surface && entry && entry.surface_form) surface = String(entry.surface_form);
    if (!surface) surface = String((entry && (entry.head || '')) || '');
    return { surface: surface };
  }

  function getHeadwordForms(entry, fallbackHead, rawLang) {
    if (!isWiktLanguage(rawLang)) return null;

    var fallback = String(fallbackHead || '');
    var headword = '';
    if (entry && entry.text) headword = String(entry.text);
    if (!headword) headword = fallback;
    if (!headword && entry && entry.surface_form) headword = String(entry.surface_form);
    if (!headword && entry && entry.head) headword = String(entry.head);

    var forms = [];
    if (headword) forms.push(headword);
    if (!forms.length && fallback) forms.push(fallback);

    return {
      headword: headword,
      forms: forms
    };
  }

  function getPanelHeadwordRows(entry, fallbackHead, rawLang) {
    if (!isWiktLanguage(rawLang)) return null;
    var top = getSurfaceLemmaInfo(entry, fallbackHead);
    var rows = [];
    var seen = Object.create(null);
    function pushRow(raw) {
      var txt = String(raw || '');
      if (!txt || seen[txt]) return;
      seen[txt] = true;
      rows.push(txt);
    }
    pushRow(top.surface);
    if (!rows.length) {
      var info = getHeadwordForms(entry, fallbackHead, rawLang) || {};
      pushRow(info.headword || fallbackHead || '');
    }
    return rows.length ? rows : [''];
  }

  function getPopupHeadwordForms(entry, fallbackHead, rawLang) {
    if (!isWiktLanguage(rawLang)) return null;
    var rows = getPanelHeadwordRows(entry, fallbackHead, rawLang) || [];
    return rows.length ? rows : null;
  }

  function formatPopupHeadwordHtml(entry, fallbackHead, rawLang, escapeHtmlFn) {
    if (!isWiktLanguage(rawLang)) return '';
    var escape = (typeof escapeHtmlFn === 'function')
      ? escapeHtmlFn
      : function(v) { return String(v || ''); };
    var top = getSurfaceLemmaInfo(entry, fallbackHead);
    if (!top.surface) return '';
    return escape(top.surface);
  }

  function buildPanelHeadwordTokenHtml(formText, rawLang, escapeHtmlFn, options) {
    if (!isWiktLanguage(rawLang)) return '';
    var escape = (typeof escapeHtmlFn === 'function')
      ? escapeHtmlFn
      : function(v) { return String(v || ''); };
    var opts = options || {};
    var text = String(formText || '');
    if (!text) return '';
    var classNames = ['headword-component', 'panel-token', 'panel-headword-token'];
    var roleClass = String(opts._panelHeadRole || '').trim();
    if (roleClass) classNames.push('panel-' + roleClass + '-token');
    if (opts.extraClass) classNames.push(String(opts.extraClass || '').trim());
    var attrs = 'class="' + classNames.join(' ') + '" data-seg="' + escape(text) + '" data-hover-mode="disabled"';
    if (opts._panelSurfacePending) {
      attrs += ' data-panel-surface-seg="' + escape(text) + '"';
      if (roleClass) attrs += ' data-panel-head-role="' + escape(roleClass) + '"';
    }
    traceUiRenderDebug('wikt_plain_headword_span', {
      text: text,
      role: roleClass,
      extra_class: String(opts.extraClass || ''),
      pending_surface: !!opts._panelSurfacePending
    });
    return '<span ' + attrs + '>' + escape(text) + '</span>';
  }

  function buildInspectableHeadwordSpanHtml(formText, rawLang, escapeHtmlFn, headDecompByForm, options) {
    void headDecompByForm;
    return buildPanelHeadwordTokenHtml(formText, rawLang, escapeHtmlFn, options);
  }

  function mergePanelEntryFields(targetEntry, parentEntry, rawLang) {
    if (!isWiktLanguage(rawLang)) return;
    if (!targetEntry || !parentEntry) return;
    var targetMatchKind = String(targetEntry.match_kind || targetEntry._match_kind || '').trim().toLowerCase();
    if (targetMatchKind === 'form') return;
    if (!targetEntry.reading && parentEntry.reading) targetEntry.reading = parentEntry.reading;
  }

  // Panel segmentation is now fully dictionary-validated for all languages.
  // Every word in gloss text is looked up via the API; only words with actual
  // dictionary entries (not UNKNOWN) become hoverable.  No per-language script
  // regex is needed — adding a new language to WIKT_LANGS is sufficient.

  function getPanelSegmentationRegex(rawLang) {
    // Kept for backward compatibility with any callers.
    // Returns null for all languages — segmentation is now dictionary-validated.
    return null;
  }

  function shouldSegmentPanelTextPart(rawText, rawLang) {
    // All languages now use dictionary-validated segmentation.
    if (!isWiktLanguage(rawLang)) return false;
    var txt = String(rawText || '');
    return !!txt.trim();
  }

  function formatPopupRoman(rawText, rawLang) {
    return String(rawText || '');
  }

  function getG2PComponentViewModel(component, helpers, rawLang) {
    return null;
  }

  function isKoreanLanguage(rawLang) {
    var lang = String(rawLang || '').toLowerCase();
    return lang === 'ko' || lang === 'korean' || lang.indexOf('ko-') === 0;
  }

  function splitMorphTags(rawMorph) {
    var out = [];
    var seen = Object.create(null);
    var src = Array.isArray(rawMorph) ? rawMorph : (rawMorph ? [rawMorph] : []);
    for (var i = 0; i < src.length; i++) {
      var chunk = String(src[i] == null ? '' : src[i]).toLowerCase();
      if (!chunk) continue;
      var parts = chunk.split(/[;|,]/);
      for (var j = 0; j < parts.length; j++) {
        var tag = String(parts[j] || '').trim();
        if (!tag || seen[tag]) continue;
        seen[tag] = true;
        out.push(tag);
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // CANONICAL WIKTIONARY DICTIONARY TEMPLATE
  // ---------------------------------------------------------------------------

  function renderWiktDictEntry(entry, fallbackHead, options) {
    var opts = options || {};
    var renderLang = String(opts._lang || '').toLowerCase();
    var e = entry || {};
    var head = String(e.head || fallbackHead || '');
    var bannerHead = String(e.text || fallbackHead || e.surface_form || e.head || '');
    var isUnk = !e.source || e.source === 'UNKNOWN' || e.source === 'PUNCT';

    var senseKey = (opts.sensesKey != null) ? String(opts.sensesKey) : 'senses';
    var hasSenseKey = Array.isArray(e[senseKey]) && e[senseKey].length > 0;
    var flatSenses = hasSenseKey ? e[senseKey] : (Array.isArray(e.senses) ? e.senses : []);
    var sensesFull = Array.isArray(e.senses_full) ? e.senses_full : [];
    var buildEntryMetaForRow = (typeof opts._buildEntryMetaForRow === 'function')
      ? opts._buildEntryMetaForRow
      : null;
    var selfEntryMetaHtml = buildEntryMetaForRow
      ? String(buildEntryMetaForRow(e, head, { isAtomicEntry: true }) || '')
      : '';
    var headDecompByForm = opts._headDecompByForm || null;

    var html = '';
    traceUiRenderDebug('wikt_render_entry', {
      head: head,
      is_unknown: !!isUnk,
      sense_key: senseKey,
      has_entry_groups: Array.isArray(e.entry_groups) && e.entry_groups.length > 0,
      has_hover_entry_groups: Array.isArray(e.entry_groups_hover) && e.entry_groups_hover.length > 0,
      flat_sense_count: flatSenses.length,
      full_sense_count: sensesFull.length
    });

    // 1. HEADWORD
    if (opts.showHead !== false) {
      if (opts.headHtml != null) {
        html += String(opts.headHtml);
      } else {
        var buildTopSurfaceHtml = (typeof opts._buildTopSurfaceHeadlineHtml === 'function')
          ? opts._buildTopSurfaceHeadlineHtml
          : null;
        var buildSurfaceHtml = (typeof opts._buildPanelSurfaceHeadlineHtml === 'function')
          ? opts._buildPanelSurfaceHeadlineHtml
          : null;
        var headHtml = buildTopSurfaceHtml
          ? buildTopSurfaceHtml(e, bannerHead, 'surface')
          : (buildSurfaceHtml
          ? buildSurfaceHtml(bannerHead, 'surface')
          : buildPanelHeadwordTokenHtml(bannerHead, renderLang, esc, { _panelHeadRole: 'surface' }));
        void headHtml;
        // Top-level surface-slice headline removed; per-entry headword below is the visible headline.
      }
    }

    if (isUnk) {
      var unknownLabel = String(e.text || fallbackHead || e.surface_form || head || '').trim();
      if (unknownLabel && html.indexOf(esc(unknownLabel)) < 0) {
        var unknownHeadHtml = buildPanelHeadwordTokenHtml(unknownLabel, renderLang, esc, {
          _panelHeadRole: 'surface'
        }) || esc(unknownLabel);
        html += '<div class="popup-headline popup-headline-inline-flow">' + unknownHeadHtml + '</div>';
      }
      return { html: html, isUnknown: true, sensesCount: 0, head: head };
    }

    // 2. ENTRY GROUPS (by POS)
    var useFiltered = (senseKey === 'senses_hover') &&
                      Array.isArray(e.entry_groups_hover) && e.entry_groups_hover.length > 0;
    var entryGroups = useFiltered
        ? e.entry_groups_hover
        : (Array.isArray(e.entry_groups) ? e.entry_groups : []);
    var otherEntryGroups = useFiltered
        ? (Array.isArray(e.entry_groups_other) ? e.entry_groups_other : [])
        : [];
    var sensesCount = 0;

    var groups = entryGroups.length ? entryGroups : null;
    if (!groups || !groups.length) {
      var atomicGroups = buildAtomicEntryGroups(getAtomicEntriesForSenseKey(e, senseKey), head);
      if (atomicGroups.length) groups = atomicGroups;
    }
    if ((!otherEntryGroups || !otherEntryGroups.length) && senseKey === 'senses_hover') {
      otherEntryGroups = buildAtomicEntryGroups(getAtomicEntriesForSenseKey(e, 'senses_hover_other'), head);
    }
    if (!groups && sensesFull.length) {
      groups = [{
        pos: e.pos || '',
        pos_raw: e.pos_raw || '',
        reading: e.reading || '',
        senses: sensesFull
      }];
    }

    if (groups && groups.length) {
      html += renderEntryGroupsHtml(groups, head, Object.assign({}, opts, {
        _headDecompByForm: headDecompByForm
      }));
      for (var gi = 0; gi < groups.length; gi++) {
        var grpSenses = Array.isArray((groups[gi] || {}).senses) ? groups[gi].senses : [];
        sensesCount += grpSenses.length;
      }
    } else if (flatSenses.length) {
      if (selfEntryMetaHtml) {
        html += renderEntryMetaHeadHtml(e, head, selfEntryMetaHtml, headDecompByForm, renderLang, opts);
      }
      var morphHtml = renderMorphBlock(e, head, opts);
      if (morphHtml) {
        html += morphHtml;
      }
      html += renderSensesFlat(flatSenses, { source: e.source || '' });
      sensesCount = flatSenses.length;
    } else {
      if (selfEntryMetaHtml) {
        html += renderEntryMetaHeadHtml(e, head, selfEntryMetaHtml, headDecompByForm, renderLang, opts);
      }
      var morphHtmlOnly = renderMorphBlock(e, head, opts);
      if (morphHtmlOnly) {
        html += morphHtmlOnly;
      }
    }

    // 3. OTHER DEFINITIONS EXPANDER
    var hasOtherGroups = otherEntryGroups && otherEntryGroups.length > 0;
    var altSenses = Array.isArray(e.senses_hover_other) ? e.senses_hover_other : [];
    var showFlatAltSenses = (!groups || !groups.length) && altSenses.length > 0;
    var hasAltPayload = hasOtherGroups || showFlatAltSenses;
    var hasFilteredAlternates = !isUnk && hasAltPayload && (!!e.hover_has_alt_senses || useFiltered);
    if (opts.showFilteredNote && hasFilteredAlternates) {
      html += '<span class="popup-alt-senses-signal" hidden aria-hidden="true"></span>';
    }
    if (opts.showOtherDefsDropdown && (hasOtherGroups || showFlatAltSenses)) {
      html += '<details class="panel-filtered-expander">';
      html += '<summary class="panel-filtered-expander-bar">';
      html += '<span class="panel-filtered-expander-arrow">&#9660;</span> Other definitions</summary>';
      html += '<div class="panel-filtered-expander-content">';
      if (hasOtherGroups) {
        html += renderEntryGroupsHtml(otherEntryGroups, head, Object.assign({}, opts, {
          _headDecompByForm: headDecompByForm
        }));
      } else {
        html += renderSensesFlat(altSenses, { source: e.source || '' });
      }
      html += '</div></details>';
    }

    return { html: html, isUnknown: false, sensesCount: sensesCount, head: head };
  }

  // ---------------------------------------------------------------------------
  // Render entry groups (grouped by POS)
  // ---------------------------------------------------------------------------

  function isSyllablePosLabel(posText) {
    var pos = String(posText || '').trim().toLowerCase();
    return pos === 'syl' || pos === 'syllable';
  }

  function resolveSenseDisplayText(sense, posText) {
    var s = sense || {};
    var glosses = Array.isArray(s.glosses) ? s.glosses : [];
    var gloss = glosses.join('; ').trim();
    var qualifier = String(s.qualifier || '').trim();
    var isPlaceholderGloss = !gloss || gloss.toLowerCase() === 'more information';

    if (!isSyllablePosLabel(posText)) return gloss;
    if (isPlaceholderGloss && !qualifier) return '';
    if (!qualifier) return gloss;
    if (isPlaceholderGloss) return qualifier;
    return qualifier + ' - ' + gloss;
  }

  function splitSenseDedupeParts(gloss) {
    return String(gloss || '')
      .split(';')
      .map(function(part) { return String(part || '').trim(); })
      .filter(Boolean);
  }

  function dedupeRenderedSenseGloss(gloss, seenWholeGlosses, seenGlossParts) {
    var fullGloss = String(gloss || '').trim();
    if (!fullGloss) return '';
    if (seenWholeGlosses && seenWholeGlosses[fullGloss]) return '';

    var parts = splitSenseDedupeParts(fullGloss);
    if (!parts.length) return '';
    var kept = [];
    for (var i = 0; i < parts.length; i++) {
      if (seenGlossParts && seenGlossParts[parts[i]]) continue;
      kept.push(parts[i]);
    }
    return kept.join('; ').trim();
  }

  function renderSenseList(senses, posText, entryRef) {
    var html = '';
    var source = entryRef && entryRef.source ? String(entryRef.source || '') : '';
    var seenWholeGlosses = Object.create(null);
    var seenGlossParts = Object.create(null);
    for (var si = 0; si < senses.length; si++) {
      var s = senses[si] || {};
      var gloss = resolveSenseDisplayText(s, posText);
      if (gloss) {
        gloss = dedupeRenderedSenseGloss(gloss, seenWholeGlosses, seenGlossParts);
      }
      if (!gloss) continue;
      seenWholeGlosses[gloss] = true;
      var glossParts = splitSenseDedupeParts(gloss);
      for (var gi = 0; gi < glossParts.length; gi++) {
        seenGlossParts[glossParts[gi]] = true;
      }

      html += '<div class="panel-segmentable" style="color:#333;">';
      html += renderGlossText(gloss, { source: source });
      html += '</div>';
    }
    return html;
  }

  function normalizeMorphInfoList(raw) {
    var out = [];
    var seen = Object.create(null);
    var src = Array.isArray(raw) ? raw : (raw ? [raw] : []);
    for (var i = 0; i < src.length; i++) {
      var text = String(src[i] == null ? '' : src[i]).trim();
      if (!text || seen[text]) continue;
      seen[text] = true;
      out.push(text);
    }
    return out;
  }

  var MORPH_PREVIEW_MAX_CHARS = 96;

  function isIgnorableMorphUiTag(text) {
    return /^error[-\s]+unrecognized[-\s]+form$/i.test(String(text || '').trim());
  }

  function cleanMorphUiGroupText(text) {
    var rawTokens = String(text || '').split(',');
    var kept = [];
    var seen = Object.create(null);
    for (var i = 0; i < rawTokens.length; i++) {
      var token = String(rawTokens[i] || '').trim();
      if (!token || isIgnorableMorphUiTag(token) || seen[token]) continue;
      seen[token] = true;
      kept.push(token);
    }
    return kept.join(', ');
  }

  function formatMorphInfoDisplay(raw) {
    var src = Array.isArray(raw) ? raw : (raw ? [raw] : []);
    var out = [];
    var seen = Object.create(null);
    for (var i = 0; i < src.length; i++) {
      var rawText = String(src[i] == null ? '' : src[i]).trim();
      if (!rawText) continue;
      var rawParts = rawText.split(';');
      var parts = [];
      var partSeen = Object.create(null);
      for (var j = 0; j < rawParts.length; j++) {
        var part = cleanMorphUiGroupText(rawParts[j]);
        if (!part || partSeen[part]) continue;
        partSeen[part] = true;
        parts.push(part);
      }
      parts.sort(function(a, b) {
        var aNorm = String(a || '').trim().toLowerCase() === 'normalized';
        var bNorm = String(b || '').trim().toLowerCase() === 'normalized';
        if (aNorm === bNorm) return 0;
        return aNorm ? -1 : 1;
      });
      var formatted = parts.join(', ');
      if (!formatted || seen[formatted]) continue;
      seen[formatted] = true;
      out.push(formatted);
    }
    out.sort(function(a, b) {
      var aNorm = String(a || '').trim().toLowerCase() === 'normalized';
      var bNorm = String(b || '').trim().toLowerCase() === 'normalized';
      if (aNorm === bNorm) return 0;
      return aNorm ? -1 : 1;
    });
    return out.join(' | ');
  }

  function truncateMorphDisplayText(text, maxChars) {
    var src = String(text || '').trim();
    var limit = parseInt(maxChars, 10);
    if (!src) return { text: '', truncated: false };
    if (!isFinite(limit) || limit < 24) limit = MORPH_PREVIEW_MAX_CHARS;
    if (src.length <= limit) return { text: src, truncated: false };
    var cut = src.lastIndexOf(' | ', limit - 4);
    if (cut < Math.floor(limit * 0.55)) cut = src.lastIndexOf(', ', limit - 4);
    if (cut < Math.floor(limit * 0.55)) cut = limit - 3;
    var trimmed = src.slice(0, cut).replace(/[,\s|;]+$/g, '').trim();
    if (!trimmed) trimmed = src.slice(0, limit - 3).trim();
    return { text: trimmed + '...', truncated: true };
  }

  // ---------------------------------------------------------------------------
  // Entry notes — community wiki-style notes on dictionary entries
  // ---------------------------------------------------------------------------

  var NOTE_COLOR = '#2d8659';
  var DECOMP_COLOR = '#b45309';

  // Parse stored decomp value: tries JSON {"decomposition","analysis"}, falls back to
  // legacy plain-text "Decomposition: ...\nAnalysis: ..." or bare text.
  function _parseDecompValue(raw) {
    var s = String(raw || '').trim();
    if (!s) return { decomposition: '', analysis: '', breakdown: '' };
    if (s.charAt(0) === '{') {
      try {
        var obj = JSON.parse(s);
        return {
          decomposition: String(obj.decomposition || obj.d || '').trim(),
          analysis: String(obj.analysis || obj.a || '').trim(),
          breakdown: String(obj.breakdown || obj.b || '').trim(),
        };
      } catch (e) {}
    }
    var decomposition = '', analysis = '', breakdown = '';
    var lines = s.split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      var low = line.toLowerCase();
      if (low.indexOf('decomposition') === 0) {
        decomposition = line.slice(line.indexOf(':') + 1).trim();
      } else if (low.indexOf('analysis') === 0) {
        analysis = line.slice(line.indexOf(':') + 1).trim();
      } else if (low.indexOf('breakdown') === 0) {
        breakdown = line.slice(line.indexOf(':') + 1).trim();
      }
    }
    if (!decomposition) decomposition = s;
    return { decomposition: decomposition, analysis: analysis, breakdown: breakdown };
  }

  function renderEntryDecompLine(decompText, entryRef, options) {
    // UI-only kill switch: stop rendering decomp rows while preserving the
    // underlying storage/edit/hydration code for future reuse.
    void decompText; void entryRef; void options;
    return '';
    var ref = entryRef || {};
    var alias = String(ref._storage_db_alias || ref.db_alias || '').trim();
    var rowId = parseInt(ref._form_row_id || ref._storage_row_id || ref.entry_row_id || 0, 10) || 0;
    // For lemma override matches _decomp_surface_form is the inflected text.
    // The server keys decomps by (lang, db_alias, entry_row_id, surface_form)
    // so each inflected form gets its own slot independent of the base entry.
    var decompSurfaceForm = String(ref._decomp_surface_form || '').trim();
    var lang = String((options || {})._lang || '').trim();
    var headword = String(ref.headword || ref.head || ref.display_headword || '').trim();
    var pos = String(ref.pos || ref.pos_raw || '').trim();
    // Collect rich context for the generate request
    var glosses = [];
    var formsTags = [];
    var lemma = String(ref.lemma || ref.lemma_headword || '').trim();
    if (ref.senses_full && Array.isArray(ref.senses_full)) {
      for (var si = 0; si < ref.senses_full.length; si++) {
        var sense = ref.senses_full[si];
        if (sense && Array.isArray(sense.glosses)) {
          for (var gi = 0; gi < sense.glosses.length; gi++) {
            var g = String(sense.glosses[gi] || '').trim();
            if (g) glosses.push(g);
          }
        }
      }
    } else if (ref.senses && Array.isArray(ref.senses)) {
      for (var si2 = 0; si2 < ref.senses.length; si2++) {
        var s2 = ref.senses[si2];
        if (typeof s2 === 'string' && s2.trim()) glosses.push(s2.trim());
        else if (s2 && typeof s2 === 'object') {
          var sg = String(s2.gloss || s2.def || '').trim();
          if (sg) glosses.push(sg);
        }
      }
    }
    if (ref.forms && Array.isArray(ref.forms)) {
      for (var fi = 0; fi < ref.forms.length; fi++) {
        var form = ref.forms[fi];
        if (Array.isArray(form) && form[1]) formsTags.push(String(form[1]).trim());
        else if (form && typeof form === 'object' && form.tags) formsTags.push(String(form.tags).trim());
      }
    }
    if (ref.morph_info && Array.isArray(ref.morph_info)) {
      for (var mi = 0; mi < ref.morph_info.length; mi++) {
        var mt = String(ref.morph_info[mi] || '').trim();
        if (mt) formsTags.push(mt);
      }
    }

    var rawDecomp = String(decompText || '').trim();
    var hasDecomp = !!rawDecomp;
    var parsed = hasDecomp ? _parseDecompValue(rawDecomp) : { decomposition: '', analysis: '', breakdown: '' };

    void DECOMP_COLOR;
    var containerStyle = 'direction:ltr;margin-top:2px;font-size:10px;line-height:1.45;color:#4b5563;pointer-events:auto;user-select:text;';
    var rowStyle = 'margin-top:2px;';
    var labelStyle = 'color:#6b7280;font-weight:600;';
    var valueStyle = 'display:inline;vertical-align:baseline;color:#2563eb;font:inherit;line-height:inherit;text-decoration:underline dotted rgba(37,99,235,0.45);text-underline-offset:2px;cursor:pointer;white-space:normal;word-break:break-word;';
    var autoButtonStyle = 'display:inline;vertical-align:baseline;color:#2563eb;font:inherit;line-height:inherit;cursor:pointer;white-space:normal;word-break:break-word;';
    // Gemini-inline rows live INSIDE the Base/Morph container so they share font/color/line-height.
    // Only the value spans get feint blue to mark them as AI-generated/editable.
    
    // Wrapper carries the data attrs reader.js needs for inline editing.
    // click handler — no own font/margin so rows render flush with Base/Morph.
    var html = '<div class="entry-decomp-line" style="' + containerStyle + '"'
      + ' data-decomp-inline="1"'
      + ' data-decomp-lang="' + esc(lang) + '"'
      + ' data-decomp-alias="' + esc(alias) + '"'
      + ' data-decomp-rowid="' + rowId + '"'
      + ' data-decomp-headword="' + esc(headword) + '"'
      + ' data-decomp-pos="' + esc(pos) + '"'
      + ' data-decomp-glosses="' + esc(JSON.stringify(glosses.slice(0, 6))) + '"'
      + ' data-decomp-forms-tags="' + esc(JSON.stringify(formsTags.slice(0, 8))) + '"'
      + ' data-decomp-lemma="' + esc(lemma) + '"'
      + (rawDecomp ? ' data-decomp-value="' + esc(rawDecomp) + '"' : '')
      + (decompSurfaceForm ? ' data-decomp-surface-form="' + esc(decompSurfaceForm) + '"' : '')
      + '>';

    if (hasDecomp) {
      if (parsed.decomposition) {
        html += '<div class="entry-decomp-row">'
          + '<span class="entry-decomp-label" style="' + labelStyle + '">Decomp:</span> '
          + '<span class="entry-decomp-value entry-decomp-morphemes" role="button" tabindex="0" style="' + valueStyle + '">'
          + esc(parsed.decomposition) + '</span>'
          + '</div>';
      }
      if (parsed.analysis) {
        html += '<div class="entry-decomp-row" style="' + rowStyle + '">'
          + '<span class="entry-decomp-label" style="' + labelStyle + '">Analysis:</span> '
          + '<span class="entry-decomp-value entry-decomp-analysis" role="button" tabindex="0" style="' + valueStyle + '">'
          + esc(parsed.analysis) + '</span>'
          + '</div>';
      }
      if (parsed.breakdown) {
        html += '<div class="entry-decomp-row" style="' + rowStyle + '">'
          + '<span class="entry-decomp-label" style="' + labelStyle + '">Breakdown:</span> '
          + '<span class="entry-decomp-value entry-decomp-breakdown" role="button" tabindex="0" style="' + valueStyle + '">'
          + esc(parsed.breakdown) + '</span>'
          + '</div>';
      }
    } else {
      html += '<span class="entry-decomp-auto-btn" role="button" tabindex="0" style="' + autoButtonStyle + '">+ decomp</span>';
    }

    html += '</div>';
    return html;
  }

  function renderEntryNoteLine(noteText, entryRef, options) {
    var ref = entryRef || {};
    var alias = String(ref._storage_db_alias || ref.db_alias || '').trim();
    var rowId = parseInt(ref._storage_row_id || ref.entry_row_id || 0, 10) || 0;
    var lang = String((options || {})._lang || '').trim();
    var headword = String(ref.headword || ref.head || ref.display_headword || '').trim();
    var pos = String(ref.pos || ref.pos_raw || '').trim();

    var note = String(noteText || '').trim();
    var hasNote = !!note;

    var html = '<div class="entry-note-line" style="direction:ltr;margin-top:3px;font-size:11px;line-height:1.5;color:' + NOTE_COLOR + ';pointer-events:auto;user-select:text;"'
      + ' data-note-lang="' + esc(lang) + '"'
      + ' data-note-alias="' + esc(alias) + '"'
      + ' data-note-rowid="' + rowId + '"'
      + ' data-note-headword="' + esc(headword) + '"'
      + ' data-note-pos="' + esc(pos) + '"'
      + '>';

    if (hasNote) {
      var preview = truncateMorphDisplayText(note, MORPH_PREVIEW_MAX_CHARS);
      if (preview.truncated) {
        html += '<span class="entry-note-toggle" role="button" tabindex="0"'
          + ' data-note-expanded="0"'
          + ' data-note-collapsed="' + esc(preview.text) + '"'
          + ' data-note-full="' + esc(note) + '"'
          + ' style="cursor:pointer;text-decoration:underline dotted;text-underline-offset:2px;">'
          + esc(preview.text)
          + '</span>';
      } else {
        html += '<span class="entry-note-toggle" role="button" tabindex="0"'
          + ' data-note-expanded="1"'
          + ' data-note-collapsed="' + esc(note) + '"'
          + ' data-note-full="' + esc(note) + '"'
          + ' style="text-decoration:underline dotted;text-underline-offset:2px;">'
          + esc(note)
          + '</span>';
      }
      // Edit button (always visible when a note exists; delete only in edit mode)
      html += ' <span class="entry-note-edit-btn" role="button" tabindex="0" data-native-tooltip title="Click to generate or edit a note"'
        + ' style="cursor:pointer;font-size:10px;">&#9998;</span>';
    } else {
      // +note triggers auto-generate directly
      html += '<span class="entry-note-auto-btn" role="button" tabindex="0" data-native-tooltip title="Click to generate or edit a note"'
        + ' style="cursor:pointer;font-size:10px;opacity:0.7;">+ note</span>';
    }

    html += '</div>';
    return html;
  }

  function renderMorphLineHtml(formattedMorph, options) {
    var morphText = String(formattedMorph || '').trim();
    if (!morphText) return '';
    var opts = options || {};
    var displayMode = String(opts._morphDisplayMode || 'popup').trim().toLowerCase();
    var preview = truncateMorphDisplayText(morphText, opts._morphPreviewMaxChars);
    var truncatedStyle = 'display:inline;vertical-align:baseline;color:inherit;font:inherit;line-height:inherit;' +
      'white-space:normal;word-break:break-word;text-decoration:underline dotted;text-underline-offset:2px;';
    var html = '<div><span style="color:#6b7280;font-weight:600;">Morph:</span> ';
    if (preview.truncated && displayMode === 'panel') {
      html += '<span class="dict-morph-inline-toggle" role="button" tabindex="0" aria-expanded="false"';
      html += ' data-morph-expanded="0"';
      html += ' data-morph-collapsed="' + esc(preview.text) + '"';
      html += ' data-morph-full="' + esc(morphText) + '"';
      html += ' style="' + truncatedStyle + 'cursor:pointer;">';
      html += esc(preview.text);
      html += '</span>';
    } else if (preview.truncated) {
      html += '<span style="' + truncatedStyle + '">';
      html += esc(preview.text);
      html += '</span>';
    } else {
      html += esc(preview.text);
    }
    html += '</div>';
    return html;
  }

  function renderMorphBlock(entry, fallbackHead, options) {
    var e = entry || {};
    var morphInfo = normalizeMorphInfoList(e.morph_info);
    var morphDisplay = formatMorphInfoDisplay(morphInfo);
    var morphBase = String(e.morph_base || '').trim();
    var grammar = String(e.grammar || '').trim();
    var head = String(e.head || fallbackHead || '').trim();
    var text = String(e.text || '').trim();
    var normalizedMatch = !!e.normalized_match;

    void normalizedMatch;
    if (!morphDisplay && !morphBase && !grammar) return '';
    traceUiRenderDebug('wikt_morph_block', {
      head: head,
      morph_base: morphBase,
      morph_display: morphDisplay,
      normalized_match: normalizedMatch,
      grammar: grammar,
      display_mode: String((options && options._morphDisplayMode) || 'popup')
    });

    var html = '<div style="margin-top:3px;font-size:10px;color:#4b5563;line-height:1.45;">';
    if (morphBase) {
      var psrApi = (typeof window !== 'undefined') ? window.PanelSegmentRenderer : null;
      var morphBaseHtml = (psrApi && typeof psrApi.renderLookupSpanHtml === 'function')
        ? psrApi.renderLookupSpanHtml(morphBase, {
            displayText: morphBase,
            panelToken: true,
            hoverMode: 'lookup',
            extraClasses: ['panel-token', 'panel-base-form-token']
          })
        : esc(morphBase);
      html += '<div style="color:#9ca3af;"><span style="color:#6b7280;font-weight:600;">Base:</span> ' + morphBaseHtml + '</div>';
    }
    if (morphDisplay) {
      html += renderMorphLineHtml(morphDisplay, options);
    }
    if (grammar) {
      var g = grammar.length > 220 ? (grammar.slice(0, 217) + '...') : grammar;
      html += '<div><span style="color:#6b7280;font-weight:600;">Grammar:</span> ' + esc(g) + '</div>';
    }
    html += '</div>';
    return html;
  }

  function getAtomicEntriesForSenseKey(entry, senseKey) {
    var target = entry || {};
    // Support both old full-object arrays and new ref-key arrays
    if (senseKey === 'senses_hover') {
      var hoverRefs = target.atomic_entry_refs_hover || target.atomic_entries_hover;
      if (Array.isArray(hoverRefs) && hoverRefs.length) return resolveEntryRefs(hoverRefs);
      var allRefs = target.atomic_entry_refs_all || target.atomic_entries_all;
      if (Array.isArray(allRefs) && allRefs.length) return resolveEntryRefs(allRefs);
    } else if (senseKey === 'senses_hover_other') {
      var otherRefs = target.atomic_entry_refs_other || target.atomic_entries_other;
      if (Array.isArray(otherRefs) && otherRefs.length) return resolveEntryRefs(otherRefs);
      return [];
    } else {
      var allRefs2 = target.atomic_entry_refs_all || target.atomic_entries_all;
      if (Array.isArray(allRefs2) && allRefs2.length) return resolveEntryRefs(allRefs2);
    }
    var entryRefs = target.entry_refs || target.entries;
    return Array.isArray(entryRefs) ? resolveEntryRefs(entryRefs) : [];
  }

  function buildAtomicEntryGroups(entries, fallbackHead) {
    var src = Array.isArray(entries) ? entries : [];
    var out = [];
    for (var i = 0; i < src.length; i++) {
      var row = src[i] || {};
      var rowSenses = Array.isArray(row.senses_full) ? row.senses_full : [];
      if (!rowSenses.length) continue;
      var rowHeadword = String(row.display_headword || row.headword || row.head || row.text || fallbackHead || '').trim();
      var rowMatchKind = String(row.match_kind || row._match_kind || row._match_source || '').trim().toLowerCase();
      var rowReading = String(row.display_reading || row.reading || (rowMatchKind === 'form' ? '' : (row.pinyin || ''))).trim();
      var rowPos = String(row.pos_raw || row.pos || '').trim();
      var rowMorphInfo = Array.isArray(row.morph_info)
        ? row.morph_info.slice().map(function(v) { return String(v || '').trim(); }).filter(Boolean)
        : (row.morph_info ? [String(row.morph_info).trim()] : []);
      var entryRefKey = String(row.ref_key || row.runtime_entry_id || '').trim();
      var posGroup = {
        headword: rowHeadword,
        base_headword: String(row.lemma_headword || row.morph_base || '').trim(),
        is_form_match: String(row.match_kind || '').trim().toLowerCase() === 'form',
        reading: rowReading,
        pos: rowPos,
        senses: rowSenses,
        normalized_match: !!row.normalized_match,
        _entryRef: entryRefKey || row
      };
      if (rowMorphInfo.length) posGroup.morph_info = rowMorphInfo;
      if (row.morph_base) posGroup.morph_base = String(row.morph_base || '').trim();
      if (row.grammar) posGroup.grammar = String(row.grammar || '');
      if (Array.isArray(row.hanja_forms) && row.hanja_forms.length) posGroup.hanja_forms = row.hanja_forms.slice();
      if (Array.isArray(row.hangeul_forms) && row.hangeul_forms.length) posGroup.hangeul_forms = row.hangeul_forms.slice();
      out.push({
        headword: rowHeadword || String(fallbackHead || '').trim(),
        reading: rowReading,
        pos_groups: [posGroup],
        _entryRef: entryRefKey || row
      });
    }
    return out;
  }

  function normalizeGroupKeyPart(raw) {
    return String(raw || '').trim().toLowerCase();
  }

  function buildEntryGroupKey(grp) {
    var g = grp || {};
    var etymKey = normalizeGroupKeyPart(g.etym_key);
    if (etymKey) {
      // Entry-level matching must not collapse unrelated entries that share
      // only the etymology key. Include display identity so "Other definitions"
      // keeps full entry blocks (headword/reading/hanja) separate.
      var headwordByKey = normalizeGroupKeyPart(g.headword);
      var readingByKey = normalizeGroupKeyPart(g.reading);
      return 'k:' + etymKey + '\u241f' + headwordByKey + '\u241f' + readingByKey;
    }
    var headword = normalizeGroupKeyPart(g.headword);
    var reading = normalizeGroupKeyPart(g.reading);
    var etym = normalizeGroupKeyPart(g.etymology);
    var key = headword + '\u241f' + reading + '\u241f' + etym;
    if (key === '\u241f\u241f') return '';
    return key;
  }

  function mergeUniqueStrings(base, extra) {
    var out = Array.isArray(base) ? base.slice() : [];
    var seen = Object.create(null);
    for (var i = 0; i < out.length; i++) {
      var b = String(out[i] || '');
      if (b) seen[b] = true;
    }
    var add = Array.isArray(extra) ? extra : [];
    for (var j = 0; j < add.length; j++) {
      var e = String(add[j] || '');
      if (!e || seen[e]) continue;
      seen[e] = true;
      out.push(e);
    }
    return out;
  }

  function cloneEntryGroup(grp) {
    var src = grp || {};
    var out = {
      headword: src.headword || '',
      reading: src.reading || '',
      etymology: src.etymology || '',
      etym_key: src.etym_key || '',
      pos_groups: Array.isArray(src.pos_groups) ? src.pos_groups.slice() : [],
      _entryRef: src._entryRef || null
    };
    if (!out.pos_groups.length && Array.isArray(src.senses) && src.senses.length) {
      out.pos_groups = [{ pos: src.pos || '', senses: src.senses }];
    }
    out.alt_forms = Array.isArray(src.alt_forms) ? src.alt_forms.slice() : [];
    out.synonyms = Array.isArray(src.synonyms) ? src.synonyms.slice() : [];
    out.antonyms = Array.isArray(src.antonyms) ? src.antonyms.slice() : [];
    out.derived = Array.isArray(src.derived) ? src.derived.slice() : [];
    out.related = Array.isArray(src.related) ? src.related.slice() : [];
    return out;
  }

  function mergeEntryGroups(baseGrp, extraGrp) {
    var out = cloneEntryGroup(baseGrp);
    var extra = cloneEntryGroup(extraGrp);
    if (Array.isArray(extra.pos_groups) && extra.pos_groups.length) {
      out.pos_groups = (Array.isArray(out.pos_groups) ? out.pos_groups : []).concat(extra.pos_groups);
    }
    out.alt_forms = mergeUniqueStrings(out.alt_forms, extra.alt_forms);
    out.synonyms = mergeUniqueStrings(out.synonyms, extra.synonyms);
    out.antonyms = mergeUniqueStrings(out.antonyms, extra.antonyms);
    out.derived = mergeUniqueStrings(out.derived, extra.derived);
    out.related = mergeUniqueStrings(out.related, extra.related);
    if (!out.etymology && extra.etymology) out.etymology = extra.etymology;
    if (!out.etym_key && extra.etym_key) out.etym_key = extra.etym_key;
    if (!out.headword && extra.headword) out.headword = extra.headword;
    if (!out.reading && extra.reading) out.reading = extra.reading;
    if (!out._entryRef && extra._entryRef) out._entryRef = extra._entryRef;
    return out;
  }

  function splitOtherGroupsForInline(primaryGroups, otherGroups) {
    var primary = Array.isArray(primaryGroups) ? primaryGroups : [];
    var others = Array.isArray(otherGroups) ? otherGroups : [];
    var primaryKeys = Object.create(null);
    for (var i = 0; i < primary.length; i++) {
      var pk = buildEntryGroupKey(primary[i]);
      if (pk) primaryKeys[pk] = true;
    }

    var inlineByKey = Object.create(null);
    var globalGroups = [];
    for (var j = 0; j < others.length; j++) {
      var grp = others[j] || {};
      var key = buildEntryGroupKey(grp);
      if (key && primaryKeys[key]) {
        if (inlineByKey[key]) {
          inlineByKey[key] = mergeEntryGroups(inlineByKey[key], grp);
        } else {
          inlineByKey[key] = cloneEntryGroup(grp);
        }
      } else {
        globalGroups.push(grp);
      }
    }
    return {
      inlineByKey: inlineByKey,
      globalGroups: globalGroups
    };
  }

  function renderFilteredPosGroupsInline(group) {
    var grp = group || {};
    var posGroups = Array.isArray(grp.pos_groups) ? grp.pos_groups : [];
    if (!posGroups.length && Array.isArray(grp.senses) && grp.senses.length) {
      posGroups = [{ pos: grp.pos || '', senses: grp.senses }];
    }
    if (!posGroups.length) return '';

    var html = '<div style="margin-top:2px;">';
    for (var i = 0; i < posGroups.length; i++) {
      var pg = posGroups[i] || {};
      var posLabel = String(pg.pos || '');
      var pgSenses = Array.isArray(pg.senses) ? pg.senses : [];
      if (!pgSenses.length) continue;
      html += '<div style="display:flex;align-items:baseline;gap:0;">';
      html += '<div class="dict-pos-label" style="min-width:36px;max-width:44px;color:#888;font-size:10px;font-style:italic;flex-shrink:0;padding-top:1px;">';
      html += posLabel ? esc(posLabel) : '';
      html += '</div>';
      html += '<div style="flex:1;min-width:0;">' + renderSenseList(pgSenses, posLabel, resolveEntryRef(pg._entryRef) || resolveEntryRef(grp._entryRef) || null) + '</div>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderEntryGroupsHtml(groups, head, options) {
    var opts = options || {};
    var headDecompByForm = opts._headDecompByForm || null;
    var buildEntryMetaForRow = (typeof opts._buildEntryMetaForRow === 'function')
      ? opts._buildEntryMetaForRow
      : null;
    // dict-entries-container marks all output below as dictionary entry text
    // (surface slices, headwords, base forms, mwt-child tokens). The panel
    // segment renderer / hover module use this ancestor to suppress hover
    // lookups within the dict entry block while leaving the token banner
    // (rendered outside this container) fully interactive.
    var html = '<div class="dict-entries-container" style="font-size:12px;line-height:1.8;">';
    var entryRowIndex = 0;
    function hasHangul(text) {
      return /[ㄱ-ㅎㅏ-ㅣ가-힣]/.test(String(text || ''));
    }
    function hasCjkHanja(text) {
      return /[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]/.test(String(text || ''));
    }
    function filterDisplayForms(forms, rowHeadword) {
      var out = [];
      var seen = Object.create(null);
      var head = String(rowHeadword || '').trim();
      var src = Array.isArray(forms) ? forms : [];
      for (var i = 0; i < src.length; i++) {
        var txt = String(src[i] || '').trim();
        if (!txt || txt === head || seen[txt]) continue;
        seen[txt] = true;
        out.push(txt);
      }
      return out;
    }
    for (var gi = 0; gi < groups.length; gi++) {
      var grp = groups[gi] || {};
      var posGroups = Array.isArray(grp.pos_groups) ? grp.pos_groups : [];
      var grpSenses = Array.isArray(grp.senses) ? grp.senses : [];
      if (!posGroups.length && grpSenses.length) {
        posGroups = [{ pos: grp.pos || '', senses: grpSenses }];
      }
      if (!posGroups.length) continue;

      var grpHeadword = String(grp.headword || head || '');
      var grpReading = String(grp.reading || '');

      // POS sub-groups (one dictionary row per POS group). Repeat the headword
      // per row so users can clearly see entry boundaries.
      for (var pi = 0; pi < posGroups.length; pi++) {
        var pg = posGroups[pi] || {};
        var posLabel = String(pg.pos || '');
        var pgSenses = Array.isArray(pg.senses) ? pg.senses : [];
        if (!pgSenses.length) continue;
        var rowHeadword = String(pg.headword || grpHeadword || '');
        var rowHeadwordTrimmed = rowHeadword.trim();
        var rowBaseHeadword = String(pg.base_headword || '').trim();
        var rowEntryRef = resolveEntryRef(pg._entryRef) || resolveEntryRef(grp._entryRef) || null;
        var isInflectedSurfaceRow = !!pg.is_form_match;
        var rowReading = String(isInflectedSurfaceRow ? (pg.reading || '') : (pg.reading || grpReading || ''));
        if (!isInflectedSurfaceRow && rowBaseHeadword && rowHeadwordTrimmed !== rowBaseHeadword) {
          rowReading = '';
        }

        html += '<div style="color:#111;font-size:14px;font-weight:600;' +
                (entryRowIndex > 0 ? 'margin-top:8px;' : '') +
                '">';
        var buildSurfaceHtml = (typeof opts._buildPanelSurfaceHeadlineHtml === 'function')
          ? opts._buildPanelSurfaceHeadlineHtml
          : null;
        traceUiRenderDebug('wikt_entry_group_row', {
          row_headword: rowHeadword,
          row_reading: rowReading,
          row_base_headword: rowBaseHeadword,
          role: isInflectedSurfaceRow ? 'surface' : 'entry-headword',
          used_shared_surface_renderer: !!buildSurfaceHtml,
          pos: posLabel,
          sense_count: pgSenses.length
        });
        void buildSurfaceHtml;
        // Headword is now plain text — no hover, no inspect, no underline.
        var rowHeadHtml = '<span class="panel-headword-plain" style="cursor:text;user-select:text;">'
          + esc(rowHeadword) + '</span>';
        if (rowReading) {
          rowHeadHtml += ' <span class="panel-headword-reading">(' + esc(rowReading) + ')</span>';
        }
        var rowHanjaForHead = filterDisplayForms(pg.hanja_forms, rowHeadword);
        if (!isInflectedSurfaceRow) {
          if (rowHanjaForHead.length && (hasHangul(rowHeadword) || !hasCjkHanja(rowHeadword))) {
            rowHeadHtml += ' <span style="color:#92400e;">' + esc(rowHanjaForHead.join(' / ')) + '</span>';
          }
        }
        // Per-row metadata comes only from the actual row object.
        var rowEntryMetaHtml = '';
        if (buildEntryMetaForRow && rowEntryRef) {
          rowEntryMetaHtml = String(buildEntryMetaForRow(rowEntryRef, rowHeadword, {
            group: grp,
            posGroup: pg,
            isInflectedSurfaceRow: isInflectedSurfaceRow
          }) || '');
        }
        // Headword wrapper stays inert; entry meta still lives outside the text span.
        var _hwRef = rowEntryRef || {};
        var _hwAlias = String(_hwRef._storage_db_alias || _hwRef.db_alias || '').trim();
        var _hwRowId = parseInt(_hwRef._form_row_id || _hwRef._storage_row_id || _hwRef.entry_row_id || 0, 10) || 0;
        var _hwPos = String(_hwRef.pos || _hwRef.pos_raw || posLabel || '').trim();
        // For lemma override matches the entry carries _decomp_surface_form
        // (the inflected text).  When present, the decomp key uses both the
        // base entry's row ID and the surface form so each inflected variant
        // of the same base entry gets its own storage slot.
        var _hwDecompSurface = String(_hwRef._decomp_surface_form || '').trim();
        void _hwAlias; void _hwRowId; void _hwPos; void _hwDecompSurface;
        // Headword wrapper is now inert — no decomp data, no hover behavior.
        var wrappedHeadword = '<span class="panel-headword-wrap" style="display:inline;">' + rowHeadHtml + '</span>';
        
        // Now apply sense-head-inline wrapper with meta (edit button) outside the headword wrapper
        if (rowEntryMetaHtml) {
          wrappedHeadword = wrapSenseHeadInline(wrappedHeadword, rowEntryMetaHtml);
        }
        
        html += wrappedHeadword + '</div>';

        var rowMorphHtml = renderMorphBlock({
          head: rowHeadword,
          text: rowHeadword,
          normalized_match: !!pg.normalized_match,
          morph_base: pg.morph_base,
          morph_info: pg.morph_info,
          grammar: pg.grammar
        }, rowHeadword, opts);
        if (rowMorphHtml) {
          html += rowMorphHtml;
        }

        // Inline Gemini decomp/analysis/breakdown rows — same layout as Base/Morph, feint blue.
        var _decompRef = rowEntryRef || {};
        if (!_decompRef._decomp_surface_form && rowHeadword) {
          _decompRef = Object.assign({}, _decompRef, { _decomp_surface_form: rowHeadword });
        }
        var _decompText = String(_decompRef.decomp || _decompRef.decomposition || '').trim();
        html += renderEntryDecompLine(_decompText, _decompRef, opts);

        html += '<div style="display:flex;align-items:baseline;gap:0;">';
        html += '<div class="dict-pos-label" style="min-width:36px;max-width:44px;color:#888;font-size:10px;font-style:italic;flex-shrink:0;padding-top:1px;">';
        html += posLabel ? esc(posLabel) : '';
        html += '</div>';
        html += '<div style="flex:1;min-width:0;">';
        html += renderSenseList(pgSenses, posLabel, rowEntryRef);
        html += '</div>';
        html += '</div>';
        // Entry note line
        var _noteRef = rowEntryRef || {};
        var _noteText = String(_noteRef.note || '').trim();
        html += renderEntryNoteLine(_noteText, _noteRef, opts);

        // Decomp UI is now triggered exclusively via the headword hover popup
        // in reader.js — no inline rendering inside the dictionary entry block.
        entryRowIndex += 1;
      }

    }
    html += '</div>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // Render flat senses
  // ---------------------------------------------------------------------------

  function renderSensesFlat(senses, options) {
    var opts = options || {};
    var html = '<div style="font-size:12px;line-height:1.7;">';
    for (var i = 0; i < senses.length; i++) {
      var line = String(senses[i] || '').trim();
      if (!line) continue;
      var parts = line.split('\t');
      var pos = '';
      var text = '';
      if (parts.length >= 4) {
        pos = (parts[2] || '').trim();
        text = parts[3] || '';
      } else if (parts.length > 1) {
        text = parts[parts.length - 1];
      } else {
        text = line;
      }
      if (!text.trim()) continue;
      html += '<div class="panel-segmentable">';
      if (pos) {
        html += '<span class="dict-pos-label" style="color:#888;font-size:10px;font-style:italic;margin-right:4px;">' + esc(pos) + '</span>';
      }
      html += renderGlossText(text, { source: opts.source });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderEntryMetaHeadHtml(entry, fallbackHead, entryMetaHtml, headDecompByForm, rawLang, options) {
    var e = entry || {};
    var headword = String(e.head || fallbackHead || '').trim();
    var reading = String(e.reading || '').trim();
    if (!headword && !reading) return '';
    traceUiRenderDebug('wikt_meta_head', {
      headword: headword,
      reading: reading,
      has_entry_meta: !!entryMetaHtml,
      uses_shared_surface_renderer: !!(options && typeof options._buildPanelSurfaceHeadlineHtml === 'function')
    });
    var mainHtml = '';
    if (headword) {
      var buildSurfaceHtml = (options && typeof options._buildPanelSurfaceHeadlineHtml === 'function')
        ? options._buildPanelSurfaceHeadlineHtml
        : null;
      mainHtml += buildSurfaceHtml
        ? buildSurfaceHtml(headword, 'meta-headword')
        : buildPanelHeadwordTokenHtml(headword, rawLang || '', esc, { _panelHeadRole: 'meta-headword' });
    }
    if (reading) {
      if (mainHtml) mainHtml += ' ';
      mainHtml += '<span class="panel-headword-reading">(' + esc(reading) + ')</span>';
    }
    if (!mainHtml) return '';
    return '<div style="color:#888;font-size:11px;">' + wrapSenseHeadInline(mainHtml, entryMetaHtml) + '</div>';
  }

  // ---------------------------------------------------------------------------
  // Render word lists (synonyms, antonyms, etc.)
  // ---------------------------------------------------------------------------

  function renderWordList(words, label, options) {
    if (!Array.isArray(words) || !words.length) return '';
    var opts = options || {};
    var hasCustomMax = (typeof opts.maxItems === 'number');
    var maxItems = hasCustomMax ? opts.maxItems : 10;
    if (maxItems < 0) maxItems = 0;
    var labelMap = { syn: 'Synonyms', ant: 'Antonyms', der: 'Derived', rel: 'Related', alt: 'Alt forms' };
    var displayLabel = labelMap[label] || label;
    var html = '<div style="font-size:10px;color:#6b7280;line-height:1.4;">';
    html += '<span style="font-weight:600;">' + esc(displayLabel) + ':</span> ';
    var items = [];
    var limit = maxItems === 0 ? words.length : Math.min(words.length, maxItems);
    for (var i = 0; i < limit; i++) {
      items.push(esc(String(words[i] || '')));
    }
    html += items.join(', ');
    if (maxItems !== 0 && words.length > maxItems) html += ', ...';
    html += '</div>';
    return html;
  }

  // ---------------------------------------------------------------------------
  // ADAPTER REGISTRATION — register for all Wiktionary general languages
  // ---------------------------------------------------------------------------

  var wiktAdapter = {
    isWiktLanguage: isWiktLanguage,
    normalizePinyinToneMarks: function(v) { return String(v || ''); },
    formatPopupRoman: formatPopupRoman,
    getHeadwordForms: getHeadwordForms,
    getPopupHeadwordForms: getPopupHeadwordForms,
    formatPopupHeadwordHtml: formatPopupHeadwordHtml,
    getPanelHeadwordRows: getPanelHeadwordRows,
    mergePanelEntryFields: mergePanelEntryFields,
    supportsDecomposeSubsegments: true,
    getPanelSegmentationRegex: getPanelSegmentationRegex,
    shouldSegmentPanelTextPart: shouldSegmentPanelTextPart,
    getG2PComponentViewModel: getG2PComponentViewModel,
    renderDictEntry: renderWiktDictEntry
  };

  window.ReaderLanguageAdapters = window.ReaderLanguageAdapters || {};

  // Register for all supported language codes and aliases.
  // Keep language-specific normalization/headword helpers when available,
  // but force the same core Wiktionary dictionary renderer everywhere.
  var langKeys = [
    'zh', 'zh-hant', 'chinese', 'traditional-chinese',
    'lzh', 'classical', 'classical-chinese',
    'ja', 'japanese',
    'ko', 'korean',
    'vi', 'vietnamese',
    'ar', 'arabic',
    'fa', 'persian',
    'hi', 'hindi',
    'id', 'indonesian',
    'ta', 'tamil',
    'th', 'thai',
    'tr', 'turkish',
    'ur', 'urdu',
    'sa', 'sanskrit',
    'ga', 'irish',
    'ang', 'oldenglish', 'old-english', 'old english',
    'fr', 'french',
    'it', 'italian',
    'ru', 'russian',
    'es', 'spanish',
    'de', 'german',
    'nl', 'dutch',
    'pt', 'portuguese',
    'la', 'latin',
    'el', 'greek',
    'hy', 'armenian',
    'grc', 'ancient-greek', 'ancientgreek',
    'he', 'hebrew',
    'hbo', 'ancient-hebrew', 'ancienthebrew', 'biblical-hebrew',
    'tl', 'tagalog', 'filipino',
    'sw', 'swahili', 'kiswahili',
    'bn', 'bengali', 'bangla',
    'pa', 'punjabi', 'panjabi'
  ];
  for (var i = 0; i < langKeys.length; i++) {
    var key = langKeys[i];
    var existing = window.ReaderLanguageAdapters[key] || {};
    var merged = Object.assign({}, wiktAdapter, existing);
    merged.isWiktLanguage = wiktAdapter.isWiktLanguage;
    merged.renderDictEntry = wiktAdapter.renderDictEntry;
    window.ReaderLanguageAdapters[key] = merged;
  }
})();
