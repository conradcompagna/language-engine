# Complete Rendering Architecture: SQLite → Hover Popup

This document explains the full end-to-end pipeline for how dictionary entries flow from SQLite storage through the hybrid client/server system and into rendered hover popups in reader.js.

---

## Table of Contents
1. [High-Level Overview](#high-level-overview)
2. [Data Storage & Hydration](#data-storage--hydration)
3. [Client-Side Processing](#client-side-processing)
4. [Provenance Field Lifecycle](#provenance-field-lifecycle)
5. [All Rendering Branches](#all-rendering-branches)
6. [Why Synthetic Badges Disappear](#why-synthetic-badges-disappear)

---

## High-Level Overview

```
User highlights text in PDF
    ↓
reader.js sends /lookup request
    ↓
dictionary_client_hybrid.js intercepts (wrapFetch)
    ↓
Server runs Trankit NLP only → returns segments + UD overlay (NO dictionary data)
    ↓
JS Client runs DP segmentation against compact SQLite key index (IndexedDB)
    ↓
Collects "winner refs" (SQLite row IDs)
    ↓
JS client POSTs to /js/hydrate with winner refs
    ↓
Server reads full entry content from SQLite files
    ↓
Server sets `source` field from entries table
    ↓
Server returns entry_store + ref_to_key mapping
    ↓
JS client normalizes entries, sets `_source` from `source`
    ↓
JS client builds results_by_seg structure, sets top-level `_dict_source`
    ↓
JS client prepares fill entries, sets `fill._dict_source`
    ↓
JS client returns { results_by_seg, entry_store, ud_overlay, ... }
    ↓
reader.js calls buildPopupForWord(entry from results_by_seg)
    ↓
buildPopupForWord decides: single-fill? multi-fill? unknown?
    ↓
Calls renderDictTemplate with badge HTML or without
    ↓
renderDictTemplate either delegates to language adapter OR renders default
    ↓
Calls renderSenseLines or renderStackedSenseLines
    ↓
renderSenseLines injects badge into first headword cell (if entryMetaHtml provided)
    ↓
Final HTML rendered to screen
```

---

## Data Storage & Hydration

### SQLite Structure

**Directory:** `dict_sqlite/`
**Files:** `*.sqlite` (e.g., `zh-cc-cedict.sqlite`, `customdb.sqlite`)

Each database has these tables:

**entries table** (regular dictionary entries):
```sql
id INTEGER PRIMARY KEY,
headword TEXT NOT NULL,
source TEXT,              -- "zh-cc-cedict", "ja-jmdict", etc.
glosses TEXT,
forms TEXT,               -- JSON serialized morphology
senses_raw TEXT           -- JSON serialized
```

**custom_dict_entries table** (Gemini + user-created):
```sql
id INTEGER PRIMARY KEY,
user_id INTEGER,
headword TEXT,
source TEXT,              -- "gemini" or "user_created"
glosses TEXT,
forms TEXT,
...
```

### Backend Hydration: `/js/hydrate` (router.py:3253)

**Request:**
```json
{
  "lang": "zh",
  "winner_refs": [
    {
      "storage_kind": "sqlite" | "custom",
      "db_alias": "zh-cc-cedict",
      "entry_row_id": 12345,
      "match_kind": "headword",
      "match_key": "normalized_key"
    }
  ]
}
```

**Processing (router.py lines 3269-3301):**

1. Wire format conversion: `storage_kind` → `_storage_kind`, `db_alias` → `_storage_db_alias`, etc.
2. Batch SQL lookup via `hydrate_winner_refs()` from `dict_lookup_sqlite.py:889`
3. For each matched row, create entry object with:
   - `headword`, `glosses`, `forms`, `senses_raw` (from SQL result)
   - `source` field (from `entries.source` or `custom_dict_entries.source` column)
   - `_storage_kind`, `_storage_db_alias`, `_storage_row_id` (for bookkeeping)
4. Intern each entry with `_intern_entry()` helper (normalizes, deduplicates)
5. Return entry_store mapping

**Response:**
```json
{
  "ok": true,
  "entry_store": {
    "zh_entry_0": {
      "headword": "测试",
      "glosses": "[{\"sense\": \"test\"}]",
      "source": "gemini",
      "_storage_kind": "custom",
      "_storage_db_alias": "customdb",
      "_storage_row_id": 1001,
      "_hydrated": true
    },
    "zh_entry_1": {
      "headword": "试",
      "glosses": "[...]",
      "source": "zh-cc-cedict",
      "_storage_kind": "sqlite",
      "_storage_db_alias": "zh-cc-cedict",
      "_storage_row_id": 5432,
      "_hydrated": true
    }
  },
  "ref_to_key": {
    "custom|customdb|1001": "zh_entry_0",
    "sqlite|zh-cc-cedict|5432": "zh_entry_1"
  }
}
```

**Critical:** The `source` field is set from the **database column**, not from `db_alias`. This means:
- Gemini entries have `source: "gemini"` (from `custom_dict_entries.source`)
- Regular CEDICT entries have `source: "zh-cc-cedict"` (from `entries.source`)

---

## Client-Side Processing

### Step 1: Hydration Call (dictionary_client_hybrid.js:6473)

```javascript
function hydrateWinnerRefs(langCode, winnerRefs) {
  return fetch("/js/hydrate", {
    method: "POST",
    body: JSON.stringify({ lang: langCode, winner_refs: winnerRefs })
  }).then(resp => resp.json())
    .then(data => ({
      entry_store: data.entry_store || {},
      ref_to_key: data.ref_to_key || {}
    }));
}
```

**Returns:**
```javascript
{
  entry_store: {
    "zh_entry_0": { headword: "测试", source: "gemini", _source: undefined, ... }
  },
  ref_to_key: { "custom|customdb|1001": "zh_entry_0" }
}
```

### Step 2: Normalization (dictionary_client_hybrid.js:908)

```javascript
function normalizeCanonicalEntryRuntime(entry) {
  // ... many fields processed ...

  // Line 938-939: Copy source → _source
  if (!entry._source && entry.source) {
    entry._source = String(entry.source || "");
  }

  // ... flatten senses ...
  return entry;
}
```

**After normalization:**
```javascript
{
  headword: "测试",
  source: "gemini",
  _source: "gemini",      // <-- NEWLY SET
  // ... other normalized fields ...
}
```

### Step 3: Building Results by Segment (dictionary_client_hybrid.js:4668)

```javascript
function buildResultsBySeg(langCode, allSegments, results) {
  // For each segment in the lookup...

  var allEntries = [...];  // Hydrated entries for this segment
  var entry = {};          // Top-level result for this segment

  // Line 4750: Merge all senses
  var mergedSenses = mergeAllEntries(dictHead, allEntries);
  entry.senses = mergedSenses;

  // Line 4810-4818: Set _dict_source from first entry's _source
  if (allEntries && allEntries.length) {
    var _srcTag = "";
    for (var si = 0; si < allEntries.length; si++) {
      if (allEntries[si] && allEntries[si]._source) {
        _srcTag = allEntries[si]._source;
        break;
      }
    }
    if (_srcTag) entry._dict_source = _srcTag;  // <-- SET HERE
  }

  return entry;
}
```

**After buildResultsBySeg:**
```javascript
entry = {
  head: "测试",
  senses: [merged from all entries],
  _dict_source: "gemini",     // <-- SET FROM allEntries[0]._source
  dict_fill: [...]            // Multi-fill entries (if any)
}
```

### Step 4: Preparing Fill Entries (dictionary_client_hybrid.js:4485)

For entries with `dict_fill` (Gemini compounds, morphology, etc.):

```javascript
function prepareFillEntries(dictHeads, fillRefs, allEntries, ...) {
  // For each fill piece...

  for (var fi = 0; fi < fillRefs.length; fi++) {
    var f = fillRefs[fi];
    var fillEntries = f.entries || [];

    // Line 4505-4517: Set _dict_source on fill entry
    for (var _fsi = 0; _fsi < fillEntries.length; _fsi++) {
      var fillSource = getFillEntrySourceTag(fillEntries[_fsi]);
      if (!fillSource) continue;
      f._dict_source = fillSource;  // <-- SET ON FILL
      break;
    }

    // Line 4534: Set senses for this fill
    var fullSenses = mergeAllEntries(displayHead, fillEntries);
    f.senses = fullSenses;
  }

  return fillRefs;
}
```

**After prepareFillEntries:**
```javascript
dict_fill = [
  {
    head: "词",
    _dict_source: "gemini",     // <-- SET
    senses: [merged],
    entries: [...]
  },
  {
    head: "汇",
    _dict_source: "gemini",     // <-- SET
    senses: [merged],
    entries: [...]
  }
]
```

---

## Provenance Field Lifecycle

### The `source` Family of Fields

Three fields track where an entry came from:

| Field | Set By | Contains |
|-------|--------|----------|
| `entry.source` | SQLite hydration (router.py:3310) | "gemini", "user_created", "zh-cc-cedict", etc. |
| `entry._source` | normalizeCanonicalEntryRuntime (line 939) | Copy of `source` field |
| `entry._dict_source` | buildResultsBySeg (line 4817) or prepareFillEntries (line 4512) | Copy of `_source` from underlying entries |

### How reader.js Reads Provenance

```javascript
// reader.js:648
function getDictSourceBadgeInfo(entry, options) {
  var dictSrc = '';

  // Precedence order:
  if (entry._dict_source) dictSrc = entry._dict_source;
  else if (entry._source) dictSrc = entry._source;
  else if (entry.source) dictSrc = entry.source;

  // Fallback: check fill entries if top-level empty
  if (!dictSrc && options && options.includeFillFallback && entry.dict_fill) {
    for (var i = 0; i < entry.dict_fill.length; i++) {
      if (entry.dict_fill[i]._dict_source) {
        dictSrc = entry.dict_fill[i]._dict_source;
        break;
      }
    }
  }

  // Return badge info
  if (dictSrc === 'gemini') {
    return { label: 'Synthetic', className: 'dict-source-badge-synth' };
  }
  return null;
}
```

**Key:** `buildDictSourceBadgeHtml()` at line 675 calls `getDictSourceBadgeInfo(entry)` with NO options, so `includeFillFallback` is never set. The fill fallback is dead code from the popup perspective.

---

## All Rendering Branches

### Entry Point: buildPopupForWord (reader.js:13362)

```
buildPopupForWord(wordSpan, parentToken, segIdx, resultsBySeg, gramOverlay)
│
├─ Entry = resultsBySeg[segIdx]
├─ fillState = getRenderableFillState(entry.dict_fill)
├─ fill = fillState.entries
│
├─ Branch A: Multi-fill (fill.length > 1 && hasRenderableFill)
│  │
│  └─ Line 13409: buildConcatenatedFillEntriesHtml(fill, word, {
│                   sensesKey: 'senses_hover',
│                   showFilteredNote: true,
│                   showOtherDefsDropdown: false
│                 })
│     │
│     └─ Loop line 2483: For each fill piece:
│        │
│        └─ renderDictTemplate(part, partHead, {
│             showHead: true,
│             showRomanUnknown: true,
│             showSensesKnown: true,
│             showEmpty: true,
│             sensesKey: opts.sensesKey,
│             showFilteredNote: !!opts.showFilteredNote,
│             showOtherDefsDropdown: !!opts.showOtherDefsDropdown
│             ❌ NO entryMetaHtml
│             ❌ NO forceSenseHead
│           })
│
├─ Branch B: Single fill or no fill (else)
│  │
│  ├─ Line 13417: singleEntry = fill.length === 1 ? fill[0] : null
│  ├─ Line 13418: senseEntry = (singleEntry && has senses) ? singleEntry : entry
│  │
│  └─ Line 13421: renderDictTemplate(senseEntry, senseHead, {
│       headHtml: ...,
│       showRomanUnknown: true,
│       showSensesKnown: true,
│       showEmpty: true,
│       sensesKey: 'senses_hover',
│       showFilteredNote: true,
│       showOtherDefsDropdown: false,
│       ✅ entryMetaHtml: buildEntrySenseMetaHtml(
│            buildDictSourceBadgeHtml(senseEntry), ''
│          )
│       ✅ forceSenseHead: true
│     })
│
└─ Branch C: Unknown entry (mainIsUnknown === true)
   │
   └─ Line 13436: renderDictTemplate(entry, word, {
        showHead: true,
        showRomanUnknown: true,
        showSensesKnown: true,
        sensesKey: 'senses_hover',
        showFilteredNote: true,
        showOtherDefsDropdown: false,
        ✅ entryMetaHtml: buildEntrySenseMetaHtml(
             buildDictSourceBadgeHtml(entry), ''
           )
        ✅ forceSenseHead: true
      })
```

---

### renderDictTemplate (reader.js:14332)

```
renderDictTemplate(entry, fallbackHead, options)
│
├─ Check: adapter = getLanguageAdapter()
│  │
│  ├─ If adapter exists:
│  │  └─ return adapter.renderDictEntry(entry, fallbackHead, options)
│  │     (COMPLETELY OVERRIDES DEFAULT RENDERING)
│  │
│  └─ Else: continue to default path
│
├─ Line 14372-14378: Render headline
│  ├─ if (opts.headHtml != null)
│  │  └─ use opts.headHtml (pre-built by caller)
│  └─ else
│     └─ call buildPopupHeadwordHtml(entry, head)
│
├─ Line 14379-14403: Render content
│  │
│  ├─ if (isUnknownDictEntry)
│  │  └─ Line 14381: renderPopupRomanLine(entry.g2p)
│  │
│  └─ else if (showSensesKnown !== false)
│     │
│     ├─ if (senses.length > 0)
│     │  └─ Line 14385-14388: renderSenseLines(senses, head, formsMetaByHeader, {
│     │                         entryMetaHtml: opts.entryMetaHtml,
│     │                         forceSenseHead: opts.forceSenseHead
│     │                       })
│     │     └─ BADGE INJECTED HERE (if entryMetaHtml provided)
│     │
│     ├─ else if (showEmpty)
│     │  └─ '[no senses]' (badge NOT injected)
│     │
│     ├─ if (showFilteredNote && hasAltSenses)
│     │  └─ <span class="popup-alt-senses-signal" hidden>
│     │
│     └─ if (showOtherDefsDropdown && hasAltSenses)
│        └─ <details class="panel-filtered-expander">
│           └─ Line 14401: renderSenseLines(altSenses, head, altFormsMetaByHeader)
│              ❌ NO entryMetaHtml PASSED
│              └─ Badge NOT injected for alternate senses
│
└─ Return { html, isUnknown, sensesCount, head }
```

---

### renderSenseLines (reader.js:3777)

```
renderSenseLines(senses, skipHead, formsMetaByHeader, options)
│
├─ Input validation: if (!senses.length) return ''
├─ forceSenseHead = !!options.forceSenseHead
├─ entryMetaHtml = String(options.entryMetaHtml || '')
│
├─ Check for Japanese forms header (line 3783-3785)
│  │
│  ├─ if (hasFormsHeader with \x1E prefix)
│  │  └─ return renderStackedSenseLines(senses, forceSenseHead ? null : skipHead, ...)
│  │     (DELEGATED TO STACKED RENDERER)
│  │
│  ├─ else if (isJapaneseLanguage && skipHead)
│  │  └─ Synthesize \x1E header and call renderStackedSenseLines(...)
│  │     (DELEGATED WITH SYNTHETIC HEADER)
│  │
│  └─ Else: 4-column grid layout (line 3794-3841)
│     │
│     ├─ HTML = '<div style="display:grid;grid-template-columns:auto auto auto 1fr;...>'
│     ├─ metaInjected = false
│     │
│     └─ For each sense line:
│        │
│        ├─ tabCount = number of leading tabs
│        │
│        ├─ if (tabCount === 0) [Full headword row]
│        │  │
│        │  ├─ Line 3808-3809: if (skipHead && !forceSenseHead)
│        │  │  └─ Render empty cell
│        │  │
│        │  └─ else
│        │     ├─ Line 3813-3815: if (!metaInjected && entryMetaHtml)
│        │     │  └─ Inject badge into headword cell
│        │     │  └─ metaInjected = true
│        │     │  └─ ✅ BADGE INJECTED HERE
│        │     │
│        │     ├─ Render headword cell (bold, 13px)
│        │     ├─ Render roman cell (italic, #666)
│        │     ├─ Render POS cell (#888, 11px)
│        │     └─ Render sense cell (segmentable)
│        │
│        ├─ else if (tabCount === 2) [POS + continuation]
│        │  └─ Render POS and sense continuation (no badge injection)
│        │
│        └─ else [Continuation or misc note]
│           └─ Render continuation (no badge injection)
│
└─ Return HTML
```

**Badge Injection Details (line 3813-3815):**
```javascript
if (!metaInjected && entryMetaHtml) {
  headwordHtml = '<span class="sense-head-inline">' +
                 '<span class="sense-head-inline-main">' + headwordHtml + '</span>' +
                 entryMetaHtml +  // <-- BADGE HTML INJECTED HERE
                 '</span>';
  metaInjected = true;
}
```

**Key:** Only the FIRST headword row (where tabCount===0 and skipHead condition allows) gets the badge. All subsequent rows skip it.

---

### renderStackedSenseLines (reader.js:3962)

```
renderStackedSenseLines(senses, skipHeadText, formsMetaByHeader, options)
│
├─ forceSenseHead = !!options.forceSenseHead
├─ entryMetaHtml = String(options.entryMetaHtml || '')
├─ headerCount = count of \x1E prefix lines
├─ singleHeaderText = text of last \x1E line
│
├─ suppressSingleHeader = !forceSenseHead
│                      && !isJapaneseLanguage()
│                      && (headerCount === 1
│                          && !!skipHeadText
│                          && singleHeaderText === skipHeadText)
│
├─ HTML setup (line 3981-3990)
│  └─ metaInjected = false
│
└─ For each sense line:
   │
   ├─ if (line starts with \x1E) [Forms header]
   │  │
   │  ├─ Line 3992-4010: if (!suppressSingleHeader)
   │  │  │
   │  │  ├─ Extract forms metadata
   │  │  ├─ Build formsHeaderHtml
   │  │  │
   │  │  ├─ Line 4004-4006: if (!metaInjected && entryMetaHtml)
   │  │  │  └─ Inject badge into forms header
   │  │  │  └─ metaInjected = true
   │  │  │  └─ ✅ BADGE INJECTED HERE
   │  │  │
   │  │  └─ Render header with bold, 13px
   │  │
   │  └─ Open 2-column grid for sense rows below
   │
   ├─ else if (tabCount === 2) [POS + sense]
   │  └─ Render POS cell + sense cell (no badge)
   │
   └─ else [Continuation]
      └─ Render continuation (no badge)

└─ Return HTML
```

**Silent Badge Suppression in Stacked Renderer:**

If `suppressSingleHeader === true`:
- The entire `\x1E` header block (the injection point) is skipped
- **Badge is never injected** because no headword row renders
- This happens when: exactly 1 header, non-Japanese, `forceSenseHead=false`, and header text matches `skipHead`

Since **all callers in buildPopupForWord set `forceSenseHead: true`**, this suppression is normally prevented. But if `buildConcatenatedFillEntriesHtml` calls renderDictTemplate without `forceSenseHead`, this suppression can fire.

---

## Why Synthetic Badges Disappear

### Problem 1: buildConcatenatedFillEntriesHtml (Line 2483)

**Multi-fill entries** (like Gemini morphology entries) take this code path:

```javascript
// Line 13407-13414 in buildPopupForWord
if (useConcatenatedFill) {  // fill.length > 1
  var concatHtml = buildConcatenatedFillEntriesHtml(fill, word, {...});
}

// Line 2483 in buildConcatenatedFillEntriesHtml
renderDictTemplate(part, partHead, {
  showHead: true,
  showRomanUnknown: true,
  showSensesKnown: true,
  showEmpty: true,
  sensesKey: opts.sensesKey,
  showFilteredNote: !!opts.showFilteredNote,
  showOtherDefsDropdown: !!opts.showOtherDefsDropdown
  // ❌ MISSING: entryMetaHtml
  // ❌ MISSING: forceSenseHead
});
```

**Why badge disappears:**
- Each fill piece has `part._dict_source = "gemini"` (set by prepareFillEntries)
- But renderDictTemplate receives no `entryMetaHtml`, so no badge HTML is built
- Result: 4-column grid (line 3795) renders but with `entryMetaHtml = ''`
- Line 3813 condition `if (!metaInjected && entryMetaHtml)` fails (empty string)
- **Badge silently never injected**

**Also:** No `forceSenseHead` passed, so line 3808-3809 can suppress headword if skipHead is set.

### Problem 2: buildDictSourceBadgeHtml Doesn't Use Fill Fallback (Line 675)

```javascript
function buildDictSourceBadgeHtml(entry) {
  var badgeInfo = getDictSourceBadgeInfo(entry);  // ❌ NO OPTIONS PASSED
  if (!badgeInfo) return '';
  // ...
}

function getDictSourceBadgeInfo(entry, options) {
  // Read entry._dict_source, entry._source, entry.source

  // ❌ DEAD CODE: never reaches line 656-664 fill fallback
  if (!dictSrc && options && options.includeFillFallback && entry.dict_fill) {
    // This checks fill[i]._dict_source but is never called
  }
}
```

**Why it matters:**
- If top-level `entry._dict_source` is not set (e.g., by buildResultsBySeg), the badge fails
- Even though `fill[0]._dict_source = "gemini"` exists, it's not checked
- Result: Badge HTML is `''` even when fill pieces have source info

### Problem 3: Alternate Senses Path (Line 14401)

```javascript
// Line 14395-14401 in renderDictTemplate
if (showOtherDefsDropdown && hasFilteredAlternates) {
  html += '<details class="panel-filtered-expander">';
  html += '<summary>Other definitions</summary>';
  html += '<div class="panel-filtered-expander-content">' +
    renderSenseLines(altSenses, head, altFormsMetaByHeader)  // ❌ NO OPTIONS
    + '</div>';
}
```

**Why badge disappears:**
- `renderSenseLines(altSenses, head, altFormsMetaByHeader)` is called with 3 args
- No 4th argument (options object with entryMetaHtml)
- Alternate senses never get badge injected

---

## Summary Table: Badge Appearance by Path

| Code Path | Entry Type | Badge Present? | Why |
|-----------|-----------|----------------|-----|
| buildPopupForWord → single-fill → renderDictTemplate | Gemini with 1 fill | ✅ YES | entryMetaHtml passed |
| buildPopupForWord → multi-fill → buildConcatenatedFillEntriesHtml | Gemini with 2+ fills | ❌ NO | entryMetaHtml NOT passed |
| buildPopupForWord → unknown → renderDictTemplate | Any unknown | ✅ YES | entryMetaHtml passed |
| buildPopupForSpan → all variants | Any | ✅ YES | entryMetaHtml passed |
| renderDictTemplate → renderSenseLines (4-col) | Any with entryMetaHtml | ✅ YES | Injected at first headword |
| renderDictTemplate → renderStackedSenseLines | Any with entryMetaHtml | ✅ YES | Injected at forms header |
| renderDictTemplate → alt-senses | Any | ❌ NO | entryMetaHtml NOT passed |
| Side panel cached path | Synthetic | ⚠️ MANUAL | Badge appended after rendering |
| Subsegment popups | Any | ❌ NO | entryMetaHtml NOT passed |

---

## The Canonical Solution Pattern

The rendering system works best when:

1. **Every entry** gets the same metadata (badge HTML, forceSenseHead) at the point where renderDictTemplate is called
2. **Branching logic** (single vs multi vs unknown) determines WHICH entry and WHICH template branch, not WHETHER to pass metadata
3. **All template calls** receive the same options, producing **identical visual output**

This means:
- Line 2483 in buildConcatenatedFillEntriesHtml should pass badge HTML and forceSenseHead
- Line 14401 alt-senses path should pass entryMetaHtml
- Line 675 buildDictSourceBadgeHtml should enable fill fallback
- Subsegment popups should receive full metadata

The goal: **same entry always looks the same, regardless of which code path spawns the popup**.
