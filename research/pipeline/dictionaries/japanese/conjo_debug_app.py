#!/usr/bin/env python3
"""
Standalone morphology debug app for the v2 Japanese analyzer data.

Purpose:
- Run on a different port than the main app.
- Surface lookup: show every rule row that could match a surface form with
  no lemma/POS constraints.
- Optional scoring context: add lemma/POS hints to see score breakdowns.
- Lemma explorer: generate possible surfaces from a lemma and show scoring.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request


def _s(value: Any) -> str:
    return str(value or "").strip()


def _split_pos_query(raw: str) -> List[str]:
    text = _s(raw)
    if not text:
        return []
    out: List[str] = []
    seen = set()
    for part in re.split(r"[,\|/;]", text):
        item = _s(part)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


try:
    # Works when launched from repository root.
    from japanese.data.analyzer import JpInflectionAnalyzer
except ModuleNotFoundError:
    # Works when launched from inside the japanese/ directory.
    HERE = Path(__file__).resolve().parent
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from data.analyzer import JpInflectionAnalyzer


class MorphRuleDebugIndex:
    def __init__(self) -> None:
        self.analyzer = JpInflectionAnalyzer()
        self.rows: List[Dict[str, Any]] = []
        self._build_index()

    def _build_index(self) -> None:
        idx = 0
        for row in self.analyzer.token_rules:
            idx += 1
            self.rows.append(
                {
                    "source_kind": "token_morph_rules",
                    "source_for_score": "token_rules",
                    "source_index": idx,
                    "rule_id": _s(row.get("rule_id")),
                    "lemma": _s(row.get("lemma")),
                    "pos_major": _s(row.get("pos_major")).upper(),
                    "pos_detail": _s(row.get("pos_detail")),
                    "lemma_class": _s(row.get("lemma_class")),
                    "surface_pattern": _s(row.get("surface")),
                    "form_name": _s(row.get("morph_slot")),
                    "reason_code": _s(row.get("reason_code")),
                    "orthography_rule_id": _s(row.get("orthography_rule_id")),
                    "register": _s(row.get("register")),
                    "productivity": _s(row.get("productivity")),
                    "ambiguity_group": _s(row.get("ambiguity_group")),
                    "requires_prev_state": _s(row.get("requires_prev_state")),
                    "emits_state": _s(row.get("emits_state")),
                    "notes": _s(row.get("notes")),
                    "raw_row": dict(row),
                }
            )

        for row in self.analyzer.allomorph_map:
            idx += 1
            self.rows.append(
                {
                    "source_kind": "morpheme_allomorph_map",
                    "source_for_score": "allomorph_map",
                    "source_index": idx,
                    "rule_id": _s(row.get("map_id")),
                    "lemma": _s(row.get("lemma")),
                    "pos_major": _s(row.get("pos_major")).upper(),
                    "pos_detail": "",
                    "lemma_class": _s(row.get("lemma_class")),
                    "surface_pattern": _s(row.get("surface")),
                    "form_name": _s(row.get("form_type")),
                    "reason_code": _s(row.get("why_code")),
                    "orthography_rule_id": _s(row.get("orthography_rule_id")),
                    "register": _s(row.get("register")),
                    "productivity": _s(row.get("productivity")),
                    "ambiguity_group": "",
                    "requires_prev_state": _s(row.get("prev_required")),
                    "emits_state": _s(row.get("next_expected")),
                    "notes": _s(row.get("examples")),
                    "raw_row": dict(row),
                }
            )

    @staticmethod
    def _extract_suffix_pattern(pattern: str, marker: str) -> Optional[str]:
        open_tag = f"<{marker}+"
        if pattern.startswith(open_tag) and pattern.endswith(">"):
            return pattern[len(open_tag) : -1]
        return None

    @staticmethod
    def _extract_stem_prefix_pattern(pattern: str) -> Optional[str]:
        match = re.match(r"^<stem=(.+)\+\.\.\.>$", pattern)
        if not match:
            return None
        return _s(match.group(1))

    def _match_surface_unconstrained(self, pattern: str, surface: str) -> Optional[Dict[str, str]]:
        pat = _s(pattern)
        srf = _s(surface)
        if not pat or not srf:
            return None

        if "<" not in pat:
            if srf != pat:
                return None
            return {"match_type": "literal_exact", "matched_tail": pat, "root_fragment": ""}

        if pat in {"<stem>", "<lemma>"}:
            return {"match_type": "placeholder_wildcard", "matched_tail": "", "root_fragment": srf}

        stem_suffix = self._extract_suffix_pattern(pat, "stem")
        if stem_suffix is not None:
            if stem_suffix == "":
                return {"match_type": "stem_suffix_empty", "matched_tail": "", "root_fragment": srf}
            if srf.endswith(stem_suffix):
                return {
                    "match_type": "stem_suffix",
                    "matched_tail": stem_suffix,
                    "root_fragment": srf[: len(srf) - len(stem_suffix)],
                }
            return None

        lemma_suffix = self._extract_suffix_pattern(pat, "lemma")
        if lemma_suffix is not None:
            if lemma_suffix == "":
                return {"match_type": "lemma_suffix_empty", "matched_tail": "", "root_fragment": srf}
            if srf.endswith(lemma_suffix):
                return {
                    "match_type": "lemma_suffix",
                    "matched_tail": lemma_suffix,
                    "root_fragment": srf[: len(srf) - len(lemma_suffix)],
                }
            return None

        stem_prefix = self._extract_stem_prefix_pattern(pat)
        if stem_prefix is not None:
            if srf.startswith(stem_prefix):
                return {
                    "match_type": "stem_prefix_series",
                    "matched_tail": "",
                    "root_fragment": srf[len(stem_prefix) :],
                }
            return None

        # Unknown placeholder: keep visible as a possible wildcard row.
        return {"match_type": "placeholder_unknown", "matched_tail": "", "root_fragment": srf}

    def _build_context(self, lemma: str, pos_query: str) -> Optional[Dict[str, Any]]:
        base = _s(lemma)
        if not base:
            return None
        pos_labels = _split_pos_query(pos_query)
        lemma_variants = self.analyzer._expand_lemma_aliases(base) or [base]
        pos_majors = self.analyzer._infer_pos_majors(base, pos_labels)
        inferred_classes = self.analyzer._infer_lemma_classes(lemma_variants, pos_labels, pos_majors)
        return {
            "lemma": base,
            "pos_labels": pos_labels,
            "lemma_variants": lemma_variants,
            "pos_majors": pos_majors,
            "inferred_classes": inferred_classes,
            "inferred_class_set": set(inferred_classes),
        }

    def _row_matches_context(self, row: Dict[str, Any], surface: str, ctx: Dict[str, Any]) -> Optional[str]:
        rule_class = _s(row.get("lemma_class"))
        if rule_class and rule_class not in ctx["inferred_class_set"]:
            return None

        rule_pos_major = _s(row.get("pos_major")).upper()
        if not self.analyzer._compatible_major(rule_pos_major, ctx["pos_majors"]):
            return None

        rule_lemma = _s(row.get("lemma"))
        surface_pattern = _s(row.get("surface_pattern"))
        for lemma_variant in ctx["lemma_variants"]:
            if not self.analyzer._rule_lemma_matches(rule_lemma, lemma_variant, ctx["pos_majors"], rule_class):
                continue
            if self.analyzer._pattern_matches_surface(surface_pattern, _s(surface), lemma_variant, rule_class):
                return lemma_variant
        return None

    def _ambiguity_trace(
        self,
        row: Dict[str, Any],
        surface: str,
        ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_row = row.get("raw_row") if isinstance(row.get("raw_row"), dict) else {}
        group = _s(raw_row.get("ambiguity_group"))
        if not group:
            return {"group": "", "adjust": 0.0, "hits": []}

        key = (group, _s(surface))
        candidates = list(self.analyzer.ambiguity_by_group_surface.get(key, []))
        if not candidates:
            candidates = [
                item
                for (agg_group, _surface_key), bucket in self.analyzer.ambiguity_by_group_surface.items()
                if agg_group == group
                for item in bucket
            ]

        this_id = _s(raw_row.get("rule_id")) or _s(raw_row.get("map_id")) or _s(row.get("rule_id"))
        hits: List[Dict[str, Any]] = []
        best_bonus = 0.0
        competing_hit = False

        for candidate in candidates:
            cond = _s(candidate.get("conditions"))
            cond_ok = self.analyzer._eval_condition(
                cond,
                ctx["lemma_variants"],
                ctx["pos_majors"],
                ctx["pos_labels"],
                raw_row,
            )
            if not cond_ok:
                continue
            prio = self.analyzer._safe_int(candidate.get("priority"), default=50)
            preferred_id = _s(candidate.get("preferred_rule_id"))
            bonus = max(0.5, 10.0 - (float(prio) / 2.0))
            is_preferred = preferred_id == this_id
            if is_preferred:
                if bonus > best_bonus:
                    best_bonus = bonus
            else:
                competing_hit = True
            hits.append(
                {
                    "preferred_rule_id": preferred_id,
                    "conditions": cond,
                    "priority": prio,
                    "bonus_formula_value": bonus,
                    "is_preferred_for_this_row": is_preferred,
                    "resolution_code": _s(candidate.get("resolution_code")),
                }
            )

        adjust = 0.0
        if best_bonus > 0.0:
            adjust = best_bonus
        elif competing_hit:
            adjust = -6.0

        return {"group": group, "adjust": adjust, "hits": hits}

    def _score_row(self, row: Dict[str, Any], surface: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        matched_lemma = self._row_matches_context(row, surface, ctx)
        if not matched_lemma:
            return {"context_match": False}

        base_score = self.analyzer._base_score(
            source=_s(row.get("source_for_score")),
            rule_lemma=_s(row.get("lemma")),
            lemma_used=matched_lemma,
            inferred_classes=ctx["inferred_classes"],
            rule_class=_s(row.get("lemma_class")),
            pos_major=_s(row.get("pos_major")),
            pos_majors=ctx["pos_majors"],
            productivity=_s(row.get("productivity")),
        )
        ambiguity = self._ambiguity_trace(row, surface, ctx)
        final_score = float(base_score) + float(ambiguity["adjust"])
        return {
            "context_match": True,
            "matched_lemma_variant": matched_lemma,
            "base_score": float(base_score),
            "ambiguity_adjust": float(ambiguity["adjust"]),
            "final_score": float(final_score),
            "ambiguity_group": _s(ambiguity.get("group")),
            "ambiguity_hits": list(ambiguity.get("hits", [])),
        }

    def _expand_surface_pattern_for_lemma(self, pattern: str, lemma_value: str, lemma_class: str) -> List[str]:
        pat = _s(pattern)
        lemma_clean = _s(lemma_value)
        if not pat or not lemma_clean:
            return []

        expanded = self.analyzer._expand_surface_pattern(pat, lemma_clean, lemma_class)
        if expanded:
            return [_s(x) for x in expanded if _s(x)]

        if "<" not in pat:
            return [pat]

        if pat == "<stem>":
            return [self.analyzer._lemma_stem(lemma_clean, lemma_class)]
        if pat == "<lemma>":
            return [lemma_clean]

        stem_suffix = self._extract_suffix_pattern(pat, "stem")
        if stem_suffix is not None:
            return [self.analyzer._lemma_stem(lemma_clean, lemma_class) + stem_suffix]

        lemma_suffix = self._extract_suffix_pattern(pat, "lemma")
        if lemma_suffix is not None:
            return [lemma_clean + lemma_suffix]

        stem_prefix = self._extract_stem_prefix_pattern(pat)
        if stem_prefix is not None:
            return [f"{stem_prefix}..."]

        return []

    def lookup_surface(self, surface: str, lemma: str = "", pos_query: str = "") -> Dict[str, Any]:
        srf = _s(surface)
        if not srf:
            return {"ok": False, "error": "missing surface"}

        ctx = self._build_context(lemma, pos_query) if _s(lemma) else None
        matches: List[Dict[str, Any]] = []
        context_match_count = 0

        for row in self.rows:
            meta = self._match_surface_unconstrained(_s(row.get("surface_pattern")), srf)
            if meta is None:
                continue
            out = dict(row)
            out.update(meta)
            if ctx is not None:
                score = self._score_row(row, srf, ctx)
                out["score"] = score
                if score.get("context_match"):
                    context_match_count += 1
            matches.append(out)

        if ctx is not None:
            matches.sort(
                key=lambda item: (
                    0 if bool(item.get("score", {}).get("context_match")) else 1,
                    -float(item.get("score", {}).get("final_score", -999999.0)),
                    -len(_s(item.get("matched_tail"))),
                    _s(item.get("source_kind")),
                    _s(item.get("rule_id")),
                    int(item.get("source_index", 0) or 0),
                )
            )
        else:
            matches.sort(
                key=lambda item: (
                    -len(_s(item.get("matched_tail"))),
                    _s(item.get("source_kind")),
                    _s(item.get("rule_id")),
                    int(item.get("source_index", 0) or 0),
                )
            )

        return {
            "ok": True,
            "surface": srf,
            "total_rules": len(self.rows),
            "match_count": len(matches),
            "context_match_count": context_match_count,
            "scoring_context": {
                "enabled": bool(ctx),
                "lemma": _s((ctx or {}).get("lemma")),
                "pos_labels": list((ctx or {}).get("pos_labels", [])),
                "pos_majors": list((ctx or {}).get("pos_majors", [])),
                "inferred_classes": list((ctx or {}).get("inferred_classes", [])),
            },
            "matches": matches,
        }

    def lookup_lemma(self, lemma: str, pos_query: str = "") -> Dict[str, Any]:
        base = _s(lemma)
        if not base:
            return {"ok": False, "error": "missing lemma"}

        ctx = self._build_context(base, pos_query)
        if ctx is None:
            return {"ok": False, "error": "failed to build scoring context"}

        matches: List[Dict[str, Any]] = []
        seen = set()

        for row in self.rows:
            rule_class = _s(row.get("lemma_class"))
            if rule_class and rule_class not in ctx["inferred_class_set"]:
                continue
            rule_pos_major = _s(row.get("pos_major")).upper()
            if not self.analyzer._compatible_major(rule_pos_major, ctx["pos_majors"]):
                continue

            rule_lemma = _s(row.get("lemma"))
            for lemma_variant in ctx["lemma_variants"]:
                if not self.analyzer._rule_lemma_matches(rule_lemma, lemma_variant, ctx["pos_majors"], rule_class):
                    continue
                generated = self._expand_surface_pattern_for_lemma(
                    _s(row.get("surface_pattern")),
                    lemma_variant,
                    rule_class,
                )
                if not generated:
                    continue
                for generated_surface in generated:
                    key = (_s(row.get("source_kind")), _s(row.get("rule_id")), lemma_variant, generated_surface)
                    if key in seen:
                        continue
                    seen.add(key)
                    out = dict(row)
                    out["lemma"] = lemma_variant
                    out["generated_surface"] = generated_surface

                    if "..." in generated_surface:
                        base_score = self.analyzer._base_score(
                            source=_s(row.get("source_for_score")),
                            rule_lemma=_s(row.get("lemma")),
                            lemma_used=lemma_variant,
                            inferred_classes=ctx["inferred_classes"],
                            rule_class=rule_class,
                            pos_major=_s(row.get("pos_major")),
                            pos_majors=ctx["pos_majors"],
                            productivity=_s(row.get("productivity")),
                        )
                        out["score"] = {
                            "context_match": True,
                            "matched_lemma_variant": lemma_variant,
                            "base_score": float(base_score),
                            "ambiguity_adjust": 0.0,
                            "final_score": float(base_score),
                            "note": "pattern contains ellipsis placeholder; ambiguity not applied",
                        }
                    else:
                        out["score"] = self._score_row(row, generated_surface, ctx)
                    matches.append(out)

        matches.sort(
            key=lambda item: (
                0 if bool(item.get("score", {}).get("context_match")) else 1,
                -float(item.get("score", {}).get("final_score", -999999.0)),
                _s(item.get("generated_surface")),
                _s(item.get("source_kind")),
                _s(item.get("rule_id")),
                int(item.get("source_index", 0) or 0),
            )
        )

        return {
            "ok": True,
            "lemma": base,
            "pos_labels": list(ctx["pos_labels"]),
            "pos_majors": list(ctx["pos_majors"]),
            "lemma_variants": list(ctx["lemma_variants"]),
            "inferred_classes": list(ctx["inferred_classes"]),
            "total_rules": len(self.rows),
            "match_count": len(matches),
            "matches": matches,
        }

    def scoring_rules(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "dataset_name": _s(self.analyzer.dataset_name),
            "dataset_version": _s(self.analyzer.dataset_version),
            "base_score_rules": [
                {"component": "source=allomorph_map", "value": 35.0},
                {"component": "source=token_rules", "value": 20.0},
                {"component": "lemma exact match", "value": 65.0},
                {"component": "lemma placeholder match (<...>)", "value": 25.0},
                {"component": "lemma fallback (non-placeholder mismatch)", "value": 10.0},
                {"component": "rule class matches inferred class", "value": 25.0},
                {"component": "rule pos major compatible", "value": 15.0},
                {"component": "productivity contains 'productive'", "value": 2.0},
                {"component": "productivity contains 'restricted'", "value": -1.0},
            ],
            "ambiguity_score_rules": {
                "bonus_formula": "max(0.5, 10 - priority/2) when preferred_rule_id matches current rule",
                "competing_penalty": -6.0,
                "applies_to_grouped_rules_only": True,
                "ambiguity_rows_loaded": len(self.analyzer.ambiguity_rows),
            },
            "sorting_rules": [
                "context_match desc",
                "final_score desc",
                "matched_tail_length desc",
                "source_kind asc",
                "rule_id asc",
                "source_index asc",
            ],
            "ambiguity_rows": list(self.analyzer.ambiguity_rows),
        }


INDEX = MorphRuleDebugIndex()
app = Flask(__name__)


@app.get("/")
def index() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>JP v2 Morph Debug</title>
  <style>
    body { font-family: Consolas, monospace; margin: 18px; }
    input, button { font-size: 14px; padding: 6px; }
    .row { margin-bottom: 10px; }
    .hint { color: #666; margin-bottom: 8px; }
    pre { white-space: pre-wrap; border: 1px solid #ddd; padding: 8px; background: #fafafa; }
  </style>
</head>
<body>
  <h2>JP v2 Morph Rule Debug</h2>

  <h3>Surface Lookup (Unconstrained)</h3>
  <div class="hint">Returns all possible surface-pattern matches. Optional lemma/POS applies scoring.</div>
  <div class="row">
    <input id="surface" placeholder="surface form" size="24" />
    <input id="surfaceLemma" placeholder="optional lemma for scoring" size="24" />
    <input id="surfacePos" placeholder="optional pos hints (AUX,COP etc.)" size="28" />
    <button id="runSurface">Surface Lookup</button>
  </div>
  <pre id="surfaceOut"></pre>

  <h3>Lemma Conjugation Explorer</h3>
  <div class="hint">Generates possible surfaces for a lemma from this ruleset.</div>
  <div class="row">
    <input id="lemma" placeholder="lemma" size="24" />
    <input id="lemmaPos" placeholder="optional pos hints" size="24" />
    <button id="runLemma">Lemma Lookup</button>
  </div>
  <pre id="lemmaOut"></pre>

  <h3>Scoring Rules</h3>
  <div class="row">
    <button id="runRules">Load Scoring Rules</button>
  </div>
  <pre id="rulesOut"></pre>

  <script>
    function show(id, obj) {
      document.getElementById(id).innerText = JSON.stringify(obj, null, 2);
    }

    async function runSurface() {
      var surface = document.getElementById("surface").value || "";
      if (!surface) return;
      var lemma = document.getElementById("surfaceLemma").value || "";
      var pos = document.getElementById("surfacePos").value || "";
      var url = "/api/raw_surface_lookup?surface=" + encodeURIComponent(surface) +
                "&lemma=" + encodeURIComponent(lemma) +
                "&pos=" + encodeURIComponent(pos);
      var r = await fetch(url);
      var d = await r.json();
      show("surfaceOut", d);
    }

    async function runLemma() {
      var lemma = document.getElementById("lemma").value || "";
      if (!lemma) return;
      var pos = document.getElementById("lemmaPos").value || "";
      var url = "/api/lemma_conjugations?lemma=" + encodeURIComponent(lemma) +
                "&pos=" + encodeURIComponent(pos);
      var r = await fetch(url);
      var d = await r.json();
      show("lemmaOut", d);
    }

    async function runRules() {
      var r = await fetch("/api/scoring_rules");
      var d = await r.json();
      show("rulesOut", d);
    }

    document.getElementById("runSurface").addEventListener("click", runSurface);
    document.getElementById("runLemma").addEventListener("click", runLemma);
    document.getElementById("runRules").addEventListener("click", runRules);
    document.getElementById("surface").addEventListener("keydown", function(e) { if (e.key === "Enter") runSurface(); });
    document.getElementById("surfaceLemma").addEventListener("keydown", function(e) { if (e.key === "Enter") runSurface(); });
    document.getElementById("surfacePos").addEventListener("keydown", function(e) { if (e.key === "Enter") runSurface(); });
    document.getElementById("lemma").addEventListener("keydown", function(e) { if (e.key === "Enter") runLemma(); });
    document.getElementById("lemmaPos").addEventListener("keydown", function(e) { if (e.key === "Enter") runLemma(); });
    runRules();
  </script>
</body>
</html>
"""


