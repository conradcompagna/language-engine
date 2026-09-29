import { additionalLanguagesState } from './additional-languages.state.mjs';
import { ancientGreekState } from './ancient-greek.state.mjs';
import { eastAsianState } from './east-asian.state.mjs';
import { europeanState } from './european.state.mjs';
import { latinState } from './latin.state.mjs';
import { registryState } from './registry.state.mjs';
import { southAsianState } from './south-asian.state.mjs';
import { westernState } from './western.state.mjs';
export function initializeRegistry() {
  // Map from lang code → XPOS dict (keys stored uppercase for lookup)
  registryState._XPOS_BY_LANG = {
    zh: eastAsianState.XPOS_ZH,
    ja: eastAsianState.XPOS_JA,
    ko: eastAsianState.XPOS_KO,
    lzh: eastAsianState.XPOS_LZH,
    vi: europeanState.XPOS_VI,
    de: europeanState.XPOS_GERMAN,
    german: europeanState.XPOS_GERMAN,
    nl: europeanState.XPOS_DUTCH,
    dutch: europeanState.XPOS_DUTCH,
    la: latinState.XPOS_LATIN,
    latin: latinState.XPOS_LATIN,
    ar: southAsianState.XPOS_ARABIC,
    arabic: southAsianState.XPOS_ARABIC,
    hi: southAsianState.XPOS_HINDI,
    hindi: southAsianState.XPOS_HINDI,
    fa: southAsianState.XPOS_PERSIAN,
    persian: southAsianState.XPOS_PERSIAN,
    id: southAsianState.XPOS_INDONESIAN,
    indonesian: southAsianState.XPOS_INDONESIAN,
    ga: westernState.XPOS_IRISH,
    irish: westernState.XPOS_IRISH,
    it: westernState.XPOS_ITALIAN,
    italian: westernState.XPOS_ITALIAN,
    tr: westernState.XPOS_TURKISH,
    turkish: westernState.XPOS_TURKISH,
    ru: additionalLanguagesState.XPOS_RUSSIAN,
    russian: additionalLanguagesState.XPOS_RUSSIAN,
    es: additionalLanguagesState.XPOS_SPANISH,
    spanish: additionalLanguagesState.XPOS_SPANISH,
    fr: additionalLanguagesState.XPOS_FRENCH,
    french: additionalLanguagesState.XPOS_FRENCH,
    he: additionalLanguagesState.XPOS_HEBREW,
    hebrew: additionalLanguagesState.XPOS_HEBREW,
    sw: additionalLanguagesState.XPOS_SWAHILI,
    swahili: additionalLanguagesState.XPOS_SWAHILI,
    tl: additionalLanguagesState.XPOS_TAGALOG,
    tagalog: additionalLanguagesState.XPOS_TAGALOG,
    pa: additionalLanguagesState.XPOS_PUNJABI,
    punjabi: additionalLanguagesState.XPOS_PUNJABI,
    grc: ancientGreekState.XPOS_GRC,
    customized: additionalLanguagesState.XPOS_CUSTOMIZED,
    ang: additionalLanguagesState.XPOS_CUSTOMIZED,
    'old-english': additionalLanguagesState.XPOS_CUSTOMIZED,
    oldenglish: additionalLanguagesState.XPOS_CUSTOMIZED
  };
  return true;
}
