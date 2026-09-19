from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple


APP_ROOT = Path(__file__).resolve().parent
TRAINING_ROOT = APP_ROOT / "training"
CAMELTOOLS_DATA_DIR = TRAINING_ROOT / "camel_tools_data"
CAMELTOOLS_TMP_DIR = TRAINING_ROOT / "camel_tools_tmp"

CAMELTOOLS_GATE_ENV = "LE_ARABIC_CAMELTOOLS_TOKENIZER"
CAMELTOOLS_MODEL_NAME = "calima-msa-r13"
CAMELTOOLS_SCHEME = "atbtok"

_SENTENCE_BREAK_RE = re.compile(r"(?:\r?\n)+|(?<=[.!?\u061f\u061b\u2026])\s+")
_TRUTHY = {"1", "true", "yes", "on"}

_BUNDLE_LOCK = threading.Lock()
_CAMELTOOLS_BUNDLE: Optional["_CamelToolsBundle"] = None


@dataclass
class _CamelToolsBundle:
    simple_word_tokenize: Any
    morph_tokenizer: Any


@dataclass
class _PretokenizedSentence:
    tokens: List[str]
    spans: List[Tuple[int, int]]


def camel_tools_gate_enabled(raw_value: Optional[str] = None) -> bool:
    value = (
        str(raw_value if raw_value is not None else os.environ.get(CAMELTOOLS_GATE_ENV, ""))
        .strip()
        .lower()
    )
    return value in _TRUTHY


@contextmanager
def _temporary_env(overrides: Dict[str, str]) -> Iterator[None]:
    previous: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _ensure_local_dirs() -> None:
    CAMELTOOLS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAMELTOOLS_TMP_DIR.mkdir(parents=True, exist_ok=True)


def _build_import_env() -> Dict[str, str]:
    training_root = str(TRAINING_ROOT)
    return {
        "CAMELTOOLS_DATA": str(CAMELTOOLS_DATA_DIR),
        "TEMP": str(CAMELTOOLS_TMP_DIR),
        "TMP": str(CAMELTOOLS_TMP_DIR),
        "HOME": training_root,
        "USERPROFILE": training_root,
    }


def _get_camel_tools_bundle() -> _CamelToolsBundle:
    global _CAMELTOOLS_BUNDLE
    if _CAMELTOOLS_BUNDLE is not None:
        return _CAMELTOOLS_BUNDLE

    with _BUNDLE_LOCK:
        if _CAMELTOOLS_BUNDLE is not None:
            return _CAMELTOOLS_BUNDLE

        _ensure_local_dirs()
        with _temporary_env(_build_import_env()):
            from camel_tools.disambig.mle import MLEDisambiguator
            from camel_tools.tokenizers.morphological import MorphologicalTokenizer
            from camel_tools.tokenizers.word import simple_word_tokenize

            disambiguator = MLEDisambiguator.pretrained(CAMELTOOLS_MODEL_NAME)
            morph_tokenizer = MorphologicalTokenizer(
                disambiguator=disambiguator,
                scheme=CAMELTOOLS_SCHEME,
                split=True,
                diac=False,
            )

        _CAMELTOOLS_BUNDLE = _CamelToolsBundle(
            simple_word_tokenize=simple_word_tokenize,
            morph_tokenizer=morph_tokenizer,
        )
        return _CAMELTOOLS_BUNDLE


def _iter_sentence_chunks(text: str) -> Iterator[str]:
    if not text:
        return
    start = 0
    for match in _SENTENCE_BREAK_RE.finditer(text):
        chunk = text[start : match.start()]
        if chunk.strip():
            yield chunk
        start = match.end()
    tail = text[start:]
    if tail.strip():
        yield tail


def _normalize_morph_token(raw_token: Any) -> str:
    text = str(raw_token or "")
    if not text:
        return ""
    # CAMeL ATB tokenization uses '+' boundary markers. Strip them so Trankit
    # receives true surface substrings that can be aligned back to the input.
    text = text.replace("_", "").replace("+", "").strip()
    return text


def _align_exact_tokens(
    text: str,
    tokens: Sequence[str],
    base_offset: int,
) -> List[Tuple[int, int]]:
    cursor = 0
    spans: List[Tuple[int, int]] = []

    for token in tokens:
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

        start = text.find(token, cursor)
        if start < 0:
            raise ValueError(f"Unable to align base token {token!r} to source text.")

        skipped = text[cursor:start]
        if skipped.strip():
            raise ValueError(
                f"Unexpected non-whitespace gap before base token {token!r}: {skipped!r}"
            )

        end = start + len(token)
        spans.append((base_offset + start, base_offset + end))
        cursor = end

    return spans


def _surface_piece_candidates(piece: str, piece_index: int) -> List[str]:
    candidates = [piece]
    # Arabic orthography may elide the article alif after an attached proclitic
    # (e.g. CAMeL: "ل" + "الدولة" vs raw text: "للدولة").
    if piece_index > 0 and piece.startswith("ال") and len(piece) > 1:
        candidates.append(piece[1:])
    return candidates


