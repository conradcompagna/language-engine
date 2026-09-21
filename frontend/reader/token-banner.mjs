import { renderSyntheticEntryBar, sendSyntheticEntries } from './custom-entry-state.mjs';
import { documentShellState } from './document-shell.state.mjs';
import {
  getCanonicalTokenEntry,
  getCanonicalTokenSurfaceText,
  getLookupEntryFillMode,
  getLookupEntryFills,
  getLookupEntryResolvedVia,
  getMwtPartSurfaceSliceText,
  getRenderableLlmGlossRows,
  getTokenBannerSurfaceText,
  getTokenMapAnchorText,
  getTokenMapLookupText
} from './entry-editing.mjs';
import { buildG2PMiniRowHtml, buildG2PMiniRows } from './flashcards.mjs';
import {
  buildLlmGlossUpgradeMessageHtml,
  getCanonicalTokenDictFill,
  getCanonicalTokenResolvedVia,
  getLlmGlossEntryForSeg,
  getTokenBannerLemmaInfo,
  hasLlmGlossEntryForSeg,
  resolveSyntheticGenerationTargets,
  setExpandableBannerExpanded,
  shouldShowLlmGlossUpgradeMessage,
  tokenShouldShowSynthHint,
  wireExpandableBannerToggle
} from './gloss-entries.mjs';
import { uposColorForTag } from './gloss-requests.mjs';
import {
  buildAlwaysHoverableLemmaHtml,
  filterFeatsForLang,
  getDependencyHoverText,
  getFeatDescription,
  getXposDescription,
  normalizeDepLabel,
  normalizeGrammarMetaValue
} from './grammar-popup.mjs';
import { hoverLayoutState } from './hover-layout.state.mjs';
import { _filterDictFillForMwtPart } from './mwt-context.mjs';
import {
  captureUiRenderBannerSnapshot,
  escapeHtml,
  getEntryDisplayHead,
  getLemmaDisplayMeta,
  getTrimmedDisplayText,
  hasSameVisibleComparisonText,
  stripZeroWidthJoiners
} from './presentation.mjs';
import { getG2PMiniGroupTextSets, upgradePendingPanelSurfaceTokens } from './pronunciation-panel.mjs';
import { getExactSidePanelLookupEntry, setExactSidePanelLookupEntry } from './segment-rendering.mjs';
import { displayDictEntry, isUnknownDictEntry } from './side-panel.mjs';
import {
  buildTokenBannerLemmaHtml,
  buildTokenBannerMwtChildrenHtml,
  buildTokenBannerMwtLookupHtml,
  buildTokenBannerSurfaceHtml
} from './token-banner-menu.mjs';
import { tokenBannerMenuState } from './token-banner-menu.state.mjs';
import {
  buildTokenMapGroupedFillEntry,
  ensureTokenMapLookupEntries,
  getRenderableTokenMapDisplaySliceItems,
  getTokenMapFillIndexesFromRaw,
  getTokenMapLemmaPartHintRows,
  getTokenMapLemmaPartTexts,
  getTokenMapPreferredLemmaLookupXpos,
  getTokenResolutionInfo,
  resolveTokenMapLookupEntry
} from './token-map.mjs';
export function renderTokenBanner(activeFillKey) {
  var banner = document.getElementById('token-banner');
  var synthBar = document.getElementById('synth-entry-bar');
  if (!banner || !hoverLayoutState.tokenMapData) {
    if (banner) banner.style.display = 'none';
    if (synthBar) synthBar.style.display = 'none';
    return;
  }
  var d = hoverLayoutState.tokenMapData;
  var posData = d.posData || {};
  var udTok = d.udTok || {};
  var _tbParentSurfaceForSlice = String(getTokenBannerSurfaceText(d) || '');
  var _tbLookupText = String(getTokenMapLookupText(d) || '').trim();
  var _tbChildSliceText = String(getTokenMapAnchorText(d) || '').trim();
  var _tbIsSurfaceAnchorPopupOnly = String(d.mwtPopupReason || '').trim() === 'surface_anchor';
  if (isFinite(Number(d.mwtPartIndex))) {
    var _tbPi = Number(d.mwtPartIndex);
    if (!_tbChildSliceText) {
      _tbChildSliceText = getMwtPartSurfaceSliceText(_tbParentSurfaceForSlice, d.udTok, _tbPi, '');
    }
    if (!_tbLookupText) _tbLookupText = String(d.mwtChildText || '').trim();
    if (!_tbChildSliceText && !_tbIsSurfaceAnchorPopupOnly && d.mwtChildText)
      _tbChildSliceText = String(d.mwtChildText);
  }
  var surface = _tbChildSliceText || _tbParentSurfaceForSlice;
  var lemmaInfo = getTokenBannerLemmaInfo(d);
  var lemma = String(lemmaInfo.lemma || '');
  var lemmaRaw = String(lemmaInfo.raw || '').trim();
  var resolvedVia = getCanonicalTokenResolvedVia(d);
  var dictFill = getCanonicalTokenDictFill(d);
  var lemmaMeta = getLemmaDisplayMeta(lemma, lemmaRaw);
  var lemmaText = lemmaMeta.lemma || lemma;
  var _tbPartIdxInit = isFinite(Number(d.mwtPartIndex)) ? Number(d.mwtPartIndex) : -1;
  var _tbMwtPartsInit = udTok && Array.isArray(udTok.mwt_parts) ? udTok.mwt_parts : [];
  var _tbChild =
    _tbPartIdxInit >= 0 && _tbMwtPartsInit[_tbPartIdxInit] ? _tbMwtPartsInit[_tbPartIdxInit] : null;
  function _tbSliceByIdx(val) {
    if (_tbPartIdxInit < 0 || !val || val.indexOf('+') === -1) return val;
    var parts = String(val).split('+');
    return _tbPartIdxInit < parts.length ? parts[_tbPartIdxInit].trim() : val;
  }
  var uposLabel = posData.upos_label || posData.upos || '' || '';
  uposLabel = _tbSliceByIdx(uposLabel);
  if (_tbChild && _tbChild.upos) uposLabel = String(_tbChild.upos);
  var uposColor = posData.upos_color || '';
  var xposLabel = String(posData.tag || posData.xpos || '').trim();
  var _tbLang = String(documentShellState.currentLanguage || '')
    .trim()
    .toLowerCase();
  var _tbKeepTokenXpos = _tbLang === 'ko' || _tbLang === 'korean' || _tbLang.indexOf('ko-') === 0;
  if (!_tbKeepTokenXpos) xposLabel = _tbSliceByIdx(xposLabel);
  if (_tbChild && (_tbChild.tag || _tbChild.xpos)) xposLabel = String(_tbChild.tag || _tbChild.xpos);
  var depLabel = normalizeDepLabel(posData.dep_label || posData.dep || '' || udTok.dep || '');
  depLabel = _tbSliceByIdx(depLabel);
  if (_tbChild && _tbChild.dep) depLabel = normalizeDepLabel(String(_tbChild.dep));
  var featsValue = filterFeatsForLang(normalizeGrammarMetaValue(posData.feats || '' || udTok.feats || ''));
  featsValue = _tbSliceByIdx(featsValue);
  if (_tbChild && _tbChild.lemma) {
    lemma = String(_tbChild.lemma);
    lemmaRaw = lemma;
    lemmaMeta = getLemmaDisplayMeta(lemma, lemmaRaw);
    lemmaText = lemmaMeta.lemma || lemma;
  }
  tokenBannerMenuState._bannerActiveFillKey =
    typeof activeFillKey === 'string' ? activeFillKey : tokenBannerMenuState._bannerActiveFillKey;

  // -- Resolve dep tree context: parent + children --
  var depParentText = '';
  var depChildrenInfo = [];
  var gramTokens =
    hoverLayoutState.latestData &&
    hoverLayoutState.latestData.grammar_overlay &&
    Array.isArray(hoverLayoutState.latestData.grammar_overlay.tokens)
      ? hoverLayoutState.latestData.grammar_overlay.tokens
      : [];
  if (gramTokens.length && typeof d.segIdx === 'number') {
    var _curTok = null;
    for (var _gti = 0; _gti < gramTokens.length; _gti++) {
      if (gramTokens[_gti] && gramTokens[_gti].i === d.segIdx) {
        _curTok = gramTokens[_gti];
        break;
      }
    }
    if (_curTok) {
      if (_curTok.head !== undefined && _curTok.head !== _curTok.i) {
        for (var _gpi = 0; _gpi < gramTokens.length; _gpi++) {
          if (gramTokens[_gpi] && gramTokens[_gpi].i === _curTok.head) {
            depParentText = String(gramTokens[_gpi].text || '');
            break;
          }
        }
      }
      for (var _gci = 0; _gci < gramTokens.length; _gci++) {
        var _ct = gramTokens[_gci];
        if (_ct && _ct.head === _curTok.i && _ct.i !== _curTok.i) {
          depChildrenInfo.push({
            text: String(_ct.text || ''),
            dep: normalizeDepLabel(String(_ct.dep || _ct.deprel || ''))
          });
        }
      }
    }
  }
  var surfaceHtml = buildTokenBannerSurfaceHtml(d, surface);
  var lemmaHtml = buildTokenBannerLemmaHtml(d, lemmaText, lemmaRaw);
  // Per-child MWT banner mode: show the unsandhied child text as the MWT row
  // when it differs from the orthographic surface slice (sandhi). Otherwise
  // fall back to the parent-mode joined-children row for non-MWT-child tokens.
  var _tbIsMwtChild = isFinite(Number(d.mwtPartIndex));
  var mwtChildrenHtml = '';
  var showMwtRow = false;
  if (_tbIsMwtChild) {
    var _tbPartIdx = Number(d.mwtPartIndex);
    var _tbChildText = _tbLookupText || String(d.mwtChildText || '').trim();
    var _tbSliceText = String(d.mwtSurfaceSlice || surface || '').trim();
    if (_tbChildText && _tbSliceText && !hasSameVisibleComparisonText(_tbChildText, _tbSliceText)) {
      mwtChildrenHtml = buildTokenBannerMwtLookupHtml(d, _tbChildText, _tbPartIdx);
      showMwtRow = true;
    }
  } else {
    mwtChildrenHtml = buildTokenBannerMwtChildrenHtml(d, udTok, surface);
    showMwtRow = !!mwtChildrenHtml;
  }
  var lemmaCompareText = String((lemmaMeta && (lemmaMeta.raw || lemmaMeta.lemma)) || lemmaText || '').trim();
  var _tbLemmaCompareSurface = _tbPartIdxInit >= 0 && _tbLookupText ? _tbLookupText : surface;
  var lemmaIsSame = !!(
    lemmaCompareText &&
    !lemmaMeta.hasRawSuffix &&
    hasSameVisibleComparisonText(lemmaCompareText, _tbLemmaCompareSurface)
  );
  var showLemmaRow = !!(lemmaHtml && !lemmaIsSame);
  var entrySliceItems = getRenderableTokenMapDisplaySliceItems(d);
  var _tbResolutionEntry = d.tokenEntry || d.entry;
  if (_tbPartIdxInit >= 0) {
    var _tbFiltered = _filterDictFillForMwtPart(dictFill, _tbPartIdxInit);
    if (_tbFiltered && Array.isArray(_tbFiltered.rows) && _tbFiltered.rows.length) {
      dictFill = _tbFiltered.rows;
      var _tbKeepIdx = {};
      for (var _tbki = 0; _tbki < _tbFiltered.origIndexes.length; _tbki++) {
        _tbKeepIdx[String(_tbFiltered.origIndexes[_tbki])] = true;
      }
      var _tbFilteredItems = [];
      for (var _tbii = 0; _tbii < entrySliceItems.length; _tbii++) {
        var _tbIt = entrySliceItems[_tbii] || {};
        var _tbFi = Array.isArray(_tbIt.fillIndexes) ? _tbIt.fillIndexes : [];
        var _tbAny = false;
        for (var _tbfj = 0; _tbfj < _tbFi.length; _tbfj++) {
          if (_tbKeepIdx[String(_tbFi[_tbfj])]) {
            _tbAny = true;
            break;
          }
        }
        if (_tbAny) _tbFilteredItems.push(_tbIt);
      }
      entrySliceItems = _tbFilteredItems;
      if (_tbResolutionEntry) {
        var _tbReClone = {};
        for (var _tbRk in _tbResolutionEntry) {
          if (Object.prototype.hasOwnProperty.call(_tbResolutionEntry, _tbRk))
            _tbReClone[_tbRk] = _tbResolutionEntry[_tbRk];
        }
        _tbReClone.dict_fill = dictFill.slice();
        _tbResolutionEntry = _tbReClone;
      }
    }
  }
  var resolutionInfo = getTokenResolutionInfo(surface, lemmaText, _tbResolutionEntry, dictFill, resolvedVia);
  var showResolvedRow = !!(resolutionInfo && resolutionInfo.primary);
  var resolvedText = showResolvedRow ? resolutionInfo.primary : '\u2014';
  var showEntriesRow = !!entrySliceItems.length;
  var tokenG2PEntry = getCanonicalTokenEntry(d) || d.entry || null;
  var g2pMiniRows = buildG2PMiniRows(
    surface,
    String(documentShellState.currentLanguage || ''),
    tokenG2PEntry && tokenG2PEntry.g2p,
    {
      groupTextSets: getG2PMiniGroupTextSets(surface, udTok, tokenG2PEntry)
    }
  );
  var orthRowHtml = g2pMiniRows ? buildG2PMiniRowHtml('graph', g2pMiniRows.orthCellsHtml) : '';
  var romRowHtml = g2pMiniRows ? buildG2PMiniRowHtml('pron', g2pMiniRows.pronCellsHtml) : '';
  var showOrthRow = !!orthRowHtml;
  var showRomRow = !!romRowHtml;
  var _hasBannerGloss = !!hasLlmGlossEntryForSeg(d.segIdx);
  var _hasBannerGlossUpgrade = !_hasBannerGloss && shouldShowLlmGlossUpgradeMessage();
  var _hasBannerDecomp = false;
  var hasExpandableRows = !!(
    showMwtRow ||
    showOrthRow ||
    showRomRow ||
    showLemmaRow ||
    depLabel ||
    depChildrenInfo.length ||
    uposLabel ||
    xposLabel ||
    featsValue ||
    _hasBannerGloss ||
    _hasBannerGlossUpgrade ||
    _hasBannerDecomp
  );
  var bannerExpanded = !!(hoverLayoutState.tokenMapVisible && hasExpandableRows);
  var resolvedCategoryClass = '';
  if (resolutionInfo && resolutionInfo.category) {
    resolvedCategoryClass =
      ' tb-pill-resolution-' +
      String(resolutionInfo.category)
        .replace(/[^a-z0-9_-]+/gi, '-')
        .toLowerCase();
  }
  var html = '';
  var toggleAttrs = hasExpandableRows
    ? ' id="tb-banner-toggle" role="button" tabindex="0" aria-expanded="' +
      (bannerExpanded ? 'true' : 'false') +
      '" aria-label="Toggle token details"'
    : '';
  html += '<div class="tb-strip' + (hasExpandableRows ? ' tb-strip-expandable' : '') + '">';
  html += '<div class="tb-stack">';
  html += '<div class="tb-header"' + toggleAttrs + '>';
  html += '<div class="tb-info-row">';
  html += '<span class="tb-slot-label">Surface</span>';
  html +=
    '<span class="tb-slot-value tb-surface-wrap">' +
    (surfaceHtml ||
      buildAlwaysHoverableLemmaHtml(surface, d.headDecompByForm, documentShellState.currentLanguage || '')) +
    '</span>';
  html += '</div>';
  if (hasExpandableRows) {
    html +=
      '<span class="tb-expand-indicator" aria-hidden="true"><span class="tb-arrow">&#9662;</span></span>';
  }
  html += '</div>';
  if (hasExpandableRows) {
    html += '<div class="tb-expand-rows">';
    if (showMwtRow) {
      html += '<div class="tb-info-row">';
      html += '<span class="tb-slot-label">MWT</span>';
      html += '<span class="tb-slot-value tb-mwt-wrap">' + mwtChildrenHtml + '</span>';
      html += '</div>';
    }
    if (showOrthRow) {
      html += '<div class="tb-info-row">';
      html += '<span class="tb-slot-label">Orth</span>';
      html += '<span class="tb-slot-value tb-g2p-slot">' + orthRowHtml + '</span>';
      html += '</div>';
    }
    if (showRomRow) {
      html += '<div class="tb-info-row">';
      html += '<span class="tb-slot-label">Rom</span>';
      html += '<span class="tb-slot-value tb-g2p-slot">' + romRowHtml + '</span>';
      html += '</div>';
    }
    if (depLabel) {
      var _tbDepParts = depLabel.indexOf('+') !== -1 ? depLabel.split('+') : [depLabel];
      var _tbDepPills = '';
      for (var _tdi = 0; _tdi < _tbDepParts.length; _tdi++) {
        var _tdTag = _tbDepParts[_tdi].trim();
        if (!_tdTag) continue;
        var _tdGloss = getDependencyHoverText(_tdTag);
        var _tdDisplay = _tdGloss || _tdTag;
        var _tdUnknown = !_tdGloss;
        _tbDepPills +=
          '<span class="tb-pill tb-grammar-pill tb-pill-desc"' +
          (_tdUnknown ? ' style="color:#dc2626;border-color:#ef4444;"' : '') +
          ' data-tb-desc="' +
          escapeHtml(_tdUnknown ? '' : _tdTag) +
          '">' +
          escapeHtml(_tdDisplay) +
          '</span>';
      }
      if (_tbDepPills) {
        html += '<div class="tb-info-row tb-info-row-grammar">';
        html += '<span class="tb-slot-label">Dep</span>';
        html += '<span class="tb-slot-value tb-grammar-value">';
        html += _tbDepPills;
        if (depParentText) {
          var tbPsrApi = window.PanelSegmentRenderer || null;
          var depParentHtml =
            tbPsrApi && typeof tbPsrApi.renderLookupSpanHtml === 'function'
              ? tbPsrApi.renderLookupSpanHtml(depParentText, {
                  displayText: stripZeroWidthJoiners(depParentText),
                  extraClasses: ['tb-dep-ctx-token']
                })
              : escapeHtml(stripZeroWidthJoiners(depParentText));
          html += '<span class="tb-dep-ctx">\u2190 ' + depParentHtml + '</span>';
        }
        html += '</span>';
        html += '</div>';
      }
    }
    if (depChildrenInfo.length) {
      var chHtml = '';
      for (var chi = 0; chi < depChildrenInfo.length; chi++) {
        var ch = depChildrenInfo[chi];
        var chDepText = getDependencyHoverText(ch.dep);
        var _tbChDepDisplay = chDepText || ch.dep;
        var _tbChDepUnknown = !chDepText;
        var tbChildPsrApi = window.PanelSegmentRenderer || null;
        chHtml +=
          tbChildPsrApi && typeof tbChildPsrApi.renderLookupSpanHtml === 'function'
            ? tbChildPsrApi.renderLookupSpanHtml(ch.text, {
                displayText: stripZeroWidthJoiners(ch.text),
                extraClasses: ['tb-dep-ctx-token']
              })
            : escapeHtml(stripZeroWidthJoiners(ch.text));
        if (ch.dep)
          chHtml +=
            '<span class="tb-pill tb-grammar-pill tb-pill-desc tb-child-dep-pill"' +
            (_tbChDepUnknown ? ' style="color:#dc2626;border-color:#ef4444;"' : '') +
            ' data-tb-desc="' +
            escapeHtml(_tbChDepUnknown ? '' : ch.dep) +
            '">' +
            escapeHtml(_tbChDepDisplay) +
            '</span>';
      }
      html += '<div class="tb-info-row tb-info-row-grammar">';
      html += '<span class="tb-slot-label">Children</span>';
      html += '<span class="tb-slot-value tb-grammar-value">' + chHtml + '</span>';
      html += '</div>';
    }
    if (uposLabel) {
      var _tbUposParts = uposLabel.indexOf('+') !== -1 ? uposLabel.split('+') : [uposLabel];
      var _tbUposPills = '';
      for (var _tui = 0; _tui < _tbUposParts.length; _tui++) {
        var _tuTag = _tbUposParts[_tui].trim();
        if (!_tuTag) continue;
        var _tuColor = uposColorForTag(_tuTag);
        var _tuStyle = _tuColor
          ? 'background-color:' + escapeHtml(String(_tuColor)) + ';color:#000;border-color:transparent;'
          : '';
        _tbUposPills +=
          '<span class="tb-pill tb-grammar-pill tb-pill-upos" style="' +
          _tuStyle +
          '">' +
          escapeHtml(_tuTag) +
          '</span>';
      }
      if (_tbUposPills) {
        html += '<div class="tb-info-row tb-info-row-grammar">';
        html += '<span class="tb-slot-label">UPoS</span>';
        html += '<span class="tb-slot-value tb-grammar-value">' + _tbUposPills + '</span>';
        html += '</div>';
      }
    }
    if (xposLabel) {
      var xposParts = /[+\uFF0B]/.test(xposLabel) ? xposLabel.split(/[+\uFF0B]/) : [xposLabel];
      var xHtml = '';
      for (var xi = 0; xi < xposParts.length; xi++) {
        var xtag = xposParts[xi].trim();
        if (!xtag) continue;
        var xDesc = getXposDescription(xtag);
        var _tbXDisplay = xDesc || xtag;
        var _tbXUnknown = !xDesc;
        xHtml +=
          '<div class="tb-xpos-stack-item"><span class="tb-pill tb-grammar-pill tb-pill-desc"' +
          (_tbXUnknown ? ' style="color:#dc2626;border-color:#ef4444;"' : '') +
          ' data-tb-desc="' +
          escapeHtml(_tbXUnknown ? '' : xtag) +
          '">' +
          escapeHtml(_tbXDisplay) +
          '</span></div>';
      }
      if (xHtml) {
        html += '<div class="tb-info-row tb-info-row-grammar">';
        html += '<span class="tb-slot-label">XPoS</span>';
        html += '<span class="tb-slot-value tb-grammar-value">' + xHtml + '</span>';
        html += '</div>';
      }
    }
    if (featsValue) {
      var _tbFeatBundles = featsValue.indexOf('+') !== -1 ? featsValue.split('+') : [featsValue];
      var _tbIsMwtFeats = _tbFeatBundles.length > 1;
      if (_tbIsMwtFeats) {
        // Column table layout � one column per subword, feats top-to-bottom
        var _tbColumns = [];
        var _tbMaxRows = 0;
        for (var _tbi = 0; _tbi < _tbFeatBundles.length; _tbi++) {
          var _tbBundle = _tbFeatBundles[_tbi].trim();
          var _tbCol = [];
          if (_tbBundle) {
            var _tbFeats = _tbBundle.split('|');
            for (var _tfi = 0; _tfi < _tbFeats.length; _tfi++) {
              var _tbF = _tbFeats[_tfi].trim();
              if (!_tbF) continue;
              var _tbFDesc = getFeatDescription(_tbF);
              var _tbFDisplay = _tbFDesc || _tbF;
              var _tbFUnknown = !_tbFDesc;
              _tbCol.push(
                '<span class="tb-pill tb-grammar-pill tb-pill-desc"' +
                  (_tbFUnknown ? ' style="color:#dc2626;border-color:#ef4444;"' : '') +
                  ' data-tb-desc="' +
                  escapeHtml(_tbFUnknown ? '' : _tbF) +
                  '">' +
                  escapeHtml(_tbFDisplay) +
                  '</span>'
              );
            }
          }
          if (_tbCol.length === 0)
            _tbCol.push('<span class="tb-pill tb-grammar-pill tb-feat-empty">\u2014</span>');
          _tbColumns.push(_tbCol);
          if (_tbCol.length > _tbMaxRows) _tbMaxRows = _tbCol.length;
        }
        // Flexbox layout: each morpheme column is a flex item stacking its pills
        // vertically. flex-wrap:wrap lets columns flow to the next line when there
        // isn't enough horizontal room, regardless of column count or pill width.
        var _tbInner = '<div style="display:flex;flex-wrap:wrap;gap:4px 0;">';
        for (var _ci = 0; _ci < _tbColumns.length; _ci++) {
          _tbInner +=
            '<div style="display:flex;flex-direction:column;min-width:80px;max-width:160px;margin-right:12px;margin-bottom:4px;">';
          for (var _pi = 0; _pi < _tbColumns[_ci].length; _pi++) {
            _tbInner += _tbColumns[_ci][_pi];
          }
          _tbInner += '</div>';
        }
        _tbInner += '</div>';
        html += '<div class="tb-info-row tb-info-row-grammar">';
        html += '<span class="tb-slot-label">Feats</span>';
        html += '<span class="tb-slot-value tb-grammar-value">' + _tbInner + '</span>';
        html += '</div>';
      } else {
        var _tbFeats = _tbFeatBundles[0].trim().split('|');
        var _tbHasFeat = false;
        for (var _tfi = 0; _tfi < _tbFeats.length; _tfi++) {
          var _tbF = _tbFeats[_tfi].trim();
          if (!_tbF) continue;
          var _tbFDesc = getFeatDescription(_tbF);
          var _tbFDisplay = _tbFDesc || _tbF;
          var _tbFUnknown = !_tbFDesc;
          var _tbPill =
            '<span class="tb-pill tb-grammar-pill tb-pill-desc"' +
            (_tbFUnknown ? ' style="color:#dc2626;border-color:#ef4444;"' : '') +
            ' data-tb-desc="' +
            escapeHtml(_tbFUnknown ? '' : _tbF) +
            '">' +
            escapeHtml(_tbFDisplay) +
            '</span>';
          html += '<div class="tb-info-row tb-info-row-grammar">';
          html += '<span class="tb-slot-label">' + (!_tbHasFeat ? 'Feats' : '') + '</span>';
          html += '<span class="tb-slot-value tb-grammar-value">' + _tbPill + '</span>';
          html += '</div>';
          _tbHasFeat = true;
        }
      }
    }
    if (showLemmaRow) {
      html += '<div class="tb-info-row">';
      html += '<span class="tb-slot-label">Lemma</span>';
      html += '<span class="tb-slot-value tb-lemma-wrap">' + lemmaHtml + '</span>';
      html += '</div>';
    }
    /*
    if (showResolvedRow) {
      html += '<div class="tb-info-row">';
      html += '<span class="tb-slot-label">Resolved</span>';
      html += '<span class="tb-slot-value tb-resolved-wrap"><span class="tb-pill tb-pill-resolution' + resolvedCategoryClass + '">' + escapeHtml(resolvedText) + '</span></span>';
      html += '</div>';
    }
    if (showEntriesRow) {
      html += '<div class="tb-info-row tb-info-row-fills">';
      html += '<span class="tb-slot-label">Entries</span>';
      html += '<span class="tb-slot-value tb-fillline">';
      for (var fi3 = 0; fi3 < entrySliceItems.length; fi3++) {
        var item = entrySliceItems[fi3] || {};
        var itemText = String(item.text || '');
        var itemIndexes = Array.isArray(item.fillIndexes) ? item.fillIndexes.slice() : [];
        if (!itemText || !itemIndexes.length) continue;
        var pUnk = !!item.isUnknown;
        var pLemmaDerived = !!item.isLemmaDerived;
        var btnClass = 'tb-fill-btn';
        if (pUnk) btnClass += ' unknown';
        else if (pLemmaDerived) btnClass += ' lemma-derived';
        var fillKey = fi3 + ':' + itemIndexes.join(',');
        if (_bannerActiveFillKey === fillKey) btnClass += ' active';
        html += '<button type="button" class="' + btnClass + '" data-tb-item-index="' + escapeHtml(String(fi3)) + '" data-tb-fill-indexes="' + escapeHtml(itemIndexes.join(',')) + '" data-tb-fill-text="' + escapeHtml(itemText) + '" data-tb-fill-key="' + escapeHtml(fillKey) + '">' + escapeHtml(itemText) + '</button>';
      }
      html += '</span>';
      html += '</div>';
    }
    */
    // LLM gloss row in token banner
    var _tbGlossIdx = typeof d.segIdx === 'number' ? d.segIdx : -1;
    var _tbG = getLlmGlossEntryForSeg(_tbGlossIdx);
    var _tbGlossRowsAdded = false;
    if (_tbG) {
      var _tbPartIdx = isFinite(Number(d.mwtPartIndex)) ? Number(d.mwtPartIndex) : -1;
      var _tbGlossRows = getRenderableLlmGlossRows(
        _tbG,
        surface || _tbParentSurfaceForSlice || '',
        {
          entry: d.tokenEntry || d.entry || null,
          udTok: udTok,
          posData: posData,
          lemma: lemma,
          lemma_raw: lemmaRaw
        },
        {
          isMwtChild: isFinite(Number(d.mwtPartIndex)),
          partIndex: _tbPartIdx,
          childLemma: lemmaText || ''
        }
      );
      for (var _tgi = 0; _tgi < _tbGlossRows.length; _tgi++) {
        var _tbRow = _tbGlossRows[_tgi] || {};
        var _tbGLabel = _tgi === 0 ? 'Gloss' : '';
        var _tbGLemma = String(_tbRow.lemma || '').trim();
        var _tbGVal = String(_tbRow.gloss || '').trim();
        if (!_tbGVal) continue;
        html += '<div class="tb-info-row tb-info-row-grammar">';
        html += '<span class="tb-slot-label">' + escapeHtml(_tbGLabel || 'Gloss') + '</span>';
        if (_tbGLemma) {
          html +=
            '<span class="tb-slot-value tb-grammar-value"><span class="tb-pill tb-grammar-pill" style="background:#e0f2fe;border-color:#7dd3fc;color:#0369a1;">' +
            escapeHtml(_tbGLemma) +
            '</span> <span style="color:#0369a1;">' +
            escapeHtml(_tbGVal) +
            '</span></span>';
        } else {
          html +=
            '<span class="tb-slot-value tb-grammar-value"><span style="color:#0369a1;">' +
            escapeHtml(_tbGVal) +
            '</span></span>';
        }
        html += '</div>';
        _tbGlossRowsAdded = true;
      }
    }
    if (!_tbGlossRowsAdded && _hasBannerGlossUpgrade) {
      html += '<div class="tb-info-row tb-info-row-grammar">';
      html += '<span class="tb-slot-label">Gloss</span>';
      html += '<span class="tb-slot-value tb-grammar-value">' + buildLlmGlossUpgradeMessageHtml() + '</span>';
      html += '</div>';
    }
    html += '</div>';
  }
  html += '</div>';
  html += '</div>';
  banner.innerHTML = html;
  banner.style.display = '';
  banner.classList.toggle('expanded', bannerExpanded);

  // -- Synth entry bar (separate div) --
  hoverLayoutState._synthHintActive = tokenShouldShowSynthHint(d, surface);
  renderSyntheticEntryBar(d, surface);

  // -- Wire banner events --
  wireTokenBannerEvents(banner, d, entrySliceItems, dictFill);
  if (window.PanelSegmentRenderer && typeof window.PanelSegmentRenderer.processPanel === 'function') {
    window.PanelSegmentRenderer.processPanel(banner, documentShellState.currentLanguage || '');
  }
  captureUiRenderBannerSnapshot('banner_render_complete', d);
  ensureTokenMapLookupEntries(d).then(function (changed) {
    if (!changed || hoverLayoutState.tokenMapData !== d) return;
    if (d && d.surfaceLookup) upgradePendingPanelSurfaceTokens(d.surface || '', d.surfaceLookup);
    renderTokenBanner(tokenBannerMenuState._bannerActiveFillKey);
  });
}
export function wireTokenBannerEvents(banner, d, entrySliceItems, dictFill) {
  function setBannerExpanded(nextExpanded) {
    hoverLayoutState.tokenMapVisible = !!nextExpanded;
    setExpandableBannerExpanded(banner, 'tb-banner-toggle', !!nextExpanded);
  }

  // Toggle expand/collapse from the visible banner header
  wireExpandableBannerToggle(banner, 'tb-banner-toggle', function () {
    setBannerExpanded(!banner.classList.contains('expanded'));
  });

  // Token/headword hover inside the banner is owned by PanelSegmentRenderer.

  // Fill entry clicks ? switch dict panel below
  var fillBtns = banner.querySelectorAll('.tb-fill-btn');
  for (var fli = 0; fli < fillBtns.length; fli++) {
    (function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var itemIndex = parseInt(String(btn.getAttribute('data-tb-item-index') || ''), 10);
        var item =
          isFinite(itemIndex) && itemIndex >= 0 && itemIndex < entrySliceItems.length
            ? entrySliceItems[itemIndex] || {}
            : {};
        var itemFill = Array.isArray(item.dictFill) ? item.dictFill : dictFill;
        var itemLookupEntry = item.lookupEntry || getTokenMapSurfaceLookupEntry(d);
        var fillIndexes = getTokenMapFillIndexesFromRaw(
          btn.getAttribute('data-tb-fill-indexes'),
          itemFill.length
        );
        if (!fillIndexes.length) return;
        var fillText = String(btn.getAttribute('data-tb-fill-text') || '').trim();
        var fillKey = String(btn.getAttribute('data-tb-fill-key') || '');
        var currentPanelFillKey =
          hoverLayoutState.panelContent && hoverLayoutState.panelContent.dataset
            ? String(hoverLayoutState.panelContent.dataset.bannerFillKey || '')
            : '';
        if (fillKey && currentPanelFillKey === fillKey) return;
        var currentPanelSignature =
          hoverLayoutState.panelContent && hoverLayoutState.panelContent.dataset
            ? String(hoverLayoutState.panelContent.dataset.bannerEntrySignature || '')
            : '';
        tokenBannerMenuState._bannerActiveFillKey = fillKey;
        var allBtns = banner.querySelectorAll('.tb-fill-btn');
        for (var ab = 0; ab < allBtns.length; ab++) {
          allBtns[ab].classList.toggle('active', allBtns[ab].getAttribute('data-tb-fill-key') === fillKey);
        }
        hoverLayoutState.tokenMapVisible = banner.classList.contains('expanded');
        if (fillIndexes.length === 1) {
          var idx = fillIndexes[0];
          if (!itemFill || !itemFill[idx]) return;
          var fillEntry = itemFill[idx];
          var fillHead = getEntryDisplayHead(fillEntry, '');
          if (!fillHead) return;
          var singleEntrySignature = 'single|' + String(idx) + '|' + fillHead;
          if (singleEntrySignature && currentPanelSignature === singleEntrySignature) return;
          if (hoverLayoutState.panelContent && hoverLayoutState.panelContent.dataset) {
            hoverLayoutState.panelContent.dataset.bannerFillKey = fillKey;
            hoverLayoutState.panelContent.dataset.bannerEntrySignature = singleEntrySignature;
          }
          displayDictEntry(fillEntry, fillHead, {
            _lookupLang: String(documentShellState.currentLanguage || ''),
            _panelTokenSurface: d.surface,
            _panelTokenLemma: d.lemma,
            _panelTokenLemmaRaw: d.lemma_raw || d.lemma,
            _panelBannerFillKey: fillKey,
            _panelEntrySignature: singleEntrySignature,
            _skipBannerRender: true
          });
          return;
        }
        var groupedEntry = buildTokenMapGroupedFillEntry(itemLookupEntry, fillIndexes, fillText, itemFill);
        if (!groupedEntry) return;
        var groupedEntrySignature = 'group|' + fillIndexes.join(',') + '|' + (fillText || d.surface);
        if (groupedEntrySignature && currentPanelSignature === groupedEntrySignature) return;
        if (hoverLayoutState.panelContent && hoverLayoutState.panelContent.dataset) {
          hoverLayoutState.panelContent.dataset.bannerFillKey = fillKey;
          hoverLayoutState.panelContent.dataset.bannerEntrySignature = groupedEntrySignature;
        }
        displayDictEntry(groupedEntry, fillText || d.surface, {
          _lookupLang: String(documentShellState.currentLanguage || ''),
          _panelTokenSurface: d.surface,
          _panelTokenLemma: d.lemma,
          _panelTokenLemmaRaw: d.lemma_raw || d.lemma,
          _panelBannerFillKey: fillKey,
          _panelEntrySignature: groupedEntrySignature,
          _skipBannerRender: true
        });
      });
    })(fillBtns[fli]);
  }
}
export function _runGeminiGeneration(d, surface, _geminiBtn, tokensToGenerate) {
  var selectedTokens = Array.isArray(tokensToGenerate)
    ? tokensToGenerate.slice()
    : resolveSyntheticGenerationTargets(d, surface);
  sendSyntheticEntries(d, surface, selectedTokens);
}

