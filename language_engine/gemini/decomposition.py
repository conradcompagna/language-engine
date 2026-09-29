"""Gemini decomposition service."""

from config import GEMINI_API_KEY
import json
import requests
import time
from .gloss import _token_to_key_suffix
from .settings import GEMINI_DICT_MODEL, log

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
    'wohn = verb stem "dwell"\n'
    "te = past tense marker\n"
    "n = first-person plural ending\n"
    "\n"
    "3_Häusern:\n"
    'Häus = noun stem "house"\n'
    "er = plural marker\n"
    "n = dative ending\n\n"
    "Input sentence:\n"
    "Çocuklar evlerimizden kaçtı .\n"
    "Output:\n"
    "0_Çocuklar:\n"
    'Çocuk = noun stem "child"\n'
    "lar = plural marker\n"
    "\n"
    "1_evlerimizden:\n"
    'ev = noun stem "house"\n'
    "ler = plural marker\n"
    'imiz = first-person plural possessive suffix "our"\n'
    "den = ablative ending\n"
    "\n"
    "2_kaçtı:\n"
    'kaç = verb stem "escape"\n'
    "tı = past tense third-person ending\n\n"
    "Input sentence:\n"
    "وكتبناها أمس .\n"
    "Output:\n"
    "0_وكتبناها:\n"
    'و = coordinating prefix "and"\n'
    'كتب = verb stem "write"\n'
    'نا = first-person plural suffix "we"\n'
    'ها = feminine object suffix "it"\n\n'
    "Input sentence:\n"
    "Hablábamos allí .\n"
    "Output:\n"
    "0_Hablábamos:\n"
    'habl = verb stem "speak"\n'
    "ába = imperfect marker\n"
    "mos = first-person plural ending\n\n"
    "Input sentence:\n"
    "बालकाः गृहेषु वसन्ति ।\n"
    "Output:\n"
    "0_बालकाः:\n"
    'बालक = noun stem "boy"\n'
    "ाः = nominative plural ending\n"
    "\n"
    "1_गृहेषु:\n"
    'गृह = noun stem "house"\n'
    "ेषु = locative plural ending\n"
    "\n"
    "2_वसन्ति:\n"
    'वस् = verb stem "dwell"\n'
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
                if ("too many states" in err_msg or "constraint" in err_msg) and len(
                    targets
                ) > 1:
                    log.warning(
                        "LLM decomp chunk: 400 schema too complex (%d targets), splitting in half",
                        len(targets),
                    )
                    mid = len(targets) // 2
                    res_a, usage_a = call_decomp_chunk(
                        sentence_tokens, targets[:mid], lang_code
                    )
                    res_b, usage_b = call_decomp_chunk(
                        sentence_tokens, targets[mid:], lang_code
                    )
                    combined_usage = {
                        k: usage_a.get(k, 0) + usage_b.get(k, 0)
                        for k in ("prompt_tokens", "response_tokens", "total_tokens")
                    }
                    if res_a is None and res_b is None:
                        return None, combined_usage
                    merged = (res_a or [None] * mid) + (
                        res_b or [None] * (len(targets) - mid)
                    )
                    return merged, combined_usage
            if resp.status_code != 200:
                log.warning(
                    "LLM decomp chunk: HTTP %d: %s", resp.status_code, resp.text[:500]
                )
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("LLM decomp chunk failed: %s", e)
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
