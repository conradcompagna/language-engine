"""
Build dict_sqlite/ang-bt.sqlite from Bosworth-Toller txt.
Supplementary to ang.sqlite. Schema matches ang.sqlite exactly.

Conventions:
- Acute-accent vowels in source (á é í ó ú ǽ ý) are converted to macron form
  (ā ē ī ō ū ǣ ȳ) at build time, matching the existing ang.sqlite convention.
- Headwords stored raw (with macrons and þ/ð); normalization layer handles
  fold-to-key at runtime.
- Entries without real glosses are folded into their `v. target` entry as a
  variant form, or dropped if there's no resolvable pointer.
- Latin equivalents are dropped; only English glosses are kept.
"""

import html, json, os, re, sqlite3, sys

SRC = os.path.join(
    os.path.dirname(__file__), "training", "oldeng", "bosworth toller old english.txt"
)
OUT = os.path.join(os.path.dirname(__file__), "dict_sqlite", "ang-bt.sqlite")

# -- entity decoding ---------------------------------------------------------

# Precomposed mappings for "<letter>-acute;" sequences not in HTML standard.
ACUTE_COMBO = {
    "aelig": "ǣ",  # æ + acute  -> macron-æ (our target form)
    "AElig": "Ǣ",
    "oelig": "œ́",  # rare, keep combining
    "OElig": "Œ́",
    "c": "ć",
    "s": "ś",
    "y": "ȳ",
    "Y": "Ȳ",
    "aleig": "ǣ",  # typo in source
    "dash": "-",  # junk
}

# Source uses acute for length. Convert to macron equivalents.
ACUTE_TO_MACRON = str.maketrans(
    {
        "á": "ā",
        "Á": "Ā",
        "é": "ē",
        "É": "Ē",
        "í": "ī",
        "Í": "Ī",
        "ó": "ō",
        "Ó": "Ō",
        "ú": "ū",
        "Ú": "Ū",
        "ý": "ȳ",
        "Ý": "Ȳ",
    }
)

# Extra named entities beyond html.unescape defaults.
EXTRA_ENTITIES = {
    "thorn": "þ",
    "THORN": "Þ",
    "yogh": "ȝ",
    "YOGH": "Ȝ",
    "eth": "ð",
    "ETH": "Ð",
    "aelig": "æ",
    "AElig": "Æ",
    "oelig": "œ",
    "OElig": "Œ",
}


def decode_entities(s):
    # Handle &xxx-acute; first.
    def acute_sub(m):
        name = m.group(1)
        return ACUTE_COMBO.get(name, m.group(0))

    s = re.sub(r"&([A-Za-z]+)-acute;", acute_sub, s)
    # Extra entities.
    for k, v in EXTRA_ENTITIES.items():
        s = s.replace("&" + k + ";", v)
    # Standard HTML entities.
    s = html.unescape(s)
    return s


def to_macron(s):
    return s.translate(ACUTE_TO_MACRON)


# -- paragraph iteration -----------------------------------------------------

SKIP_TAGS_RE = re.compile(
    r"<(?:PAGE|HEADER|letterheader|INTRODUCTION|/INTRODUCTION)[^>]*>.*?(?:</(?:HEADER|letterheader|INTRODUCTION)>|$)",
    re.IGNORECASE | re.DOTALL,
)
# Simpler: drop any <TAG>...</TAG> wrapper lines and <TAG ...> self-closed
LINE_SKIP_RE = re.compile(r"^\s*<(PAGE|HEADER|letterheader|/?INTRODUCTION)\b", re.IGNORECASE)


