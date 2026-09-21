"""Gemini ner service."""

from config import GEMINI_API_KEY
import json
import re
import requests
import time
import unicodedata
from .settings import GEMINI_DICT_ENABLED, GEMINI_DICT_MODEL, log

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


def _gemini_ner_sentence_inputs(
    segments: list, ud_overlay: dict | None, lang_code: str
) -> tuple[list[dict], dict]:
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
            sentences.append(
                {
                    "id": sent_id,
                    "start": start,
                    "end": start + len(local_tokens),
                    "tokens": local_tokens,
                }
            )
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
    hi = (
        len(segments)
        if end_limit is None
        else max(lo, min(len(segments), int(end_limit)))
    )
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
            if (
                end > start
                and end - start <= _GEMINI_NER_MAX_SPAN_TOKENS
                and (start, end) not in occupied
            ):
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
    hi = (
        len(seg_keys)
        if end_limit is None
        else max(lo, min(len(seg_keys), int(end_limit)))
    )
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
            phrase_tokens = [
                t.strip().strip("\"'`") for t in left.split() if t.strip().strip("\"'`")
            ]
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
        out.append(
            {
                "start": start,
                "end": end,
                "label": label,
                "text": text,
                "tokens": tokens,
                "source": "gemini",
            }
        )
    return out


def _parse_gemini_ner_object(
    parsed: dict, sentences: list[dict], segments: list, lang_code: str
) -> list[dict]:
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
        out.extend(
            _parse_gemini_ner_lines(
                raw_value,
                segments,
                lang_code,
                occupied,
                start_limit=start_limit,
                end_limit=end_limit,
            )
        )
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
        return {
            "ok": False,
            "error": "Paid feature.",
            "upgrade_required": True,
            "ents": [],
        }

    sentences, meta = _gemini_ner_sentence_inputs(segments, ud_overlay, lang_code)
    if not sentences:
        return {"ok": True, "ents": [], "meta": meta}

    usage = ApiUsage.query.filter_by(user_id=user.id).first()
    if not usage:
        usage = ApiUsage(user_id=user.id)
        _db.session.add(usage)
    usage._maybe_reset(user)
    if not usage.can_use_llm(user):
        return {
            "ok": False,
            "error": "Monthly LLM budget reached.",
            "ents": [],
            "meta": meta,
        }

    model = TIER_CAPS.get(user.tier, {}).get("gemini_model") or GEMINI_DICT_MODEL
    src_obj, keys = _gemini_ner_request_object(sentences)
    schema_props = {key: {"type": "STRING"} for key in keys}
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": json.dumps(src_obj, ensure_ascii=False)}]}],
        "systemInstruction": {
            "parts": [{"text": f"Language: {lang_code}. " + _GEMINI_NER_SYSTEM_PROMPT}]
        },
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
        return {
            "ok": False,
            "error": "LLM request timed out.",
            "ents": [],
            "meta": meta,
        }
    except Exception as e:
        log.warning("Gemini NER failed: %s", e)
        return {"ok": False, "error": "LLM service error.", "ents": [], "meta": meta}

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
        return {
            "ok": False,
            "error": "No response from model.",
            "ents": [],
            "meta": meta,
        }
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except Exception:
        return {
            "ok": False,
            "error": "Malformed NER response.",
            "ents": [],
            "meta": meta,
        }

    ents = _parse_gemini_ner_object(parsed, sentences, segments, lang_code)
    usage.record_llm(
        usage_counts.get("prompt_tokens", 0), usage_counts.get("response_tokens", 0)
    )
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
