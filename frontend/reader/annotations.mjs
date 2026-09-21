import { debounce, isContentChar } from './document-shell.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { escapeHtml, formatPopupRoman, isJapaneseLanguage, renderPopupRomanLine } from './presentation.mjs';
import { segmentRenderingState } from './segment-rendering.state.mjs';
export function matchTokenWithInvisibleChars(source, startIndex, token) {
  // Frontend no longer does any normalization.
  // We only wrap tokens that are exact substrings of the original text.
  if (!token || !token.length) return null;
  var tLen = token.length;
  // Require an exact match starting at this position
  if (source.substr(startIndex, tLen) !== token) {
    return null;
  }
  return {
    end: startIndex + tLen - 1
  };
}
export function _blockHasOverlap(spans, debug) {
  if (!spans || spans.length < 2) return false;

  // Group spans into lines using attached source line data.
  var byLine = {};
  for (var i = 0; i < spans.length; i++) {
    var s = spans[i];
    var lineKey = s.dataset.line || '0';
    if (!byLine[lineKey]) byLine[lineKey] = [];
    byLine[lineKey].push(s);
  }

  // Within each line, sort by X and compute gap for each adjacent pair
  var allGaps = []; // Positive = gap, negative = overlap
  var overlaps = [];
  var lineKeys = Object.keys(byLine);
  for (var li = 0; li < lineKeys.length; li++) {
    var lineSpans = byLine[lineKeys[li]];
    if (lineSpans.length < 2) continue;
    // Get rects and sort by left edge
    var indexed = lineSpans.map(function (s) {
      return {
        r: s.getBoundingClientRect(),
        s: s
      };
    });
    indexed.sort(function (a, b) {
      return a.r.left - b.r.left;
    });
    // Check adjacent pairs
    for (var j = 0; j < indexed.length - 1; j++) {
      var curr = indexed[j];
      var next = indexed[j + 1];
      // Gap = next.left - curr.right (positive = gap, negative = overlap)
      var gap = next.r.left - curr.r.right;
      allGaps.push(gap);
      if (gap < 0) {
        overlaps.push({
          line: lineKeys[li],
          curr: {
            text: curr.s.textContent,
            left: curr.r.left,
            right: curr.r.right
          },
          next: {
            text: next.s.textContent,
            left: next.r.left,
            right: next.r.right
          },
          overlapPx: -gap
        });
      }
    }
  }

  // Calculate median gap - if median is negative, we have significant overlap
  var medianGap = 0;
  if (allGaps.length > 0) {
    allGaps.sort(function (a, b) {
      return a - b;
    });
    var mid = Math.floor(allGaps.length / 2);
    medianGap = allGaps.length % 2 ? allGaps[mid] : (allGaps[mid - 1] + allGaps[mid]) / 2;
  }
  var hasSignificantOverlap = medianGap < 0;
  if (debug) {
    return {
      hasOverlap: hasSignificantOverlap,
      overlaps: overlaps,
      lines: lineKeys.length,
      totalSpans: spans.length,
      totalPairs: allGaps.length,
      medianGap: medianGap,
      minGap: allGaps.length ? allGaps[0] : 0,
      maxGap: allGaps.length ? allGaps[allGaps.length - 1] : 0
    };
  }
  return hasSignificantOverlap;
}
export function normalizeBlockFontSizes(container, baseFontPx) {
  if (!container) return;
  var spans = container.querySelectorAll('.pdf-raw-word');
  if (!spans || !spans.length) return;
  var byBlock = {};
  spans.forEach(function (s) {
    var b = s.dataset.block || '0';
    if (!byBlock[b]) byBlock[b] = [];
    byBlock[b].push(s);
  });
  Object.keys(byBlock).forEach(function (blockKey) {
    var blockSpans = byBlock[blockKey];
    if (!blockSpans || blockSpans.length < 2) return;
    var baseSize = baseFontPx && isFinite(baseFontPx) && baseFontPx > 0 ? baseFontPx : 0;
    if (!baseSize) {
      for (var i = 0; i < blockSpans.length; i++) {
        var fs = parseFloat(blockSpans[i].style.fontSize || '0');
        if (fs > 0) {
          baseSize = fs;
          break;
        }
      }
    }
    if (!baseSize) return;
    var size = Math.floor(baseSize);
    var minSize = Math.max(6, size - 12);
    for (; size >= minSize; size -= 1) {
      for (var k = 0; k < blockSpans.length; k++) {
        blockSpans[k].style.fontSize = size + 'px';
      }
      if (!_blockHasOverlap(blockSpans)) break;
    }
  });
}
export function normalizeLinePositions(container) {
  if (!container) return;
  var spans = container.querySelectorAll('.pdf-raw-word');
  if (!spans || !spans.length) return;

  // Group spans by block and line
  var byBlockLine = {};
  spans.forEach(function (s) {
    var blockKey = s.dataset.block || '0';
    var lineKey = s.dataset.line || '0';
    var key = blockKey + ':' + lineKey;
    if (!byBlockLine[key])
      byBlockLine[key] = {
        block: blockKey,
        line: lineKey,
        spans: []
      };
    byBlockLine[key].spans.push(s);
  });

  // Convert to array and sort by original Y position
  var lines = Object.values(byBlockLine);
  lines.forEach(function (lineData) {
    var minY = Infinity;
    lineData.spans.forEach(function (s) {
      var y = parseFloat(s.dataset.bboxY) || 0;
      if (y < minY) minY = y;
    });
    lineData.origY = minY;
  });
  lines.sort(function (a, b) {
    return a.origY - b.origY;
  });

  // Calculate the rendered height of each line
  lines.forEach(function (lineData) {
    var maxH = 0;
    lineData.spans.forEach(function (s) {
      var rect = s.getBoundingClientRect();
      if (rect.height > maxH) maxH = rect.height;
    });
    lineData.renderedH = maxH;
  });

  // Keep original vertical layout. Do not globally re-stack lines, which can
  // break tables/columns. Only straighten each line so all words on that line
  // share one top value.
  var containerH = container.getBoundingClientRect().height || 0;
  lines.forEach(function (lineData) {
    var topVals = [];
    lineData.spans.forEach(function (s) {
      var t = parseFloat(s.style.top || '');
      if (isFinite(t)) topVals.push(t);
    });
    var topPct;
    if (topVals.length) {
      topVals.sort(function (a, b) {
        return a - b;
      });
      topPct = topVals[Math.floor(topVals.length / 2)];
    } else if (containerH > 0) {
      topPct = (lineData.origY / containerH) * 100;
    } else {
      topPct = 0;
    }
    lineData.spans.forEach(function (s) {
      s.style.top = topPct + '%';
    });
  });
}
export function wrapTokensInText(text) {
  if (!text) return '';
  var tokens = [];
  var currentToken = '';
  for (var i = 0; i < text.length; i++) {
    var char = text[i];
    var code = char.charCodeAt(0);
    // Check if this is a content character (any non-ASCII script character)
    if (isContentChar(char)) {
      currentToken += char;
    } else {
      if (currentToken) {
        tokens.push({
          type: 'token',
          value: currentToken
        });
        currentToken = '';
      }
      tokens.push({
        type: 'text',
        value: char
      });
    }
  }
  if (currentToken) {
    tokens.push({
      type: 'token',
      value: currentToken
    });
  }
  var html = '';
  for (var j = 0; j < tokens.length; j++) {
    var t = tokens[j];
    if (t.type === 'token') {
      html +=
        '<span class="panel-token" data-seg="' + escapeHtml(t.value) + '">' + escapeHtml(t.value) + '</span>';
    } else {
      html += escapeHtml(t.value);
    }
  }
  return html;
}
export function renderSenseText(rawText) {
  // Split on \x1F � text before is the gloss, text after is the s_inf note
  var idx = rawText.indexOf('\x1F');
  if (idx >= 0) {
    var glossPart = rawText.substring(0, idx);
    var notePart = rawText.substring(idx + 1);
    return (
      escapeHtml(formatPopupRoman(glossPart)) +
      ' <span style="color:#888;font-style:italic;font-size:0.92em;">' +
      escapeHtml(formatPopupRoman(notePart)) +
      '</span>'
    );
  }
  return escapeHtml(formatPopupRoman(rawText));
}
export function isSharedMiscNoteText(rawText) {
  var txt = String(rawText || '').trim();
  if (!txt) return false;
  if (txt.charAt(0) !== '[' || txt.charAt(txt.length - 1) !== ']') return false;
  var lower = txt.toLowerCase();
  if (lower.indexOf('[cf.') === 0 || lower.indexOf('[ant.') === 0) return false;
  return true;
}
export function renderSharedMiscNoteHtml(rawText) {
  return (
    '<span style="color:#0f766e;font-style:italic;font-size:0.95em;">' +
    escapeHtml(formatPopupRoman(rawText)) +
    '</span>'
  );
}
// DEBUG MAP: non-stacked sense renderer.
// Provenance/edit does NOT come from the popup headline anymore.
// Instead, entryMetaHtml is injected into the first visible sense headword row.
export function renderSenseLines(senses, skipHead, formsMetaByHeader, options) {
  var opts = options || {};
  var forceSenseHead = !!opts.forceSenseHead;
  var entryMetaHtml = String(opts.entryMetaHtml || '');
  if (!senses || !senses.length) return '';
  // Detect Japanese-style entries with \x1E forms-header lines
  var hasFormsHeader = false;
  for (var fi = 0; fi < senses.length; fi++) {
    if (senses[fi] && senses[fi].charAt(0) === '\x1E') {
      hasFormsHeader = true;
      break;
    }
  }
  if (hasFormsHeader)
    return renderStackedSenseLines(senses, forceSenseHead ? null : skipHead, formsMetaByHeader, opts);
  // Japanese entries without a forms header: synthesize one from the headword
  // so the reading + romaji line is always shown (e.g. ? ? ?/ha)
  if (isJapaneseLanguage() && skipHead) {
    var synthSenses = ['\x1E' + skipHead].concat(senses);
    return renderStackedSenseLines(synthSenses, null, formsMetaByHeader, opts);
  }
  // --- Original 4-column grid layout (Chinese etc.) ---
  var html =
    '<div style="display:grid;grid-template-columns:auto auto auto 1fr;gap:0 12px;align-items:start;font-size:12px;line-height:1.8;">';
  var metaInjected = false;
  for (var li = 0; li < senses.length; li++) {
    var line = senses[li];
    if (!line || !line.trim()) continue;
    var tabCount = 0;
    for (var ci = 0; ci < line.length; ci++) {
      if (line[ci] === '\t') tabCount++;
      else break;
    }
    var content = line.substring(tabCount);
    if (!content || !content.trim()) continue;
    if (tabCount === 0) {
      var parts = content.split('\t');
      if (parts.length >= 4) {
        var headword = parts[0] || '',
          roman = parts[1] || '',
          pos = parts[2] || '',
          sense = parts.slice(3).join('\t');
        if (skipHead && !forceSenseHead) {
          html += '<div style="font-weight:bold;font-size:13px;"></div>';
        } else {
          var headwordHtml = escapeHtml(headword);
          // DEBUG MAP: first non-stacked headword row gets the provenance/edit bundle.
          if (!metaInjected && entryMetaHtml) {
            headwordHtml =
              '<span class="sense-head-inline"><span class="sense-head-inline-main">' +
              headwordHtml +
              '</span>' +
              entryMetaHtml +
              '</span>';
            metaInjected = true;
          }
          html += '<div style="font-weight:bold;font-size:13px;">' + headwordHtml + '</div>';
        }
        html +=
          '<div style="font-style:italic;color:#666;">' + escapeHtml(formatPopupRoman(roman)) + '</div>';
        html += pos
          ? '<div style="color:#888;font-size:11px;">[' + escapeHtml(pos) + ']</div>'
          : '<div></div>';
        html += '<div class="panel-segmentable" style="color:#333;">' + renderSenseText(sense) + '</div>';
      }
    } else if (tabCount === 2) {
      var parts2 = content.split('\t');
      if (parts2.length >= 2) {
        html +=
          '<div></div><div></div><div style="color:#888;font-size:11px;">[' +
          escapeHtml(parts2[0]) +
          ']</div>';
        html +=
          '<div class="panel-segmentable" style="color:#333;">' +
          renderSenseText(parts2.slice(1).join('\t')) +
          '</div>';
      }
    } else {
      var sense3 = content.trim();
      if (sense3) {
        if (isSharedMiscNoteText(sense3)) {
          html += '<div></div><div></div><div></div><div>' + renderSharedMiscNoteHtml(sense3) + '</div>';
        } else {
          html +=
            '<div></div><div></div><div></div><div class="panel-segmentable" style="color:#333;">' +
            renderSenseText(sense3) +
            '</div>';
        }
      }
    }
  }
  html += '</div>';
  return html;
}
export function buildFormsMetaPayload(formKind, formText, formsMetaBundle) {
  var payload = {
    kind: String(formKind || ''),
    form: String(formText || ''),
    info_tags: [],
    priority_tags: [],
    priority_score: 0,
    priority_basis_tag: '',
    spec_priority_tag: '',
    no_kanji: false,
    is_restricted: false,
    restricted_to_kanji: []
  };
  if (!formsMetaBundle || typeof formsMetaBundle !== 'object') return payload;
  var byKey = formKind === 'kanji' ? formsMetaBundle.kanji_by_form : formsMetaBundle.readings_by_form;
  var formMeta = byKey && typeof byKey === 'object' ? byKey[formText] : null;
  if (!formMeta || typeof formMeta !== 'object') return payload;
  payload.info_tags = Array.isArray(formMeta.info_tags) ? formMeta.info_tags.slice() : [];
  payload.priority_tags = Array.isArray(formMeta.priority_tags) ? formMeta.priority_tags.slice() : [];
  if (typeof formMeta.priority_score === 'number' && isFinite(formMeta.priority_score)) {
    payload.priority_score = formMeta.priority_score;
  }
  payload.priority_basis_tag = String(formMeta.priority_basis_tag || '');
  payload.spec_priority_tag = String(formMeta.spec_priority_tag || '');
  if (formKind === 'reading') {
    payload.no_kanji = !!formMeta.no_kanji;
    payload.is_restricted = !!formMeta.is_restricted;
    payload.restricted_to_kanji = Array.isArray(formMeta.restricted_to_kanji)
      ? formMeta.restricted_to_kanji.slice()
      : [];
  }
  return payload;
}
export function buildFormsMetaSpan(formKind, formText, innerHtml, formsMetaBundle, escapeFn) {
  var text = String(formText || '');
  if (!text) return '';
  var payload = buildFormsMetaPayload(formKind, text, formsMetaBundle);
  var encodedMeta = '';
  try {
    encodedMeta = encodeURIComponent(JSON.stringify(payload));
  } catch (e) {
    encodedMeta = '';
  }
  var attrs = 'class="headword-component headword-meta-component"';
  attrs += ' data-seg="' + escapeFn(text) + '"';
  attrs += ' data-meta-kind="' + escapeFn(String(formKind || '')) + '"';
  attrs += ' data-meta-form="' + escapeFn(text) + '"';
  if (encodedMeta) {
    attrs += ' data-form-meta="' + escapeFn(encodedMeta) + '"';
  }
  return '<span ' + attrs + '>' + innerHtml + '</span>';
}

