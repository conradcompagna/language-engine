"""
gemini_dict.py — Gemini Flash Lite synthetic dictionary generation.

Entries are stored as TSV files in gemini_generated_tsvs/{lang_code}.tsv:
    headword\tromanization\tpos\tglosses\tforms\tcommentary\tlemma

Each surface token is stored as its own singleton row.  The canonical/lemma
form (if different from the surface) and Gemini's commentary tags are stored
in dedicated columns rather than collapsed onto an existing lemma row.

To disable: set GEMINI_DICT_ENABLED = False or remove the API key.
Budget is shared with the chatbot via ApiUsage.
"""
import json
import logging
import re
import time
import unicodedata
import uuid
from pathlib import Path

import requests

from config import GEMINI_API_KEY
from dict_lookup_sqlite import (
    delete_custom_form_index_entry,
    ensure_custom_form_index,
    sync_custom_form_index_entry,
)

log = logging.getLogger(__name__)

# Feature flag
GEMINI_DICT_ENABLED = True

# Model — stable low-cost Gemini option
GEMINI_DICT_MODEL = "gemini-3.1-flash-lite"

# Folder for generated TSVs
TSV_DIR = Path(__file__).resolve().parent / "gemini_generated_tsvs"
TSV_HEADER = "headword\tromanization\tpos\tglosses\tforms\tcommentary\tlemma"
LEGACY_TSV_HEADER = "headword\tromanization\tpos\tglosses\tlabel\tlemma\tforms"

# ---------------------------------------------------------------------------
# Language morphology / romanization policy
# ---------------------------------------------------------------------------

# Languages whose primary script is non-Latin — Gemini MUST produce romanization.
# For all other registered languages, romanization is forbidden (null).
LANGS_REQUIRING_ROMANIZATION: frozenset[str] = frozenset({
    "zh", "lzh", "ja", "ko", "th", "ar", "fa", "ur", "hi",
    "ta", "bn", "pa", "he", "hbo", "hy", "ru", "el", "grc",
})

