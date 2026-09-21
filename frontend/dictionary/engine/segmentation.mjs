import { DictionaryEngine } from './model.mjs';
import { getLemmaHintTexts, lookupKey } from './normalization.mjs';
export function initializeSegmentation() {
  DictionaryEngine.prototype._greedy_fill = function (
    word,
    excludeWhole,
    upos,
    debug,
    boundaries,
    _koreanGroups,
    lemmaHints
  ) {
    void upos;
    return this._greedy_fill_simple(
      word,
      !!excludeWhole,
      boundaries || null,
      null,
      !!debug,
      lemmaHints || null
    );
  };
  DictionaryEngine.prototype.fill_token = function (word, allowExactOrOpts, excludeWhole, upos, debug) {
    var opts;
    if (allowExactOrOpts && typeof allowExactOrOpts === 'object' && !Array.isArray(allowExactOrOpts)) {
      opts = allowExactOrOpts;
    } else {
      opts = {
        allowExact: allowExactOrOpts !== false,
        excludeWhole: !!excludeWhole,
        upos: upos || '',
        debug: !!debug
      };
    }
    var allowExact = opts.allowExact !== false;
    var exWhole = !!opts.excludeWhole;
    var uposValue = String(opts.upos || '');
    var debugValue = !!opts.debug;
    var boundariesValue = Array.isArray(opts.boundaries) ? opts.boundaries : null;
    var lemmaHintsValue = Array.isArray(opts.lemma_hints) ? opts.lemma_hints : null;
    if (allowExact && !exWhole) {
      var entries = this.lookup_all(word);
      if (entries.length) {
        var fill = this._entry_to_fill(entries[0], word);
        fill.entries = entries;
        var promotedLemma = null;
        var promotedMeta = null;
        var engineLang = String(this._lang_code || '')
          .trim()
          .toLowerCase();
        var hintList = Array.isArray(lemmaHintsValue) ? lemmaHintsValue : [];
        for (var hi = 0; hi < hintList.length; hi++) {
          var rawHint = hintList[hi];
          var hintTexts = getLemmaHintTexts(rawHint, engineLang);
          for (var hti = 0; hti < hintTexts.length; hti++) {
            var hintText = hintTexts[hti];
            if (!hintText) continue;
            var hintKey = lookupKey(hintText, engineLang);
            if (hintKey === lookupKey(word, engineLang)) {
              promotedLemma = hintText;
              promotedMeta =
                rawHint && typeof rawHint === 'object'
                  ? {
                      upos: String(rawHint.upos || ''),
                      xpos: String(rawHint.xpos || '')
                    }
                  : null;
              break;
            }
            for (var ei = 0; ei < entries.length; ei++) {
              var headKey = lookupKey(entries[ei].headword || '', engineLang);
              if (headKey && headKey === hintKey) {
                promotedLemma = hintText;
                promotedMeta =
                  rawHint && typeof rawHint === 'object'
                    ? {
                        upos: String(rawHint.upos || ''),
                        xpos: String(rawHint.xpos || '')
                      }
                    : null;
                break;
              }
            }
            if (promotedLemma) break;
          }
          if (promotedLemma) break;
        }
        if (promotedLemma) {
          fill._lemma_promoted = promotedLemma;
          fill._lemma_promoted_headword = String(entries[0].headword || '');
          if (promotedMeta && promotedMeta.upos) fill._lemma_upos_hint = promotedMeta.upos;
          if (promotedMeta && promotedMeta.xpos) fill._lemma_xpos_hint = promotedMeta.xpos;
        }
        return {
          mode: promotedLemma ? 'exact_lemma_promoted' : 'exact',
          fills: [fill],
          has_known: true,
          has_unknown: false,
          has_lemma_promotion: !!promotedLemma
        };
      }
    }
    return this._greedy_fill(word, exWhole, uposValue, debugValue, boundariesValue, null, lemmaHintsValue);
  };
  return true;
}
