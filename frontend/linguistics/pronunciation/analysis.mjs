import { inferRole } from './codepoints.mjs';
import {
  analyzeSingleCluster,
  applySpanSequenceRomanization,
  cloneAnalysisItem,
  codePointHex,
  getLanguageProfile,
  normalizeClusterSequence,
  normalizeUnit,
  splitGraphemeClusters
} from './graphemes.mjs';
import { graphemesState } from './graphemes.state.mjs';
import {
  applyAbugidaSmoothing,
  applyArabicSunLetterSmoothing,
  applyJapaneseGraphemeSmoothing,
  smoothGraphemeItems
} from './smoothing.mjs';
export function analyzeGraphemeStream(language, clusters, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const units = normalizeClusterSequence(profile.id, clusters, options);
  const baseItems = [];
  for (const cluster of units) {
    const item = analyzeSingleCluster(profile.id, cluster, {
      ...options,
      normalize: false,
      forceSingleCluster: true
    });
    if (!item) return null;
    baseItems.push(item);
  }
  const items = smoothGraphemeItems(profile, units, baseItems, options);
  const joinedRomanization = items.map((item) => item.romanization || item.sound || '').join('');
  return {
    language: profile.id,
    script: profile.script,
    items,
    clusters: units,
    joinedSound: joinedRomanization,
    joinedRomanization
  };
}
export function analyzeCluster(language, cluster, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const unit = normalizeUnit(profile.id, cluster, options);
  const graphemes = splitGraphemeClusters(unit);
  if (options.forceSingleCluster !== true && graphemes.length > 1) {
    const stream = analyzeGraphemeStream(profile.id, graphemes, {
      ...options,
      normalize: false,
      forceSingleCluster: true
    });
    return {
      language: profile.id,
      script: profile.script,
      cluster: unit,
      sound: stream.joinedRomanization,
      romanization: stream.joinedRomanization,
      notes: [],
      parts: stream.items.flatMap((item, clusterIndex) =>
        item.parts.map((part) => ({
          ...part,
          cluster: item.cluster,
          clusterIndex
        }))
      ),
      graphemes: stream.items
    };
  }
  const analysis = analyzeSingleCluster(profile.id, unit, {
    ...options,
    normalize: false,
    forceSingleCluster: true
  });
  return {
    ...analysis,
    graphemes: [cloneAnalysisItem(analysis)]
  };
}
export function analyzeParts(language, parts, options = {}) {
  const arr = Array.isArray(parts) ? parts.map((x) => String(x)) : [];
  const cluster = arr.join('').normalize('NFC');
  return analyzeCluster(language, cluster, {
    ...options,
    parts: arr,
    normalize: false
  });
}
export function analyzeMany(language, clusters, options = {}) {
  return analyzeGraphemeStream(language, clusters, options);
}
export function normalizePronunciationComponent(part) {
  const ch = String(part && part.char != null ? part.char : '');
  const sound = String((part && (part.romanization != null ? part.romanization : part.sound)) || '');
  const codePoint = String(part && part.codePoint != null ? part.codePoint : ch ? codePointHex(ch) : '');
  const role = String(part && part.role != null ? part.role : inferRole(ch));
  return {
    ch,
    roman: sound,
    sound,
    label: role,
    meta: codePoint,
    role,
    codePoint,
    emphasis:
      role === 'base' ||
      role === 'letter' ||
      role === 'choseong' ||
      role === 'jungseong' ||
      role === 'jongseong'
  };
}
export function buildPronunciationAnalysis(language, text, options = {}) {
  const profile = getLanguageProfile(language);
  if (!profile) return null;
  const rawText = String(text || '');
  if (!rawText) return null;
  const clusters = splitGraphemeClusters(rawText, options);
  if (!clusters.length) return null;
  const syllables = [];
  const syllableClusterIndex = [];
  let lastClusterIdx = -1;
  for (let ci = clusters.length - 1; ci >= 0; ci--) {
    if (String(clusters[ci] || '')) {
      lastClusterIdx = ci;
      break;
    }
  }
  for (let ci = 0; ci < clusters.length; ci++) {
    const cluster = clusters[ci];
    const surface = String(cluster || '');
    if (!surface) continue;
    const analysis = analyzeCluster(profile.id, surface, {
      ...graphemesState.DEFAULT_OPTIONS,
      ...options,
      normalize: options.normalize !== false,
      decompose: true,
      compatibility: options.compatibility !== false,
      preserveUnknown: !!options.preserveUnknown,
      forceSingleCluster: true,
      isFinal: ci === lastClusterIdx
    });
    if (!analysis) continue;
    const clusterRoman = String(analysis.romanization || analysis.sound || '');
    const components = [
      {
        ch: surface,
        roman: clusterRoman,
        sound: String(analysis.sound || ''),
        label: 'cluster',
        meta: surface ? codePointHex(surface) : '',
        role: 'cluster',
        codePoint: surface ? codePointHex(surface) : '',
        emphasis: true
      }
    ];
    syllables.push({
      orth: surface,
      roman: clusterRoman,
      sound: String(analysis.sound || ''),
      notes: Array.isArray(analysis.notes) ? [...analysis.notes] : [],
      components,
      part_count: 1,
      has_decomposition: false
    });
    syllableClusterIndex.push(ci);
  }
  if (syllables.length) {
    const itemView = syllables.map((s) => ({
      sound: s.sound || s.roman || '',
      romanization: s.roman || s.sound || ''
    }));
    const surfaceClusters = syllableClusterIndex.map((ci) => String(clusters[ci] || ''));
    if (profile.scriptFamily === 'japanese') {
      applyJapaneseGraphemeSmoothing(surfaceClusters, itemView);
    } else {
      if (profile.scriptFamily === 'arabic' || profile.scriptFamily === 'abugida') {
        const effectiveClusters = surfaceClusters.slice();
        for (let idx = 0; idx + 1 < syllableClusterIndex.length; idx++) {
          const here = syllableClusterIndex[idx];
          const next = syllableClusterIndex[idx + 1];
          if (next - here > 1) {
            const gap = clusters.slice(here + 1, next).join('');
            if (gap) effectiveClusters[idx + 1] = gap + effectiveClusters[idx + 1];
          }
        }
        if (profile.scriptFamily === 'arabic') {
          applyArabicSunLetterSmoothing(effectiveClusters, itemView);
        }
        if (profile.scriptFamily === 'abugida') {
          applyAbugidaSmoothing(profile, effectiveClusters, itemView);
        }
      }
      if (profile.spanMap) {
        applySpanSequenceRomanization(profile, surfaceClusters, itemView);
      }
    }
    for (let i = 0; i < syllables.length; i++) {
      syllables[i].roman = itemView[i].romanization || itemView[i].sound || '';
      syllables[i].sound = itemView[i].sound || itemView[i].romanization || '';
      syllables[i].components[0].roman = syllables[i].roman;
      syllables[i].components[0].sound = syllables[i].sound;
    }
  }
  const romanParts = [];
  for (const s of syllables) if (s.roman) romanParts.push(s.roman);
  return {
    language: profile.id,
    script: profile.script,
    text: rawText,
    clusters,
    syllables,
    overallRomanization: romanParts.join(' '),
    overallSound: romanParts.join(' '),
    notes: []
  };
}
export function explainCluster(language, cluster, options = {}) {
  const x = analyzeCluster(language, cluster, options);
  if (!x) return '';
  if (options.verbose === true) {
    const lines = [`${x.cluster} -> ${x.romanization || x.sound}`];
    for (const part of x.parts) {
      lines.push(`  ${part.char} (${part.codePoint}) [${part.role}] -> ${part.romanization || part.sound}`);
    }
    if (x.notes.length) lines.push(`notes: ${x.notes.join(', ')}`);
    return lines.join('\n');
  }
  return x.romanization || x.sound || '';
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                     */
/* -------------------------------------------------------------------------- */