// -- Token Map: grammar + segmentation overview in side panel --
// Now just toggles the banner expansion
export function showTokenMap() {
  if (!hoverLayoutState.tokenMapData) return;
  var banner = document.getElementById('token-banner');
  if (banner) {
    banner.classList.add('expanded');
    var expandToggle = document.getElementById('tb-banner-toggle');
    if (expandToggle) expandToggle.setAttribute('aria-expanded', 'true');
  }
  hoverLayoutState.tokenMapVisible = true;
  ensureTokenMapLookupEntries(hoverLayoutState.tokenMapData).then(function (changed) {
    if (changed && hoverLayoutState.tokenMapVisible && hoverLayoutState.tokenMapData) {
      if (hoverLayoutState.tokenMapData.surfaceLookup)
        upgradePendingPanelSurfaceTokens(
          hoverLayoutState.tokenMapData.surface || '',
          hoverLayoutState.tokenMapData.surfaceLookup
        );
      renderTokenBanner();
    }
  });
}
export function buildAggregateLookupEntry(results, fallbackHead) {
  var entries = Array.isArray(results)
    ? results.filter(function (entry) {
        return !!entry;
      })
    : [];
  if (!entries.length) return null;
  if (entries.length === 1) return entries[0];
  var hasKnown = false;
  var hasUnknown = false;
  for (var i = 0; i < entries.length; i++) {
    if (isUnknownDictEntry(entries[i])) hasUnknown = true;
    else hasKnown = true;
  }
  var aggregateHead = getEntryDisplayHead(entries[0], fallbackHead || '');
  return {
    text: String(fallbackHead || entries[0].text || entries[0].surface_form || aggregateHead || ''),
    head: String(aggregateHead || fallbackHead || ''),
    surface_form: String(fallbackHead || entries[0].surface_form || aggregateHead || ''),
    pos: hasKnown ? 'group' : 'unknown',
    senses: [],
    senses_hover: [],
    fills: entries.slice(),
    dict_fill: entries.slice(),
    dict_fill_has_known: hasKnown,
    dict_fill_has_unknown: hasUnknown
  };
}
export function cacheSidePanelLookupEntry(entry, aliasKey, langOverride, lookupOptions) {
  if (!entry) return;
  var alias = String(aliasKey || entry.surface_form || getEntryDisplayHead(entry, '') || '').trim();
  if (!alias) return;
  setExactSidePanelLookupEntry(alias, entry, langOverride, lookupOptions || {});
}
export function getTokenMapSurfaceLookupEntry(data) {
  return resolveTokenMapLookupEntry('surface', data, getCanonicalTokenSurfaceText(data));
}
export function splitTokenMapCompoundText(text) {
  return String(text || '').split(/(\s+|[+\uFF0B])/);
}
export function isTokenMapCompoundSeparator(part) {
  return part === '+' || part === '\uFF0B';
}
export function isLiveTokenMapStateMatch(data, tokenText, segIdx) {
  if (!data || typeof data !== 'object') return false;
  var expectedSegIdx = Number(segIdx);
  var liveSegIdx = Number(data.segIdx);
  if (isFinite(expectedSegIdx) && isFinite(liveSegIdx)) {
    return expectedSegIdx === liveSegIdx;
  }
  var expectedSurface = getTrimmedDisplayText(tokenText);
  var liveSurface = getTrimmedDisplayText(data.surface || '');
  if (expectedSurface && liveSurface && !hasSameVisibleComparisonText(expectedSurface, liveSurface)) {
    return false;
  }
  return !!(expectedSurface || liveSurface);
}
export function buildTokenMapLookupRequestOptions(role, data, partIndex, options) {
  var roleKey = String(role || 'surface')
    .trim()
    .toLowerCase();
  var liveData = data || null;
  var opts = options || {};
  var request = {};
  if (!liveData) return request;
  var tokenEntry = liveData.tokenEntry || liveData.entry || null;
  var uposHint = String(
    (liveData.posData && (liveData.posData.upos || liveData.posData.upos_label)) ||
      (liveData.udTok && liveData.udTok.upos) ||
      (tokenEntry && tokenEntry.upos) ||
      ''
  ).trim();
  var xposHint = String(
    (liveData.posData && (liveData.posData.tag || liveData.posData.xpos)) ||
      (liveData.udTok && (liveData.udTok.tag || liveData.udTok.xpos)) ||
      (tokenEntry && tokenEntry.tag) ||
      ''
  ).trim();
  if (roleKey === 'lemma-part') {
    var hintRows = getTokenMapLemmaPartHintRows(liveData);
    var hint = isFinite(partIndex) ? hintRows[parseInt(partIndex, 10)] || null : null;
    if (hint) {
      if (String(hint.upos || '').trim()) request.upos = String(hint.upos || '').trim();
      if (String(hint.xpos || '').trim()) request.xpos = String(hint.xpos || '').trim();
    }
    return request;
  }
  if (opts.isFillHit) return request;
  if (roleKey === 'lemma') {
    if (uposHint) request.upos = uposHint;
    var lemmaXpos = getTokenMapPreferredLemmaLookupXpos(liveData, xposHint);
    if (lemmaXpos) request.xpos = lemmaXpos;
    return request;
  }
  if (roleKey === 'surface') {
    if (uposHint) request.upos = uposHint;
    if (xposHint) request.xpos = xposHint;
    return request;
  }
  return request;
}
export function buildTokenMapHoverLookupRequest(role, lookupKey, partIndex, surfaceText, data, isFillHit) {
  var roleKey = String(role || 'surface')
    .trim()
    .toLowerCase();
  var text = String(
    isFillHit
      ? surfaceText || ''
      : roleKey === 'lemma' || roleKey === 'lemma-part'
        ? lookupKey || ''
        : surfaceText || lookupKey || ''
  ).trim();
  return {
    text: text,
    options: buildTokenMapLookupRequestOptions(roleKey, data, partIndex, {
      isFillHit: !!isFillHit
    })
  };
}
export function buildGrammarPopupTokenMapState(posData, udTok, tokenText, tokenEntry, options) {
  var opts = options || {};
  var surfaceRaw = String(tokenText || (tokenEntry && tokenEntry.surface_form) || '');
  var liveState = opts.liveState || null;
  if (!liveState && isLiveTokenMapStateMatch(hoverLayoutState.tokenMapData, surfaceRaw, opts.segIdx)) {
    liveState = hoverLayoutState.tokenMapData;
  }
  if (liveState) return liveState;
  var lemmaValue = getTrimmedDisplayText(
    (posData && (posData.lemma || '')) ||
      (udTok && (udTok.lemma || '')) ||
      (tokenEntry && (tokenEntry.lemma_form || tokenEntry.lemma || '')) ||
      ''
  );
  var lemmaRawValue = getTrimmedDisplayText(
    (posData && (posData.lemma_raw || '')) ||
      (udTok && (udTok.lemma_raw || '')) ||
      (tokenEntry && (tokenEntry.lemma_raw || tokenEntry.lemma_form || tokenEntry.lemma || '')) ||
      lemmaValue
  );
  var lemmaMeta = getLemmaDisplayMeta(lemmaValue, lemmaRawValue);
  var dictFill = getLookupEntryFills(tokenEntry).slice();
  var resolvedVia = getLookupEntryResolvedVia(tokenEntry);
  var state = {
    segIdx: isFinite(Number(opts.segIdx)) ? Number(opts.segIdx) : -1,
    surface: surfaceRaw,
    anchorText: String(opts.anchorText || opts.mwtSurfaceSlice || surfaceRaw || '').trim(),
    lookupText: String(
      opts.lookupText || opts.mwtChildText || (tokenEntry && tokenEntry.text) || surfaceRaw || ''
    ).trim(),
    mwtSurfaceSlice: String(opts.mwtSurfaceSlice || '').trim(),
    mwtChildText: String(opts.mwtChildText || '').trim(),
    mwtPopupReason: String(opts.mwtPopupReason || '').trim(),
    lemma: lemmaMeta.lemma || lemmaValue,
    lemma_raw: lemmaMeta.raw || lemmaRawValue,
    lemma_suffix: lemmaMeta.suffix || '',
    posData: posData || {},
    udTok: udTok || {},
    entry: tokenEntry || null,
    tokenEntry: tokenEntry || null,
    dictFill: dictFill.slice(),
    tokenDictFill: dictFill.slice(),
    fillMode: getLookupEntryFillMode(tokenEntry),
    tokenFillMode: getLookupEntryFillMode(tokenEntry),
    resolvedVia: resolvedVia,
    tokenResolvedVia: resolvedVia,
    surfaceLookup: null,
    lemmaLookup: null,
    lemmaPartLookups: Object.create(null),
    surfaceLookupPromise: null,
    lemmaLookupPromise: null,
    lemmaPartLookupPromises: Object.create(null),
    headDecompByForm: null
  };
  if (surfaceRaw) {
    state.surfaceLookup =
      getExactSidePanelLookupEntry(
        surfaceRaw,
        documentShellState.currentLanguage || '',
        buildTokenMapLookupRequestOptions('surface', state, null)
      ) || null;
  }
  if (lemmaMeta.lemma || lemmaValue) {
    state.lemmaLookup =
      getExactSidePanelLookupEntry(
        lemmaMeta.lemma || lemmaValue,
        documentShellState.currentLanguage || '',
        buildTokenMapLookupRequestOptions('lemma', state, null)
      ) || null;
  }
  if ((lemmaMeta.lemma || lemmaValue) && /[+\uFF0B]/.test(lemmaMeta.lemma || lemmaValue)) {
    var partTexts = getTokenMapLemmaPartTexts(lemmaMeta.lemma || lemmaValue);
    for (var i = 0; i < partTexts.length; i++) {
      var partText = String(partTexts[i] || '').trim();
      if (!partText || state.lemmaPartLookups[partText]) continue;
      var partLookup = getExactSidePanelLookupEntry(
        partText,
        documentShellState.currentLanguage || '',
        buildTokenMapLookupRequestOptions('lemma-part', state, i)
      );
      if (partLookup) state.lemmaPartLookups[partText] = partLookup;
    }
  }
  return state;
}
export function splitTokenMapCompoundHintTags(text) {
  var raw = String(text || '').trim();
  if (!raw) return [];
  var parts = raw.split(/[+\uFF0B]/);
  var out = [];
  for (var i = 0; i < parts.length; i++) {
    var part = String(parts[i] || '').trim();
    if (part) out.push(part);
  }
  return out;
}