@app.get("/api/raw_surface_lookup")
def api_raw_surface_lookup():
    surface = _s(request.args.get("surface", ""))
    lemma = _s(request.args.get("lemma", ""))
    pos_query = _s(request.args.get("pos", ""))
    if not surface:
        return jsonify({"ok": False, "error": "missing surface"}), 400
    return jsonify(INDEX.lookup_surface(surface, lemma=lemma, pos_query=pos_query))


@app.get("/api/lemma_conjugations")
def api_lemma_conjugations():
    lemma = _s(request.args.get("lemma", ""))
    pos_query = _s(request.args.get("pos", ""))
    if not lemma:
        return jsonify({"ok": False, "error": "missing lemma"}), 400
    return jsonify(INDEX.lookup_lemma(lemma, pos_query=pos_query))


@app.get("/api/scoring_rules")
def api_scoring_rules():
    return jsonify(INDEX.scoring_rules())


@app.get("/api/ping")
def api_ping():
    return jsonify(
        {
            "ok": True,
            "dataset_name": _s(INDEX.analyzer.dataset_name),
            "dataset_version": _s(INDEX.analyzer.dataset_version),
            "rule_count_total": len(INDEX.rows),
            "token_rule_count": len(INDEX.analyzer.token_rules),
            "allomorph_rule_count": len(INDEX.analyzer.allomorph_map),
            "ambiguity_row_count": len(INDEX.analyzer.ambiguity_rows),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5051)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
