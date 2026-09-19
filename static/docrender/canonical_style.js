/* canonical_style.js
 *
 * Text-style normalization for the bottom lookup-window canonical document system.
 *
 * Rule of the system:
 *   Preserve text-related look: font, size, weight, style, alignment,
 *   direction, spacing, decoration, and rough layout hints.
 *   Source text color is deliberately not preserved so lookup/POS UI color
 *   treatments always sit on the app's normal text color.
 *   Drop source-document behavior and non-text objects.
 *
 * Browser global:
 *   window.CanonicalStyle
 */
(function(global) {
  'use strict';

  var DEFAULT_STYLE = Object.freeze({
    fontFamily: '',
    fontSize: '',
    fontWeight: '',
    fontStyle: '',
    color: '',
    backgroundColor: '',
    textDecoration: '',
    lineHeight: '',
    letterSpacing: '',
    wordSpacing: '',
    textAlign: '',
    direction: '',
    writingMode: '',
    verticalAlign: '',
    whiteSpace: ''
  });

  var STYLE_KEYS = Object.keys(DEFAULT_STYLE);

  function toStr(v) {
    return v == null ? '' : String(v).trim();
  }

  function normalizeColor(v) {
    var s = toStr(v);
    if (!s || s === 'transparent' || s === 'rgba(0, 0, 0, 0)') return '';
    return s;
  }

  function normalizeFontWeight(v) {
    var s = toStr(v).toLowerCase();
    if (!s) return '';
    if (s === 'normal') return '400';
    if (s === 'bold') return '700';
    return s;
  }

  function normalizeFontStyle(v) {
    var s = toStr(v).toLowerCase();
    return s === 'normal' ? '' : s;
  }

  function normalizeTextDecoration(v) {
    var s = toStr(v).toLowerCase();
    if (!s || s === 'none') return '';
    return s;
  }

  function normalizeTextStyle(raw) {
    var src = raw || {};
    return {
      fontFamily: toStr(src.fontFamily),
      fontSize: toStr(src.fontSize),
      fontWeight: normalizeFontWeight(src.fontWeight),
      fontStyle: normalizeFontStyle(src.fontStyle),
      color: '',
      backgroundColor: normalizeColor(src.backgroundColor),
      textDecoration: normalizeTextDecoration(src.textDecoration || src.textDecorationLine),
      lineHeight: toStr(src.lineHeight),
      letterSpacing: toStr(src.letterSpacing),
      wordSpacing: toStr(src.wordSpacing),
      textAlign: toStr(src.textAlign),
      direction: toStr(src.direction),
      writingMode: toStr(src.writingMode),
      verticalAlign: toStr(src.verticalAlign),
      whiteSpace: toStr(src.whiteSpace)
    };
  }

  function mergeTextStyle(parent, child) {
    var p = normalizeTextStyle(parent);
    var c = normalizeTextStyle(child);
    var out = {};
    for (var i = 0; i < STYLE_KEYS.length; i++) {
      var k = STYLE_KEYS[i];
      out[k] = c[k] || p[k] || '';
    }
    return out;
  }

  function readComputedTextStyle(el, fallback) {
    var base = normalizeTextStyle(fallback);
    if (!el || el.nodeType !== 1) return base;
    var view = (el.ownerDocument && el.ownerDocument.defaultView) || global;
    if (!view || !view.getComputedStyle) return base;
    var cs;
    try { cs = view.getComputedStyle(el); } catch (_e) { cs = null; }
    if (!cs) return base;
    return mergeTextStyle(base, {
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      fontStyle: cs.fontStyle,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      textDecoration: cs.textDecorationLine || cs.textDecoration,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      wordSpacing: cs.wordSpacing,
      textAlign: cs.textAlign,
      direction: cs.direction,
      writingMode: cs.writingMode,
      verticalAlign: cs.verticalAlign,
      whiteSpace: cs.whiteSpace
    });
  }

  function sameTextStyle(a, b) {
    var x = normalizeTextStyle(a);
    var y = normalizeTextStyle(b);
    for (var i = 0; i < STYLE_KEYS.length; i++) {
      var k = STYLE_KEYS[i];
      if ((x[k] || '') !== (y[k] || '')) return false;
    }
    return true;
  }

  function styleToCssObject(style) {
    var s = normalizeTextStyle(style);
    var out = {};
    if (s.fontFamily) out.fontFamily = s.fontFamily;
    if (s.fontSize) out.fontSize = s.fontSize;
    if (s.fontWeight) out.fontWeight = s.fontWeight;
    if (s.fontStyle) out.fontStyle = s.fontStyle;
    if (s.color) out.color = s.color;
    if (s.backgroundColor) out.backgroundColor = s.backgroundColor;
    if (s.textDecoration) out.textDecoration = s.textDecoration;
    if (s.lineHeight) out.lineHeight = s.lineHeight;
    if (s.letterSpacing) out.letterSpacing = s.letterSpacing;
    if (s.wordSpacing) out.wordSpacing = s.wordSpacing;
    if (s.textAlign) out.textAlign = s.textAlign;
    if (s.direction) out.direction = s.direction;
    if (s.writingMode) out.writingMode = s.writingMode;
    if (s.verticalAlign) out.verticalAlign = s.verticalAlign;
    if (s.whiteSpace) out.whiteSpace = s.whiteSpace;
    return out;
  }

  function cssName(camel) {
    return String(camel || '').replace(/[A-Z]/g, function(m) { return '-' + m.toLowerCase(); });
  }

  function escapeCssValue(v) {
    // Values originate from computed style / parser style snapshots, not user CSS text.
    // Strip semicolons to prevent accidental declaration injection if callers pass raw strings.
    return String(v == null ? '' : v).replace(/;/g, '');
  }

  function styleToCssText(style) {
    var obj = styleToCssObject(style);
    var parts = [];
    Object.keys(obj).forEach(function(k) {
      if (obj[k]) parts.push(cssName(k) + ':' + escapeCssValue(obj[k]));
    });
    return parts.join(';');
  }

  function applyStyleToElement(el, style) {
    if (!el || !el.style) return el;
    var obj = styleToCssObject(style);
    Object.keys(obj).forEach(function(k) {
      try { el.style[k] = obj[k]; } catch (_e) {}
    });
    return el;
  }

  function rectFromDomRect(rect, originRect) {
    if (!rect) return null;
    var ox = originRect ? originRect.left : 0;
    var oy = originRect ? originRect.top : 0;
    var w = Number(rect.width || 0);
    var h = Number(rect.height || 0);
    if (!isFinite(w)) w = 0;
    if (!isFinite(h)) h = 0;
    return {
      x: Number(rect.left || 0) - ox,
      y: Number(rect.top || 0) - oy,
      width: w,
      height: h
    };
  }

  global.CanonicalStyle = {
    DEFAULT_STYLE: DEFAULT_STYLE,
    STYLE_KEYS: STYLE_KEYS.slice(),
    normalizeTextStyle: normalizeTextStyle,
    mergeTextStyle: mergeTextStyle,
    readComputedTextStyle: readComputedTextStyle,
    sameTextStyle: sameTextStyle,
    styleToCssObject: styleToCssObject,
    styleToCssText: styleToCssText,
    applyStyleToElement: applyStyleToElement,
    rectFromDomRect: rectFromDomRect
  };
})(window);