def _surface_pieces_from_group(base_token: str, morph_group: Sequence[str]) -> List[str]:
    normalized = [_normalize_morph_token(tok) for tok in morph_group]
    normalized = [tok for tok in normalized if tok]
    if len(normalized) <= 1:
        return [base_token]

    out: List[str] = []
    cursor = 0
    last_idx = len(normalized) - 1

    for piece_index, piece in enumerate(normalized):
        if piece_index == last_idx:
            remainder = base_token[cursor:]
            if not remainder:
                return [base_token]
            out.append(remainder)
            break

        chosen = ""
        for candidate in _surface_piece_candidates(piece, piece_index):
            if candidate and base_token.startswith(candidate, cursor):
                chosen = candidate
                break

        if not chosen:
            return [base_token]

        out.append(chosen)
        cursor += len(chosen)

    if "".join(out) != base_token:
        return [base_token]

    return out


def _tokenize_sentence_chunk(
    chunk: str,
    base_offset: int,
) -> _PretokenizedSentence:
    bundle = _get_camel_tools_bundle()
    base_tokens = list(bundle.simple_word_tokenize(chunk) or [])
    if not base_tokens:
        return _PretokenizedSentence(tokens=[], spans=[])

    base_spans = _align_exact_tokens(chunk, base_tokens, base_offset)
    out_tokens: List[str] = []
    out_spans: List[Tuple[int, int]] = []

    for base_token, (start, end) in zip(base_tokens, base_spans):
        morph_group = list(bundle.morph_tokenizer.tokenize([base_token]) or [])
        surface_pieces = _surface_pieces_from_group(base_token, morph_group)

        piece_cursor = start
        for piece in surface_pieces:
            piece_end = piece_cursor + len(piece)
            out_tokens.append(base_token[piece_cursor - start : piece_end - start])
            out_spans.append((piece_cursor, piece_end))
            piece_cursor = piece_end

    return _PretokenizedSentence(tokens=out_tokens, spans=out_spans)


def _camel_morph_tokenize_text(text: str) -> List[_PretokenizedSentence]:
    sentences: List[_PretokenizedSentence] = []
    search_start = 0

    for chunk in _iter_sentence_chunks(text):
        base_offset = text.find(chunk, search_start)
        if base_offset < 0:
            raise ValueError(f"Unable to locate sentence chunk {chunk!r} in source text.")
        sentence = _tokenize_sentence_chunk(chunk, base_offset)
        if sentence.tokens:
            sentences.append(sentence)
        search_start = base_offset + len(chunk)

    if sentences:
        return sentences

    sentence = _tokenize_sentence_chunk(text, 0)
    return [sentence] if sentence.tokens else []


def _attach_sentence_and_token_spans(
    doc: Dict[str, Any],
    text: str,
    sentences: Sequence[_PretokenizedSentence],
) -> Dict[str, Any]:
    doc["text"] = text
    out_sentences = doc.get("sentences", [])
    if len(out_sentences) != len(sentences):
        raise ValueError(
            f"Trankit returned {len(out_sentences)} sentences for {len(sentences)} CAMeL-tokenized sentences."
        )

    for sent_idx, sent in enumerate(out_sentences):
        token_texts = list(sentences[sent_idx].tokens)
        token_spans = list(sentences[sent_idx].spans)
        out_tokens = sent.get("tokens", [])
        if len(out_tokens) != len(token_texts):
            raise ValueError(
                f"Trankit returned {len(out_tokens)} tokens for CAMeL sentence with {len(token_texts)} tokens."
            )

        sent["id"] = sent_idx + 1
        if token_spans:
            sent_start = token_spans[0][0]
            sent_end = token_spans[-1][1]
            sent["text"] = text[sent_start:sent_end]
            sent["dspan"] = (sent_start, sent_end)
        else:
            sent["text"] = ""
            sent["dspan"] = (0, 0)

        for tok_idx, tok in enumerate(out_tokens):
            start, end = token_spans[tok_idx]
            sent_start = sent["dspan"][0]
            tok["id"] = tok_idx + 1
            tok["text"] = token_texts[tok_idx]
            tok["dspan"] = (start, end)
            tok["span"] = (start - sent_start, end - sent_start)

    return doc


def run_trankit_with_camel_tools_tokenization(pipeline: Any, text: str) -> Dict[str, Any]:
    sentences = _camel_morph_tokenize_text(text)
    if not sentences:
        return {"text": text, "sentences": []}

    doc = pipeline([sentence.tokens for sentence in sentences])
    doc = _attach_sentence_and_token_spans(doc, text, sentences)
    doc["camel_tools_meta"] = {
        "enabled": True,
        "gate_env": CAMELTOOLS_GATE_ENV,
        "model": CAMELTOOLS_MODEL_NAME,
        "scheme": CAMELTOOLS_SCHEME,
        "split": True,
        "diac": False,
        "sentence_count": len(sentences),
        "token_count": sum(len(sentence.tokens) for sentence in sentences),
    }
    return doc
