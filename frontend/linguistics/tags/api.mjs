import { apiState } from './api.state.mjs';
import { dependenciesState } from './dependencies.state.mjs';
import { eastAsianState } from './east-asian.state.mjs';
import { featuresState } from './features.state.mjs';
import { registryState } from './registry.state.mjs';
export // ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

function _normalizeLang(raw) {
  var s = String(raw || '')
    .trim()
    .toLowerCase();
  if (s === 'ancient-greek' || s === 'ancientgreek' || s === 'ancient greek') return 'grc';
  if (s === 'modern-greek' || s === 'moderngreek' || s === 'modern greek') return 'el';
  var dash = s.indexOf('-');
  return dash > 0 ? s.slice(0, dash) : s;
}
export function getXpos(lang, tag) {
  var code = _normalizeLang(lang);
  var map = registryState._XPOS_BY_LANG[code];
  if (!map) return '';
  // Try exact key first, then uppercase
  var k = String(tag || '').trim();
  if (Object.prototype.hasOwnProperty.call(map, k)) return map[k];
  var ku = k.toUpperCase();
  if (Object.prototype.hasOwnProperty.call(map, ku)) return map[ku];
  return '';
}
export function getXposMap(lang) {
  var code = _normalizeLang(lang);
  return registryState._XPOS_BY_LANG[code] || null;
}
export function getDep(rel) {
  var key = String(rel || '')
    .trim()
    .toLowerCase();
  if (!key) return '';
  if (Object.prototype.hasOwnProperty.call(dependenciesState.DEP, key)) return dependenciesState.DEP[key];
  var base = key.split(':')[0];
  if (base && Object.prototype.hasOwnProperty.call(dependenciesState.DEP, base))
    return dependenciesState.DEP[base];
  return '';
}
export function getFeat(feat) {
  var key = String(feat || '').trim();
  if (!key) return '';
  if (Object.prototype.hasOwnProperty.call(featuresState.FEATS, key)) return featuresState.FEATS[key];
  return '';
}
export function initializeApi() {
  apiState.GRC_DEP_ADDITIONS = {
    _exd0_pred: 'Extra-Sentential Slot 0, Predicate',
    adv: 'Adverbial',
    adv_ap: 'Adverbial, Apposing',
    adv_ap_co: 'Adverbial, Apposing, Coordinated',
    adv_co: 'Adverbial, Coordinated',
    adv_exd_obj: 'Adverbial, Extra-Sentential Element, Object',
    apos: 'Apposition / Appositive',
    apos_co: 'Apposition / Appositive, Coordinated',
    atr: 'Attribute',
    atr_ap: 'Attribute, Apposing',
    atr_ap_co: 'Attribute, Apposing, Coordinated',
    atr_co: 'Attribute, Coordinated',
    atr_exd_sbj: 'Attribute, Extra-Sentential Element, Subject',
    atv: 'Verbal Attribute',
    atv_ap: 'Verbal Attribute, Apposing',
    atv_ap_co: 'Verbal Attribute, Apposing, Coordinated',
    atv_co: 'Verbal Attribute, Coordinated',
    atvv: 'Verbal Attribute',
    atvv_ap: 'Verbal Attribute, Apposing',
    atvv_co: 'Verbal Attribute, Coordinated',
    auxc: 'Subordinating Conjunction',
    auxg: 'Non-Comma Modern Punctuation',
    auxk: 'Final Punctuation',
    auxp: 'Preposition',
    auxp_co: 'Preposition, Coordinated',
    auxp_exd_pred_co: 'Preposition, Extra-Sentential Element, Predicate, Coordinated',
    auxr: 'Reflexive Passive',
    auxv: 'Auxiliary Verb',
    auxx: 'Comma',
    auxx_co: 'Comma, Coordinated',
    auxy: 'Sentence Adverbial',
    auxz: 'Emphasizing Particle',
    auxz_co: 'Emphasizing Particle, Coordinated',
    auxz_exd_sbj_ap_co: 'Emphasizing Particle, Extra-Sentential Element, Subject, Apposing, Coordinated',
    coord: 'Coordinator / Coordinating Conjunction',
    coord_exd0_adv: 'Coordinator / Coordinating Conjunction, Extra-Sentential Slot 0, Adverbial',
    exd: 'Extra-Sentential Element',
    exd_ap: 'Extra-Sentential Element, Apposing',
    exd_ap_co: 'Extra-Sentential Element, Apposing, Coordinated',
    exd_co: 'Extra-Sentential Element, Coordinated',
    mwe: 'Multiword Expression',
    obj_ap: 'Object, Apposing',
    obj_ap_co: 'Object, Apposing, Coordinated',
    obj_co: 'Object, Coordinated',
    obj_exd_pred_co: 'Object, Extra-Sentential Element, Predicate, Coordinated',
    ocomp: 'Object Complement',
    ocomp_ap: 'Object Complement, Apposing',
    ocomp_co: 'Object Complement, Coordinated',
    pnom: 'Predicate Nominal',
    pnom_ap: 'Predicate Nominal, Apposing',
    pnom_ap_co: 'Predicate Nominal, Apposing, Coordinated',
    pnom_co: 'Predicate Nominal, Coordinated',
    pnom_exd0_obj: 'Predicate Nominal, Extra-Sentential Slot 0, Object',
    pred: 'Predicate',
    pred_ap: 'Predicate, Apposing',
    pred_ap_co: 'Predicate, Apposing, Coordinated',
    pred_co: 'Predicate, Coordinated',
    pred_pa: 'Predicate, PA Subtype',
    pred_pa_co: 'Predicate, PA Subtype, Coordinated',
    sbj: 'Subject',
    sbj_ap: 'Subject, Apposing',
    sbj_ap_co: 'Subject, Apposing, Coordinated',
    sbj_ap_exd_apos: 'Subject, Apposing, Extra-Sentential Element, Apposition / Appositive',
    sbj_co: 'Subject, Coordinated',
    sbj_exd0_obj: 'Subject, Extra-Sentential Slot 0, Object',
    undefined: 'Undefined',
    xseg: 'Segment Boundary / Segmentation Artifact'
  };
  apiState.GRC_FEAT_ADDITIONS = {
    'Mood=Inf': 'Mood: Infinitive',
    'Mood=Part': 'Mood: Participle',
    'Tense=Aor': 'Tense: Aorist',
    'Tense=Perf': 'Tense: Perfect',
    'Tense=FutPerf': 'Tense: Future Perfect',
    'Voice=MidPass': 'Voice: Middle, Passive'
  };
  Object.assign(dependenciesState.DEP, apiState.GRC_DEP_ADDITIONS);
  Object.assign(featuresState.FEATS, apiState.GRC_FEAT_ADDITIONS);
  eastAsianState.root.TRANKIT_TAGS = {
    XPOS: registryState._XPOS_BY_LANG,
    DEP: dependenciesState.DEP,
    FEATS: featuresState.FEATS,
    getXpos: getXpos,
    getXposMap: getXposMap,
    getDep: getDep,
    getFeat: getFeat
  };
  return true;
}
