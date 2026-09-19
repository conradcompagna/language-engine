#!/usr/bin/env python3
"""
Compact Korean dictionary lookup web app (standalone).

Default port: 5051
"""

from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, Response, request


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_DICT_DIR = APP_ROOT / "korean" / "dict"
LEVEL_SUFFIXES = {"\ucd08\uae09", "\uc911\uae09", "\uace0\uae09"}  # beginner/intermediate/advanced


def _esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _to_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


class KoreanIndex:
    def __init__(self, dict_dir: Path):
        self.dict_dir = Path(dict_dir)
        self.entries: List[Dict[str, Any]] = []
        self._load()

    def _normalize_pos_level(self, pos_raw: str, level_tag: str) -> tuple[str, str]:
        pos = _to_text(pos_raw).replace("_", " ")
        level = _to_text(level_tag)
        if " " in pos:
            maybe = pos.rsplit(" ", 1)[1]
            if maybe in LEVEL_SUFFIXES:
                pos = pos.rsplit(" ", 1)[0]
                if not level:
                    level = maybe
        if level == "\uc5c6\uc74c":  # 없음
            level = ""
        return pos.strip(), level.strip()

    def _parse_old_list_row(self, row: List[Any], fp_name: str, idx: int, eid: int) -> Dict[str, Any]:
        head = _to_text(row[0] if len(row) > 0 else "")
        reading = _to_text(row[1] if len(row) > 1 else "")
        pos_raw = _to_text(row[2] if len(row) > 2 else "")
        level_tag = _to_text(row[7] if len(row) > 7 else "")
        score = _to_int(row[4] if len(row) > 4 else 0)
        defs = row[5] if len(row) > 5 and isinstance(row[5], list) else []
        glosses = [str(x).strip() for x in defs if str(x).strip()]
        pos, level = self._normalize_pos_level(pos_raw, level_tag)
        return {
            "id": eid,
            "headword": head,
            "reading": reading,
            "pos": pos,
            "level": level,
            "score": score,
            "glosses": glosses,
            "source_file": fp_name,
            "source_index": idx,
            "raw_row": row,
        }

    def _parse_new_dict_row(self, row: Dict[str, Any], fp_name: str, idx: int, eid: int) -> Dict[str, Any]:
        head = _to_text(row.get("headword") or row.get("word"))
        reading = _to_text(row.get("pronunciation") or row.get("reading"))
        pos_raw = _to_text(row.get("part_of_speech") or row.get("pos"))
        level_tag = _to_text(row.get("vocabulary_level") or row.get("level"))
        pos, level = self._normalize_pos_level(pos_raw, level_tag)

        score = _to_int(row.get("score"), default=0)
        if score == 0:
            # Soft ranking fallback for new schema.
            if level == "\ucd08\uae09":
                score = 300
            elif level == "\uc911\uae09":
                score = 200
            elif level == "\uace0\uae09":
                score = 100

        glosses: List[str] = []
        senses = row.get("senses")
        if isinstance(senses, list):
            for s in senses:
                if isinstance(s, dict):
                    en_def = _to_text(s.get("en_definition"))
                    ko_def = _to_text(s.get("definition_ko") or s.get("definition"))
                    if en_def:
                        glosses.append(en_def)
                    elif ko_def:
                        glosses.append(ko_def)
                else:
                    txt = _to_text(s)
                    if txt:
                        glosses.append(txt)

        if not glosses:
            # Fallback keys if this variant differs.
            for k in ("gloss", "definition", "meaning"):
                txt = _to_text(row.get(k))
                if txt:
                    glosses.append(txt)

        # Deduplicate while preserving order.
        seen = set()
        deduped: List[str] = []
        for g in glosses:
            key = g.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(g)

        return {
            "id": eid,
            "headword": head,
            "reading": reading,
            "pos": pos,
            "level": level,
            "score": score,
            "glosses": deduped,
            "source_file": fp_name,
            "source_index": idx,
            "raw_row": row,
        }

    def _load(self) -> None:
        files = sorted(self.dict_dir.glob("term_bank_*.json"))
        if not files:
            raise FileNotFoundError(f"No term_bank_*.json in {self.dict_dir}")
        eid = 1
        for fp in files:
            rows = json.loads(fp.read_text(encoding="utf-8"))
            for i, row in enumerate(rows):
                entry = None
                if isinstance(row, list) and len(row) >= 2:
                    entry = self._parse_old_list_row(row, fp.name, i, eid)
                elif isinstance(row, dict):
                    entry = self._parse_new_dict_row(row, fp.name, i, eid)
                if not entry:
                    continue
                if not entry.get("headword") and not entry.get("reading"):
                    continue
                self.entries.append(entry)
                eid += 1

    def search(self, q: str, mode: str, limit: int) -> Dict[str, Any]:
        q = (q or "").strip()
        if not q:
            return {"hits": [], "total_matches": 0, "scanned_entries": 0}
        mode = mode if mode in {"exact", "prefix", "contains"} else "exact"
        qf = q.casefold()
        hits: List[Dict[str, Any]] = []
        scanned = 0
        for e in self.entries:
            scanned += 1
            fields = [e["headword"], e["reading"], e["pos"], e["level"]] + list(e["glosses"])
            ok = False
            for f in fields:
                ff = str(f).casefold()
                if mode == "exact" and ff == qf:
                    ok = True
                    break
                if mode == "prefix" and ff.startswith(qf):
                    ok = True
                    break
                if mode == "contains" and qf in ff:
                    ok = True
                    break
            if ok:
                hits.append(e)
        hits.sort(key=lambda x: (-int(x.get("score", 0)), len(str(x.get("headword", ""))), int(x.get("id", 0))))
        return {"hits": hits[:limit], "total_matches": len(hits), "scanned_entries": scanned}


