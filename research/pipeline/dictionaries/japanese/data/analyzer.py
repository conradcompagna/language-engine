#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Japanese token-level morphology analyzer (v2 ruleset).

This module is designed for an already-tokenized NLP pipeline where each token
already has:
- surface form
- lemma
- approximate POS

The analyzer explains why a token is written differently from its lemma using
the v2 CSV/JSON rules in this directory, then returns grammar-popup payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import csv
import json
import re

if __package__:
    from .rules import load_bundle
else:
    from rules import load_bundle


def _s(v: Any) -> str:
    return str(v or "").strip()


def _split_pipe_text(v: Any) -> List[str]:
    raw = _s(v)
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def _parse_features(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for piece in _split_pipe_text(raw):
        if "=" in piece:
            k, val = piece.split("=", 1)
            k = _s(k)
            val = _s(val)
            if k:
                out[k] = val
        else:
            out[piece] = "True"
    return out


def _humanize_code(raw: Any) -> str:
    text = _s(raw)
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return text[0].upper() + text[1:].lower()


@dataclass(frozen=True)
class Token:
    surface: str
    lemma: str
    pos: str


@dataclass(frozen=True)
class Analysis:
    surface: str
    lemma: str
    pos_major: str
    lemma_class: str
    source: str
    rule_id: str
    morph_slot: str
    reason_code: str
    orthography_rule_id: str
    orthography_desc: str
    register: str
    productivity: str
    requires_prev_state: str
    emits_state: str
    ambiguity_group: str
    canonical_form: str
    next_expected: str
    notes: str
    features: Dict[str, str]
    score: float


class JpInflectionAnalyzer:
    """
    Data-driven token morphology analyzer for jp_tokenized_pipeline_morphology_ruleset v2.

    Compatibility note:
    The constructor accepts legacy keyword args (kwpos_path/conj_path/etc.) so
    old call sites do not crash. They are ignored.
    """

    _GODAN_FROM_TAG = {
        "v5u": "V_GODAN_う",
        "v5k": "V_GODAN_く",
        "v5g": "V_GODAN_ぐ",
        "v5s": "V_GODAN_す",
        "v5t": "V_GODAN_つ",
        "v5n": "V_GODAN_ぬ",
        "v5b": "V_GODAN_ぶ",
        "v5m": "V_GODAN_む",
        "v5r": "V_GODAN_る",
        "v5k-s": "V_GODAN_く",
    }

    _KNOWN_AUX_CLASSES = {
        "ます": "AUX_MASU",
        "です": "AUX_DESU",
        "ない": "AUX_NAI",
        "た": "AUX_TA",
        "たり": "AUX_TARI",
        "て": "AUX_TE",
        "たい": "AUX_TAI",
        "たがる": "AUX_TAGARU",
        "れる": "AUX_RERU",
        "られる": "AUX_RARERU",
        "せる": "AUX_SERU",
        "させる": "AUX_SASERU",
        "ぬ": "AUX_NU",
        "ず": "AUX_ZU",
        "いる": "V_AUX_ICHIDAN_IRU",
        "ている": "AUX_CHAIN_TEIRU",
        "ておく": "AUX_CHAIN_TEOKU",
        "でおく": "AUX_CHAIN_DEOKU",
        "てしまう": "AUX_CHAIN_TESHIMAU",
        "でしまう": "AUX_CHAIN_DESHIMAU",
    }

    _KNOWN_PART_CLASSES = {
        "に": "PART_NI",
        "で": "PART_DE",
        "な": "PART_NA",
        "ば": "PART_BA",
        "て": "PART_TE",
    }

    def __init__(self, data_dir: str | Path | None = None, **_ignored: Any) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent

        self.dataset_name = "jp_tokenized_pipeline_morphology_ruleset_v2"
        self.dataset_version = ""

        self.token_rules: List[Dict[str, str]] = []
        self.allomorph_map: List[Dict[str, str]] = []
        self.ambiguity_rows: List[Dict[str, str]] = []
        self.orthography_rows: List[Dict[str, str]] = []
        self.alias_rows: List[Dict[str, str]] = []
        self.validation_rows: List[Dict[str, str]] = []

        self.orthography_by_id: Dict[str, Dict[str, str]] = {}
        self.validation_reason_by_rule: Dict[str, str] = {}
        self.alias_variant_to_canonical: Dict[str, str] = {}
        self.alias_canonical_to_variants: Dict[str, List[str]] = {}
        self.ambiguity_by_group_surface: Dict[Tuple[str, str], List[Dict[str, str]]] = {}

        self._load_rules()

    @staticmethod
    def _read_csv(path: Path) -> List[Dict[str, str]]:
        if not path.exists():
            return []
        out: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not isinstance(row, dict):
                    continue
                out.append({str(k or "").strip(): _s(v) for k, v in row.items()})
        return out

    def _load_rules(self) -> None:
        bundle_path = self.data_dir / "jp_tokenized_pipeline_morphology_ruleset_v2_bundle.json"
        rules_dir = self.data_dir / "rules"
        if (rules_dir / "manifest.json").exists() or bundle_path.exists():
            try:
                bundle = load_bundle(rules_dir) if (rules_dir / "manifest.json").exists() else json.loads(bundle_path.read_text(encoding="utf-8"))
            except Exception:
                bundle = {}
            meta = bundle.get("metadata", {}) if isinstance(bundle, dict) else {}
            if isinstance(meta, dict):
                self.dataset_name = _s(meta.get("dataset_name")) or self.dataset_name
                self.dataset_version = _s(meta.get("version"))
            self.token_rules = [dict(x) for x in list(bundle.get("token_morph_rules", []) or []) if isinstance(x, dict)]
            self.allomorph_map = [dict(x) for x in list(bundle.get("morpheme_allomorph_map", []) or []) if isinstance(x, dict)]
            self.ambiguity_rows = [dict(x) for x in list(bundle.get("ambiguity_resolution", []) or []) if isinstance(x, dict)]
            self.orthography_rows = [dict(x) for x in list(bundle.get("orthography_rules", []) or []) if isinstance(x, dict)]
            self.alias_rows = [dict(x) for x in list(bundle.get("normalization_aliases", []) or []) if isinstance(x, dict)]
            self.validation_rows = [dict(x) for x in list(bundle.get("validation_examples", []) or []) if isinstance(x, dict)]

        if not self.token_rules:
            self.token_rules = self._read_csv(self.data_dir / "jp_v2_token_morph_rules.csv")
        if not self.allomorph_map:
            self.allomorph_map = self._read_csv(self.data_dir / "jp_v2_morpheme_allomorph_map.csv")
        if not self.ambiguity_rows:
            self.ambiguity_rows = self._read_csv(self.data_dir / "jp_v2_ambiguity_resolution.csv")
        if not self.orthography_rows:
            self.orthography_rows = self._read_csv(self.data_dir / "jp_v2_orthography_rules.csv")
        if not self.alias_rows:
            self.alias_rows = self._read_csv(self.data_dir / "jp_v2_normalization_aliases.csv")
        if not self.validation_rows:
            self.validation_rows = self._read_csv(self.data_dir / "jp_v2_validation_examples.csv")

        self.orthography_by_id = {}
        for row in self.orthography_rows:
            rid = _s(row.get("orthography_rule_id"))
            if rid:
                self.orthography_by_id[rid] = row

        self.validation_reason_by_rule = {}
        for row in self.validation_rows:
            rid = _s(row.get("matched_rule_id"))
            why = _s(row.get("why_written_differently"))
            if rid and why:
                self.validation_reason_by_rule[rid] = why

        self.alias_variant_to_canonical = {}
        self.alias_canonical_to_variants = {}
        for row in self.alias_rows:
            variant = _s(row.get("variant"))
            canonical = _s(row.get("canonical"))
            if not variant or not canonical:
                continue
            self.alias_variant_to_canonical[variant] = canonical
            self.alias_canonical_to_variants.setdefault(canonical, [])
            if variant not in self.alias_canonical_to_variants[canonical]:
                self.alias_canonical_to_variants[canonical].append(variant)

        self.ambiguity_by_group_surface = {}
        for row in self.ambiguity_rows:
            group = _s(row.get("ambiguity_group"))
            surface = _s(row.get("surface"))
            if not group:
                continue
            key = (group, surface)
            self.ambiguity_by_group_surface.setdefault(key, []).append(row)

    def _expand_lemma_aliases(self, lemma: str) -> List[str]:
        seed = _s(lemma)
        if not seed:
            return []
        out: List[str] = []
        seen = set()
        queue = [seed]
        while queue:
            cur = _s(queue.pop(0))
            if not cur or cur in seen:
                continue
            seen.add(cur)
            out.append(cur)
            can = self.alias_variant_to_canonical.get(cur)
            if can and can not in seen:
                queue.append(can)
            for v in self.alias_canonical_to_variants.get(cur, []):
                if v not in seen:
                    queue.append(v)
        return out

    @staticmethod
    def _extract_pos_atoms(pos_labels: Sequence[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for label in pos_labels:
            raw = _s(label)
            if not raw:
                continue
            chunks = [raw]
            cleaned = re.sub(r"[\[\]\(\)]", " ", raw)
            chunks.extend(re.split(r"[,\|/;]", cleaned))
            for chunk in chunks:
                atom = _s(chunk).lower()
                if not atom or atom in seen:
                    continue
                seen.add(atom)
                out.append(atom)
        return out

    def _infer_pos_majors(self, lemma: str, pos_labels: Sequence[str]) -> List[str]:
        atoms = self._extract_pos_atoms(pos_labels)
        majors: List[str] = []
        seen = set()

        def add(x: str) -> None:
            y = _s(x).upper()
            if not y or y in seen:
                return
            seen.add(y)
            majors.append(y)

        for atom in atoms:
            if atom.startswith("v") or "verb" in atom:
                add("VERB")
            if atom.startswith("adj") or "adjective" in atom or "keiyou" in atom:
                add("ADJ")
            if atom.startswith("aux") or "auxiliary" in atom:
                add("AUX")
            if atom.startswith("cop") or "copula" in atom:
                add("COP")
            if atom in {"prt", "part", "particle", "adp"} or "particle" in atom:
                add("PART")

        lem = _s(lemma)
        if lem in {"だ", "では", "です"}:
            add("COP")
        if lem in self._KNOWN_AUX_CLASSES:
            add("AUX")
        if lem in self._KNOWN_PART_CLASSES:
            add("PART")
        if lem.endswith("する") or lem.endswith("くる") or lem.endswith("来る"):
            add("VERB")
        if lem.endswith("い"):
            add("ADJ")

        if not majors:
            add("VERB")
        return majors

    def _infer_lemma_classes(self, lemma_variants: Sequence[str], pos_labels: Sequence[str], pos_majors: Sequence[str]) -> List[str]:
        atoms = self._extract_pos_atoms(pos_labels)
        out: List[str] = []
        seen = set()

        def add(c: str) -> None:
            cls = _s(c)
            if not cls or cls in seen:
                return
            seen.add(cls)
            out.append(cls)

        # POS-tag-driven classes
        for atom in atoms:
            if atom in self._GODAN_FROM_TAG:
                add(self._GODAN_FROM_TAG[atom])
            if atom.startswith("v1"):
                add("V_ICHIDAN")
            if atom.startswith("vk"):
                add("V_IRR_KURU")
            if atom.startswith("vs") or atom == "vz":
                add("V_IRR_SURU")
            if atom == "adj-i" or atom == "aux-adj":
                add("A_I")
            if atom in {"adj-na", "adj-nari", "adj-t", "adj-f"}:
                add("A_NA")
            if atom in {"cop", "aux"}:
                add("COP_DA")

        # Lemma-driven classes
        for lem in lemma_variants:
            if not lem:
                continue

            if lem in self._KNOWN_AUX_CLASSES:
                add(self._KNOWN_AUX_CLASSES[lem])
            if lem in self._KNOWN_PART_CLASSES:
                add(self._KNOWN_PART_CLASSES[lem])

            if lem == "だ":
                add("COP_DA")
            if lem == "では":
                add("COPULA_DEWA")
            if lem in {"いい", "良い", "よい"}:
                add("A_I_SPECIAL_II")
                add("A_I")

            if lem.endswith("する") or lem == "する":
                add("V_IRR_SURU")
            if lem.endswith("くる") or lem.endswith("来る") or lem in {"くる", "来る"}:
                add("V_IRR_KURU")

            if "VERB" in pos_majors:
                if len(lem) >= 1:
                    last = lem[-1]
                    if last == "う":
                        add("V_GODAN_う")
                    elif last == "く":
                        add("V_GODAN_く")
                    elif last == "ぐ":
                        add("V_GODAN_ぐ")
                    elif last == "す":
                        add("V_GODAN_す")
                    elif last == "つ":
                        add("V_GODAN_つ")
                    elif last == "ぬ":
                        add("V_GODAN_ぬ")
                    elif last == "ぶ":
                        add("V_GODAN_ぶ")
                    elif last == "む":
                        add("V_GODAN_む")
                    elif last == "る":
                        add("V_ICHIDAN")
                        add("V_GODAN_る")

            if lem.endswith("い"):
                add("A_I")

        return out
    def _rule_lemma_matches(self, rule_lemma: str, lemma_candidate: str, pos_majors: Sequence[str], lemma_class: str) -> bool:
        rl = _s(rule_lemma)
        if not rl:
            return False
        if rl == lemma_candidate:
            return True

        if not (rl.startswith("<") and rl.endswith(">")):
            return False

        marker = rl.lower()
        if marker == "<lexical-verb>":
            return "VERB" in pos_majors or lemma_class.startswith("V_")
        if marker == "<i-adj>":
            return "ADJ" in pos_majors or lemma_class in {"A_I", "A_I_SPECIAL_II"}
        if marker == "<na-adj>":
            return "ADJ" in pos_majors or "COP" in pos_majors or lemma_class == "A_NA"
        return False

    @staticmethod
    def _lemma_stem(lemma: str, lemma_class: str) -> str:
        lem = _s(lemma)
        cls = _s(lemma_class)
        if not lem:
            return ""
        if cls.startswith("V_GODAN_"):
            return lem[:-1] if len(lem) > 1 else ""
        if cls in {"V_ICHIDAN", "V_AUX_ICHIDAN_IRU", "AUX_RERU", "AUX_RARERU", "AUX_SERU", "AUX_SASERU"}:
            return lem[:-1] if lem.endswith("る") else lem
        if cls in {"A_I", "A_I_SPECIAL_II"}:
            if lem in {"いい", "良い", "よい"}:
                return "よ"
            return lem[:-1] if lem.endswith("い") else lem
        if cls in {"A_NA", "COP_DA"}:
            return lem
        if lem.endswith("る") or lem.endswith("い"):
            return lem[:-1]
        return lem[:-1] if len(lem) > 1 else lem

    def _expand_surface_pattern(self, pattern: str, lemma: str, lemma_class: str) -> List[str]:
        pat = _s(pattern)
        if not pat:
            return []
        if "<" not in pat:
            return [pat]

        if pat == "<lemma>":
            return [_s(lemma)]
        if pat.startswith("<lemma+") and pat.endswith(">"):
            suffix = pat[len("<lemma+") : -1]
            return [_s(lemma) + suffix]
        if pat == "<stem>":
            return [self._lemma_stem(lemma, lemma_class)]
        if pat.startswith("<stem+") and pat.endswith(">"):
            suffix = pat[len("<stem+") : -1]
            return [self._lemma_stem(lemma, lemma_class) + suffix]

        # Special placeholder for いい/良い -> よ stem inflection series.
        if pat == "<stem=よ+...>":
            return []

        return []

    def _pattern_matches_surface(self, pattern: str, surface: str, lemma: str, lemma_class: str) -> bool:
        candidates = self._expand_surface_pattern(pattern, lemma, lemma_class)
        if candidates:
            return _s(surface) in candidates

        pat = _s(pattern)
        if pat == "<stem=よ+...>":
            lem = _s(lemma)
            srf = _s(surface)
            if lem not in {"いい", "良い", "よい"}:
                return False
            return bool(srf.startswith("よ") or srf.startswith("良"))
        return False

    @staticmethod
    def _compatible_major(rule_major: str, inferred_majors: Sequence[str]) -> bool:
        rm = _s(rule_major).upper()
        if not rm:
            return True
        majors = {_s(x).upper() for x in inferred_majors if _s(x)}
        if not majors:
            return True
        if rm in majors:
            return True
        if rm == "COP" and "AUX" in majors:
            return True
        if rm == "AUX" and "COP" in majors:
            return True
        return False

    def _base_score(
        self,
        source: str,
        rule_lemma: str,
        lemma_used: str,
        inferred_classes: Sequence[str],
        rule_class: str,
        pos_major: str,
        pos_majors: Sequence[str],
        productivity: str,
    ) -> float:
        score = 0.0
        if source == "allomorph_map":
            score += 35.0
        else:
            score += 20.0

        if _s(rule_lemma) == _s(lemma_used):
            score += 65.0
        elif _s(rule_lemma).startswith("<") and _s(rule_lemma).endswith(">"):
            score += 25.0
        else:
            score += 10.0

        if _s(rule_class) and _s(rule_class) in {_s(x) for x in inferred_classes}:
            score += 25.0
        if self._compatible_major(pos_major, pos_majors):
            score += 15.0

        prod = _s(productivity).lower()
        if "productive" in prod:
            score += 2.0
        elif "restricted" in prod:
            score -= 1.0

        return score

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def _eval_condition_atom(
        self,
        atom: str,
        lemma_variants: Sequence[str],
        pos_majors: Sequence[str],
        pos_labels: Sequence[str],
        match_row: Dict[str, str],
    ) -> bool:
        a = _s(atom)
        if not a:
            return True
        text = a.lower().strip()
        text = text.strip("()")

        m = re.search(r"lemma\s*!=\s*([^\s\)]+)", text)
        if m:
            rhs = _s(m.group(1))
            return rhs not in set(lemma_variants)

        m = re.search(r"lemma\s*=\s*([^\s\)]+)", text)
        if m:
            rhs = _s(m.group(1))
            return rhs in set(lemma_variants)

        m = re.search(r"pos\s*=\s*([A-Za-z]+)", text)
        if m:
            rhs = _s(m.group(1)).upper()
            return rhs in {_s(x).upper() for x in pos_majors}

        m = re.search(r"pos\s+in\s*\{([^\}]+)\}", text)
        if m:
            rhs_values = {_s(x).upper() for x in m.group(1).split(",")}
            majors = {_s(x).upper() for x in pos_majors}
            return bool(rhs_values & majors)

        m = re.search(r"register\s*=\s*([A-Za-z_]+)", text)
        if m:
            rhs = _s(m.group(1)).lower()
            return rhs in _s(match_row.get("register")).lower()

        if "xpos indicates copula" in text:
            labels = " ".join(_s(x).lower() for x in pos_labels)
            return ("cop" in labels) or ("copula" in labels) or ("adj-na" in labels)

        # Context-dependent checks unavailable in this interface.
        if "deprel" in text or "next_token" in text or "modifies following noun" in text or "sentence_final" in text:
            return False

        return False

    def _eval_condition(
        self,
        cond: str,
        lemma_variants: Sequence[str],
        pos_majors: Sequence[str],
        pos_labels: Sequence[str],
        match_row: Dict[str, str],
    ) -> bool:
        expr = _s(cond)
        if not expr:
            return True
        # OR has lower precedence than AND.
        or_chunks = [c.strip() for c in re.split(r"\s+OR\s+", expr, flags=re.IGNORECASE) if c.strip()]
        if not or_chunks:
            return True
        for chunk in or_chunks:
            and_atoms = [a.strip() for a in re.split(r"\s+AND\s+", chunk, flags=re.IGNORECASE) if a.strip()]
            if not and_atoms:
                continue
            ok = True
            for atom in and_atoms:
                if not self._eval_condition_atom(atom, lemma_variants, pos_majors, pos_labels, match_row):
                    ok = False
                    break
            if ok:
                return True
        return False

    def _ambiguity_adjust(
        self,
        match_row: Dict[str, str],
        surface: str,
        lemma_variants: Sequence[str],
        pos_majors: Sequence[str],
        pos_labels: Sequence[str],
    ) -> float:
        group = _s(match_row.get("ambiguity_group"))
        if not group:
            return 0.0

        key = (group, _s(surface))
        rows = list(self.ambiguity_by_group_surface.get(key, []))
        if not rows:
            # Some rows in CSV might omit the surface field; fallback by group.
            rows = [r for (g, _srf), group_rows in self.ambiguity_by_group_surface.items() if g == group for r in group_rows]
        if not rows:
            return 0.0

        this_id = _s(match_row.get("rule_id")) or _s(match_row.get("map_id"))
        best = 0.0
        competing_hit = False

        for row in rows:
            cond = _s(row.get("conditions"))
            if not self._eval_condition(cond, lemma_variants, pos_majors, pos_labels, match_row):
                continue
            prio = self._safe_int(row.get("priority"), default=50)
            preferred_id = _s(row.get("preferred_rule_id"))
            bonus = max(0.5, 10.0 - (float(prio) / 2.0))
            if preferred_id == this_id:
                if bonus > best:
                    best = bonus
            else:
                competing_hit = True

        if best > 0.0:
            return best
        if competing_hit:
            return -6.0
        return 0.0

    def _orthography_desc(self, rule_id: str) -> str:
        rid = _s(rule_id)
        if not rid:
            return ""
        row = self.orthography_by_id.get(rid)
        if not row:
            return ""
        return _humanize_code(row.get("description_code"))

    def _build_analysis_from_token_rule(
        self,
        row: Dict[str, str],
        lemma_used: str,
        surface: str,
        inferred_classes: Sequence[str],
        pos_majors: Sequence[str],
    ) -> Analysis:
        rid = _s(row.get("rule_id"))
        lemma_class = _s(row.get("lemma_class"))
        pos_major = _s(row.get("pos_major")).upper()
        return Analysis(
            surface=surface,
            lemma=lemma_used,
            pos_major=pos_major,
            lemma_class=lemma_class,
            source="token_morph_rules",
            rule_id=rid,
            morph_slot=_s(row.get("morph_slot")) or "FORM",
            reason_code=_s(row.get("reason_code")),
            orthography_rule_id=_s(row.get("orthography_rule_id")),
            orthography_desc=self._orthography_desc(_s(row.get("orthography_rule_id"))),
            register=_s(row.get("register")),
            productivity=_s(row.get("productivity")),
            requires_prev_state=_s(row.get("requires_prev_state")),
            emits_state=_s(row.get("emits_state")),
            ambiguity_group=_s(row.get("ambiguity_group")),
            canonical_form="",
            next_expected=_s(row.get("emits_state")),
            notes=_s(row.get("notes")),
            features=_parse_features(row.get("morph_features")),
            score=self._base_score(
                source="token_rules",
                rule_lemma=_s(row.get("lemma")),
                lemma_used=lemma_used,
                inferred_classes=inferred_classes,
                rule_class=lemma_class,
                pos_major=pos_major,
                pos_majors=pos_majors,
                productivity=_s(row.get("productivity")),
            ),
        )

    def _build_analysis_from_allomorph_row(
        self,
        row: Dict[str, str],
        lemma_used: str,
        surface: str,
        inferred_classes: Sequence[str],
        pos_majors: Sequence[str],
    ) -> Analysis:
        rid = _s(row.get("map_id"))
        lemma_class = _s(row.get("lemma_class"))
        pos_major = _s(row.get("pos_major")).upper()
        return Analysis(
            surface=surface,
            lemma=lemma_used,
            pos_major=pos_major,
            lemma_class=lemma_class,
            source="allomorph_map",
            rule_id=rid,
            morph_slot=_s(row.get("form_type")) or "FORM",
            reason_code=_s(row.get("why_code")),
            orthography_rule_id=_s(row.get("orthography_rule_id")),
            orthography_desc=self._orthography_desc(_s(row.get("orthography_rule_id"))),
            register=_s(row.get("register")),
            productivity=_s(row.get("productivity")),
            requires_prev_state=_s(row.get("prev_required")),
            emits_state=_s(row.get("next_expected")),
            ambiguity_group="",
            canonical_form=_s(row.get("canonical_form")),
            next_expected=_s(row.get("next_expected")),
            notes=_s(row.get("examples")),
            features={},
            score=self._base_score(
                source="allomorph_map",
                rule_lemma=_s(row.get("lemma")),
                lemma_used=lemma_used,
                inferred_classes=inferred_classes,
                rule_class=lemma_class,
                pos_major=pos_major,
                pos_majors=pos_majors,
                productivity=_s(row.get("productivity")),
            ),
        )
    def analyze(self, surface: str, lemma: str, pos_labels: Sequence[str]) -> List[Analysis]:
        srf = _s(surface)
        lem = _s(lemma)
        if not srf or not lem:
            return []

        lemma_variants = self._expand_lemma_aliases(lem)
        if not lemma_variants:
            lemma_variants = [lem]

        pos_majors = self._infer_pos_majors(lem, pos_labels)
        inferred_classes = self._infer_lemma_classes(lemma_variants, pos_labels, pos_majors)
        if not inferred_classes:
            return []

        raw_matches: List[Analysis] = []

        # Token rules
        for row in self.token_rules:
            rule_class = _s(row.get("lemma_class"))
            rule_pos_major = _s(row.get("pos_major")).upper()
            if rule_class and rule_class not in set(inferred_classes):
                continue
            if not self._compatible_major(rule_pos_major, pos_majors):
                continue

            rule_lemma = _s(row.get("lemma"))
            surface_pattern = _s(row.get("surface"))
            matched_lemma: Optional[str] = None
            for lv in lemma_variants:
                if self._rule_lemma_matches(rule_lemma, lv, pos_majors, rule_class):
                    if self._pattern_matches_surface(surface_pattern, srf, lv, rule_class):
                        matched_lemma = lv
                        break
            if not matched_lemma:
                continue

            match = self._build_analysis_from_token_rule(row, matched_lemma, srf, inferred_classes, pos_majors)
            boost = self._ambiguity_adjust(row, srf, lemma_variants, pos_majors, pos_labels)
            match = Analysis(**{**match.__dict__, "score": match.score + boost})
            raw_matches.append(match)

        # Allomorph map
        for row in self.allomorph_map:
            rule_class = _s(row.get("lemma_class"))
            rule_pos_major = _s(row.get("pos_major")).upper()
            if rule_class and rule_class not in set(inferred_classes):
                continue
            if not self._compatible_major(rule_pos_major, pos_majors):
                continue

            rule_lemma = _s(row.get("lemma"))
            surface_pattern = _s(row.get("surface"))
            matched_lemma = None
            for lv in lemma_variants:
                if self._rule_lemma_matches(rule_lemma, lv, pos_majors, rule_class):
                    if self._pattern_matches_surface(surface_pattern, srf, lv, rule_class):
                        matched_lemma = lv
                        break
            if not matched_lemma:
                continue

            match = self._build_analysis_from_allomorph_row(row, matched_lemma, srf, inferred_classes, pos_majors)
            raw_matches.append(match)

        if not raw_matches:
            return []

        # De-duplicate near-identical analyses; keep the highest-scored one.
        best_by_key: Dict[Tuple[str, str, str, str, str, str], Analysis] = {}
        for item in raw_matches:
            key = (
                _s(item.lemma_class),
                _s(item.morph_slot),
                _s(item.reason_code),
                _s(item.requires_prev_state),
                _s(item.emits_state),
                _s(item.canonical_form),
            )
            prev = best_by_key.get(key)
            if prev is None or item.score > prev.score:
                best_by_key[key] = item

        out = list(best_by_key.values())
        out.sort(key=lambda x: (-float(x.score), _s(x.source), _s(x.rule_id)))
        return out

    def analyze_token(self, token: Token) -> List[Analysis]:
        # token.pos is treated as a single POS hint label.
        labels = [_s(token.pos)] if _s(token.pos) else []
        return self.analyze(token.surface, token.lemma, labels)

    def analyze_tokens(self, tokens: Iterable[Token]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tok in tokens:
            rows = self.analyze_token(tok)
            out.append(
                {
                    "surface": _s(tok.surface),
                    "lemma": _s(tok.lemma),
                    "pos": _s(tok.pos),
                    "analysis_count": len(rows),
                    "rows": [r.__dict__ for r in rows],
                }
            )
        return out

    # Legacy compatibility shim for old debug code that still references this.
    def _infer_root(self, lemma: str, _pos_code: str = "", _rule: Optional[Dict[str, Any]] = None) -> str:
        lem = _s(lemma)
        if not lem:
            return ""
        if lem.endswith("する") or lem.endswith("くる") or lem.endswith("来る"):
            return lem[:-2]
        if lem.endswith("る") or lem.endswith("い"):
            return lem[:-1]
        return lem[:-1] if len(lem) > 1 else lem


_ANALYZER_SINGLETON: Optional[JpInflectionAnalyzer] = None


def _get_analyzer() -> JpInflectionAnalyzer:
    global _ANALYZER_SINGLETON
    if _ANALYZER_SINGLETON is None:
        _ANALYZER_SINGLETON = JpInflectionAnalyzer()
    return _ANALYZER_SINGLETON


def _extract_pos_labels(all_pos_or_entry: Any) -> List[str]:
    labels: List[str] = []
    seen = set()

    def add(raw: Any) -> None:
        text = _s(raw)
        if not text or text in seen:
            return
        seen.add(text)
        labels.append(text)

    if isinstance(all_pos_or_entry, dict):
        all_pos = all_pos_or_entry.get("all_pos", [])
        pos = all_pos_or_entry.get("pos", "")
        if isinstance(all_pos, (list, tuple, set)):
            for x in all_pos:
                add(x)
        else:
            add(all_pos)
        if isinstance(pos, (list, tuple, set)):
            for x in pos:
                add(x)
        else:
            add(pos)
    elif isinstance(all_pos_or_entry, (list, tuple, set)):
        for x in all_pos_or_entry:
            add(x)
    else:
        add(all_pos_or_entry)

    return labels


def _analysis_sort_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        -float(item.get("_score", 0.0)),
        _s(item.get("analysis_variant")),
        _s(item.get("conjugation")),
        _s(item.get("rule_id")),
    )


def _analysis_desc(analyzer: JpInflectionAnalyzer, row: Analysis) -> str:
    why = _s(analyzer.validation_reason_by_rule.get(_s(row.rule_id)))
    if why:
        return why
    if _s(row.reason_code):
        return _humanize_code(row.reason_code)
    return _humanize_code(row.morph_slot) or "Morphological form"


_FORM_LABELS: Dict[str, str] = {
    "ADNOMINAL": "Attributive Form",
    "ADVERBIAL": "Adverbial Form",
    "ATTRIBUTIVE": "Attributive Form",
    "CONDITIONAL": "Conditional Form",
    "CONDITIONAL_PART": "Conditional Form",
    "CONNECTIVE": "Connective Form",
    "CONNECTIVE_ALLOMORPH": "Connective Form",
    "FINITE": "Base Form",
    "FINITE_ALLOMORPH": "Base Form",
    "FINITE_COLLOQ": "Colloquial Base Form",
    "IMPERATIVE": "Imperative Form",
    "INFLECTED_NONFINAL": "Non-final Form",
    "KATEI": "Conditional Form",
    "MIZEN": "Pre-auxiliary Stem",
    "NEGATIVE": "Negative Form",
    "ONBIN": "Sound-change Stem",
    "PARTICLE": "Particle Form",
    "PAST": "Past Form",
    "POLITE_PREP": "Polite Stem",
    "PREDICATIVE": "Predicative Form",
    "RENYO": "Adverbial Form",
    "RENYO_BEFORE_TA": "Past-linking Stem",
    "STEM": "Stem Form",
    "TE_CONNECTIVE": "Te Connective Form",
    "VOLITIONAL": "Volitional Form",
    "VOLITIONAL_BASE": "Volitional Form",
}

_FORM_GLOSSES: Dict[str, str] = {
    "ADNOMINAL": "Used before nouns.",
    "ADVERBIAL": "Links to following predicate or auxiliary.",
    "ATTRIBUTIVE": "Used before nouns.",
    "CONDITIONAL": "Shows if-condition meaning.",
    "CONDITIONAL_PART": "Shows if-condition meaning.",
    "CONNECTIVE": "Connects this clause to next clause.",
    "CONNECTIVE_ALLOMORPH": "Connects this clause to next clause.",
    "FINITE": "Normal clause-ending form.",
    "FINITE_ALLOMORPH": "Normal clause-ending form.",
    "FINITE_COLLOQ": "Colloquial clause-ending form.",
    "IMPERATIVE": "Command form.",
    "INFLECTED_NONFINAL": "Inflected form requiring continuation.",
    "KATEI": "Shows if-condition meaning.",
    "MIZEN": "Stem used before auxiliaries.",
    "NEGATIVE": "Negative form.",
    "ONBIN": "Sound-change stem before endings.",
    "PARTICLE": "Particle role in syntax.",
    "PAST": "Past-tense form.",
    "POLITE_PREP": "Stem preparing polite forms.",
    "PREDICATIVE": "Predicate-position form.",
    "RENYO": "Links to auxiliaries or predicates.",
    "RENYO_BEFORE_TA": "Stem linking to past endings.",
    "STEM": "Stem for further inflection.",
    "TE_CONNECTIVE": "Te-linking connective form.",
    "VOLITIONAL": "Shows intention or suggestion.",
    "VOLITIONAL_BASE": "Shows intention or suggestion.",
}

_STATE_TEXT: Dict[str, str] = {
    "AUX": "an auxiliary",
    "AUX_CHAIN": "an auxiliary chain",
    "AUX_MIZEN": "an auxiliary mizen stem",
    "AUX_RENYO": "an auxiliary renyo stem",
    "A_NA_STEM": "a na-adjective stem",
    "COPULA_SLOT": "a copula form",
    "END": "sentence end",
    "END_OR_CHAIN": "sentence end or an auxiliary chain",
    "FINITE": "a finite form",
    "NEG_SLOT": "a negative form",
    "NOUN": "a noun",
    "POLITE_SLOT": "a polite form",
    "SENTENCE_END": "sentence end",
    "TE_CHAIN": "a te-chain sequence",
    "VERB": "a verb",
    "VERB_MIZEN": "a verb mizen stem",
    "VERB_RENYO": "a verb renyo stem",
    "V_ONBIN_T": "an onbin stem for te/ta endings",
    "V_RENYO": "a renyo stem",
}


_MAX_TAG_WORDS = 10


def _limit_words(text: str, max_words: int = _MAX_TAG_WORDS) -> str:
    raw = _s(text)
    if not raw:
        return ""
    words = raw.split()
    if len(words) <= max_words:
        return raw
    return " ".join(words[:max_words])


def _simple_variant_label(lemma_class: str, pos_major: str) -> str:
    cls = _s(lemma_class)
    pm = _s(pos_major).upper()

    if cls == "A_I" or cls.startswith("A_I_"):
        return "i-adjective"
    if cls == "A_NA":
        return "na-adjective"
    if cls == "COP_DA" or cls.startswith("COPULA"):
        return "copula"
    if cls.startswith("V_GODAN_"):
        return "godan verb"
    if cls == "V_ICHIDAN" or cls.startswith("V_AUX_ICHIDAN"):
        return "ichidan verb"
    if cls == "V_IRR_SURU":
        return "suru verb"
    if cls == "V_IRR_KURU":
        return "kuru verb"
    if cls.startswith("AUX_CHAIN"):
        return "auxiliary chain"
    if cls.startswith("AUX_"):
        return "auxiliary"
    if cls.startswith("PART_"):
        return "particle"

    if pm == "VERB":
        return "verb"
    if pm == "ADJ":
        return "adjective"
    if pm == "AUX":
        return "auxiliary"
    if pm == "COP":
        return "copula"
    if pm == "PART":
        return "particle"
    return "word"


def _simple_form_label(morph_slot: str) -> str:
    slot = _s(morph_slot).upper()
    if not slot:
        return "Form"
    return _FORM_LABELS.get(slot, _humanize_code(slot) or "Form")


def _simple_form_explanation(morph_slot: str) -> str:
    slot = _s(morph_slot).upper()
    core = _FORM_GLOSSES.get(slot, "Grammar inflection form.")
    return _limit_words(core)


def _simple_orthography_note(raw: str) -> str:
    text = _s(raw).rstrip(".")
    if not text:
        return ""
    return _limit_words(f"Spelling: {text}")


def _human_state_expr(raw_state: str) -> str:
    parts: List[str] = []
    for piece in _split_pipe_text(raw_state):
        token = _s(piece).upper()
        if not token:
            continue
        if token in {"NONE", "ANY"}:
            continue
        if token in _STATE_TEXT:
            parts.append(_STATE_TEXT[token])
            continue
        if token.startswith("EXPECTS_"):
            token = token[len("EXPECTS_") :]
        fallback = _humanize_code(token).lower()
        if fallback:
            parts.append(fallback)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} or {parts[1]}"
    return ", ".join(parts[:-1]) + f", or {parts[-1]}"


def _context_hint(prev_state: str, next_state: str) -> str:
    prev_text = _s(prev_state)
    next_text = _s(next_state)
    if prev_text.upper() in {"", "NONE", "ANY"}:
        prev_text = ""
    if next_text.upper() in {"", "NONE", "ANY"}:
        next_text = ""
    if prev_text and next_text:
        return _limit_words(f"Context: prev={prev_text} next={next_text}")
    if prev_text:
        return _limit_words(f"Context: prev={prev_text}")
    if next_text:
        return _limit_words(f"Context: next={next_text}")
    return ""

def deconjugate(surface_form: str, lemma: str, all_pos_or_entry: Any) -> Optional[Dict[str, Any]]:
    """
    Return grammar-popup CONJ payload for a token or None.

    Designed for tokenized pipelines where `surface != lemma` generally means
    a meaningful allomorphic/morphological alternation to explain.
    """
    surface = _s(surface_form)
    base = _s(lemma)
    if not surface or not base:
        return None
    if surface == base:
        return None

    analyzer = _get_analyzer()
    pos_labels = _extract_pos_labels(all_pos_or_entry)
    rows = analyzer.analyze(surface, base, pos_labels)
    if not rows:
        return None

    merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        label = _simple_form_label(_s(row.morph_slot))
        desc = _simple_form_explanation(_s(row.morph_slot))
        key = (label, desc)

        item = merged.get(key)
        if item is None:
            item = {
                "conjugation": label,
                "conjugation_desc": desc,
                "_score": float(row.score),
            }
            merged[key] = item
        else:
            item["_score"] = max(float(item.get("_score", 0.0)), float(row.score))

    converted = list(merged.values())
    if not converted:
        return None

    converted.sort(
        key=lambda item: (
            -float(item.get("_score", 0.0)),
            _s(item.get("conjugation")),
        )
    )

    for c in converted:
        c.pop("_score", None)

    first = converted[0]
    is_ambiguous = len(converted) > 1

    return {
        "conjugation": first.get("conjugation", ""),
        "conjugation_desc": first.get("conjugation_desc", ""),
        "analysis_count": len(converted),
        "ambiguous": is_ambiguous,
        "analyses": converted,
    }


if __name__ == "__main__":
    ana = JpInflectionAnalyzer()
    samples = [
        ("に", "だ", ["cop"]),
        ("さ", "する", ["vs-s"]),
        ("れ", "れる", ["v1", "aux-v"]),
        ("て", "て", ["prt"]),
        ("い", "いる", ["aux-v", "v1"]),
        ("た", "た", ["aux-v"]),
    ]
    for surface, lemma, pos in samples:
        print(surface, lemma, deconjugate(surface, lemma, pos))
