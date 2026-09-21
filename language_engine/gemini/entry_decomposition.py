"""Gemini entry decomposition service."""

from config import GEMINI_API_KEY
import json
import requests
import time
from .settings import GEMINI_DICT_MODEL, is_enabled, log

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
                        for g in inner if isinstance(inner, list) else [inner]:
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
    if lemma and (
        not isinstance(trankit, dict) or not str(trankit.get("lemma") or "").strip()
    ):
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

    usage_meta_raw = data.get("usageMetadata") or {}
    total = usage_meta_raw.get("totalTokenCount", 0)
    resp_tok = usage_meta_raw.get("candidatesTokenCount", 0) + usage_meta_raw.get(
        "thoughtsTokenCount", 0
    )
    usage_meta = {
        "input_tokens": usage_meta_raw.get(
            "promptTokenCount", max(0, total - resp_tok)
        ),
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