def read_entries(path):
    """Yield raw entry paragraphs (text starting with <B>headword...)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    # Skip everything up to first real <B> entry after the introduction.
    # Drop <PAGE .../>, <HEADER>...</HEADER>, <letterheader>...</letterheader>
    text = re.sub(r"<PAGE[^>]*>", "", text)
    text = re.sub(r"<HEADER>.*?</HEADER>", "", text, flags=re.DOTALL)
    text = re.sub(r"<letterheader>.*?</letterheader>", "", text, flags=re.DOTALL)
    text = re.sub(r"<INTRODUCTION>.*?</INTRODUCTION>", "", text, flags=re.DOTALL)
    # Entries separated by blank lines
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if not para.startswith("<B>"):
            continue
        yield para


# -- entry parsing -----------------------------------------------------------

TAG_RE = re.compile(r"<(/?[A-Za-z][A-Za-z0-9]*)>")
B_RE = re.compile(r"<B>(.*?)</B>", re.DOTALL)
I_RE = re.compile(r"<I>(.*?)</I>", re.DOTALL)

POS_MAP = [
    # (regex on the italic block start, pos string, extra tags)
    (r"\bv\.\s*a\.", "verb", "transitive"),
    (r"\bv\.\s*trans\.", "verb", "transitive"),
    (r"\bv\.\s*intrans\.", "verb", "intransitive"),
    (r"\bv\.\s*impers\.", "verb", "impersonal"),
    (r"\bv\.\s*refl\.", "verb", "reflexive"),
    (r"\bv\.\s*n\.", "verb", "intransitive"),
    (r"\badj\.", "adj", ""),
    (r"\badv\.", "adv", ""),
    (r"\bprep\.", "prep", ""),
    (r"\bpron\.", "pron", ""),
    (r"\bconj\.", "conj", ""),
    (r"\binterj\.", "intj", ""),
    (r"\bpart\.", "particle", ""),
    (r"\bnum\.", "num", ""),
    (r"\bindecl\.?;\s*m\.", "noun", "masculine;indeclinable"),
    (r"\bindecl\.?;\s*f\.", "noun", "feminine;indeclinable"),
    (r"\bindecl\.?;\s*n\.", "noun", "neuter;indeclinable"),
    (r"\bindecl\.", "noun", "indeclinable"),
    (r"\bm\.", "noun", "masculine"),
    (r"\bf\.", "noun", "feminine"),
    (r"\bn\.", "noun", "neuter"),
]

# Morph tag keys used in the B-T inflection signature.
# Map abbrev -> (morph_tags_string, applies_to_next_form)
MORPH_KEYS = {
    "ic": "1;singular;present",
    "þú": "2;singular;present",
    "ðú": "2;singular;present",
    "he": "3;singular;present",
    "heo": "3;singular;present",
    "hit": "3;singular;present",
    "pl.": "plural",
    "p.": "past",
    "pp.": "past-participle",
    "pres.": "present",
    "subj.": "subjunctive",
    "imp.": "imperative",
    "impert.": "imperative",
    "gen.": "genitive",
    "dat.": "dative",
    "acc.": "accusative",
    "nom.": "nominative",
    "voc.": "vocative",
    "inst.": "instrumental",
    "comp.": "comparative",
    "sup.": "superlative",
    "superl.": "superlative",
}


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def normalize_headword(hw):
    hw = hw.strip().strip(",;: ")
    # Drop trailing single-char junk
    hw = to_macron(hw)
    return hw


def is_english_gloss(s):
    """Heuristic: English gloss lines have at least one space-separated word
    that looks English. Latin glosses tend to end in -us/-are/-ere/-ire/-um
    and have no English function words."""
    s = s.strip().rstrip(",;.")
    if not s:
        return False
    # All-lowercase Latin terminators
    words = [w.strip(",;.") for w in s.split() if w.strip(",;.")]
    if not words:
        return False
    english_markers = {
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "and",
        "or",
        "but",
        "not",
        "is",
        "was",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "one",
        "who",
        "that",
        "which",
        "any",
        "some",
        "by",
        "from",
        "as",
        "it",
        "its",
        "this",
        "these",
        "person",
        "thing",
        "place",
        "time",
    }
    if any(w.lower() in english_markers for w in words):
        return True
    # Single-word glosses: accept if not obviously Latin.
    if len(words) <= 3:
        latin_endings = ("are", "ere", "ire", "us", "um", "is", "atur", "ere.", "are.")
        if all(w.lower().endswith(latin_endings) for w in words):
            return False
        return True
    return False


def parse_entry(para):
    """Return dict or None."""
    # Grab headword group (everything up to first <I>).
    m_first_i = re.search(r"<I>", para)
    head_section = para[: m_first_i.start()] if m_first_i else para
    tail_section = para[m_first_i.start() :] if m_first_i else ""

    # All <B>...</B> blobs in head_section = headword + variants
    bs = B_RE.findall(head_section)
    if not bs:
        return None
    hw_raw = decode_entities(bs[0])
    headword = normalize_headword(strip_tags(hw_raw))
    if not headword:
        return None
    # Variants come from trailing <B> blobs or bare commas in first <B>
    # The first <B> can itself be comma-separated: "abbadisse, abbodisse, abbatisse, abbudisse, abedisse"
    variants = []
    first_b_plain = strip_tags(decode_entities(bs[0]))
    # split on comma at top level
    pieces = [p.strip().rstrip(",;: ") for p in first_b_plain.split(",")]
    pieces = [p for p in pieces if p]
    if len(pieces) > 1:
        headword = to_macron(pieces[0])
        for p in pieces[1:]:
            v = to_macron(p)
            if v and v != headword:
                variants.append(v)
    # Additional <B> blobs after the first (before <I>) are more variants
    for extra in bs[1:]:
        v = to_macron(strip_tags(decode_entities(extra))).strip().rstrip(",;: ")
        if v and v != headword and v not in variants:
            variants.append(v)

    # Parse inflection signature from text between first <B>...</B> and first <I>
    # Pattern: "; p. -bealg, -bealh, pl. -bulgon; pp. -bolgen"
    sig_region = head_section
    # Remove <B>...</B> groups from the sig region
    sig_region = B_RE.sub(" ", sig_region)
    sig_region = strip_tags(decode_entities(sig_region))
    forms_from_sig = parse_inflection_signature(sig_region, headword)

    # POS + gloss: look at first <I>...</I> blocks
    italics = [decode_entities(x) for x in I_RE.findall(tail_section)]
    italics = [to_macron(strip_tags(x)).strip() for x in italics]
    italics = [x for x in italics if x]

    pos = ""
    pos_tags = ""
    glosses = []
    cross_ref = None

    # Inflection-signature abbrev pattern for stripping from gloss blocks
    infl_strip_rx = re.compile(
        r"\b(?:ic|þú|ðú|he|heo|hit|pl\.|p\.|pp\.|pres\.|subj\.|imp\.|impert\.|"
        r"gen\.|dat\.|acc\.|nom\.|voc\.|inst\.|comp\.|sup\.|superl\.|indecl\.|"
        r"es|an|e|a|an)\b"
    )

    # Locate the first `:--` in the whole paragraph (plain-text form): everything
    # after it is examples/quotations, not glosses.
    plain_full = to_macron(strip_tags(decode_entities(para)))
    cutoff_idx = plain_full.find(":--")

    for idx, ital in enumerate(italics):
        # If this italic starts after the `:--` marker in the original, skip
        if cutoff_idx >= 0 and plain_full.find(ital) > cutoff_idx:
            continue
        # Detect POS in this italic (first one that matches wins)
        ital_clean = ital
        if not pos:
            for rx, p, tags in POS_MAP:
                if re.search(rx, ital_clean):
                    pos = p
                    pos_tags = tags
                    ital_clean = re.sub(rx, "", ital_clean)
                    break
        # Strip inflection-signature keys
        # Use a loop so overlapping don't hide one another
        # But only strip when the token is attached to nothing (standalone abbr)
        cleaned_parts = []
        for sub in re.split(r":--", ital_clean):
            sub = sub.strip()
            if not sub:
                continue
            # Strip leading inflection-sig chunk like "pl. -bacaþ; p. -bóc, pl. -bócon; pp. -bacen"
            # Heuristic: remove any leading segment that matches "<key> <token>[, <token>]*;?"
            pattern = (
                r"^(?:(?:"
                + r"ic|þú|ðú|he|heo|hit|pl\.|p\.|pp\.|pres\.|subj\.|imp\.|impert\.|gen\.|dat\.|acc\.|nom\.|voc\.|inst\.|comp\.|sup\.|superl\.|indecl\."
                + r")\s+[^\s;]+(?:,\s*[^\s;]+)*\s*;?\s*)+"
            )
            sub = re.sub(pattern, "", sub).strip()
            if not sub:
                continue
            cleaned_parts.append(sub)
        for part in cleaned_parts:
            glosses.extend(split_glosses(part))

    clean_glosses = []
    for g in glosses:
        g = g.strip(" ,;.:-—")
        # Drop lone abbreviations like "pl", "m", "f", "n", "adj"
        if not g or len(g) <= 2:
            continue
        if re.fullmatch(r"(?:pl|m|f|n|adj|adv|gen|dat|acc|nom)\.?", g, re.IGNORECASE):
            continue
        if is_english_gloss(g):
            clean_glosses.append(g)

    # Detect cross-reference: "v. TARGET" anywhere in the entry means it points
    # to TARGET. Used for form-only entries.
    # Look in the full plain text.
    plain = to_macron(strip_tags(decode_entities(para)))
    # Exclude v.a./v.trans./v.intrans./v.n./v.refl./v.impers.
    POS_ABBRS = {
        "a",
        "trans",
        "intrans",
        "n",
        "refl",
        "impers",
        "a.",
        "trans.",
        "intrans.",
        "n.",
        "refl.",
        "impers.",
    }
    for m_vref in re.finditer(r"\bv\.\s+([A-Za-zþðǣāēīōūȳæÆÞÐ][A-Za-zþðǣāēīōūȳæÆÞÐ\-]*)", plain):
        target = m_vref.group(1).strip().rstrip(",.;")
        if not target:
            continue
        if target.lower() in POS_ABBRS:
            continue
        if target.lower() == headword.lower():
            continue
        cross_ref = target
        break

    return {
        "headword": headword,
        "variants": variants,
        "pos": pos,
        "pos_tags": pos_tags,
        "glosses": clean_glosses,
        "forms": forms_from_sig,
        "cross_ref": cross_ref,
    }


def split_glosses(s):
    """Split an English gloss blob on ';' -> separate senses.
    Further split on ',' only if the result still looks like full phrases."""
    s = s.strip(" ,;.:-—")
    if not s:
        return []
    parts = [p.strip() for p in re.split(r"\s*;\s*", s) if p.strip()]
    return parts


def expand_dashed_form(form, headword):
    """B-T forms starting with '-' are shorthand for 'headword-root + suffix'.
    Heuristic: prefix with headword minus its last syllable, or minus final
    vowel group. Simplest reliable approach: prefix with the headword's
    initial stem (headword up to last 2 chars). But commonly the dashed
    forms are paradigm tails where the stem is headword minus infinitival
    ending. We'll just prepend the part of the headword before its final
    vowel cluster."""
    if not form.startswith("-"):
        return form
    # Strip leading '-'
    tail = form[1:]
    # Simple approach: the dash stands for the headword's stem, and we
    # reconstruct by replacing the headword's final vocalic ending.
    # B-T convention: for "a-belgan" with "-beige", actual form is "a-beige".
    # So the dash replaces everything up through the last matching consonant
    # cluster. Better heuristic: replace headword's final morpheme.
    # Practical: prefix with everything in headword before the last vowel run.
    m = re.search(r"^(.*?[^aeiouāēīōūȳæǣyæ]*)([aeiouāēīōūȳæǣy].*)$", headword)
    if m:
        return m.group(1) + tail
    return headword + tail


def parse_inflection_signature(sig, headword):
    """Parse '; p. -bealg, -bealh, pl. -bulgon; pp. -bolgen; ic -beige, ðú -bilgst, ...'
    Return list of (form_text, morph_tags) tuples."""
    out = []
    # Split the signature into segments by ';' so each segment has one "header key"
    # Actually keys can appear mid-segment too, so tokenize more carefully.
    # Normalize whitespace
    sig = re.sub(r"\s+", " ", sig).strip()
    if not sig:
        return out
    # Find all "KEY form[, form]*" chunks. Keys can be: ic|þú|ðú|he|heo|hit|
    # pl\.|p\.|pp\.|subj\.|imp\.|gen\.|dat\.|acc\.|nom\.
    key_pattern = r"(?:ic|þú|ðú|he|heo|hit|pl\.|p\.|pp\.|pres\.|subj\.|imp\.|impert\.|gen\.|dat\.|acc\.|nom\.|voc\.|inst\.|comp\.|sup\.|superl\.)"
    # Iterate key positions
    matches = list(re.finditer(r"\b" + key_pattern, sig))
    for i, m in enumerate(matches):
        key = m.group(0)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sig)
        chunk = sig[start:end]
        # Stop at punctuation that definitely ends the inflection area: ':--' or end-paren
        chunk = chunk.split(":--")[0]
        # Forms are comma-separated tokens
        tokens = [t.strip().strip(",;") for t in chunk.split(",")]
        tokens = [t for t in tokens if t]
        morph = MORPH_KEYS.get(key, key)
        for tok in tokens:
            # Take only the first word of the token (may have trailing prose)
            first_word = tok.split()[0] if tok.split() else ""
            first_word = first_word.strip(".,;:()")
            if not first_word or len(first_word) > 40:
                continue
            # Must contain at least one letter
            if not re.search(r"[A-Za-zþðǣāēīōūȳæÆÞÐ]", first_word):
                continue
            form = expand_dashed_form(first_word, headword)
            out.append((form, morph))
    return out


# -- build -------------------------------------------------------------------


def build():
    print(f"Reading {SRC}")
    entries = []
    skipped_no_head = 0
    for para in read_entries(SRC):
        e = parse_entry(para)
        if e is None:
            skipped_no_head += 1
            continue
        entries.append(e)
    print(f"Parsed {len(entries)} candidate entries (skipped {skipped_no_head}).")

    # Pass 2: classify and resolve cross-refs.
    by_hw = {}
    for e in entries:
        by_hw.setdefault(e["headword"], []).append(e)

    real_entries = []  # entries with glosses -> kept
    to_attach = []  # (target_headword, surface_form, morph_tag) for dropped xrefs
    dropped = 0

    for e in entries:
        if e["glosses"]:
            real_entries.append(e)
        else:
            # No glosses: try to attach as a variant form to cross_ref target
            target = e["cross_ref"]
            if target and target in by_hw:
                to_attach.append((target, e["headword"], "variant"))
            else:
                dropped += 1

    # Collapse multiple entries with the same headword? Keep separate (homographs).
    # Merge attachments into real entries.
    attach_map = {}
    for tgt, form, morph in to_attach:
        attach_map.setdefault(tgt, []).append((form, morph))

    print(f"Keeping {len(real_entries)} entries with glosses.")
    print(f"Redirecting {len(to_attach)} glossless entries as variants.")
    print(f"Dropping {dropped} glossless entries with no resolvable target.")

    # Build DB
    if os.path.exists(OUT):
        os.remove(OUT)
    conn = sqlite3.connect(OUT)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            headword TEXT NOT NULL,
            romanization TEXT NOT NULL DEFAULT '',
            pos TEXT NOT NULL DEFAULT '',
            glosses TEXT NOT NULL DEFAULT '[]',
            forms TEXT NOT NULL DEFAULT '[]',
            commentary TEXT NOT NULL DEFAULT '',
            lemma TEXT NOT NULL DEFAULT '',
            etymology TEXT NOT NULL DEFAULT '',
            etymology_number INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT '',
            entry_id TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT 'compact'
        );
        CREATE TABLE forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES entries(id),
            form_text TEXT NOT NULL,
            morph_tags TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != '';
        CREATE INDEX idx_entries_headword ON entries(headword);
        CREATE INDEX idx_forms_entry_id ON forms(entry_id);
        CREATE INDEX idx_forms_form_text ON forms(form_text);
    """)

    c.execute("INSERT INTO meta VALUES (?,?)", ("source", "bosworth-toller"))
    c.execute("INSERT INTO meta VALUES (?,?)", ("lang", "ang"))
    c.execute(
        "INSERT INTO meta VALUES (?,?)",
        ("notes", "Supplementary. Acutes converted to macrons at build time."),
    )

    for e in real_entries:
        glosses_json = json.dumps([{"glosses": [g]} for g in e["glosses"]], ensure_ascii=False)
        # Build forms list
        form_tuples = list(e["forms"])
        # Variants from the headword line
        for v in e["variants"]:
            form_tuples.append((v, "variant"))
        # Attached redirects
        for v, m in attach_map.get(e["headword"], []):
            form_tuples.append((v, m))
        # Dedupe while preserving order
        seen = set()
        deduped = []
        for f, m in form_tuples:
            key = (f, m)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((f, m))
        forms_json = json.dumps([[f, m, ""] for f, m in deduped], ensure_ascii=False)
        c.execute(
            """
            INSERT INTO entries (headword, pos, glosses, forms, tags, source, format)
            VALUES (?,?,?,?,?,?,?)
        """,
            (
                e["headword"],
                e["pos"],
                glosses_json,
                forms_json,
                e["pos_tags"],
                "bosworth-toller",
                "compact",
            ),
        )
        entry_id = c.lastrowid
        for f, m in deduped:
            c.execute(
                "INSERT INTO forms (entry_id, form_text, morph_tags) VALUES (?,?,?)",
                (entry_id, f, m),
            )

    conn.commit()
    # Stats
    n_entries = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    n_forms = c.execute("SELECT COUNT(*) FROM forms").fetchone()[0]
    print(f"Wrote {OUT}: {n_entries} entries, {n_forms} forms.")
    conn.close()


if __name__ == "__main__":
    build()