# Inflecting UPOS per language. Value is a frozenset of UPOS tags (uppercased)
# for which the language carries productive token-level inflection.
# If a language is absent from this map, it is treated as non-inflecting.
# Source: binary UD matrix supplied by the user.
LANGS_WITH_MORPHOLOGY: dict[str, frozenset[str]] = {
    # European / classical — full-blown inflection
    "la":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "grc": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "el":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ang": frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ru":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "de":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "nl":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "fr":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "it":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "es":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    "pt":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "VERB"}),
    # Celtic / Semitic / Indo-Iranian / Armenian / Turkic
    "ga":  frozenset({"ADJ", "ADP", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ar":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "he":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "VERB"}),
    "hbo": frozenset({"ADJ", "AUX", "NOUN", "PRON", "VERB"}),
    "fa":  frozenset({"AUX", "NOUN", "PRON", "VERB"}),
    "ur":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "hi":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "sa":  frozenset({"ADJ", "AUX", "DET", "NOUN", "NUM", "PRON", "PROPN", "VERB"}),
    "ta":  frozenset({"AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    "bn":  frozenset({"ADJ", "AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    "pa":  frozenset({"ADJ", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "hy":  frozenset({"ADJ", "ADP", "AUX", "DET", "NOUN", "PRON", "PROPN", "VERB"}),
    "tr":  frozenset({"AUX", "NOUN", "PRON", "PROPN", "VERB"}),
    # East Asian / Southeast Asian / African — narrow or none
    "ko":  frozenset({"ADJ", "AUX", "VERB"}),
    "ja":  frozenset({"ADJ", "AUX", "VERB"}),
    "id":  frozenset({"VERB"}),
    "tl":  frozenset({"PRON", "VERB"}),
    "sw":  frozenset({"ADJ", "DET", "NOUN", "NUM", "PRON", "VERB"}),
    # Fully isolating — no entry needed but listed for clarity (empty set)
    "zh":  frozenset(),
    "lzh": frozenset(),
    "vi":  frozenset(),
    "th":  frozenset(),
}


def _requires_romanization(lang_code: str) -> bool:
    return (lang_code or "").strip().lower() in LANGS_REQUIRING_ROMANIZATION


def _upos_inflects(lang_code: str, upos: str) -> bool:
    """True if `upos` is in this language's inflecting UPOS set."""
    code = (lang_code or "").strip().lower()
    tag = (upos or "").strip().upper()
    if not code or not tag:
        return False
    return tag in LANGS_WITH_MORPHOLOGY.get(code, frozenset())


# Inflectional feature keys — presence of any of these in the Trankit feats
# string forces the entry generator to produce lemma + morphological analysis.
# Derived from the complete FEATS dictionary in static/TRANKIT_TAGS.js (the
# authoritative reference for tags produced by the custom-trained Trankit
# models). Excludes lexical-category refinements (PronType, NumType, NameType,
# AdpType, AdvType, ConjType, NounType, VerbType, InflClass), metadata (Abbr,
# Foreign, Typo, Style, Dialect, ExtPos, NumForm, NumValue, Compound, Hyph,
# Prefix), and noise (Distance, Echo, Invariable, Subcat, PartType, Variant,
# Uninflected, inflectedUninflected).
# Bracketed agreement variants like `Number[psor]` / `Person[obj]` are
# handled by stripping the `[...]` suffix before comparing.
_INFLECTIONAL_FEATURE_KEYS: frozenset[str] = frozenset({
    # User-specified core UD inflectional features
    "Gender", "VerbForm", "Animacy", "Mood", "NounClass", "Tense",
    "Number", "Aspect", "Case", "Voice", "Definite", "Evident",
    "Deixis", "Polarity", "DeixisRef", "Person", "Degree", "Polite",
    "Clusivity",
    # Additional inflectional features present in TRANKIT_TAGS.js FEATS
    "Clitic", "Connegative", "Form", "Formation", "HebBinyan", "InfForm",
    "Poss", "PrepCase", "PrepForm", "Reflex",
    # Agreement-target noun class/number/person/gender (e.g. ObjNumber,
    # RelPerson, ObjNounClass) — Bantu / Semitic / Celtic agreement markers
    "ObjNumber", "ObjPerson", "ObjNounClass",
    "RelNumber", "RelPerson", "RelNounClass",
})


def _trankit_requires_morph(surface: str, lemma_hint: str, feats: str, lang_code: str = "") -> bool:
    """Decide whether Gemini should lemmatize / give morph analysis.

    Returns True only when Trankit reported at least one inflectional feature
    from `_INFLECTIONAL_FEATURE_KEYS`.
    Bracketed agreement variants like `Number[psor]` are normalized by
    stripping the `[...]` suffix before comparison.
    """
    feats_str = (feats or "").strip()
    is_sanskrit = (lang_code or "").strip().lower() in ("sa", "sanskrit")
    if feats_str and feats_str != "_":
        for part in feats_str.split("|"):
            key, _, val = part.partition("=")
            key = key.strip()
            # Sanskrit Case=Compound marks a bare compound stem — not an inflected form.
            if is_sanskrit and key.lower() == "case" and val.strip().lower() == "compound":
                continue
            # Strip bracketed agreement suffix: Number[psor] -> Number
            bracket = key.find("[")
            if bracket > 0:
                key = key[:bracket]
            if key in _INFLECTIONAL_FEATURE_KEYS:
                return True
    return False


_POS_ENUM = [
    "noun", "verb", "adj", "adv", "pron", "det", "num", "conj",
    "prep", "postp", "particle", "intj", "suffix", "prefix",
    "name", "phrase",
]


def _build_response_schema(requires_roman: bool, inflects: bool) -> dict:
    """Per-call schema. Only includes fields the model is allowed/required to emit."""
    props: dict = {}
    ordering: list[str] = []
    required: list[str] = []

    if requires_roman:
        props["romanization"] = {
            "type": "string",
            "description": "MANDATORY romanization of the target word (non-Latin script language).",
        }
        ordering.append("romanization")
        required.append("romanization")

    props["pos"] = {
        "type": "string",
        "enum": _POS_ENUM,
        "description": "Choose the best matching part of speech.",
    }
    ordering.append("pos")
    required.append("pos")

    props["glosses"] = {
        "type": "string",
        "description": "1-5 short English glosses explaining the meaning of the target word separated by semicolons.",
    }
    ordering.append("glosses")
    required.append("glosses")

    if inflects:
        props["lemma"] = {
            "type": "string",
            "description": (
                "MANDATORY: lemmatize the word, reducing it to its uninflected base form."
            ),
        }
        props["morphological properties"] = {
            "type": "string",
            "description": (
                "MANDATORY: brief labels tagging the surface form's morphological "
                "properties using full unabbreviated Universal Dependencies category names "
                "(e.g. case, number, gender, animacy, noun class, person, tense, aspect, "
                "mood, voice, verb form, definiteness, degree, pronoun type, polarity, "
                "politeness, clusivity, evidentiality)."
            ),
        }
        ordering.extend(["lemma", "morphological properties"])
        required.extend(["lemma", "morphological properties"])

    return {
        "type": "object",
        "propertyOrdering": ordering,
        "properties": props,
        "required": required,
    }


def _build_system_prompt(requires_roman: bool, inflects: bool) -> str:
    parts = [
        "You are a dictionary entry generator for a commercial reader app.",
        "You are to analyze the surface form of the word provided to you.",
        "Choose the best part of speech from the selection provided, and provide 1-5 concise English"
        " glosses explaining the meaning of the target word.",
    ]
    if requires_roman:
        parts.append("The target is written in a non-Latin script: you MUST provide an accurate romanization.")
    if inflects:
        parts.append(
            "If the word is inflected, you MUST lemmatize it, reducing it to its uninflected base form,"
            " and provide brief labels tagging its morphological properties using full unabbreviated"
            " Universal Dependencies category names (e.g. case, number, gender, animacy, person,"
            " tense, aspect, mood, voice, degree, verb form, definiteness, pronoun type, polarity,"
            " politeness, clusivity)."
        )
        parts.append(
            "Examples:\n"
            "  Latin — portārum (noun): lemma=porta, morphological properties=genitive plural feminine\n"
            "  Russian — писала (verb): lemma=писать, morphological properties=past tense, feminine, singular\n"
            "  German — schönsten (adj): lemma=schön, morphological properties=superlative degree, dative plural\n"
            "  Ancient Greek — ἔλυσαν (verb): lemma=λύω, morphological properties=aorist tense, active voice, third person plural\n"
            "  Sanskrit — rājñaḥ (noun): lemma=rājan, morphological properties=genitive singular masculine"
        )
    else:
        parts.append("This word does not inflect: DO NOT output `lemma` or `morphological properties` fields.")
        parts.append(
            "Examples:\n"
            "  French — vite (adv): glosses=quickly; fast\n"
            "  Turkish — ev (noun): glosses=house; home\n"
            "  Indonesian — pergi (verb): glosses=go; leave; depart\n"
            "  Swahili — haraka (adv): glosses=quickly; hastily\n"
            "  Vietnamese — đẹp (adj): glosses=beautiful; pretty; attractive"
        )
    return " ".join(parts)


def is_enabled() -> bool:
    return bool(GEMINI_DICT_ENABLED and GEMINI_API_KEY)


def get_tsv_path(lang_code: str) -> Path:
    return TSV_DIR / f"{lang_code.lower()}.tsv"


def get_tsv_text(lang_code: str) -> str:
    """Return TSV file content for this language, or empty string if none."""
    path = get_tsv_path(lang_code)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_entry(
    token: str,
    sentence: str,
    lang_code: str,
    lemma_hint: str = "",
    upos: str = "",
    xpos: str = "",
    feats: str = "",
    dep: str = "",
    surface_form: str = "",
    target_word: str = "",
    user=None,
) -> dict | None:
    """Generate a dictionary entry for one token via Gemini.

    Each surface token is stored as its own singleton row.  The canonical
    form and commentary are stored in dedicated columns.

    Returns frontend-compatible entry dict or None.
    Budget-tracks if user is provided.
    """
    if not is_enabled():
        return None

    # Budget check
    if user is not None:
        from db import db, ApiUsage
        usage = ApiUsage.query.filter_by(user_id=user.id).first()
        if not usage:
            usage = ApiUsage(user_id=user.id)
            db.session.add(usage)
            db.session.commit()
        if not usage.can_use_llm(user):
            log.info("Gemini dict: budget exhausted for user %s", user.id)
            return None

    try:
        entry, usage_counts = _call_gemini(
            token,
            sentence,
            lang_code,
            lemma_hint=lemma_hint,
            upos=upos,
            xpos=xpos,
            feats=feats,
            dep=dep,
            surface_form=surface_form,
            target_word=target_word,
        )
    except Exception as e:
        log.warning("Gemini dict: API call failed: %s", e)
        return None

    if not entry:
        return None

    # Write to TSV — may merge into existing canonical row
    stored_entry = _store_generated_entry_db(lang_code, entry)

    # Record usage
    if user is not None:
        from db import db, ApiUsage
        usage = ApiUsage.query.filter_by(user_id=user.id).first()
        if usage:
            usage.record_llm(
                usage_counts.get("prompt_tokens", 0),
                usage_counts.get("response_tokens", 0),
            )
            db.session.commit()

    return _entry_to_frontend(stored_entry or entry)


def _entry_to_frontend(entry: dict) -> dict:
    """Convert internal entry dict to the format expected by the frontend."""
    glosses = entry.get("glosses") or []
    if isinstance(glosses, str):
        glosses = [g.strip() for g in glosses.split(";") if g.strip()]

    return {
        "headword": entry.get("headword", ""),
        "pos": entry.get("pos", ""),
        "romanization": entry.get("romanization", ""),
        "glosses": glosses,
        "forms": entry.get("forms") or [],
        "commentary": entry.get("commentary", ""),
        "lemma": entry.get("canonical_form", "") or entry.get("lemma", ""),
    }


# ---------------------------------------------------------------------------
# TSV file helpers
# ---------------------------------------------------------------------------

def _parse_tsv_rows(path: Path) -> tuple[str, list[dict]]:
    """Read a TSV file and return (header_line, list_of_row_dicts).

    Each row dict has keys matching the header columns.
    """
    if not path.exists() or path.stat().st_size == 0:
        return "", []

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return "", []

    header = lines[0].strip()
    cols = header.split("\t")
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        fields = line.split("\t")
        row = {}
        for i, col in enumerate(cols):
            row[col] = fields[i] if i < len(fields) else ""
        rows.append(row)
    return header, rows


def _write_tsv_file(path: Path, header: str, rows: list[dict]):
    """Rewrite the entire TSV file from header + row dicts.
    Automatically upgrades old headers to include commentary and lemma columns."""
    # Upgrade old 5-column header to new 7-column header
    if header == "headword\tromanization\tpos\tglosses\tforms":
        header = TSV_HEADER
    cols = header.split("\t")
    lines = [header]
    for row in rows:
        fields = [str(row.get(c, "")) for c in cols]
        lines.append("\t".join(fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _write_entry(lang_code: str, entry: dict):
    """Write an entry to the TSV as a singleton row.

    The surface form is always the headword.  The canonical/lemma form
    (if different) and Gemini's commentary tags are stored in their own
    columns so the edit UI can display them.
    """
    TSV_DIR.mkdir(exist_ok=True)
    path = get_tsv_path(lang_code)

    # Parse glosses to senses format
    glosses_raw = entry.get("glosses") or ""
    if isinstance(glosses_raw, str):
        gloss_list = [g.strip() for g in glosses_raw.split(";") if g.strip()]
    else:
        gloss_list = glosses_raw
    senses = [{"glosses": [g]} for g in gloss_list]

    entry["forms"] = entry.get("forms") or []
    _append_tsv_row(path, entry, senses)


def _append_tsv_row(path: Path, entry: dict, senses: list[dict]):
    """Append a single new row to the TSV file."""
    forms = entry.get("forms") or []
    commentary = _tsv_escape(entry.get("commentary", ""))
    lemma = _tsv_escape(entry.get("canonical_form", "") or entry.get("lemma", ""))

    existing_header = ""
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing_header = (f.readline() or "").strip()
        except Exception:
            existing_header = ""

    OLD_COMPACT_HEADER = "headword\tromanization\tpos\tglosses\tforms"

    if existing_header == LEGACY_TSV_HEADER:
        row = "\t".join([
            _tsv_escape(entry.get("headword", "")),
            _tsv_escape(entry.get("romanization", "")),
            _tsv_escape(entry.get("pos", "")),
            json.dumps(senses, ensure_ascii=False),
            "",
            "[]",
            json.dumps(forms, ensure_ascii=False),
        ])
    else:
        # Migrate old 5-column header to new 7-column header on first new append
        if existing_header == OLD_COMPACT_HEADER:
            _migrate_tsv_header(path, OLD_COMPACT_HEADER, TSV_HEADER)

        row = "\t".join([
            _tsv_escape(entry.get("headword", "")),
            _tsv_escape(entry.get("romanization", "")),
            _tsv_escape(entry.get("pos", "")),
            json.dumps(senses, ensure_ascii=False),
            json.dumps(forms, ensure_ascii=False),
            commentary,
            lemma,
        ])

    needs_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        if needs_header:
            f.write(TSV_HEADER + "\n")
        f.write(row + "\n")


def _migrate_tsv_header(path: Path, old_header: str, new_header: str):
    """Replace the first line of a TSV file to upgrade the header.
    Existing rows keep their original columns; new columns will be empty."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith(old_header):
            content = new_header + content[len(old_header):]
            path.write_text(content, encoding="utf-8", newline="")
    except Exception:
        pass


def _tsv_escape(s: str) -> str:
    """Escape tabs and newlines for TSV safety."""
    return str(s).replace("\t", " ").replace("\n", " ").replace("\r", "")


# ---------------------------------------------------------------------------
# Gemini API call — structured JSON output via responseSchema
# ---------------------------------------------------------------------------

def _call_gemini(
    token: str,
    sentence: str,
    lang_code: str,
    lemma_hint: str = "",
    upos: str = "",
    xpos: str = "",
    feats: str = "",
    dep: str = "",
    surface_form: str = "",
    target_word: str = "",
) -> tuple[dict | None, dict]:
    """Call Gemini for a single token. Returns (entry_dict, usage_counts)."""
    _ = (xpos, dep, upos)
    requires_roman = _requires_romanization(lang_code)
    target_text = (
        str(target_word or "").strip()
        or str(surface_form or "").strip()
        or str(token or "").strip()
    )
    inflects = _trankit_requires_morph(target_text, lemma_hint, feats, lang_code)
    response_schema = _build_response_schema(requires_roman, inflects)
    system_prompt = _build_system_prompt(requires_roman, inflects)
    user_prompt_lines = [f"Sentence context: {sentence}"]
    user_prompt_lines.append(f"Target: {target_text}")
    user_prompt = "\n".join(user_prompt_lines)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": 1000,
        },
    }

    for _attempt in range(3):
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 503:
            log.warning("Gemini dict: 503 overloaded, retrying in 5s...")
            time.sleep(5)
            continue
        if resp.status_code != 200:
            log.warning("Gemini dict: HTTP %d response body: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()
    data = resp.json()

    # Log the full communication
    try:
        from gemini_log import log_gemini_call
        log_gemini_call("dict_generation", GEMINI_DICT_MODEL, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("Gemini dict: no candidates in response")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("Gemini dict: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    if not isinstance(parsed, dict):
        log.warning("Gemini dict: expected object, got %s", type(parsed))
        return None, usage_counts

    surface_token = str(token or "").strip()

    romanization = str(parsed.get("romanization", "") or "").strip() if requires_roman else ""
    if inflects:
        # Schema sends "morphological properties" and "lemma"; remap to internal names
        commentary = str(parsed.get("morphological properties", "") or "").strip()
        canonical_raw = str(parsed.get("lemma", "") or "").strip()
    else:
        commentary = ""
        canonical_raw = ""

    entry = {
        "headword": surface_token,
        "pos": parsed.get("pos", ""),
        "romanization": romanization,
        "glosses": parsed.get("glosses", ""),
        "commentary": commentary,
        "canonical_form": canonical_raw,
    }

    return entry, usage_counts


# ---------------------------------------------------------------------------
# Entry notes — reader annotations generated by Gemini
# ---------------------------------------------------------------------------

_NOTE_SYSTEM_PROMPT = (
    "You are an expert semantic annotator for a multilingual reader app. "
    "The reader is looking at a dictionary entry and requires elaboration on the meaning of the target word. "
    "Read the context provided, then enrich the entry by adding a short note (max 50 words) that briefly explains "
    "the core meaning of the word, or meanings if the word is polysemous."
)


def generate_entry_note(
    lang: str,
    db_alias: str,
    entry_row_id: int,
    headword: str,
    pos: str = "",
    model: str = "",
    sentence_tokens: list | None = None,
    fills: list | None = None,
) -> dict:
    """Generate a reader note for a dictionary entry via Gemini.

    Fetches the full entry from SQLite, then calls the shared Gemini wrapper
    with a system prompt that elaborates on core meaning and etymology.

    Returns {"ok": True, "note": str, "usage_meta": dict}
         or {"ok": False, "error": str}.
    """
    if not is_enabled():
        return {"ok": False, "error": "LLM service not configured."}

    # Hydrate full entry from SQLite
    glosses = ""
    try:
        from dict_lookup_sqlite import hydrate_winner_refs, SQLITE_DIR
        import json as _json
        candidate = {
            "_storage_kind": "sqlite" if db_alias != "customdb" else "custom",
            "_storage_db_alias": db_alias,
            "_storage_row_id": entry_row_id,
            "_match_kind": "headword",
            "match_key": headword,
        }
        db_paths = None
        if db_alias and db_alias != "customdb":
            p = SQLITE_DIR / f"{db_alias}.sqlite"
            if p.exists():
                db_paths = [p]
        hydrated = hydrate_winner_refs([candidate], lang, db_paths=db_paths)
        if hydrated:
            ent = next(iter(hydrated.values()))
            # Glosses
            raw = ent.get("glosses") or "[]"
            if isinstance(raw, str):
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = []
            gloss_parts = []
            for sense in (raw or []):
                if isinstance(sense, dict):
                    inner = sense.get("glosses") or []
                    for g in (inner if isinstance(inner, list) else [inner]):
                        text = str(g).strip() if g else ""
                        if text:
                            gloss_parts.append(text)
                elif isinstance(sense, str) and sense.strip():
                    gloss_parts.append(sense.strip())
            glosses = "; ".join(gloss_parts)
            # Forms (surface + per-form morph tags — native Wiktionary morphology lives here)
            forms_raw = ent.get("forms") or "[]"
            if isinstance(forms_raw, str):
                try:
                    forms_raw = _json.loads(forms_raw)
                except Exception:
                    forms_raw = []
            form_labels = []
            for f in (forms_raw or [])[:12]:
                if isinstance(f, (list, tuple)) and len(f) >= 2:
                    w = str(f[0] or "").strip()
                    t = str(f[1] or "").strip()
                    if w:
                        form_labels.append(f"{w} [{t}]" if t else w)
                elif isinstance(f, dict):
                    w = str(f.get("form") or f.get("word") or "").strip()
                    t_raw = f.get("tags") or f.get("tag") or ""
                    if isinstance(t_raw, list):
                        t = " ".join(str(x) for x in t_raw).strip()
                    else:
                        t = str(t_raw).strip()
                    if w:
                        form_labels.append(f"{w} [{t}]" if t else w)
            forms_text = "; ".join(form_labels)
            # Lemma + morphology commentary (the latter is populated on Gemini entries)
            lemma_text = str(ent.get("lemma") or "").strip()
            morph_text = str(ent.get("commentary") or "").strip()
            # Etymology, reading/romanization, entry-level tags, pos
            etymology_text = str(ent.get("etymology") or "").strip()
            reading_text = str(ent.get("reading") or ent.get("romanization") or "").strip()
            tags_text = str(ent.get("tags") or "").strip()
            pos_from_entry = str(ent.get("pos_raw") or ent.get("pos") or "").strip()
    except Exception:
        pass

    # Build user prompt
    entry_parts = []
    if glosses:
        entry_parts.append(f"Glosses: {glosses}")
    entry_summary = "\n".join(p for p in entry_parts if p)

    user_prompt = f"Word: {headword}\nLanguage: {lang}"
    if entry_summary:
        user_prompt += f"\nEntry visible to reader:\n{entry_summary}"

    # Sentence-level token stream (surface tokens in order).
    tok_stream = [str(t).strip() for t in (sentence_tokens or []) if str(t or "").strip()]
    if tok_stream:
        user_prompt += "\nSentence tokens (context only): " + " | ".join(tok_stream[:200])

    # Fills attached to the target token. Each fill describes one dictionary
    # sub-match inside the same surface. One of them is the TARGET; the others
    # are sibling fills (e.g. a greedy-matched prefix).
    fills_lines = []
    if isinstance(fills, list):
        for f in fills:
            if not isinstance(f, dict):
                continue
            surf = str(f.get("surface") or f.get("match_key") or "").strip()
            hw = str(f.get("headword") or "").strip()
            gl = f.get("glosses") or []
            if isinstance(gl, str):
                gl = [gl]
            gl_txt = "; ".join(str(g).strip() for g in gl if str(g or "").strip())[:160]
            is_target = bool(f.get("is_target"))
            tag = "TARGET" if is_target else "other"
            parts = [f"[{tag}]", f"surface={surf}" if surf else "", f"headword={hw}" if hw else ""]
            if gl_txt:
                parts.append(f"glosses={gl_txt}")
            fills_lines.append(" ".join(p for p in parts if p))
    if fills_lines:
        user_prompt += (
            "\nDictionary fills on this token (the target word is flagged TARGET; "
            "others are sibling sub-entries greedily attached to the same surface):\n"
            + "\n".join(fills_lines[:8])
        )

    from api_services import _call_gemini
    result = _call_gemini(
        model or GEMINI_DICT_MODEL,
        [{"text": user_prompt}],
        system_prompt=_NOTE_SYSTEM_PROMPT,
        caller="entry_note_generate",
        max_output_tokens=100,
    )

    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "LLM error.")}

    note_text = result["text"].strip()
    if not note_text:
        return {"ok": False, "error": "Empty response from LLM."}

    usage_meta = result.get("usage_meta") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    output_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    return {
        "ok": True,
        "note": note_text,
        "usage_meta": {
            "input_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - output_tokens)),
            "output_tokens": output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Entry morpheme decompositions — Leipzig-style breakdowns
# ---------------------------------------------------------------------------

_DECOMP_SYSTEM_PROMPT = (
    "You are a morpheme decomposer for a professional-grade reader app used by "
    "academics, journalists, translators and other professionals. "
    "You will receive a dictionary headword with supporting context (part of speech, "
    "glosses, morphological tags, lemma) to help you interpret the form correctly.\n\n"
    "Your job is to fill three fields:\n"
    "  decomposition — the headword split into its constituent morphemes, joined with "
    "hyphens. Bundle features for the SAME morpheme into one slot; only separate "
    "DIFFERENT morphemes.\n"
    "  analysis — a gloss for each morpheme in the same order, joined with hyphens. "
    "Use plain English, no abbreviations (write 'masculine singular nominative ending' "
    "not 'M.SG.NOM').\n"
    "  breakdown — a short natural-English rendering of the whole surface form that "
    "ACTUALLY INCORPORATES the morphological features.  Do NOT just repeat the "
    "dictionary definition of the base word.  Every case ending, tense/aspect/mood "
    "marker, plural marker, possessive affix, voice, negation, etc. must surface in "
    "the English.  Reference guide (apply whichever are present in the form):\n"
    "    - ablative → 'from ...'\n"
    "    - instrumental → 'by / with (as instrument) ...'\n"
    "    - dative → 'to / for ...'\n"
    "    - genitive → 'of ...' / 'belonging to ...'\n"
    "    - locative → 'in / at / on ...'\n"
    "    - vocative → '(address) O ...'\n"
    "    - nominative → '(as subject) ...'\n"
    "    - accusative → '(as object) ...'\n"
    "    - optative / subjunctive → 'might / could / should / may ...'\n"
    "    - imperative → '(command) ...!'\n"
    "    - past / aorist / preterite → '... -ed / did ...'\n"
    "    - future → 'will ...'\n"
    "    - perfect → 'has ...-ed'\n"
    "    - imperfect / progressive → 'was ...-ing'\n"
    "    - conditional → 'would ...'\n"
    "    - causative → 'cause to ...'\n"
    "    - passive → 'be ...-ed' / 'was ...-ed'\n"
    "    - middle/reflexive → '... oneself'\n"
    "    - negation → 'not ...'\n"
    "    - plural → pluralize the noun\n"
    "    - possessive affix → 'my / your / his / our / their ...'\n"
    "    - diminutive → 'little ...' / 'small ...'\n"
    "    - abstract noun ending → turn action/quality into a noun ('-ness', '-ity')\n"
    "    - absolutive / gerund → 'having ...-ed' / 'after ...-ing'\n"
    "  Keep breakdown short (a phrase or two comma-separated variants).  Never emit "
    "a bare dictionary definition that ignores the morphology.\n\n"
    "Examples (shown as decomposition | analysis | breakdown):\n"
    "  dravyāṇām (Sanskrit) → dravya-āṇām | substance-genitive plural ending | of substances, of the ingredients\n"
    "  gṛheṇa (Sanskrit) → gṛha-ena | house-instrumental singular ending | by means of the house, with the house\n"
    "  vane (Sanskrit) → vana-e | forest-locative singular ending | in the forest\n"
    "  gacchet (Sanskrit) → gam-et | go-optative third singular | he might go, he could go\n"
    "  kṛtvā (Sanskrit) → kṛ-tvā | do-absolutive | having done, after doing\n"
    "  prajeśaḥ (Sanskrit) → praja-īśa-ḥ | people-lord-masculine singular nominative ending | the lord of the people (as subject)\n"
    "  Unabhängigkeit (German) → un-abhängig-keit | not-dependent-abstract noun ending | independence, the state of not being dependent\n"
    "  evlerinizden (Turkish) → ev-ler-iniz-den | house-plural-your (plural)-ablative ending | from your houses\n"
    "  فكتبناها (Arabic) → fa-katab-nā-hā | then-write-past tense 1st plural-it (feminine) | and then we wrote it\n"
    "  يذهبون (Arabic) → ya-dhhab-ūna | 3rd person imperfect-go-masculine plural | they are going, they go\n"
    "  ἐλύθη (Ancient Greek) → e-lu-thē | augment (past)-loose-aorist passive 3rd singular | he/she/it was loosed\n"
    "  amaremus (Latin) → am-āre-mus | love-imperfect subjunctive-1st plural | we would love, we might love\n"
    "  portārum (Latin) → port-ārum | gate-genitive plural ending | of the gates\n"
    "  unhappiness (English) → un-happy-ness | negating prefix-happy-abstract noun suffix | the state of not being happy"
)


def generate_entry_decomp(
    lang: str,
    db_alias: str,
    entry_row_id: int,
    headword: str,
    pos: str = "",
    model: str = "",
    glosses: list[str] | None = None,
    forms_tags: list[str] | None = None,
    lemma: str = "",
    trankit: dict | None = None,
) -> dict:
    """Generate a two-field morpheme decomposition for a dictionary entry.

    Returns {"ok": True, "decomp": str (JSON), "usage_meta": dict}
         or {"ok": False, "error": str}.

    The returned decomp string is JSON: {"decomposition": "...", "analysis": "..."}.
    """
    if not is_enabled():
        return {"ok": False, "error": "LLM service not configured."}

    headword = (headword or "").strip()
    if not headword:
        return {"ok": False, "error": "Missing headword."}

    # If caller didn't pass glosses, hydrate from SQLite (same path as note gen)
    if not glosses:
        try:
            from dict_lookup_sqlite import hydrate_winner_refs, SQLITE_DIR
            import json as _json
            candidate = {
                "_storage_kind": "sqlite" if db_alias != "customdb" else "custom",
                "_storage_db_alias": db_alias,
                "_storage_row_id": entry_row_id,
                "_match_kind": "headword",
                "match_key": headword,
            }
            db_paths = None
            if db_alias and db_alias != "customdb":
                p = SQLITE_DIR / f"{db_alias}.sqlite"
                if p.exists():
                    db_paths = [p]
            hydrated = hydrate_winner_refs([candidate], lang, db_paths=db_paths)
            if hydrated:
                ent = next(iter(hydrated.values()))
                raw = ent.get("glosses") or "[]"
                if isinstance(raw, str):
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = []
                collected = []
                for sense in (raw or [])[:6]:
                    if isinstance(sense, dict):
                        inner = sense.get("glosses") or []
                        for g in (inner if isinstance(inner, list) else [inner]):
                            t = str(g).strip() if g else ""
                            if t:
                                collected.append(t)
                    elif isinstance(sense, str) and sense.strip():
                        collected.append(sense.strip())
                if collected:
                    glosses = collected[:6]
        except Exception:
            pass

    lines = [f"Headword: {headword}  (language: {lang})"]
    if pos:
        lines.append(f"Part of speech: {pos}")
    if glosses:
        gl = "; ".join(str(g).strip() for g in glosses if str(g).strip())
        if gl:
            lines.append(f"Glosses: {gl}")
    # Trankit morphological analysis — UPOS, XPOS, morph features, lemma.
    # These inform the decomposition directly: case/number/tense endings
    # surfaced by the analyzer should be reflected in the morpheme split
    # and the English breakdown.
    if isinstance(trankit, dict):
        tk_parts = []
        for key in ("upos", "xpos", "feats", "lemma"):
            val = str(trankit.get(key) or "").strip()
            if val:
                tk_parts.append(f"{key}={val}")
        if tk_parts:
            lines.append("Trankit analysis: " + " | ".join(tk_parts))
    if lemma and (not isinstance(trankit, dict) or not str(trankit.get("lemma") or "").strip()):
        lines.append(f"Lemma: {lemma}")
    if forms_tags:
        ft = "; ".join(str(t).strip() for t in forms_tags if str(t).strip())
        if ft:
            lines.append(f"Form tags: {ft}")
    user_prompt = "\n".join(lines)

    schema = {
        "type": "object",
        "properties": {
            "decomposition": {"type": "string"},
            "analysis": {"type": "string"},
            "breakdown": {"type": "string"},
        },
        "required": ["decomposition", "analysis", "breakdown"],
        "propertyOrdering": ["decomposition", "analysis", "breakdown"],
    }

    used_model = model or GEMINI_DICT_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{used_model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _DECOMP_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "maxOutputTokens": 320,
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 503:
                time.sleep(5)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("generate_entry_decomp: request failed: %s", e)
        return {"ok": False, "error": "LLM service error."}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("entry_decomp_generate", used_model, payload, data)
    except Exception:
        pass

    usage_meta_raw = data.get("usageMetadata") or {}
    total = usage_meta_raw.get("totalTokenCount", 0)
    resp_tok = usage_meta_raw.get("candidatesTokenCount", 0) + usage_meta_raw.get("thoughtsTokenCount", 0)
    usage_meta = {
        "input_tokens": usage_meta_raw.get("promptTokenCount", max(0, total - resp_tok)),
        "output_tokens": resp_tok,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        return {"ok": False, "error": "No response from model."}

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        return {"ok": False, "error": "Empty response from LLM."}

    try:
        parsed = json.loads(text)
    except Exception:
        return {"ok": False, "error": "Could not parse LLM response as JSON."}

    decomposition = str(parsed.get("decomposition") or "").strip()
    analysis = str(parsed.get("analysis") or "").strip()
    breakdown = str(parsed.get("breakdown") or "").strip()
    if not decomposition:
        return {"ok": False, "error": "Missing decomposition in response."}

    decomp_json = json.dumps(
        {"decomposition": decomposition, "analysis": analysis, "breakdown": breakdown},
        ensure_ascii=False,
    )
    return {"ok": True, "decomp": decomp_json, "usage_meta": usage_meta}


# ---------------------------------------------------------------------------
# LLM per-token glosses — word-sense disambiguation aid
# ---------------------------------------------------------------------------

import unicodedata as _unicodedata

# Unicode categories that are "junk" — if a token is composed entirely of
# characters in these categories we skip it (no point glossing punctuation).
_GLOSS_SKIP_CATEGORIES = frozenset({
    "Mn", "Mc", "Me",          # Mark
    "Nd", "Nl", "No",          # Number
    "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",  # Punctuation
    "Sm", "Sc", "Sk", "So",    # Symbol
    "Zs", "Zl", "Zp",          # Separator
    "Cc", "Cf", "Cs", "Co", "Cn",  # Other/Control
})


def _is_glossable_token(text: str) -> bool:
    """Return True if the token contains at least one non-junk character."""
    for ch in text:
        if _unicodedata.category(ch) not in _GLOSS_SKIP_CATEGORIES:
            return True
    return False


_LLM_GLOSS_SYSTEM_PROMPT = (
    "You are a per-token gloss generator for a multilingual reader app. "
    "The input is pretokenized and each token already has dictionary entries attached; "
    "however, for word-sense disambiguation the user needs a short, economical gloss "
    "that captures the meaning of each token in context. "
    "THIS IS NOT AN IDIOMATIC OR HOLISTIC TRANSLATION TASK. Each token must be "
    "glossed individually, and the gloss must reflect that individual token's "
    "lexical content or grammatical role. "
    "For closed-class words with no clear lexical meaning, gloss their grammatical function "
    "(e.g. 'topic marker', 'plural marker', 'the', 'of', 'past tense'). "
    "Glosses must ALWAYS be in English.\n\n"
    "The input is organized into numbered sentences ('sentence 1:', 'sentence 2:', ...). "
    "Each sentence's tokens are numbered starting from 0, and numbering resets for each "
    "new sentence. Respond with one gloss per numbered token slot in the schema.\n\n"
    "Examples:\n\n"
    "Input:\n"
    "sentence 1:\n"
    "Yo no lo vi en la casa ayer porque estaba trabajando\n"
    "Output:\n"
    "0_Yo: I\n"
    "1_no: not\n"
    "2_lo: him\n"
    "3_vi: saw\n"
    "4_en: in\n"
    "5_la: the\n"
    "6_casa: house\n"
    "7_ayer: yesterday\n"
    "8_porque: because\n"
    "9_estaba: was\n"
    "10_trabajando: working\n\n"
    "Input:\n"
    "sentence 1:\n"
    "वह कल मेरे साथ उस बड़े घर में था\n"
    "Output:\n"
    "0_वह: he\n"
    "1_कल: yesterday\n"
    "2_मेरे: my\n"
    "3_साथ: with\n"
    "4_उस: that\n"
    "5_बड़े: big\n"
    "6_घर: house\n"
    "7_में: in\n"
    "8_था: was\n\n"
    "Input:\n"
    "sentence 1:\n"
    "و كتب الرسالة إلى صديقه في المدينة الكبيرة أمس\n"
    "Output:\n"
    "0_و: and\n"
    "1_كتب: wrote\n"
    "2_الرسالة: the letter\n"
    "3_إلى: to\n"
    "4_صديقه: his friend\n"
    "5_في: in\n"
    "6_المدينة: the city\n"
    "7_الكبيرة: big\n"
    "8_أمس: yesterday\n\n"
    "Input:\n"
    "sentence 1:\n"
    "私 は 昨日 友達 と 大きい 学校 に 行った\n"
    "Output:\n"
    "0_私: I\n"
    "1_は: topic marker\n"
    "2_昨日: yesterday\n"
    "3_友達: friend\n"
    "4_と: with\n"
    "5_大きい: big\n"
    "6_学校: school\n"
    "7_に: to\n"
    "8_行った: went\n\n"
    "Input:\n"
    "sentence 1:\n"
    "나 는 어제 친구 들 과 큰 학교 에 갔다\n"
    "Output:\n"
    "0_나: I\n"
    "1_는: topic marker\n"
    "2_어제: yesterday\n"
    "3_친구: friend\n"
    "4_들: plural marker\n"
    "5_과: with\n"
    "6_큰: big\n"
    "7_학교: school\n"
    "8_에: to\n"
    "9_갔다: went\n\n"
    "When multiple sentences are sent in one request, each sentence's token numbering "
    "resets to 0 and the schema keys are prefixed with the sentence number "
    "(e.g. 's1_0_...', 's1_1_...', 's2_0_...', 's2_1_...')."
)

import re as _re

def _token_to_key_suffix(text: str) -> str:
    """Turn a token's display text into a JSON-key suffix.

    Pass through raw token text unchanged except for whitespace → underscores
    (so each key stays one token). Preserves combining marks, which `\\w`
    would strip — essential for Devanagari, Bengali, Tamil, Thai, pointed
    Hebrew, etc.
    """
    s = _re.sub(r"\s+", "_", text)
    return s if s else "_"


def _is_korean_gloss_lang(lang_code: str) -> bool:
    lang = str(lang_code or "").strip().lower()
    return lang == "ko" or lang == "korean" or lang.startswith("ko-")


def _gloss_token_lemmas(tok: dict) -> list[str]:
    raw = tok.get("lemmas") if isinstance(tok, dict) else None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and _is_glossable_token(text):
            out.append(text)
    return out


def _gloss_prompt_token_text(tok: dict, lang_code: str) -> str:
    if _is_korean_gloss_lang(lang_code):
        lemmas = _gloss_token_lemmas(tok)
        if lemmas:
            return " ".join(lemmas)
    return str((tok or {}).get("text", "") or "").strip()


def _build_gloss_schema(
    chunk: list[dict],
    sentence_spans: list[tuple[int, int]] | None = None,
) -> tuple[dict, list[list[str]]]:
    """Build a strict one-slot-per-token schema with token text embedded in key names.

    Compound tokens (multiple lemmas) are expanded into one slot per lemma so
    Gemini glosses each subword independently.  Returns (schema, slot_groups)
    where slot_groups[i] is the list of schema keys that belong to chunk
    token i — single-lemma tokens get one key, compounds get several.

    If ``sentence_spans`` is provided as a list of [start, end) pairs over
    chunk indices, keys are prefixed with ``sN_`` and the per-token counter
    resets at each sentence boundary.  Otherwise keys use the legacy flat
    ``N_suffix`` scheme.
    """
    # Build a per-chunk-index lookup: chunk_idx -> (sent_num, local_idx_start)
    # We only need the sentence number and the slot_idx reset rule.
    sent_lookup: dict[int, int] | None = None
    if sentence_spans:
        sent_lookup = {}
        for sn, (start, end) in enumerate(sentence_spans, start=1):
            for ci in range(start, end):
                sent_lookup[ci] = sn

    props = {}
    required = []
    ordering = []
    slot_groups: list[list[str]] = []
    slot_idx = 0
    cur_sent = None
    for i, tok in enumerate(chunk):
        sent_num = sent_lookup.get(i) if sent_lookup is not None else None
        if sent_num is not None and sent_num != cur_sent:
            cur_sent = sent_num
            slot_idx = 0
        prefix = f"s{sent_num}_" if sent_num is not None else ""
        lemmas = _gloss_token_lemmas(tok)
        group_keys: list[str] = []
        if lemmas:
            for lemma in lemmas:
                suffix = _token_to_key_suffix(lemma)
                key = f"{prefix}{slot_idx}_{suffix}"
                props[key] = {"type": "string"}
                required.append(key)
                ordering.append(key)
                group_keys.append(key)
                slot_idx += 1
        else:
            suffix = _token_to_key_suffix(tok["text"])
            key = f"{prefix}{slot_idx}_{suffix}"
            props[key] = {"type": "string"}
            required.append(key)
            ordering.append(key)
            group_keys.append(key)
            slot_idx += 1
        slot_groups.append(group_keys)
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }, slot_groups


def generate_llm_glosses(
    context_text: str,
    tokens: list[dict],
    lang_code: str,
) -> tuple[list[dict] | None, dict]:
    """Call Gemini to produce a short contextual gloss for each token.

    Args:
        context_text: full sentence/passage for context
        tokens: list of dicts, each with keys:
            - ``text``: surface form
            - ``lemmas``: list of lemma strings (retained for compatibility)
        lang_code: BCP-47 language code

    Returns:
        (gloss_list, usage_counts) where gloss_list mirrors the input token
        order.  Each entry is ``{"gloss": "..."}`` or ``None``.  Returns
        ``(None, usage_counts)`` on failure.
    """
    if not GEMINI_DICT_ENABLED or not GEMINI_API_KEY:
        return None, {}

    # Filter to glossable tokens only
    glossable = []
    glossable_indices = []
    for i, tok in enumerate(tokens):
        text = tok.get("text", "")
        if text and _is_glossable_token(text):
            glossable.append(tok)
            glossable_indices.append(i)

    if not glossable:
        return None, {}

    # Split into chunks of 100 to stay within Gemini's schema state limit
    CHUNK_SIZE = 100
    chunks = [glossable[i:i+CHUNK_SIZE] for i in range(0, len(glossable), CHUNK_SIZE)]
    chunk_index_offsets = list(range(0, len(glossable), CHUNK_SIZE))

    combined_g = []
    combined_usage = {"prompt_tokens": 0, "response_tokens": 0, "total_tokens": 0}

    for chunk, chunk_offset in zip(chunks, chunk_index_offsets):
        g_chunk, usage_chunk = call_gloss_chunk(chunk, lang_code, context=context_text)
        for k in combined_usage:
            combined_usage[k] += usage_chunk.get(k, 0)
        if g_chunk is None:
            # Pad with None so indices stay aligned
            combined_g.extend([None] * len(chunk))
        else:
            combined_g.extend(g_chunk)

    result = [None] * len(tokens)
    for j, gi in enumerate(glossable_indices):
        if j < len(combined_g):
            result[gi] = combined_g[j]

    return result, combined_usage


def stream_llm_glosses(
    tokens: list[dict],
    lang_code: str,
    context_text: str = "",
):
    """Generator that yields (chunk_result, usage_counts) as each 200-token chunk completes.

    chunk_result is a list of (original_token_index, gloss_entry) pairs so the
    caller can merge partial results into a full-length array incrementally.
    """
    if not GEMINI_DICT_ENABLED or not GEMINI_API_KEY:
        return

    glossable = []
    glossable_indices = []
    for i, tok in enumerate(tokens):
        text = tok.get("text", "")
        if text and _is_glossable_token(text):
            glossable.append(tok)
            glossable_indices.append(i)

    if not glossable:
        return

    CHUNK_SIZE = 100
    chunks = [glossable[i:i+CHUNK_SIZE] for i in range(0, len(glossable), CHUNK_SIZE)]
    gi_chunks = [glossable_indices[i:i+CHUNK_SIZE] for i in range(0, len(glossable_indices), CHUNK_SIZE)]

    for chunk, gi_chunk in zip(chunks, gi_chunks):
        g_chunk, usage_chunk = call_gloss_chunk(chunk, lang_code, context=context_text)
        pairs = []
        if g_chunk is not None:
            for j, gi in enumerate(gi_chunk):
                if j < len(g_chunk) and g_chunk[j] is not None:
                    pairs.append((gi, g_chunk[j]))
        yield pairs, usage_chunk


def call_gloss_chunk(
    chunk: list[dict],
    lang_code: str,
    context: str = "",
    sentences: list[list[int]] | None = None,
) -> tuple[list | None, dict]:
    """Call Gemini for a single chunk of glossable tokens. Returns (list|None, usage).

    ``sentences`` is an optional list of [start, end) pairs over ``chunk`` that
    partitions the tokens into sentences.  When supplied, the user prompt
    labels each sentence and schema keys use the ``sN_idx_suffix`` form so
    token numbering resets per sentence.
    """
    sentence_spans: list[tuple[int, int]] | None = None
    if sentences:
        sentence_spans = []
        for s in sentences:
            if isinstance(s, (list, tuple)) and len(s) >= 2:
                sentence_spans.append((int(s[0]), int(s[1])))

    schema, slot_groups = _build_gloss_schema(chunk, sentence_spans)

    if sentence_spans:
        parts = []
        for sn, (start, end) in enumerate(sentence_spans, start=1):
            stream = " ".join(_gloss_prompt_token_text(chunk[i], lang_code) for i in range(start, end))
            parts.append(f"sentence {sn}:\n{stream}")
        user_prompt = f"Language: {lang_code}.\n" + "\n\n".join(parts) + "\n"
    else:
        token_stream = " ".join(_gloss_prompt_token_text(tok, lang_code) for tok in chunk)
        user_prompt = f"Language: {lang_code}.\nTokens: {token_stream}\n"

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _LLM_GLOSS_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(200, len(chunk) * 30),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 503:
                log.warning("LLM gloss chunk: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            if resp.status_code == 400:
                # Schema-too-complex error — split chunk in half and retry each half
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("error", {}).get("message", "")
                except Exception:
                    err_msg = resp.text[:200]
                if "too many states" in err_msg or "constraint" in err_msg:
                    if len(chunk) <= 1:
                        log.warning("LLM gloss chunk: 400 schema too complex on single token, giving up")
                        return None, {}
                    log.warning(
                        "LLM gloss chunk: 400 schema too complex (%d tokens), splitting in half",
                        len(chunk),
                    )
                    mid = len(chunk) // 2
                    half_a = chunk[:mid]
                    half_b = chunk[mid:]
                    # sentence_spans need to be adjusted for each half
                    spans_a: list[list[int]] | None = None
                    spans_b: list[list[int]] | None = None
                    if sentences:
                        spans_a_raw = []
                        spans_b_raw = []
                        for s in sentences:
                            if not (isinstance(s, (list, tuple)) and len(s) >= 2):
                                continue
                            s0, s1 = int(s[0]), int(s[1])
                            # Clamp to first half
                            a0, a1 = max(0, s0), min(mid, s1)
                            if a1 > a0:
                                spans_a_raw.append([a0, a1])
                            # Clamp to second half, rebased to 0
                            b0, b1 = max(0, s0 - mid), min(len(chunk) - mid, s1 - mid)
                            if b1 > b0:
                                spans_b_raw.append([b0, b1])
                        spans_a = spans_a_raw or None
                        spans_b = spans_b_raw or None
                    res_a, usage_a = call_gloss_chunk(half_a, lang_code, context=context, sentences=spans_a)
                    res_b, usage_b = call_gloss_chunk(half_b, lang_code, context=context, sentences=spans_b)
                    combined_usage = {
                        k: usage_a.get(k, 0) + usage_b.get(k, 0)
                        for k in ("prompt_tokens", "response_tokens", "total_tokens")
                    }
                    if res_a is None and res_b is None:
                        return None, combined_usage
                    merged = (res_a or [None] * len(half_a)) + (res_b or [None] * len(half_b))
                    return merged, combined_usage
                # 400 but not schema error — fall through to raise
            if resp.status_code != 200:
                log.warning("LLM gloss chunk: HTTP %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("LLM gloss chunk failed: %s", e)
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("llm_gloss", GEMINI_DICT_MODEL, payload, None, error=str(e))
        except Exception:
            pass
        return None, {}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("llm_gloss", GEMINI_DICT_MODEL, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("LLM gloss chunk: no candidates")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("LLM gloss chunk: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    # Strict validation: exactly the expected keys, all strings.
    # Keys are now "{index}_{token_suffix}" — rebuild them to validate.
    expected_keys = set(schema["required"])
    if not isinstance(parsed, dict) or set(parsed.keys()) != expected_keys:
        log.warning("LLM gloss chunk: key mismatch. Expected %s, got %s",
                    sorted(expected_keys),
                    sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed))
        return None, usage_counts

    # Read values back, collapsing expanded compound slots into "g1 + g2 + g3".
    result = []
    for group_keys in slot_groups:
        parts = []
        for key in group_keys:
            val = parsed.get(key)
            if not isinstance(val, str):
                log.warning("LLM gloss chunk: non-string value for %s: %r", key, val)
                return None, usage_counts
            parts.append(val.strip())
        combined = " + ".join(p for p in parts if p)
        result.append({"gloss": combined} if combined else None)

    return result, usage_counts


# ---------------------------------------------------------------------------
# LLM per-token inflectional decomposition
# ---------------------------------------------------------------------------

_LLM_DECOMP_SYSTEM_PROMPT = (
    "You are an internal morpheme segmenter for a multilingual reader app. "
    "You will receive up to 10 inflected tokens from one language. Each token "
    "comes with its surface form plus lemma, UPOS, XPOS, and UD morphological features.\n\n"
    "For each token, return one concise English decomposition string showing "
    "the token's visible internal pieces. Use this format inside each value:\n"
    "  morpheme = explanation, morpheme = explanation, ...\n\n"
    "Rules:\n"
    "  - Separate the lexical stem from overt inflectional material whenever the form has overt inflection.\n"
    "  - If one ending bundles several features, keep it as one morpheme and describe all bundled features in plain English.\n"
    "  - Include prefixes, suffixes, endings, clitics, infixes, augment/personal endings, and possessive markers when present.\n"
    "  - Use the actual surface pieces from the token, not abstract placeholders.\n"
    "  - Keep explanations short and concrete.\n"
    "  - Do not give a holistic translation of the whole word.\n"
    "  - Do not mention lemma / UPOS / XPOS / feats labels inside the output values; use them only as analysis context.\n"
    "  - If no defensible visible split exists, return a single morpheme with a short description.\n\n"
    "Examples:\n"
    "Input:\n"
    "أبي\n"
    "Output:\n"
    "أب = root-based noun \"father\", ي = genitive case ending\n\n"
    "Input:\n"
    "गृहेण\n"
    "Output:\n"
    "गृह = noun stem \"house\", ेण = instrumental singular ending\n\n"
    "Input:\n"
    "portarum\n"
    "Output:\n"
    "port = noun stem \"gate\", arum = genitive plural ending\n\n"
    "Input:\n"
    "λόγοις\n"
    "Output:\n"
    "λόγ = noun stem \"word\", οις = dative plural ending\n\n"
    "Input:\n"
    "книгой\n"
    "Output:\n"
    "книг = noun stem \"book\", ой = instrumental singular ending\n\n"
    "Input:\n"
    "Häusern\n"
    "Output:\n"
    "Häus = noun stem \"house\", er = plural marker, n = dative ending\n\n"
    "Input:\n"
    "evlerimizden\n"
    "Output:\n"
    "ev = noun stem \"house\", ler = plural marker, imiz = first-person plural possessive suffix \"our\", den = ablative case ending\n\n"
    "Input:\n"
    "talossa\n"
    "Output:\n"
    "talo = noun stem \"house\", ssa = inessive case ending\n\n"
    "Input:\n"
    "hablábamos\n"
    "Output:\n"
    "habl = verb stem \"speak\", ába = imperfect marker, mos = first-person plural ending\n\n"
    "Input:\n"
    "लड़कों\n"
    "Output:\n"
    "लड़क = noun stem \"boy\", ों = oblique plural ending"
)


def _build_decomp_schema(chunk: list[dict]) -> tuple[dict, list[str]]:
    props = {}
    required = []
    ordering = []
    slot_keys: list[str] = []
    for i, tok in enumerate(chunk):
        suffix = _token_to_key_suffix(tok.get("text", "") or str(i))
        key = f"{i}_{suffix}"
        props[key] = {"type": "string"}
        required.append(key)
        ordering.append(key)
        slot_keys.append(key)
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }, slot_keys


def call_decomp_chunk(
    chunk: list[dict],
    lang_code: str,
) -> tuple[list | None, dict]:
    """Call Gemini for a single chunk of inflectional token decompositions."""
    schema, slot_keys = _build_decomp_schema(chunk)

    lines = [
        f"Language: {lang_code}.",
        "Analyze each token internally and return one decomposition string per schema key.",
    ]
    for i, tok in enumerate(chunk):
        key = slot_keys[i]
        lines.append(f"{key}:")
        lines.append(f"  surface: {tok.get('text', '')}")
        lemma = str(tok.get("lemma", "") or "").strip()
        upos = str(tok.get("upos", "") or "").strip()
        xpos = str(tok.get("xpos", "") or "").strip()
        feats = str(tok.get("feats", "") or "").strip()
        if lemma:
            lines.append(f"  lemma: {lemma}")
        if upos:
            lines.append(f"  upos: {upos}")
        if xpos:
            lines.append(f"  xpos: {xpos}")
        if feats:
            lines.append(f"  feats: {feats}")
        lines.append("")
    user_prompt = "\n".join(lines).strip()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _LLM_DECOMP_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(240, len(chunk) * 80),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 503:
                log.warning("LLM decomp chunk: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            if resp.status_code == 400:
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("error", {}).get("message", "")
                except Exception:
                    err_msg = resp.text[:200]
                if ("too many states" in err_msg or "constraint" in err_msg) and len(chunk) > 1:
                    log.warning(
                        "LLM decomp chunk: 400 schema too complex (%d tokens), splitting in half",
                        len(chunk),
                    )
                    mid = len(chunk) // 2
                    res_a, usage_a = call_decomp_chunk(chunk[:mid], lang_code)
                    res_b, usage_b = call_decomp_chunk(chunk[mid:], lang_code)
                    combined_usage = {
                        k: usage_a.get(k, 0) + usage_b.get(k, 0)
                        for k in ("prompt_tokens", "response_tokens", "total_tokens")
                    }
                    if res_a is None and res_b is None:
                        return None, combined_usage
                    merged = (res_a or [None] * mid) + (res_b or [None] * (len(chunk) - mid))
                    return merged, combined_usage
            if resp.status_code != 200:
                log.warning("LLM decomp chunk: HTTP %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("LLM decomp chunk failed: %s", e)
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("llm_decomp", GEMINI_DICT_MODEL, payload, None, error=str(e))
        except Exception:
            pass
        return None, {}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("llm_decomp", GEMINI_DICT_MODEL, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("LLM decomp chunk: no candidates")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("LLM decomp chunk: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    expected_keys = set(slot_keys)
    if not isinstance(parsed, dict) or set(parsed.keys()) != expected_keys:
        log.warning(
            "LLM decomp chunk: key mismatch. Expected %d keys, got %d",
            len(expected_keys),
            len(parsed) if isinstance(parsed, dict) else -1,
        )
        return None, usage_counts

    result = []
    for key in slot_keys:
        val = parsed.get(key)
        if not isinstance(val, str):
            log.warning("LLM decomp chunk: non-string value for %s: %r", key, val)
            return None, usage_counts
        cleaned = val.strip()
        result.append({"decomp": cleaned} if cleaned else None)

    return result, usage_counts


# Sentence-scoped override: keep full sentence context, target only eligible slots,
# and allow empty-string skips for monomorphemic targets.
_LLM_DECOMP_SYSTEM_PROMPT = (
    "You are an internal morpheme segmenter for a multilingual reader app. "
    "You will receive one full sentence token stream from a single language, plus a set "
    "of target tokens from that sentence that may need decomposition.\n\n"
    "Return newline-separated morpheme glosses for each target token. "
    "Each non-empty value must look like this:\n"
    "morpheme = explanation\n"
    "morpheme = explanation\n"
    "morpheme = explanation\n\n"
    "Rules:\n"
    "  - Use one morpheme per line, never comma-separated left-to-right lists.\n"
    "  - Segment at the morpheme level. If a token contains multiple visible bound morphemes, split them line by line.\n"
    "  - Include all visible morphemes inside the token, bound and unbound: prefixes, stems, suffixes, endings, clitics, augment, agreement markers, possessive markers, derivational pieces, etc.\n"
    "  - Use the actual surface pieces from the token.\n"
    "  - Keep explanations short, concrete, and in English.\n"
    "  - Do not give a holistic translation of the whole word.\n"
    "  - If a target token is monomorphemic, opaque, or should be skipped, return an empty string for that key.\n"
    "  - In the actual JSON output, every schema key must be present. Use empty string for skipped tokens.\n\n"
    "Examples:\n"
    "Input sentence:\n"
    "Wir wohnten in Häusern .\n"
    "Output:\n"
    "1_wohnten:\n"
    "wohn = verb stem \"dwell\"\n"
    "te = past tense marker\n"
    "n = first-person plural ending\n"
    "\n"
    "3_Häusern:\n"
    "Häus = noun stem \"house\"\n"
    "er = plural marker\n"
    "n = dative ending\n\n"
    "Input sentence:\n"
    "Çocuklar evlerimizden kaçtı .\n"
    "Output:\n"
    "0_Çocuklar:\n"
    "Çocuk = noun stem \"child\"\n"
    "lar = plural marker\n"
    "\n"
    "1_evlerimizden:\n"
    "ev = noun stem \"house\"\n"
    "ler = plural marker\n"
    "imiz = first-person plural possessive suffix \"our\"\n"
    "den = ablative ending\n"
    "\n"
    "2_kaçtı:\n"
    "kaç = verb stem \"escape\"\n"
    "tı = past tense third-person ending\n\n"
    "Input sentence:\n"
    "وكتبناها أمس .\n"
    "Output:\n"
    "0_وكتبناها:\n"
    "و = coordinating prefix \"and\"\n"
    "كتب = verb stem \"write\"\n"
    "نا = first-person plural suffix \"we\"\n"
    "ها = feminine object suffix \"it\"\n\n"
    "Input sentence:\n"
    "Hablábamos allí .\n"
    "Output:\n"
    "0_Hablábamos:\n"
    "habl = verb stem \"speak\"\n"
    "ába = imperfect marker\n"
    "mos = first-person plural ending\n\n"
    "Input sentence:\n"
    "बालकाः गृहेषु वसन्ति ।\n"
    "Output:\n"
    "0_बालकाः:\n"
    "बालक = noun stem \"boy\"\n"
    "ाः = nominative plural ending\n"
    "\n"
    "1_गृहेषु:\n"
    "गृह = noun stem \"house\"\n"
    "ेषु = locative plural ending\n"
    "\n"
    "2_वसन्ति:\n"
    "वस् = verb stem \"dwell\"\n"
    "न्ति = present third-person plural ending"
)


def _build_decomp_schema(targets: list[dict]) -> tuple[dict, list[str]]:
    props = {}
    required = []
    ordering = []
    slot_keys: list[str] = []
    for target in targets:
        sentence_index = int(target.get("sentence_index", 0))
        suffix = _token_to_key_suffix(target.get("text", "") or str(sentence_index))
        key = f"{sentence_index}_{suffix}"
        props[key] = {"type": "string"}
        required.append(key)
        ordering.append(key)
        slot_keys.append(key)
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }, slot_keys


def call_decomp_chunk(
    sentence_tokens: list[str],
    targets: list[dict],
    lang_code: str,
) -> tuple[list | None, dict]:
    """Call Gemini for one sentence token stream and its target tokens."""
    if not sentence_tokens or not targets:
        return None, {}

    schema, slot_keys = _build_decomp_schema(targets)

    stream_parts = []
    for i, tok in enumerate(sentence_tokens):
        stream_parts.append(f"{i}:{tok}")

    lines = [
        f"Language: {lang_code}.",
        "Sentence token stream:",
        " ".join(stream_parts),
        "",
        "Analyze only these target tokens from that sentence. Return empty string for any target token that is monomorphemic or should be skipped.",
    ]
    for i, target in enumerate(targets):
        lines.append(f"  {slot_keys[i]}: {target.get('text', '')}")
    user_prompt = "\n".join(lines).strip()

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _LLM_DECOMP_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(320, len(targets) * 90),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 503:
                log.warning("LLM decomp chunk: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            if resp.status_code == 400:
                try:
                    err_body = resp.json()
                    err_msg = err_body.get("error", {}).get("message", "")
                except Exception:
                    err_msg = resp.text[:200]
                if ("too many states" in err_msg or "constraint" in err_msg) and len(targets) > 1:
                    log.warning(
                        "LLM decomp chunk: 400 schema too complex (%d targets), splitting in half",
                        len(targets),
                    )
                    mid = len(targets) // 2
                    res_a, usage_a = call_decomp_chunk(sentence_tokens, targets[:mid], lang_code)
                    res_b, usage_b = call_decomp_chunk(sentence_tokens, targets[mid:], lang_code)
                    combined_usage = {
                        k: usage_a.get(k, 0) + usage_b.get(k, 0)
                        for k in ("prompt_tokens", "response_tokens", "total_tokens")
                    }
                    if res_a is None and res_b is None:
                        return None, combined_usage
                    merged = (res_a or [None] * mid) + (res_b or [None] * (len(targets) - mid))
                    return merged, combined_usage
            if resp.status_code != 200:
                log.warning("LLM decomp chunk: HTTP %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("LLM decomp chunk failed: %s", e)
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("llm_decomp", GEMINI_DICT_MODEL, payload, None, error=str(e))
        except Exception:
            pass
        return None, {}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("llm_decomp", GEMINI_DICT_MODEL, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("LLM decomp chunk: no candidates")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("LLM decomp chunk: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    expected_keys = set(slot_keys)
    if not isinstance(parsed, dict) or set(parsed.keys()) != expected_keys:
        log.warning(
            "LLM decomp chunk: key mismatch. Expected %d keys, got %d",
            len(expected_keys),
            len(parsed) if isinstance(parsed, dict) else -1,
        )
        return None, usage_counts

    result = []
    for key in slot_keys:
        val = parsed.get(key)
        if not isinstance(val, str):
            log.warning("LLM decomp chunk: non-string value for %s: %r", key, val)
            return None, usage_counts
        cleaned = val.strip()
        result.append({"decomp": cleaned} if cleaned else None)

    return result, usage_counts


# ---------------------------------------------------------------------------
# Orthographic / pronunciation breakdown  (ORTH feature)
# ---------------------------------------------------------------------------

_ORTH_BREAKDOWN_SYSTEM_PROMPT = (
    "You are a romanization tool. For each token provided, output its pronunciation "
    "written in plain English letters (romanized). Use ONLY English letters, "
    "no IPA, no original script, no explanations. One romanization per token."
)


def call_orth_chunk(
    chunk: list[dict],
    lang_code: str,
    slot_counts: list[int] | None = None,
) -> tuple[list | None, dict]:
    """Call Gemini to romanize each token.

    chunk: list of {text, ...} — one per sub-part (flattened for MWT/compound lemmas).
    slot_counts: how many sub-parts per original token (for + joining).

    Returns (list_of_results | None, usage_counts).
    Each entry is {"rom": "..."} or None, one per original segment.
    MWT/compound sub-parts are joined with " + ".
    """
    # One schema slot per sub-part token
    props = {}
    required = []
    ordering = []
    slot_keys: list[str] = []
    for i, tok in enumerate(chunk):
        suffix = _token_to_key_suffix(tok.get("text", "") or str(i))
        key = f"{i}_{suffix}"
        props[key] = {"type": "string"}
        required.append(key)
        ordering.append(key)
        slot_keys.append(key)

    # Group sub-part tokens into original segments via slot_counts
    if slot_counts:
        slot_groups: list[list[int]] = []
        ti = 0
        for count in slot_counts:
            slot_groups.append(list(range(ti, ti + count)))
            ti += count
    else:
        slot_groups = [[i] for i in range(len(chunk))]

    schema = {
        "type": "object",
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }

    # User prompt lists each token inline next to its schema key name
    lines = [f"Language: {lang_code}.", "Romanize each token into English letters:"]
    for i, tok in enumerate(chunk):
        lines.append(f"  {slot_keys[i]}: {tok.get('text', '')}")
    user_prompt = "\n".join(lines)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_DICT_MODEL}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _ORTH_BREAKDOWN_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(200, len(chunk) * 40),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 503:
                log.warning("Orth breakdown chunk: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            if resp.status_code != 200:
                log.warning("Orth breakdown chunk: HTTP %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("Orth breakdown chunk failed: %s", e)
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("orth_breakdown", GEMINI_DICT_MODEL, payload, None, error=str(e))
        except Exception:
            pass
        return None, {}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("orth_breakdown", GEMINI_DICT_MODEL, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        log.warning("Orth breakdown chunk: no candidates")
        return None, usage_counts

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning("Orth breakdown chunk: JSON parse error: %s\nRaw: %s", e, text[:300])
        return None, usage_counts

    expected_keys = set(required)
    if not isinstance(parsed, dict) or set(parsed.keys()) != expected_keys:
        log.warning("Orth breakdown chunk: key mismatch. Expected %d keys, got %d",
                    len(expected_keys),
                    len(parsed) if isinstance(parsed, dict) else -1)
        return None, usage_counts

    # Collapse sub-parts with " + " for MWT/compound tokens
    result = []
    for seg_token_indices in slot_groups:
        sub_parts = []
        for tok_idx in seg_token_indices:
            val = parsed.get(slot_keys[tok_idx], "")
            if not isinstance(val, str):
                val = str(val)
            sub_parts.append(val.strip())
        combined = " + ".join(p for p in sub_parts if p)
        result.append({"rom": combined} if combined else None)

    return result, usage_counts


# ---------------------------------------------------------------------------
# Community editing helpers — used by router.py for user-created entries
# ---------------------------------------------------------------------------

def headword_exists(lang_code: str, headword: str) -> bool:
    """Check if a headword already exists in the gemini TSV for this language."""
    path = get_tsv_path(lang_code)
    header, rows = _parse_tsv_rows(path)
    if not rows:
        return False
    for row in rows:
        if row.get("headword", "") == headword:
            return True
    return False


def append_user_entry(lang_code: str, headword: str, romanization: str,
                      pos: str, glosses: list[str], forms: list | None = None):
    """Append a user-created entry to the gemini TSV.
    A _source marker is embedded in the senses JSON so the frontend can
    distinguish user-created entries from Gemini-generated ones."""
    TSV_DIR.mkdir(exist_ok=True)
    path = get_tsv_path(lang_code)
    senses = [{"glosses": [g]} for g in glosses]
    senses.append({"_source": "user_created"})
    entry = {
        "headword": headword,
        "romanization": romanization or "",
        "pos": pos or "",
        "forms": forms or [],
    }
    _append_tsv_row(path, entry, senses)


def update_tsv_entry(lang_code: str, headword: str, new_romanization: str | None = None,
                     new_pos: str | None = None, new_glosses: list[str] | None = None,
                     new_forms: list | None = None,
                     new_commentary: str | None = None,
                     new_lemma: str | None = None) -> bool:
    """Update an existing entry in the gemini TSV. Returns True if found and updated.
    Preserves any _source marker already embedded in the glosses JSON."""
    path = get_tsv_path(lang_code)
    header, rows = _parse_tsv_rows(path)
    if not header or not rows:
        return False
    found = False
    for row in rows:
        if row.get("headword", "") == headword:
            if new_romanization is not None:
                row["romanization"] = _tsv_escape(new_romanization)
            if new_pos is not None:
                row["pos"] = _tsv_escape(new_pos)
            if new_glosses is not None:
                # Preserve _source marker if present
                source_marker = None
                try:
                    existing = json.loads(row.get("glosses", "[]"))
                    if isinstance(existing, list):
                        for s in existing:
                            if isinstance(s, dict) and "_source" in s:
                                source_marker = s
                                break
                except (json.JSONDecodeError, TypeError):
                    pass
                senses = [{"glosses": [g]} for g in new_glosses]
                if source_marker:
                    senses.append(source_marker)
                row["glosses"] = json.dumps(senses, ensure_ascii=False)
            if new_forms is not None:
                row["forms"] = json.dumps(new_forms, ensure_ascii=False)
            if new_commentary is not None:
                row["commentary"] = _tsv_escape(new_commentary)
            if new_lemma is not None:
                row["lemma"] = _tsv_escape(new_lemma)
            found = True
            break
    if found:
        _write_tsv_file(path, header, rows)
    return found


def remove_tsv_entry(lang_code: str, headword: str) -> bool:
    """Remove an entry from the gemini TSV. Returns True if found and removed."""
    path = get_tsv_path(lang_code)
    header, rows = _parse_tsv_rows(path)
    if not header or not rows:
        return False
    new_rows = [r for r in rows if r.get("headword", "") != headword]
    if len(new_rows) == len(rows):
        return False
    _write_tsv_file(path, header, new_rows)
    return True


# ---------------------------------------------------------------------------
# SQLite-backed custom entry storage (live path)
# ---------------------------------------------------------------------------

CUSTOM_TSV_HEADER = "entry_id\theadword\tromanization\tpos\tglosses\tforms\tcommentary\tlemma\tsource"


def _json_load_list(raw, default=None):
    if default is None:
        default = []
    if raw is None:
        return list(default)
    if isinstance(raw, list):
        return list(raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (TypeError, ValueError):
        pass
    return list(default)


def _normalize_glosses(glosses) -> list[str]:
    if isinstance(glosses, str):
        glosses = [g.strip() for g in glosses.split(";") if g.strip()]
    out = []
    seen = set()
    for gloss in (glosses or []):
        text = str(gloss or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    if len(out) >= 3 and all(len(g) == 1 for g in out):
        merged = "".join(out).strip()
        if merged:
            return [merged]
    return out


def _normalize_forms(forms) -> list[list[str]]:
    out = []
    for form in (forms or []):
        if not isinstance(form, (list, tuple)):
            continue
        word = str(form[0] if len(form) > 0 else "").strip()
        tags = str(form[1] if len(form) > 1 else "").strip()
        roman = str(form[2] if len(form) > 2 else "").strip()
        if not word:
            continue
        out.append([word, tags, roman])
    return out


def _glosses_to_senses(glosses: list[str], source: str = "") -> list[dict]:
    senses = [{"glosses": [g]} for g in _normalize_glosses(glosses)]
    src = str(source or "").strip().lower()
    if src == "user_created":
        senses.append({"_source": "user_created"})
    return senses


def _entry_model_to_frontend(entry) -> dict:
    glosses = []
    for sense in _json_load_list(entry.glosses_json):
        if isinstance(sense, dict):
            for gloss in (sense.get("glosses") or []):
                text = str(gloss or "").strip()
                if text:
                    glosses.append(text)
    return {
        "entry_id": entry.entry_id,
        "entry_row_id": entry.id,
        "db_alias": "customdb",
        "headword": entry.headword or "",
        "pos": entry.pos or "",
        "romanization": entry.romanization or "",
        "glosses": _normalize_glosses(glosses),
        "forms": _normalize_forms(_json_load_list(entry.forms_json)),
        "commentary": entry.commentary or "",
        "lemma": entry.lemma or "",
        "source": entry.source or "gemini",
    }


def _entry_to_frontend(entry) -> dict:
    if hasattr(entry, "entry_id") and hasattr(entry, "glosses_json"):
        return _entry_model_to_frontend(entry)
    glosses = entry.get("glosses") or []
    if isinstance(glosses, str):
        glosses = [g.strip() for g in glosses.split(";") if g.strip()]
    result = {
        "entry_id": entry.get("entry_id", ""),
        "headword": entry.get("headword", ""),
        "pos": entry.get("pos", ""),
        "romanization": entry.get("romanization", ""),
        "glosses": _normalize_glosses(glosses),
        "forms": _normalize_forms(entry.get("forms") or []),
        "commentary": entry.get("commentary", ""),
        "lemma": entry.get("canonical_form", "") or entry.get("lemma", ""),
        "source": entry.get("source", "gemini"),
    }
    row_id = entry.get("entry_row_id") or entry.get("id")
    if row_id:
        result["entry_row_id"] = int(row_id)
        result["db_alias"] = str(entry.get("db_alias") or "customdb")
    return result


def _store_generated_entry_db(lang_code: str, entry: dict):
    source = str(entry.get("source") or "gemini").strip().lower() or "gemini"
    return upsert_custom_entry(
        lang_code=lang_code,
        headword=str(entry.get("headword", "")).strip(),
        romanization=str(entry.get("romanization", "") or "").strip(),
        pos=str(entry.get("pos", "") or "").strip(),
        glosses=entry.get("glosses") or [],
        forms=entry.get("forms") or [],
        commentary=str(entry.get("commentary", "") or "").strip(),
        lemma=str(entry.get("canonical_form", "") or entry.get("lemma", "") or "").strip(),
        source=source,
    )


def _query_custom_entry(lang_code: str, headword: str = "", entry_id: str = ""):
    from db import CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    eid = str(entry_id or "").strip()
    hw = str(headword or "").strip()
    q = CustomDictEntry.query
    if eid:
        return q.filter_by(entry_id=eid).first()
    if not lang or not hw:
        return None
    return q.filter_by(language=lang, headword=hw).first()


def upsert_custom_entry(lang_code: str, headword: str, romanization: str = "",
                        pos: str = "", glosses=None, forms=None,
                        commentary: str = "", lemma: str = "",
                        source: str = "gemini", entry_id: str = ""):
    from db import db, CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    hw = str(headword or "").strip()
    if not lang or not hw:
        return None

    src = str(source or "gemini").strip().lower() or "gemini"
    entry = _query_custom_entry(lang, headword=hw, entry_id=entry_id)
    if not entry:
        entry = CustomDictEntry(
            entry_id=str(entry_id or uuid.uuid4().hex),
            language=lang,
            headword=hw,
        )
        db.session.add(entry)

    entry.romanization = str(romanization or "").strip() or None
    entry.pos = str(pos or "").strip() or None
    entry.glosses_json = json.dumps(_glosses_to_senses(glosses, src), ensure_ascii=False)
    entry.forms_json = json.dumps(_normalize_forms(forms), ensure_ascii=False)
    entry.commentary = str(commentary or "").strip() or None
    entry.lemma = str(lemma or "").strip() or None
    entry.source = src
    db.session.commit()
    sync_custom_form_index_entry(entry.id, entry.language, entry.forms_json)
    return entry


def iter_custom_entry_tsv_lines(lang_code: str, batch_size: int = 500):
    from db import CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    yield CUSTOM_TSV_HEADER + "\n"
    if not lang:
        return

    q = (
        CustomDictEntry.query
        .filter_by(language=lang)
        .filter((CustomDictEntry.source == "gemini") | (CustomDictEntry.source.is_(None)))
        .order_by(CustomDictEntry.id.asc())
        .yield_per(batch_size)
    )
    for entry in q:
        normalized_glosses = _entry_model_to_frontend(entry)["glosses"]
        row = [
            _tsv_escape(entry.entry_id or ""),
            _tsv_escape(entry.headword or ""),
            _tsv_escape(entry.romanization or ""),
            _tsv_escape(entry.pos or ""),
            json.dumps(_glosses_to_senses(normalized_glosses, entry.source or "gemini"), ensure_ascii=False),
            json.dumps(_normalize_forms(_json_load_list(entry.forms_json)), ensure_ascii=False),
            _tsv_escape(entry.commentary or ""),
            _tsv_escape(entry.lemma or ""),
            _tsv_escape(entry.source or "gemini"),
        ]
        yield "\t".join(row) + "\n"


def get_tsv_text(lang_code: str) -> str:
    return "".join(iter_custom_entry_tsv_lines(lang_code))


def headword_exists(lang_code: str, headword: str) -> bool:
    return _query_custom_entry(lang_code, headword=headword) is not None


def append_user_entry(lang_code: str, headword: str, romanization: str,
                      pos: str, glosses: list[str], forms: list | None = None):
    return upsert_custom_entry(
        lang_code=lang_code,
        headword=headword,
        romanization=romanization or "",
        pos=pos or "",
        glosses=glosses or [],
        forms=forms or [],
        commentary="",
        lemma="",
        source="user_created",
    )


def update_tsv_entry(lang_code: str, headword: str, new_romanization: str | None = None,
                     new_pos: str | None = None, new_glosses: list[str] | None = None,
                     new_forms: list | None = None,
                     new_commentary: str | None = None,
                     new_lemma: str | None = None,
                     entry_id: str = ""):
    entry = _query_custom_entry(lang_code, headword=headword, entry_id=entry_id)
    if not entry:
        return None

    glosses = None
    if new_glosses is not None:
        glosses = new_glosses
    else:
        existing_glosses = []
        for sense in _json_load_list(entry.glosses_json):
            if isinstance(sense, dict):
                existing_glosses.extend([str(g or "").strip() for g in (sense.get("glosses") or []) if str(g or "").strip()])

    forms = _normalize_forms(new_forms if new_forms is not None else _json_load_list(entry.forms_json))
    updated = upsert_custom_entry(
        lang_code=entry.language,
        headword=entry.headword,
        romanization=(new_romanization if new_romanization is not None else (entry.romanization or "")),
        pos=(new_pos if new_pos is not None else (entry.pos or "")),
        glosses=(glosses if glosses is not None else existing_glosses),
        forms=forms,
        commentary=(new_commentary if new_commentary is not None else (entry.commentary or "")),
        lemma=(new_lemma if new_lemma is not None else (entry.lemma or "")),
        source=entry.source or "gemini",
        entry_id=entry.entry_id,
    )
    return updated


def remove_tsv_entry(lang_code: str, headword: str, entry_id: str = "") -> bool:
    from db import db, CustomDictEntry

    entry = _query_custom_entry(lang_code, headword=headword, entry_id=entry_id)
    if not entry:
        return False
    entry_pk = int(entry.id or 0)
    db.session.delete(entry)
    db.session.commit()
    delete_custom_form_index_entry(entry_pk)
    return True


def migrate_legacy_custom_entries():
    from db import db, CustomDictEntry

    if CustomDictEntry.query.first():
        ensure_custom_form_index()
        return

    existing_pairs = {
        (str(e.language or "").strip().lower(), str(e.headword or "").strip())
        for e in CustomDictEntry.query.with_entities(CustomDictEntry.language, CustomDictEntry.headword).all()
    }
    def import_row(lang_code: str, row: dict, fallback_source: str = "gemini"):
        lang = str(lang_code or "").strip().lower()
        headword = str(row.get("headword", "") or "").strip()
        if not lang or not headword:
            return
        key = (lang, headword)
        if key in existing_pairs:
            return

        glosses_raw = row.get("glosses", "[]")
        glosses = []
        detected_source = str(row.get("source", "") or fallback_source or "gemini").strip().lower() or "gemini"
        try:
            parsed = json.loads(glosses_raw)
            if isinstance(parsed, list):
                for sense in parsed:
                    if isinstance(sense, dict) and sense.get("_source"):
                        detected_source = str(sense.get("_source") or detected_source).strip().lower() or detected_source
                        continue
                    if isinstance(sense, dict):
                        for gloss in (sense.get("glosses") or []):
                            text = str(gloss or "").strip()
                            if text:
                                glosses.append(text)
        except (TypeError, ValueError):
            pass

        forms = _normalize_forms(_json_load_list(row.get("forms", "[]")))
        entry = CustomDictEntry(
            entry_id=uuid.uuid4().hex,
            language=lang,
            headword=headword,
            romanization=str(row.get("romanization", "") or "").strip() or None,
            pos=str(row.get("pos", "") or "").strip() or None,
            glosses_json=json.dumps(_glosses_to_senses(glosses, detected_source), ensure_ascii=False),
            forms_json=json.dumps(forms, ensure_ascii=False),
            commentary=str(row.get("commentary", "") or "").strip() or None,
            lemma=str(row.get("lemma", "") or "").strip() or None,
            source=detected_source,
        )
        db.session.add(entry)
        existing_pairs.add(key)

    TSV_DIR.mkdir(exist_ok=True)
    for path in sorted(TSV_DIR.glob("*.tsv")):
        lang = path.stem.strip().lower()
        _header, rows = _parse_tsv_rows(path)
        if not rows:
            continue
        for row in rows:
            import_row(lang, row, fallback_source="gemini")
        db.session.commit()

    db.session.commit()
    ensure_custom_form_index(force_rebuild=True)


# ---------------------------------------------------------------------------
# Gemini NER / multiword-expression overlay
# ---------------------------------------------------------------------------

_GEMINI_NER_MAX_TOKENS = 900
_GEMINI_NER_MAX_SENTENCES = 80
_GEMINI_NER_MAX_SPAN_TOKENS = 16

_NO_SPACE_SPAN_LANGS = frozenset({"zh", "ja", "lzh", "th"})

_GEMINI_NER_SYSTEM_PROMPT = (
    "Tag useful named entities and multiword expressions in each token stream. "
    "Input is JSON with keys s0, s1, s2, ... . "
    "Output MUST be a JSON object with EXACTLY the same keys. "
    "Each value is a string. Use an empty string when there is nothing worth tagging. "
    "Inside a non-empty string, use one line per tag: token token token = TAG. "
    "Use exact tokens from the stream, separated by spaces. No indexes, no bullets, no explanations. "
    "Skip aggressively. Good tags include PERSON, PLACE, ORG, DATE, TIME, WORK, EVENT, TITLE, ETHNIC, IDIOM, MWE, TERM. "
    "Example value: Bo Pum Phak = PERSON"
)


def _gemini_ner_join_tokens(tokens: list[str], lang_code: str) -> str:
    clean = [str(t or "") for t in tokens]
    if (lang_code or "").strip().lower() in _NO_SPACE_SPAN_LANGS:
        return "".join(clean).strip()
    text = " ".join(t for t in clean if t)
    return re.sub(r"\s+([,.;:!?،。、「」『』)])", r"\1", text).strip()


def _gemini_ner_sentence_inputs(segments: list, ud_overlay: dict | None, lang_code: str) -> tuple[list[dict], dict]:
    segs = [str(s or "") for s in (segments or [])]
    if not segs:
        return [], {"token_count": 0, "sentence_count": 0, "truncated": False}

    raw_spans = []
    overlay = ud_overlay if isinstance(ud_overlay, dict) else {}
    for raw in list(overlay.get("sentences") or []):
        if not (isinstance(raw, (list, tuple)) and len(raw) >= 2):
            continue
        try:
            start = int(raw[0])
            end = int(raw[1])
        except Exception:
            continue
        start = max(0, min(len(segs), start))
        end = max(start, min(len(segs), end))
        if end > start:
            raw_spans.append((start, end))
    if not raw_spans:
        raw_spans = [(0, len(segs))]

    sentences = []
    token_count = 0
    truncated = False
    for sent_id, (start, end) in enumerate(raw_spans):
        if len(sentences) >= _GEMINI_NER_MAX_SENTENCES:
            truncated = True
            break
        if token_count >= _GEMINI_NER_MAX_TOKENS:
            truncated = True
            break
        local_tokens = []
        for idx in range(start, end):
            if token_count >= _GEMINI_NER_MAX_TOKENS:
                truncated = True
                break
            local_tokens.append(segs[idx])
            token_count += 1
        if local_tokens:
            sentences.append({
                "id": sent_id,
                "start": start,
                "end": start + len(local_tokens),
                "tokens": local_tokens,
            })
        if truncated:
            break

    return sentences, {
        "token_count": token_count,
        "sentence_count": len(sentences),
        "truncated": truncated,
    }


def _clean_gemini_ner_label(raw_label: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_ -]+", "", str(raw_label or "")).strip().upper()
    label = re.sub(r"[\s-]+", "_", label)
    return label[:24] or "NE"


def _gemini_ner_request_object(sentences: list[dict]) -> tuple[dict, list[str]]:
    keys = []
    src_obj = {}
    for i, sent in enumerate(sentences):
        key = f"s{i}"
        tokens = [str(t or "") for t in list(sent.get("tokens") or [])]
        src_obj[key] = " ".join(t for t in tokens if t)
        keys.append(key)
    return src_obj, keys


def _gemini_ner_token_key(token: str) -> str:
    text = unicodedata.normalize("NFKC", str(token or "")).strip().casefold()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n\"'`“”‘’.,;:!?()[]{}")


def _gemini_ner_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(" " if ch.isspace() else ch for ch in normalized)


def _find_gemini_ner_span_text(
    phrase: str,
    segments: list[str],
    occupied: set[tuple[int, int]],
    *,
    start_limit: int = 0,
    end_limit: int | None = None,
) -> tuple[int, int] | None:
    phrase_key = _gemini_ner_search_text(str(phrase or "").strip().strip("\"'`“”‘’"))
    if not phrase_key:
        return None
    lo = max(0, int(start_limit or 0))
    hi = len(segments) if end_limit is None else max(lo, min(len(segments), int(end_limit)))
    chars: list[str] = []
    char_to_seg: list[int | None] = []
    for seg_idx in range(lo, hi):
        if chars:
            chars.append(" ")
            char_to_seg.append(None)
        seg_text = str(segments[seg_idx] or "")
        for ch in seg_text:
            chars.append(ch)
            char_to_seg.append(seg_idx)
    haystack = _gemini_ner_search_text("".join(chars))
    if not haystack:
        return None
    search_from = 0
    while True:
        pos = haystack.find(phrase_key, search_from)
        if pos < 0:
            return None
        end_pos = pos + len(phrase_key)
        mapped = [
            char_to_seg[i]
            for i in range(pos, min(end_pos, len(char_to_seg)))
            if isinstance(char_to_seg[i], int)
        ]
        if mapped:
            start = min(mapped)
            end = max(mapped) + 1
            if end > start and end - start <= _GEMINI_NER_MAX_SPAN_TOKENS and (start, end) not in occupied:
                return start, end
        search_from = pos + 1


def _find_gemini_ner_span(
    tokens: list[str],
    segments: list[str],
    occupied: set[tuple[int, int]],
    *,
    start_limit: int = 0,
    end_limit: int | None = None,
) -> tuple[int, int] | None:
    if not tokens or len(tokens) > _GEMINI_NER_MAX_SPAN_TOKENS:
        return None
    wanted = [_gemini_ner_token_key(t) for t in tokens]
    if not all(wanted):
        return None
    seg_keys = [_gemini_ner_token_key(s) for s in segments]
    width = len(wanted)
    lo = max(0, int(start_limit or 0))
    hi = len(seg_keys) if end_limit is None else max(lo, min(len(seg_keys), int(end_limit)))
    for start in range(lo, hi - width + 1):
        end = start + width
        if (start, end) in occupied:
            continue
        if seg_keys[start:end] == wanted:
            return start, end
    return None


def _parse_gemini_ner_lines(
    text: str,
    segments: list,
    lang_code: str,
    occupied: set[tuple[int, int]],
    *,
    start_limit: int = 0,
    end_limit: int | None = None,
) -> list[dict]:
    segs = [str(s or "") for s in (segments or [])]
    if not segs:
        return []

    out = []
    seen = set()
    for raw_line in str(text or "").splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        line = re.sub(r"^[-*•\d.)\s]+", "", line).strip()
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        left = left.strip().strip("\"'`")
        right = right.strip()
        if not left or not right:
            continue
        label = _clean_gemini_ner_label(re.split(r"[\s:;,()]+", right, maxsplit=1)[0])
        span = _find_gemini_ner_span_text(
            left,
            segs,
            occupied,
            start_limit=start_limit,
            end_limit=end_limit,
        )
        if span is None:
            phrase_tokens = [t.strip().strip("\"'`") for t in left.split() if t.strip().strip("\"'`")]
            span = _find_gemini_ner_span(
                phrase_tokens,
                segs,
                occupied,
                start_limit=start_limit,
                end_limit=end_limit,
            )
        if span is None:
            continue
        start, end = span
        key = (start, end, label)
        if key in seen:
            continue
        seen.add(key)
        occupied.add((start, end))
        tokens = segs[start:end]
        text = _gemini_ner_join_tokens(tokens, lang_code)
        out.append({
            "start": start,
            "end": end,
            "label": label,
            "text": text,
            "tokens": tokens,
            "source": "gemini",
        })
    return out


def _parse_gemini_ner_object(parsed: dict, sentences: list[dict], segments: list, lang_code: str) -> list[dict]:
    if not isinstance(parsed, dict):
        return []
    out = []
    occupied: set[tuple[int, int]] = set()
    for i, sent in enumerate(sentences):
        key = f"s{i}"
        raw_value = parsed.get(key, "")
        if raw_value is None:
            raw_value = ""
        if not isinstance(raw_value, str):
            continue
        try:
            start_limit = int(sent.get("start") or 0)
            end_limit = int(sent.get("end") or start_limit)
        except Exception:
            start_limit = 0
            end_limit = len(segments or [])
        out.extend(_parse_gemini_ner_lines(
            raw_value,
            segments,
            lang_code,
            occupied,
            start_limit=start_limit,
            end_limit=end_limit,
        ))
    return out


def recognize_ner_mwe_for_overlay(
    segments: list,
    ud_overlay: dict | None,
    user,
    *,
    lang_code: str = "",
) -> dict:
    """Replace model NER spans with Gemini NER/MWE spans for ud_overlay.ents."""
    from db import ApiUsage, db as _db
    from config import TIER_CAPS

    if not GEMINI_DICT_ENABLED or not GEMINI_API_KEY:
        return {"ok": False, "error": "LLM service is not configured.", "ents": []}
    if not getattr(user, "is_authenticated", False):
        return {"ok": False, "error": "Not logged in.", "ents": []}
    if getattr(user, "tier", "free") == "free":
        return {"ok": False, "error": "Paid feature.", "upgrade_required": True, "ents": []}

    sentences, meta = _gemini_ner_sentence_inputs(segments, ud_overlay, lang_code)
    if not sentences:
        return {"ok": True, "ents": [], "meta": meta}

    usage = ApiUsage.query.filter_by(user_id=user.id).first()
    if not usage:
        usage = ApiUsage(user_id=user.id)
        _db.session.add(usage)
    usage._maybe_reset(user)
    if not usage.can_use_llm(user):
        return {"ok": False, "error": "Monthly LLM budget reached.", "ents": [], "meta": meta}

    model = TIER_CAPS.get(user.tier, {}).get("gemini_model") or GEMINI_DICT_MODEL
    src_obj, keys = _gemini_ner_request_object(sentences)
    schema_props = {key: {"type": "STRING"} for key in keys}
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": json.dumps(src_obj, ensure_ascii=False)}]}],
        "systemInstruction": {"parts": [{"text": f"Language: {lang_code}. " + _GEMINI_NER_SYSTEM_PROMPT}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": schema_props,
                "required": keys,
                "propertyOrdering": keys,
            },
            "candidateCount": 1,
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "seed": 7,
            "maxOutputTokens": max(256, min(1024, 32 * len(keys) + 128)),
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 503:
                log.warning("Gemini NER: 503 overloaded, retrying in 5s...")
                time.sleep(5)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("gemini_ner", model, payload, None, error="timeout")
        except Exception:
            pass
        return {"ok": False, "error": "LLM request timed out.", "ents": [], "meta": meta}
    except Exception as e:
        log.warning("Gemini NER failed: %s", e)
        try:
            from gemini_log import log_gemini_call
            log_gemini_call("gemini_ner", model, payload, None, error=str(e))
        except Exception:
            pass
        return {"ok": False, "error": "LLM service error.", "ents": [], "meta": meta}

    try:
        from gemini_log import log_gemini_call
        log_gemini_call("gemini_ner", model, payload, data)
    except Exception:
        pass

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get("thoughtsTokenCount", 0)
    usage_counts = {
        "prompt_tokens": usage_meta.get("promptTokenCount", max(0, total_tokens - response_tokens)),
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }

    candidates = data.get("candidates", [])
    if not candidates:
        return {"ok": False, "error": "No response from model.", "ents": [], "meta": meta}
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except Exception:
        return {"ok": False, "error": "Malformed NER response.", "ents": [], "meta": meta}

    ents = _parse_gemini_ner_object(parsed, sentences, segments, lang_code)
    usage.record_llm(usage_counts.get("prompt_tokens", 0), usage_counts.get("response_tokens", 0))
    _db.session.commit()

    meta = dict(meta)
    meta["model"] = model
    meta["tag_count"] = len(ents)
    return {
        "ok": True,
        "ents": ents,
        "meta": meta,
        "usage": usage_counts,
    }


# ---------------------------------------------------------------------------
# Sentence-level fluent translation (batch)
# ---------------------------------------------------------------------------

def translate_sentences(
    sentences: list,
    user,
    *,
    lang_code: str = "",
    sentence_requests=None,
) -> dict:
    """Batch translate per-sentence token lists into fluent idiomatic English via Gemini.

    Uses responseSchema=OBJECT<STRING> for minimal token overhead. Returns
    {"ok": True, "translations": [...]} aligned 1:1 with input, or
    {"ok": False, "error": "..."}.
    """
    from db import ApiUsage, db as _db
    from config import TIER_CAPS
    from gemini_log import log_gemini_call
    from api_services import _record_gemini_usage

    if not GEMINI_API_KEY:
        return {"ok": False, "error": "LLM service is not configured."}
    if getattr(user, "tier", "free") == "free":
        return {"ok": False, "error": "upgrade_required", "upgrade": True}

    structured = []
    if isinstance(sentence_requests, list):
        for item in sentence_requests:
            if not isinstance(item, dict):
                continue
            tokens = [str(t or "").strip() for t in (item.get("tokens") or []) if str(t or "").strip()]
            if not tokens:
                continue
            structured.append({"tokens": tokens})

    if not structured:
        return {"ok": True, "translations": []}

    usage = ApiUsage.query.filter_by(user_id=user.id).first()
    if not usage:
        usage = ApiUsage(user_id=user.id)
        _db.session.add(usage)
    usage._maybe_reset(user)
    if not usage.can_use_llm(user):
        return {"ok": False, "error": "Monthly LLM budget reached."}

    model = TIER_CAPS.get(user.tier, {}).get("gemini_model", "gemini-3.1-flash-lite")
    lang_hint = f" from {lang_code}" if lang_code else ""
    system_instruction = (
        "Translate each input token list" + lang_hint + " into fluent English. "
        "Each JSON value is an array of source tokens from one sentence. "
        "You must explicitly use all of the lexical content in the source tokens. "
        "Do not add anything that is not there. "
        "Do not invent subjects, objects, connectives, modality, aspect, discourse material, or explanatory content not supported by the source tokens. "
        "Do not omit lexical material unless English truly requires it to be absorbed into another word or construction. "
        "Keep the result clean, accurate, and natural, but maximally faithful. "
        "Input is JSON with keys s0, s1, s2, ... . "
        "Output MUST be a JSON object with EXACTLY the same keys (s0, s1, ...), "
        "each mapped to its English translation as a string. "
        "Do not merge, split, skip, reorder, or rename keys. "
        "If a token list is untranslatable, return an empty string for that key. "
        "No commentary, no numbering in values, no explanations."
    )
    src_obj = {f"s{i}": item["tokens"] for i, item in enumerate(structured)}
    joined = json.dumps(src_obj, ensure_ascii=False)
    item_count = len(structured)
    keys = [f"s{i}" for i in range(item_count)]
    schema_props = {k: {"type": "STRING"} for k in keys}

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": joined}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "generationConfig": {
            "maxOutputTokens": max(256, min(8192, 80 * item_count + 128)),
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": schema_props,
                "required": keys,
                "propertyOrdering": keys,
            },
        },
    }

    try:
        resp = None
        for _attempt in range(3):
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 503:
                time.sleep(5)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        usage_meta = log_gemini_call("sentence_xlate", model, payload, data)
        candidates = data.get("candidates", [])
        if not candidates:
            return {"ok": False, "error": "No response from model."}
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
            translations = [str(parsed.get(f"s{i}", "") or "") for i in range(item_count)]
        except Exception:
            return {"ok": False, "error": "Malformed translation response."}

        _record_gemini_usage(usage, usage_meta)
        _db.session.commit()
        return {"ok": True, "translations": translations}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "LLM request timed out."}
    except Exception as e:
        log.warning("translate_sentences error: %s", e)
        return {"ok": False, "error": "LLM service error."}
