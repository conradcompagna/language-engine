import { inferRole, mapCodepoint, partObject, stripCombining } from './codepoints.mjs';
export /* -------------------------------------------------------------------------- */
/* Latin family (Old English only; modern Latin scripts intentionally removed) */
/* -------------------------------------------------------------------------- */

function analyzeLatin(profile, unit, parts) {
  const raw = profile.caseInsensitive ? unit.toLowerCase() : unit;
  if (profile.spanMap && profile.spanMap[raw] != null) {
    return {
      sound: profile.spanMap[raw],
      parts: parts.map((ch) => partObject(ch, latinPartSound(profile, ch), inferRole(ch))),
      notes: ['span-override']
    };
  }
  const mapped = parts.map((ch) => partObject(ch, latinPartSound(profile, ch), inferRole(ch)));
  let sound = composeLatin(profile, raw, parts);
  if (!sound) sound = mapped.map((x) => x.sound).join('');
  return {
    sound,
    parts: mapped,
    notes: []
  };
}
export function latinPartSound(profile, ch) {
  return mapCodepoint(profile, ch);
}
export function longestSpanCompose(raw, spanMap, fallbackCharFn) {
  if (!raw) return '';
  let i = 0;
  let out = '';
  while (i < raw.length) {
    let matched = null;
    const maxLen = Math.min(5, raw.length - i);
    for (let len = maxLen; len >= 1; len -= 1) {
      const slice = raw.slice(i, i + len);
      if (spanMap && spanMap[slice] != null) {
        matched = {
          len,
          sound: spanMap[slice]
        };
        break;
      }
    }
    if (matched) {
      out += matched.sound;
      i += matched.len;
      continue;
    }
    out += fallbackCharFn(raw[i]);
    i += 1;
  }
  return out;
}
export function composeLatin(profile, raw, parts) {
  if (profile.composeLatin) {
    const v = profile.composeLatin(raw, parts);
    if (v != null) return v;
  }
  const bare = stripCombining(raw);
  const direct = longestSpanCompose(raw, profile.spanMap || {}, (ch) => latinPartSound(profile, ch));
  if (direct) return direct;
  return longestSpanCompose(bare, profile.spanMap || {}, (ch) => latinPartSound(profile, ch));
}

/* -------------------------------------------------------------------------- */
/* Data tables                                                                 */
/* -------------------------------------------------------------------------- */

/* Arabic, Persian, Urdu */
