"""Gemini notes service."""

from .settings import GEMINI_DICT_MODEL, is_enabled

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
            for sense in raw or []:
                if isinstance(sense, dict):
                    inner = sense.get("glosses") or []
                    for g in inner if isinstance(inner, list) else [inner]:
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
            reading_text = str(
                ent.get("reading") or ent.get("romanization") or ""
            ).strip()
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
    tok_stream = [
        str(t).strip() for t in (sentence_tokens or []) if str(t or "").strip()
    ]
    if tok_stream:
        user_prompt += "\nSentence tokens (context only): " + " | ".join(
            tok_stream[:200]
        )

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
            parts = [
                f"[{tag}]",
                f"surface={surf}" if surf else "",
                f"headword={hw}" if hw else "",
            ]
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
    output_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get(
        "thoughtsTokenCount", 0
    )
    return {
        "ok": True,
        "note": note_text,
        "usage_meta": {
            "input_tokens": usage_meta.get(
                "promptTokenCount", max(0, total_tokens - output_tokens)
            ),
            "output_tokens": output_tokens,
        },
    }