// Annotate a forms header with inline romaji slashes next to each reading.
// Input:  "?�??"        -> "?/de�??/ide"
// Input:  "????"        -> "???/de?"
// Input:  "?�?, ????" -> "?/te�?/de, ???/de?"
// Returns HTML (already escaped) with romaji in styled spans and metadata chips.
export function buildFormsHeaderWithRomaji(formsText, escapeFn, formsMetaBundle) {
  var hasRomajiEngine = !!(
    window.RomajiEngine &&
    window.RomajiEngine.containsKana &&
    window.RomajiEngine.toRomaji
  );
  // Helper: romanize a single kana token
  function romanizeKana(kana) {
    if (!hasRomajiEngine || !kana || !window.RomajiEngine.containsKana(kana)) return '';
    var rom = window.RomajiEngine.toRomaji(kana);
    return rom
      ? '<span style="color:#888;font-style:italic;font-weight:normal;">/' + escapeFn(rom) + '</span>'
      : '';
  }
  // Helper: annotate a single segment (no �) with inline romaji and metadata
  function annotateSegment(seg, kind) {
    var text = String(seg || '');
    if (!text) return '';
    var inner = escapeFn(text);
    if (kind === 'reading') {
      inner += romanizeKana(text);
    }
    return buildFormsMetaSpan(kind, text, inner, formsMetaBundle, escapeFn);
  }
  // Helper: annotate a form that may contain �-separated segments
  function annotateFormByKind(rawStr, kind) {
    var parts = String(rawStr || '').split('\u30FB');
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      out.push(annotateSegment(parts[i], kind));
    }
    return out.join('\u30FB');
  }
  // Split on ", " to get individual forms (e.g., "?�?, ????")
  var forms = formsText.split(/,\s*/);
  var htmlParts = [];
  for (var fi = 0; fi < forms.length; fi++) {
    var form = forms[fi].trim();
    if (!form) continue;
    // Check for kanji?reading? bracket notation
    var bracketMatch = form.match(/^(.+?)\u3010(.+?)\u3011$/);
    if (bracketMatch) {
      var kanji = bracketMatch[1];
      var reading = bracketMatch[2];
      htmlParts.push(
        annotateFormByKind(kanji, 'kanji') + '\u3010' + annotateFormByKind(reading, 'reading') + '\u3011'
      );
    } else {
      // Pure kana/readings or reading-only entry headers.
      var inferredKind = 'reading';
      if (formsMetaBundle && formsMetaBundle.kanji_by_form && formsMetaBundle.kanji_by_form[form]) {
        inferredKind = 'kanji';
      } else if (
        formsMetaBundle &&
        formsMetaBundle.readings_by_form &&
        formsMetaBundle.readings_by_form[form]
      ) {
        inferredKind = 'reading';
      } else if (!hasRomajiEngine || !window.RomajiEngine.containsKana(form)) {
        inferredKind = 'kanji';
      }
      htmlParts.push(annotateFormByKind(form, inferredKind));
    }
  }
  return htmlParts.join(', ');
}
// Stacked layout for Japanese entries: forms header on its own line,
// then a 2-column grid (POS | sense) underneath � same columnar feel
// as the Chinese 4-column grid but without cramming forms into col 1.
// DEBUG MAP: stacked/header-based sense renderer (Japanese-style and similar).
// Provenance/edit is injected into the first visible forms/header row here.
export function renderStackedSenseLines(senses, skipHead, formsMetaByHeader, options) {
  var opts = options || {};
  var forceSenseHead = !!opts.forceSenseHead;
  var entryMetaHtml = String(opts.entryMetaHtml || '');
  // Count \x1E headers. For a single header, only suppress when it
  // duplicates the popup head text.
  var headerCount = 0;
  var singleHeaderText = '';
  for (var ci = 0; ci < senses.length; ci++) {
    if (senses[ci] && senses[ci].charAt(0) === '\x1E') {
      headerCount++;
      singleHeaderText = senses[ci].substring(1).trim();
    }
  }
  var skipHeadText = String(skipHead || '').trim();
  // For Japanese, never suppress � the header carries inline romaji even when
  // the text duplicates the headword.  Other languages suppress to avoid redundancy.
  var suppressSingleHeader =
    !forceSenseHead &&
    !isJapaneseLanguage() &&
    headerCount === 1 &&
    !!skipHeadText &&
    singleHeaderText === skipHeadText;
  var html = '';
  var isFirstEntry = true;
  var gridOpen = false;
  var metaInjected = false;
  for (var li = 0; li < senses.length; li++) {
    var line = senses[li];
    if (!line || !line.trim()) continue;
    // \x1E prefix = full-width forms header
    if (line.charAt(0) === '\x1E') {
      // Close previous grid if open
      if (gridOpen) {
        html += '</div>';
        gridOpen = false;
      }
      if (!suppressSingleHeader) {
        var formsText = line.substring(1);
        if (!isFirstEntry) {
          html += '<div style="margin-top:8px;border-top:1px solid #e5e7eb;padding-top:6px;"></div>';
        }
        if (formsText) {
          var formsMetaBundle = null;
          if (formsMetaByHeader && typeof formsMetaByHeader === 'object') {
            formsMetaBundle =
              formsMetaByHeader[formsText] || formsMetaByHeader[String(formsText || '').trim()] || null;
          }
          var formsHeaderHtml = buildFormsHeaderWithRomaji(formsText, escapeHtml, formsMetaBundle);
          // DEBUG MAP: first stacked header row gets the provenance/edit bundle.
          if (!metaInjected && entryMetaHtml) {
            formsHeaderHtml =
              '<span class="sense-head-inline"><span class="sense-head-inline-main">' +
              formsHeaderHtml +
              '</span>' +
              entryMetaHtml +
              '</span>';
            metaInjected = true;
          }
          html +=
            '<div style="font-weight:bold;font-size:13px;line-height:1.5;margin-bottom:2px;">' +
            formsHeaderHtml +
            '</div>';
        }
      }
      // Open a 2-column grid for senses
      html +=
        '<div style="display:grid;grid-template-columns:auto 1fr;gap:0 12px;align-items:start;font-size:12px;line-height:1.8;">';
      gridOpen = true;
      isFirstEntry = false;
      continue;
    }
    var tabCount = 0;
    for (var ci = 0; ci < line.length; ci++) {
      if (line[ci] === '\t') tabCount++;
      else break;
    }
    var content = line.substring(tabCount);
    if (!content || !content.trim()) continue;
    if (tabCount === 2) {
      // POS + sense
      var parts = content.split('\t');
      if (parts.length >= 2) {
        var pos = parts[0],
          sense = parts.slice(1).join('\t');
        html += pos
          ? '<div style="color:#888;font-size:11px;">[' + escapeHtml(pos) + ']</div>'
          : '<div></div>';
        html += '<div class="panel-segmentable" style="color:#333;">' + renderSenseText(sense) + '</div>';
      }
    } else {
      // Continuation sense or shared misc note
      var trimmed = content.trim();
      if (isSharedMiscNoteText(trimmed)) {
        html += '<div></div><div>' + renderSharedMiscNoteHtml(trimmed) + '</div>';
      } else {
        html +=
          '<div></div><div class="panel-segmentable" style="color:#333;">' +
          renderSenseText(trimmed) +
          '</div>';
      }
    }
  }
  if (gridOpen) html += '</div>';
  return html;
}
// Extract first sense as plain text for fuzzy preview
export function getFirstSenseText(senses) {
  if (!senses || !senses.length) return '';
  for (var i = 0; i < senses.length; i++) {
    var line = senses[i];
    if (!line || !line.trim()) continue;
    // Skip \x1E forms-header lines
    if (line.charAt(0) === '\x1E') continue;
    var tabCount = 0;
    for (var ci = 0; ci < line.length; ci++) {
      if (line[ci] === '\t') tabCount++;
      else break;
    }
    var content = line.substring(tabCount);
    if (tabCount === 0) {
      var parts = content.split('\t');
      if (parts.length >= 4) {
        return parts.slice(3).join(' ').substring(0, 100);
      }
    } else if (tabCount === 2) {
      var parts2 = content.split('\t');
      if (parts2.length >= 2) {
        return parts2.slice(1).join(' ').substring(0, 100);
      }
    } else {
      return content.trim().substring(0, 100);
    }
  }
  return '';
}
// Render unknown word with spelling and romanization
export function renderUnknownWord(spelling, g2pData) {
  var html = '';
  if (spelling) {
    html += '<div style="margin-bottom:2px;">' + escapeHtml(spelling) + '</div>';
  }
  html += renderPopupRomanLine(g2pData);
  return html;
}
export function applyNoteToPopup(head, note) {
  if (!hoverLayoutState.notePopup) return;
  if (head !== segmentRenderingState.currentPopupHead) return;
  note = note || '';
  if (note.trim()) {
    hoverLayoutState.notePopup.textContent = note;
    hoverLayoutState.notePopup.style.display = 'block';
    hoverLayoutState.hoverPopupContainer.style.display = 'flex';
  } else {
    hoverLayoutState.notePopup.textContent = '';
    hoverLayoutState.notePopup.style.display = 'none';
  }
}
export function updateNotePopupForHead(head) {
  if (!hoverLayoutState.notePopup) return;
  segmentRenderingState.currentPopupHead = head || null;
  if (!head) {
    hoverLayoutState.notePopup.textContent = '';
    hoverLayoutState.notePopup.style.display = 'none';
    return;
  }
  if (segmentRenderingState.noteCache.has(head)) {
    applyNoteToPopup(head, segmentRenderingState.noteCache.get(head));
    return;
  }
  fetch('/annotation?head=' + encodeURIComponent(head))
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      if (head !== segmentRenderingState.currentPopupHead) return;
      var note = data && data.ok && typeof data.note === 'string' ? data.note : '';
      segmentRenderingState.noteCache.set(head, note);
      applyNoteToPopup(head, note);
    })
    .catch(function () {
      if (head !== segmentRenderingState.currentPopupHead) return;
      segmentRenderingState.noteCache.set(head, '');
      applyNoteToPopup(head, '');
    });
}
export function setupAnnotationBox(head) {
  var area = document.getElementById('dict-annotation');
  var statusEl = document.getElementById('dict-annotation-status');
  if (!area) return;
  fetch('/annotation?head=' + encodeURIComponent(head))
    .then(function (resp) {
      return resp.json();
    })
    .then(function (data) {
      var note = data && data.ok && typeof data.note === 'string' ? data.note : '';
      area.value = note;
      segmentRenderingState.noteCache.set(head, note);
      if (statusEl) statusEl.textContent = note ? 'Saved' : '';
    })
    .catch(function () {
      if (statusEl) statusEl.textContent = 'Could not load note';
    });
  var saveNote = debounce(function () {
    var value = area.value || '';
    fetch('/annotation', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        head: head,
        note: value
      })
    })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (!data || !data.ok) {
          if (statusEl) statusEl.textContent = 'Error saving';
          return;
        }
        segmentRenderingState.noteCache.set(head, value);
        if (statusEl) {
          statusEl.textContent = value.trim() ? 'Saved' : 'Note cleared';
        }
        if (segmentRenderingState.currentPopupHead === head) {
          applyNoteToPopup(head, value);
        }
      })
      .catch(function () {
        if (statusEl) statusEl.textContent = 'Error saving';
      });
  }, 500);
  area.oninput = function () {
    if (statusEl) statusEl.textContent = 'Saving...';
    saveNote();
  };
}
// DOM refs
export function initializeAnnotations() {
  window._blockHasOverlap = _blockHasOverlap;
  window.normalizeLinePositions = normalizeLinePositions;
  return true;
}
