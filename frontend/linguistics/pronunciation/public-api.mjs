import { aliasesState } from './aliases.state.mjs';
import {
  analyzeCluster,
  analyzeGraphemeStream,
  analyzeMany,
  analyzeParts,
  buildPronunciationAnalysis,
  explainCluster
} from './analysis.mjs';
import {
  codePointHex,
  decomposeCluster,
  getLanguageProfile,
  normalizeLanguageId,
  splitGraphemeClusters
} from './graphemes.mjs';
import { profilesState } from './profiles.state.mjs';
import { publicApiState } from './public-api.state.mjs';
export function initializePublicApi() {
  publicApiState.GraphemePronunciationProfiles = {
    analyzeCluster,
    analyzeParts,
    analyzeMany,
    analyzeGraphemeStream,
    analyzeText: buildPronunciationAnalysis,
    buildPronunciationAnalysis,
    decomposeCluster,
    explainCluster,
    getLanguageProfile,
    normalizeLanguageId,
    splitGraphemeClusters,
    codePointHex,
    PHONOLOGY_PROFILES: profilesState.PHONOLOGY_PROFILES,
    LANGUAGE_ALIASES: aliasesState.LANGUAGE_ALIASES
  };
  if (typeof globalThis !== 'undefined') {
    globalThis.GraphemePronunciationProfiles = publicApiState.GraphemePronunciationProfiles;
    globalThis.grapheme_pronunciation_profiles = publicApiState.GraphemePronunciationProfiles;
  }
  const commonJsModule = typeof module !== 'undefined' ? module : null;
  if (commonJsModule && commonJsModule.exports) {
    commonJsModule.exports = publicApiState.GraphemePronunciationProfiles;
  }
  Object.assign(profilesState.PHONOLOGY_PROFILES['arabic'].spanMap, {
    و: 'wa',
    ف: 'fa',
    ب: 'bi',
    ك: 'ka',
    ل: 'li',
    س: 'sa',
    ت: 'ta',
    ن: 'na',
    م: 'ma',
    ه: 'ha',
    ي: 'ya',
    ى: 'ā',
    إ: 'ʔi',
    أ: 'ʔa',
    آ: 'ʔā'
  });
  Object.assign(profilesState.PHONOLOGY_PROFILES['persian'].spanMap, {
    و: 'v',
    در: 'dar',
    به: 'be',
    می: 'mi'
  });
  Object.assign(profilesState.PHONOLOGY_PROFILES['urdu'].spanMap, {
    و: 'vo/u',
    ب: 'ba',
    ک: 'ka',
    ل: 'li',
    م: 'ma',
    ہ: 'ha',
    ے: 'e'
  });
  return true;
}
