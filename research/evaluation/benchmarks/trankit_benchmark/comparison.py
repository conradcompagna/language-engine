"""Trankit benchmark: comparison."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def _annotation_fingerprint(annotation: Any) -> str:
    payload = json.dumps(
        annotation,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _annotation_counts(annotation: Any) -> Dict[str, int]:
    sentences = annotation.get("sentences") if isinstance(annotation, dict) else []
    if not isinstance(sentences, list):
        sentences = []
    token_count = 0
    ner_count = 0
    dependency_edge_count = 0
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        tokens = sentence.get("tokens")
        if not isinstance(tokens, list):
            tokens = (
                sentence.get("TOKENS")
                if isinstance(sentence.get("TOKENS"), list)
                else []
            )
        for token in tokens:
            if not isinstance(token, dict):
                continue
            token_count += 1
            if token.get("ner") or token.get("NER"):
                ner_count += 1
            if token.get("head") is not None or token.get("HEAD") is not None:
                dependency_edge_count += 1
    return {
        "sentence_count": len(sentences),
        "token_count": token_count,
        "ner_count": ner_count,
        "dependency_edge_count": dependency_edge_count,
    }


def _annotation_sentences(annotation: Any) -> list[Any]:
    if not isinstance(annotation, dict):
        return []
    sentences = annotation.get("sentences")
    if isinstance(sentences, list):
        return sentences
    sentences = annotation.get("SENTENCES")
    return sentences if isinstance(sentences, list) else []


def _sentence_tokens(sentence: Any) -> list[Any]:
    if not isinstance(sentence, dict):
        return []
    tokens = sentence.get("tokens")
    if isinstance(tokens, list):
        return tokens
    tokens = sentence.get("TOKENS")
    return tokens if isinstance(tokens, list) else []


def _first_value(data: Any, keys: list[str]) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _compact_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _token_text(token: Any) -> str:
    return _compact_value(_first_value(token, ["text", "TEXT"]))


def _expanded_texts(token: Any) -> tuple[str, ...]:
    expanded = _first_value(token, ["expanded", "EXPANDED"])
    if not isinstance(expanded, list):
        return ()
    return tuple(_token_text(item) for item in expanded if isinstance(item, dict))


def _analysis_units(sentence: Any) -> list[Any]:
    out: list[Any] = []
    for token in _sentence_tokens(sentence):
        expanded = _first_value(token, ["expanded", "EXPANDED"])
        if isinstance(expanded, list) and expanded:
            out.extend(item for item in expanded if isinstance(item, dict))
        elif isinstance(token, dict):
            out.append(token)
    return out


def _sentence_signature(sentence: Any) -> str:
    return "\u241f".join(_token_text(token) for token in _sentence_tokens(sentence))


def _sentence_boundary_signature(sentence: Any) -> str:
    if not isinstance(sentence, dict):
        return "missing"
    span = _first_value(sentence, ["dspan", "DSPAN", "span", "SPAN"])
    if isinstance(span, (list, tuple)) and len(span) >= 2:
        try:
            return f"span:{int(span[0])}:{int(span[1])}"
        except (TypeError, ValueError):
            pass
    text = _first_value(sentence, ["text", "TEXT"])
    if text is not None:
        return f"text:{_compact_value(text)}"
    tokens = _sentence_tokens(sentence)
    if not tokens:
        return "empty"
    first_span = _first_value(tokens[0], ["dspan", "DSPAN", "span", "SPAN"])
    last_span = _first_value(tokens[-1], ["dspan", "DSPAN", "span", "SPAN"])
    if (
        isinstance(first_span, (list, tuple))
        and len(first_span) >= 1
        and isinstance(last_span, (list, tuple))
        and len(last_span) >= 2
    ):
        try:
            return f"token-span:{int(first_span[0])}:{int(last_span[1])}"
        except (TypeError, ValueError):
            pass
    return f"tokens:{_sentence_signature(sentence)}"


def _matching_index_pairs(left: list[str], right: list[str]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    matcher = __import__("difflib").SequenceMatcher(a=left, b=right)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            pairs.append((block.a + offset, block.b + offset))
    return pairs


def _sequence_same_count(left: list[str], right: list[str]) -> int:
    matcher = __import__("difflib").SequenceMatcher(a=left, b=right)
    return sum(block.size for block in matcher.get_matching_blocks())


def _metric_payload(label: str, same: int, total: int) -> Dict[str, Any]:
    same = int(max(0, same))
    total = int(max(0, total))
    diff = max(0, total - same)
    same_percent = (same / total * 100.0) if total else None
    diff_percent = (diff / total * 100.0) if total else None
    return {
        "label": label,
        "same": same,
        "diff": diff,
        "total": total,
        "same_percent": same_percent,
        "diff_percent": diff_percent,
    }


def _metric_line(metric: Dict[str, Any]) -> str:
    same_percent = metric.get("same_percent")
    diff_percent = metric.get("diff_percent")
    if same_percent is None or diff_percent is None:
        return f"{metric['label']}: n/a"
    return (
        f"{metric['label']}: "
        f"{same_percent:.1f}% same / {diff_percent:.1f}% diff "
        f"({metric['same']}/{metric['total']})"
    )


def _annotation_discrepancy_report(
    cpu_annotation: Any, gpu_annotation: Any
) -> Dict[str, Any]:
    cpu_fingerprint = _annotation_fingerprint(cpu_annotation)
    gpu_fingerprint = _annotation_fingerprint(gpu_annotation)

    cpu_sentences = _annotation_sentences(cpu_annotation)
    gpu_sentences = _annotation_sentences(gpu_annotation)
    metrics: list[Dict[str, Any]] = []
    cpu_sentence_boundaries = [
        _sentence_boundary_signature(sentence) for sentence in cpu_sentences
    ]
    gpu_sentence_boundaries = [
        _sentence_boundary_signature(sentence) for sentence in gpu_sentences
    ]
    cpu_sentence_sigs = [_sentence_signature(sentence) for sentence in cpu_sentences]
    gpu_sentence_sigs = [_sentence_signature(sentence) for sentence in gpu_sentences]
    sentence_total = max(len(cpu_sentence_boundaries), len(gpu_sentence_boundaries))
    sentence_same = (
        _sequence_same_count(cpu_sentence_boundaries, gpu_sentence_boundaries)
        if sentence_total
        else 0
    )
    metrics.append(_metric_payload("Sentences", sentence_same, sentence_total))
    sentence_token_total = max(len(cpu_sentence_sigs), len(gpu_sentence_sigs))
    sentence_token_same = (
        _sequence_same_count(cpu_sentence_sigs, gpu_sentence_sigs)
        if sentence_token_total
        else 0
    )
    metrics.append(
        _metric_payload(
            "Sentence token sequences", sentence_token_same, sentence_token_total
        )
    )

    cpu_token_texts: list[str] = []
    gpu_token_texts: list[str] = []
    cpu_word_texts: list[str] = []
    gpu_word_texts: list[str] = []
    mwt_same = 0
    mwt_total = 0
    field_counts: Dict[str, Dict[str, int]] = {
        "Morph feats": {"same": 0, "total": 0},
        "UPOS": {"same": 0, "total": 0},
        "XPOS": {"same": 0, "total": 0},
        "Dependency relations": {"same": 0, "total": 0},
        "Heads": {"same": 0, "total": 0},
        "NER tags": {"same": 0, "total": 0},
        "Lemmas": {"same": 0, "total": 0},
    }
    field_keys = [
        ("Morph feats", ["feats", "FEATS"]),
        ("UPOS", ["upos", "UPOS"]),
        ("XPOS", ["xpos", "XPOS"]),
        ("Dependency relations", ["deprel", "DEPREL"]),
        ("Heads", ["head", "HEAD"]),
        ("NER tags", ["ner", "NER"]),
        ("Lemmas", ["lemma", "LEMMA"]),
    ]

    for sentence in cpu_sentences:
        cpu_token_texts.extend(
            _token_text(token) for token in _sentence_tokens(sentence)
        )
        cpu_word_texts.extend(_token_text(unit) for unit in _analysis_units(sentence))
    for sentence in gpu_sentences:
        gpu_token_texts.extend(
            _token_text(token) for token in _sentence_tokens(sentence)
        )
        gpu_word_texts.extend(_token_text(unit) for unit in _analysis_units(sentence))

    for cpu_sent_index, gpu_sent_index in _matching_index_pairs(
        cpu_sentence_boundaries, gpu_sentence_boundaries
    ):
        cpu_sentence = cpu_sentences[cpu_sent_index]
        gpu_sentence = gpu_sentences[gpu_sent_index]
        cpu_tokens = _sentence_tokens(cpu_sentence)
        gpu_tokens = _sentence_tokens(gpu_sentence)

        for token_index in range(min(len(cpu_tokens), len(gpu_tokens))):
            cpu_token = cpu_tokens[token_index]
            gpu_token = gpu_tokens[token_index]
            if _token_text(cpu_token) != _token_text(gpu_token):
                continue
            cpu_expanded = _expanded_texts(cpu_token)
            gpu_expanded = _expanded_texts(gpu_token)
            if cpu_expanded or gpu_expanded:
                mwt_total += 1
                if cpu_expanded == gpu_expanded:
                    mwt_same += 1

        cpu_units = _analysis_units(cpu_sentence)
        gpu_units = _analysis_units(gpu_sentence)
        for unit_index in range(min(len(cpu_units), len(gpu_units))):
            cpu_unit = cpu_units[unit_index]
            gpu_unit = gpu_units[unit_index]
            if _token_text(cpu_unit) != _token_text(gpu_unit):
                continue
            for label, keys in field_keys:
                cpu_value = _first_value(cpu_unit, keys)
                gpu_value = _first_value(gpu_unit, keys)
                if cpu_value is None and gpu_value is None:
                    continue
                field_counts[label]["total"] += 1
                if cpu_value == gpu_value:
                    field_counts[label]["same"] += 1

    token_total = max(len(cpu_token_texts), len(gpu_token_texts))
    token_same = (
        _sequence_same_count(cpu_token_texts, gpu_token_texts) if token_total else 0
    )
    word_total = max(len(cpu_word_texts), len(gpu_word_texts))
    word_same = (
        _sequence_same_count(cpu_word_texts, gpu_word_texts) if word_total else 0
    )
    metrics.append(_metric_payload("Tokens", token_same, token_total))
    metrics.append(_metric_payload("Analysis units", word_same, word_total))
    metrics.append(_metric_payload("MWT expansions", mwt_same, mwt_total))
    for label in [
        "UPOS",
        "XPOS",
        "Morph feats",
        "Dependency relations",
        "Heads",
        "NER tags",
        "Lemmas",
    ]:
        row = field_counts[label]
        metrics.append(_metric_payload(label, row["same"], row["total"]))

    text = "\n".join(_metric_line(metric) for metric in metrics)
    return {
        "match": bool(cpu_fingerprint == gpu_fingerprint),
        "diff_count": sum(int(metric["diff"]) for metric in metrics),
        "truncated": False,
        "metrics": metrics,
        "text": text,
    }
