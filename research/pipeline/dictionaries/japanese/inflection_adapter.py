"""Adapter: jp_inflection_table_analyzer -> grammar popup conjugation payload."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence

from japanese.jp_inflection_table_analyzer import JapaneseInflectionTableAnalyzer

_ANALYZER = JapaneseInflectionTableAnalyzer()

_TAG_DESCRIPTIONS: Dict[str, str] = {
    "Negative": "negative form",
    "Past": "past form",
    "Te": "te-form",
    "Conditional": "conditional form",
    "Imperative": "imperative form",
    "Volitional": "volitional form",
    "Conjunctive": "continuative/linking stem",
    "Irrealis": "irrealis stem",
    "ConditionalStem": "conditional stem",
    "TeTaStem": "te/ta stem",
    "Polite": "polite morphology",
    "ClassicalNegative": "classical negative morphology",
    "Zu": "classical -zu negative",
    "Nu": "classical -nu negative",
    "Passive": "passive derivation",
    "Potential": "potential derivation",
    "Causative": "causative derivation",
    "CausativePassive": "causative-passive derivation",
    "Dictionary": "dictionary/non-past form",
    "Adverbial": "adverbial form",
    "Attributive": "attributive form",
    "Copula": "copular form",
    "Alt": "alternate variant",
    "NonPast": "non-past",
    "Suppletive": "suppletive form",
}

_CONJUGATION_TAGS = {
    "Negative",
    "Past",
    "Ta",
    "Te",
    "Conditional",
    "Imperative",
    "Volitional",
    "Conjunctive",
    "Irrealis",
    "Dictionary",
    "Tara",
    "Tari",
    "Zu",
    "Nu",
    "Polite",
    "Adverbial",
    "Attributive",
    "Copula",
    "ConditionalStem",
    "TeTaStem",
}


def _split_derivation_chain(chain: Sequence[str]) -> tuple[str, List[str]]:
    """
    Analyzer rows are not guaranteed to place conjugation first.
    Prefer the first conjugation-like tag; treat the rest as auxiliaries/derivations.
    """
    clean = [str(tag or "").strip() for tag in chain if str(tag or "").strip()]
    if not clean:
        return "", []
    if clean[0] in _CONJUGATION_TAGS:
        return clean[0], clean[1:]

    conjugation = ""
    conj_idx = -1
    for idx, tag in enumerate(clean):
        if tag in _CONJUGATION_TAGS:
            conjugation = tag
            conj_idx = idx
            break

    if not conjugation:
        return clean[0], clean[1:]

    auxiliaries = [tag for idx, tag in enumerate(clean) if idx != conj_idx]
    return conjugation, auxiliaries


def _extract_pos_labels(all_pos_or_entry: Any) -> List[str]:
    labels: List[str] = []
    seen = set()

    def _add(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        labels.append(text)

    if isinstance(all_pos_or_entry, dict):
        all_pos = all_pos_or_entry.get("all_pos", [])
        pos = all_pos_or_entry.get("pos", "")
        if isinstance(all_pos, (list, tuple, set)):
            for item in all_pos:
                _add(item)
        else:
            _add(all_pos)
        if isinstance(pos, (list, tuple, set)):
            for item in pos:
                _add(item)
        else:
            _add(pos)
    elif isinstance(all_pos_or_entry, (list, tuple, set)):
        for item in all_pos_or_entry:
            _add(item)
    else:
        _add(all_pos_or_entry)

    return labels


def _pos_atoms(pos_labels: Sequence[str]) -> List[str]:
    """Explode POS labels into normalized atoms (e.g. '[v1, vt]' -> ['v1','vt'])."""
    out: List[str] = []
    seen = set()
    for label in pos_labels:
        raw = str(label or "").strip()
        if not raw:
            continue
        candidates = [raw]
        cleaned = re.sub(r"[\[\]\(\)]", " ", raw)
        candidates.extend(re.split(r"[,\|/;]", cleaned))
        for part in candidates:
            atom = str(part or "").strip().lower()
            if not atom or atom in seen:
                continue
            seen.add(atom)
            out.append(atom)
    return out


def _infer_analyzer_pos(pos_labels: Sequence[str], lemma: str) -> Optional[str]:
    atoms = _pos_atoms(pos_labels)
    if lemma in {"だ", "です"}:
        return "copula"

    is_verb = False
    is_i_adj = False
    is_na_adj = False
    is_copula = False

    for atom in atoms:
        if atom.startswith(("v1", "v5", "vs", "vk", "vz")):
            is_verb = True
        if "verb" in atom or atom in {"aux-v", "aux", "auxiliary"} or "動詞" in atom:
            is_verb = True
        if (
            atom in {"adj-i", "i-adjective", "auxiliary adjective"}
            or (atom.startswith("adj") and "na" not in atom)
            or ("adjective" in atom and "na-adjective" not in atom and "adjectival noun" not in atom)
            or "shiku' adjective" in atom
            or "'ku' adjective" in atom
        ):
            is_i_adj = True
        if (
            atom in {"adj-na", "na-adjective"}
            or "adjectival noun" in atom
            or "形容動詞" in atom
            or "taru' adjective" in atom
            or "form of na-adjective" in atom
        ):
            is_na_adj = True
        if atom.startswith("cop") or "copula" in atom:
            is_copula = True

    if is_copula:
        return "copula"
    if is_verb:
        return "verb"
    if is_i_adj and not is_na_adj:
        return "i-adj"
    if is_na_adj:
        return "na-adj"
    if is_i_adj:
        return "i-adj"
    return None


def _infer_verb_classes(pos_labels: Sequence[str], lemma: str) -> List[str]:
    if lemma == "する":
        return ["suru"]
    if lemma in {"来る", "くる"}:
        return ["kuru"]

    atoms = _pos_atoms(pos_labels)
    out: List[str] = []

    def _add(label: str) -> None:
        if label not in out:
            out.append(label)

    for atom in atoms:
        if atom.startswith("vs") or "suru verb" in atom:
            _add("suru")
        if atom.startswith("vk") or "kuru verb" in atom:
            _add("kuru")
        if atom.startswith("v1") or "ichidan verb" in atom:
            _add("ichidan")
        if atom.startswith("v5") or "godan verb" in atom:
            _add("godan")

    return out


@lru_cache(maxsize=4096)
def _cached_analysis_json(
    surface: str,
    lemma: str,
    analyzer_pos: Optional[str],
    verb_class: Optional[str],
) -> str:
    out = _ANALYZER.analyze(
        surface=surface,
        lemma=lemma,
        pos=analyzer_pos,
        verb_class=verb_class,
    )
    return json.dumps([asdict(item) for item in out], ensure_ascii=False, separators=(",", ":"))


def deconjugate(surface_form: str, lemma: str, all_pos_or_entry: Any) -> Optional[Dict[str, Any]]:
    """Return grammar-popup conjugation payload, or None."""
    surface = str(surface_form or "").strip()
    base = str(lemma or "").strip()
    if not surface or not base:
        return None
    if surface == base:
        return None

    pos_labels = _extract_pos_labels(all_pos_or_entry)
    analyzer_pos = _infer_analyzer_pos(pos_labels, base)
    verb_classes = _infer_verb_classes(pos_labels, base)

    rows_with_class: List[Dict[str, Any]] = []
    class_by_row_id: Dict[int, Optional[str]] = {}

    def _collect_rows(payload: str, used_class: Optional[str]) -> None:
        if not payload:
            return
        try:
            rows = json.loads(payload)
        except Exception:
            return
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            rows_with_class.append(row)
            class_by_row_id[id(row)] = used_class

    if analyzer_pos == "verb" and verb_classes:
        for vc in verb_classes:
            _collect_rows(_cached_analysis_json(surface, base, analyzer_pos, vc), vc)
    else:
        default_class = verb_classes[0] if (analyzer_pos == "verb" and len(verb_classes) == 1) else None
        _collect_rows(_cached_analysis_json(surface, base, analyzer_pos, default_class), default_class)

    analyses: List[Dict[str, Any]] = []
    seen = set()
    for row in rows_with_class:
        if not isinstance(row, dict):
            continue
        chain = [
            str(tag or "").strip()
            for tag in list(row.get("derivation", []) or [])
            if str(tag or "").strip()
        ]
        if not chain:
            continue

        conjugation, auxiliaries = _split_derivation_chain(chain)
        category = str(row.get("category", "") or "").strip()
        description = str(row.get("description", "") or "").strip()
        features = row.get("features", {})
        used_verb_class = class_by_row_id.get(id(row))

        if analyzer_pos == "verb" and category and category != "verb":
            continue
        if analyzer_pos == "i-adj" and category and category != "i-adj":
            continue
        if analyzer_pos == "na-adj" and category and category != "na-adj":
            continue
        if analyzer_pos == "copula" and category and category != "copula":
            continue

        analysis_variant = ""
        if category == "verb" and used_verb_class:
            analysis_variant = str(used_verb_class)
        elif category:
            analysis_variant = category

        item = {
            "category": category,
            "analysis_variant": analysis_variant,
            "conjugation": conjugation,
            "conjugation_desc": description,
            "auxiliaries": auxiliaries,
            "auxiliary_info": [
                {"name": tag, "description": _TAG_DESCRIPTIONS.get(tag, "")}
                for tag in auxiliaries
            ],
            "result_forms": [surface],
            "derivation_chain": chain,
            "features": features if isinstance(features, dict) else {},
        }
        dedupe_key = (
            item["category"],
            item["analysis_variant"],
            item["conjugation"],
            tuple(item["auxiliaries"]),
            item["conjugation_desc"],
            tuple(sorted((item["features"] or {}).items())),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        analyses.append(item)

    if not analyses:
        return None

    first = analyses[0]
    out: Dict[str, Any] = {
        "conjugation": first.get("conjugation", ""),
        "conjugation_desc": first.get("conjugation_desc", ""),
        "auxiliaries": list(first.get("auxiliaries", []) or []),
        "auxiliary_info": list(first.get("auxiliary_info", []) or []),
        "result_forms": list(first.get("result_forms", []) or []),
        "analysis_count": len(analyses),
        "ambiguous": len(analyses) > 1,
        "analyses": analyses,
        "source": "jp_inflection_table_analyzer",
    }
    if analyzer_pos:
        out["analyzer_pos_hint"] = analyzer_pos
    if len(verb_classes) == 1:
        out["dict_verb_class"] = verb_classes[0]
    if pos_labels:
        out["pos_labels_used"] = list(pos_labels)
    if verb_classes:
        out["verb_classes_used"] = list(verb_classes)
    return out