def create_app(index: KoreanIndex) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def home() -> Response:
        q = request.args.get("q", "").strip()
        mode = request.args.get("mode", "exact").strip()
        details = str(request.args.get("details", "")).strip().lower() in {"1", "true", "yes"}
        limit = _to_int(request.args.get("limit", "40"), default=40)
        limit = max(1, min(limit, 500))

        payload = {"hits": [], "total_matches": 0, "scanned_entries": 0}
        took_ms = 0
        if q:
            t0 = time.time()
            payload = index.search(q, mode=mode, limit=limit)
            took_ms = int((time.time() - t0) * 1000)

        cards = []
        for i, e in enumerate(payload["hits"], 1):
            gloss = " | ".join(_esc(x) for x in e.get("glosses", [])) or "<span class='muted'>(none)</span>"
            detail_html = ""
            if details:
                detail_html = (
                    f"<div class='meta'>source={_esc(e.get('source_file'))}#{_esc(e.get('source_index'))} | score={_esc(e.get('score'))}</div>"
                    f"<details><summary>raw row</summary><pre>{_esc(json.dumps(e.get('raw_row'), ensure_ascii=False))}</pre></details>"
                )
            cards.append(
                f"<article class='card'><div class='top'><b>#{i} {_esc(e.get('headword'))}</b> "
                f"<span class='r'>{_esc(e.get('reading'))}</span> "
                f"<span class='pill'>{_esc(e.get('pos'))}</span> "
                f"<span class='pill'>{_esc(e.get('level'))}</span></div>"
                f"<div class='g'>{gloss}</div>{detail_html}</article>"
            )

        page = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Korean Dictionary Gloss App</title>
<style>
body{{font:13px/1.4 "Segoe UI",sans-serif;background:#f5f7f6;color:#102028;margin:0}}
.wrap{{max-width:1200px;margin:0 auto;padding:10px}}
.search{{display:flex;gap:6px;flex-wrap:wrap;background:#fff;border:1px solid #d5dcdc;border-radius:10px;padding:8px}}
input,select,button{{font:13px "Segoe UI";padding:5px 8px;border:1px solid #ccd5d9;border-radius:7px}}
input[name=q]{{flex:1;min-width:220px}}
button{{background:#135f58;color:#fff;border-color:#0f534d;font-weight:700}}
.meta{{font-size:11px;color:#5a6a73;margin:6px 0}}
.card{{background:#fff;border:1px solid #d5dcdc;border-radius:10px;padding:7px 9px;margin-top:7px}}
.top{{display:flex;gap:7px;align-items:center;flex-wrap:wrap}}
.pill{{background:#e9f3f1;border:1px solid #c6dfdb;border-radius:999px;padding:1px 7px;font-size:11px}}
.r{{color:#254b56}} .g{{margin-top:4px}} .muted{{color:#7b8991}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f2f5f6;border:1px solid #d5dcdc;padding:6px;border-radius:8px}}
</style></head><body><div class="wrap">
<h3 style="margin:4px 0 8px 0;">Korean Dictionary Gloss App</h3>
<form class="search" method="get" action="/">
<input type="text" name="q" value="{_esc(q)}" placeholder="word / reading / gloss">
<select name="mode"><option value="exact" {"selected" if mode=="exact" else ""}>exact</option><option value="prefix" {"selected" if mode=="prefix" else ""}>prefix</option><option value="contains" {"selected" if mode=="contains" else ""}>contains</option></select>
<input type="number" name="limit" value="{limit}" min="1" max="500">
<label><input type="checkbox" name="details" value="1" {"checked" if details else ""}> details</label>
<button type="submit">Lookup</button></form>
<div class="meta">entries={len(index.entries):,} | scanned={payload["scanned_entries"]} | matches={payload["total_matches"]} | returned={len(payload["hits"])} | lookup_ms={took_ms}</div>
{''.join(cards) if cards else "<div class='meta'>Enter a query above.</div>"}
</div></body></html>"""
        return Response(page, mimetype="text/html")

    @app.get("/api/lookup")
    def api_lookup() -> Response:
        q = request.args.get("q", "").strip()
        mode = request.args.get("mode", "exact").strip()
        limit = _to_int(request.args.get("limit", "40"), default=40)
        limit = max(1, min(limit, 500))
        payload = index.search(q, mode=mode, limit=limit)
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), mimetype="application/json")

    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict-dir", default=str(DEFAULT_DICT_DIR))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5051)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    index = KoreanIndex(Path(args.dict_dir))
    app = create_app(index)
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
