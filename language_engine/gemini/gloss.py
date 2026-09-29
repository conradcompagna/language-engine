"""Gemini gloss service."""

from config import GEMINI_API_KEY
import json
import re as _re
import requests
import time
import unicodedata as _unicodedata
from .settings import GEMINI_DICT_ENABLED, GEMINI_DICT_MODEL, log

_GLOSS_SKIP_CATEGORIES = frozenset(
    {
        "Mn",
        "Mc",
        "Me",  # Mark
        "Nd",
        "Nl",
        "No",  # Number
        "Pc",
        "Pd",
        "Ps",
        "Pe",
        "Pi",
        "Pf",
        "Po",  # Punctuation
        "Sm",
        "Sc",
        "Sk",
        "So",  # Symbol
        "Zs",
        "Zl",
        "Zp",  # Separator
        "Cc",
        "Cf",
        "Cs",
        "Co",
        "Cn",  # Other/Control
    }
)


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
    chunks = [
        glossable[i : i + CHUNK_SIZE] for i in range(0, len(glossable), CHUNK_SIZE)
    ]
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
    chunks = [
        glossable[i : i + CHUNK_SIZE] for i in range(0, len(glossable), CHUNK_SIZE)
    ]
    gi_chunks = [
        glossable_indices[i : i + CHUNK_SIZE]
        for i in range(0, len(glossable_indices), CHUNK_SIZE)
    ]

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
            stream = " ".join(
                _gloss_prompt_token_text(chunk[i], lang_code) for i in range(start, end)
            )
            parts.append(f"sentence {sn}:\n{stream}")
        user_prompt = f"Language: {lang_code}.\n" + "\n\n".join(parts) + "\n"
    else:
        token_stream = " ".join(
            _gloss_prompt_token_text(tok, lang_code) for tok in chunk
        )
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
                        log.warning(
                            "LLM gloss chunk: 400 schema too complex on single token, giving up"
                        )
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
                    res_a, usage_a = call_gloss_chunk(
                        half_a, lang_code, context=context, sentences=spans_a
                    )
                    res_b, usage_b = call_gloss_chunk(
                        half_b, lang_code, context=context, sentences=spans_b
                    )
                    combined_usage = {
                        k: usage_a.get(k, 0) + usage_b.get(k, 0)
                        for k in ("prompt_tokens", "response_tokens", "total_tokens")
                    }
                    if res_a is None and res_b is None:
                        return None, combined_usage
                    merged = (res_a or [None] * len(half_a)) + (
                        res_b or [None] * len(half_b)
                    )
                    return merged, combined_usage
                # 400 but not schema error — fall through to raise
            if resp.status_code != 200:
                log.warning(
                    "LLM gloss chunk: HTTP %d: %s", resp.status_code, resp.text[:500]
                )
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("LLM gloss chunk failed: %s", e)
        return None, {}

    usage_meta = data.get("usageMetadata") or {}
    total_tokens = usage_meta.get("totalTokenCount", 0)
    response_tokens = usage_meta.get("candidatesTokenCount", 0) + usage_meta.get(
        "thoughtsTokenCount", 0
    )
    usage_counts = {
        "prompt_tokens": usage_meta.get(
            "promptTokenCount", max(0, total_tokens - response_tokens)
        ),
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
        log.warning(
            "LLM gloss chunk: key mismatch. Expected %s, got %s",
            sorted(expected_keys),
            sorted(parsed.keys()) if isinstance(parsed, dict) else type(parsed),
        )
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
