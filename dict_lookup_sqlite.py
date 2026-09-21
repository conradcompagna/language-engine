"""Build compact dictionary indexes and hydrate selected SQLite rows.

The browser selects winner references; this module resolves full entries and
forms with batched queries and maintains the custom-entry form index.
"""

import json
import re
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import unquote
from sqlite_prune_policy import (
    entry_cut_reason,
    has_always_keep_tag,
    occurrence_cut_reason,
    surface_fanout_cut_reason,
)

APP_ROOT = Path(__file__).resolve().parent
SQLITE_DIR = APP_ROOT / "dict_sqlite"
_JS_NORMALIZER = APP_ROOT / "tools" / "normalize_keys.js"


def _sqlite_database_url_path(database_url: str) -> Path | None:
    raw = str(database_url or "").strip()
    prefix = "sqlite:///"
    if not raw.startswith(prefix):
        return None
    path_text = unquote(raw[len(prefix) :])
    if not path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else (APP_ROOT / path)


def _app_db_path() -> Path:
    try:
        import config as le_config

        configured = _sqlite_database_url_path(getattr(le_config, "DATABASE_URL", ""))
        if configured is not None:
            return configured
    except Exception:
        pass
    return APP_ROOT / "language_engine.db"


APP_DB_PATH = _app_db_path()

# Per-thread connection storage
_thread_local = threading.local()
_custom_form_index_lock = threading.Lock()
_custom_form_index_ready = False

_READ_ONLY_CACHE_KB = 32768
_READ_ONLY_MMAP_BYTES = 268435456
_AGGREGATE_CUSTOM_ALIAS = "customdb"
_SPLIT_PAGE_HEADWORD_RE = re.compile(r"/languages [A-Z] to [A-Z]$", re.IGNORECASE)


def _db_uri_for_readonly(db_path: Path, *, immutable: bool) -> str:
    resolved = Path(db_path).resolve().as_posix()
    if immutable:
        return f"file:{resolved}?mode=ro&immutable=1"
    return f"file:{resolved}?mode=ro"


def _is_static_dictionary_db(db_path: Path) -> bool:
    try:
        return Path(db_path).resolve().parent == SQLITE_DIR.resolve()
    except Exception:
        return False


def _alias_for_path(db_path: Path) -> str:
    """Return a stable SQLite ATTACH alias derived from the file stem.

    Using the file stem (e.g. "zh-cc-cedict") as the alias makes it
    consistent across index-build time and hydration time, regardless of
    how many databases are attached or in what order.
    """
    return Path(db_path).stem


def _is_korean_language_code(lang_code: str) -> bool:
    lang = (lang_code or "").strip().lower()
    return lang == "ko" or lang == "korean" or lang.startswith("ko-")


def _is_sanskrit_language_code(lang_code: str) -> bool:
    lang = (lang_code or "").strip().lower()
    return (
        lang == "sa"
        or lang == "san"
        or lang == "sanskrit"
        or lang.startswith("sa-")
        or lang.startswith("san-")
        or lang.startswith("sanskrit-")
    )


# Pre-nasal → anusvāra mirror of canonicalizeSanskritAnusvara() in
# static/dictionary_normalization_layer.js. Produces a SECOND lookup key so
# that a dict entry with sandhi-assimilated nasals (saṅskṛta, sandhi…) is
# also reachable under the canonical anusvāra spelling the user tends to
# type (saṃskṛta, saṃdhi…).
_SANSKRIT_ANUSVARA_PATTERNS = (
    (re.compile("\u1e45(?=[kg]h?)"), "\u1e43"),  # ṅ before k/g → ṃ
    (re.compile("\u00f1(?=[cj]h?)"), "\u1e43"),  # ñ before c/j → ṃ
    (re.compile("\u1e47(?=[\u1e6d\u1e0d]h?)"), "\u1e43"),  # ṇ before ṭ/ḍ → ṃ
    (re.compile("n(?=[td]h?)"), "\u1e43"),  # n before t/d → ṃ
    (re.compile("m(?=[pb]h?)"), "\u1e43"),  # m before p/b → ṃ
)


def _sanskrit_anusvara_canonical(text: str) -> str:
    """Return the anusvāra-canonicalized form of an IAST string, or '' if
    unchanged. Input must already be IAST."""
    s = str(text or "")
    if not s:
        return ""
    out = s
    for pat, repl in _SANSKRIT_ANUSVARA_PATTERNS:
        out = pat.sub(repl, out)
    return out if out != s else ""


def _build_aggregate_conn_key(
    db_paths: Sequence[str | Path],
    *,
    include_custom_entries: bool,
) -> tuple[tuple[str, ...], bool]:
    resolved = tuple(str(Path(p).resolve()) for p in list(db_paths or []))
    return resolved, bool(include_custom_entries and APP_DB_PATH.exists())


def _attach_database(conn: sqlite3.Connection, db_path: Path, alias: str) -> None:
    # Double-quote the alias so stems with hyphens (e.g. "zh-cc-cedict") are valid SQL identifiers.
    quoted = '"' + alias.replace('"', '""') + '"'
    sql = f"ATTACH DATABASE ? AS {quoted}"
    try:
        conn.execute(
            sql,
            (_db_uri_for_readonly(db_path, immutable=_is_static_dictionary_db(db_path)),),
        )
    except Exception:
        conn.execute(sql, (str(Path(db_path)),))


def _get_aggregate_conn(
    db_paths: Sequence[str | Path],
    *,
    include_custom_entries: bool,
) -> tuple[sqlite3.Connection, dict[str, str]]:
    key = _build_aggregate_conn_key(db_paths, include_custom_entries=include_custom_entries)
    aggregate_conns = getattr(_thread_local, "aggregate_connections", None)
    if aggregate_conns is None:
        aggregate_conns = {}
        _thread_local.aggregate_connections = aggregate_conns
    existing = aggregate_conns.get(key)
    if existing is not None:
        conn = existing["conn"]
        return conn, dict(existing["alias_by_path"])

    conn = sqlite3.connect(":memory:", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA cache_size=-{_READ_ONLY_CACHE_KB}")
    conn.execute("PRAGMA temp_store=MEMORY")
    try:
        conn.execute(f"PRAGMA mmap_size={_READ_ONLY_MMAP_BYTES}")
    except Exception:
        pass

    alias_by_path: dict[str, str] = {}
    for raw_path in list(db_paths or []):
        db_path = Path(raw_path).resolve()
        alias = _alias_for_path(db_path)
        _attach_database(conn, db_path, alias)
        alias_by_path[str(db_path)] = alias

    if include_custom_entries and APP_DB_PATH.exists():
        _attach_database(conn, APP_DB_PATH.resolve(), _AGGREGATE_CUSTOM_ALIAS)
    conn.execute("PRAGMA query_only=ON")

    aggregate_conns[key] = {
        "conn": conn,
        "alias_by_path": dict(alias_by_path),
    }
    return conn, dict(alias_by_path)


def _resolve_db_path(lang_code: str, source: str = "") -> Optional[Path]:
    """Find the .sqlite file for a language + source combination."""
    if source and source not in ("default",):
        p = SQLITE_DIR / f"{lang_code}-{source}.sqlite"
        if p.exists():
            return p
    p = SQLITE_DIR / f"{lang_code}.sqlite"
    if p.exists():
        return p
    return None


def _resolve_all_db_paths(lang_code: str) -> list[Path]:
    """Find ALL .sqlite files for a language (default + all alternative sources).
    In SQLite mode we can query them all at no memory cost.
    """
    paths = []
    # Default dict
    p = SQLITE_DIR / f"{lang_code}.sqlite"
    if p.exists():
        paths.append(p)
    # Alternative sources (e.g. ja-jmdict.sqlite, zh-cc-cedict.sqlite)
    for f in SQLITE_DIR.glob(f"{lang_code}-*.sqlite"):
        if f not in paths:
            paths.append(f)
    # Fallback for variants that share a base dict (e.g. zh-Hant -> zh)
    if not paths and "-" in lang_code:
        base = lang_code.split("-")[0]
        return _resolve_all_db_paths(base)
    return paths


def _filter_db_paths(all_paths: list[Path], lang_code: str, sources: list[str]) -> list[Path]:
    """Filter db paths to only include those matching the requested source names."""
    if not sources:
        return all_paths
    filtered = []
    source_set = set(s.lower().strip() for s in sources if s)
    for p in all_paths:
        stem = p.stem  # e.g. "ar", "ja-jmdict", "zh-cc-cedict"
        # The default dict (lang.sqlite) matches "wiktionary" or "default"
        if stem == lang_code:
            if "wiktionary" in source_set or "default" in source_set:
                filtered.append(p)
        else:
            # Extract source suffix: "ja-jmdict" -> "jmdict"
            suffix = stem[len(lang_code) + 1 :] if stem.startswith(lang_code + "-") else stem
            if suffix.lower() in source_set:
                filtered.append(p)
    return filtered if filtered else all_paths  # fallback to all if nothing matched


def _iter_query_rows(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
    *,
    chunk_size: int = 5000,
):
    cur = conn.execute(sql, params)
    while True:
        rows = cur.fetchmany(chunk_size)
        if not rows:
            break
        for row in rows:
            yield row


def _is_split_page_headword(text: str) -> bool:
    return bool(_SPLIT_PAGE_HEADWORD_RE.search(str(text or "").strip()))


def _is_promotable_split_page_form(form_text: str, morph_tags: str = "") -> bool:
    text = str(form_text or "").strip()
    tags = str(morph_tags or "").strip().lower()
    if not text or text == "-":
        return False
    if "table-tags" in tags or "inflection-template" in tags:
        return False
    return True


def _fetch_split_page_form_rows_for_entries(
    conn: sqlite3.Connection,
    alias: str,
    entry_ids: Sequence[int],
    *,
    lang_code: str = "",
) -> dict[int, list[dict[str, Any]]]:
    ids = sorted({int(raw_id or 0) for raw_id in list(entry_ids or []) if int(raw_id or 0) > 0})
    if not ids:
        return {}
    qa = '"' + alias.replace('"', '""') + '"'
    out: dict[int, list[dict[str, Any]]] = {}
    for chunk_start in range(0, len(ids), 900):
        chunk = ids[chunk_start : chunk_start + 900]
        placeholders = ",".join("?" * len(chunk))
        sql = (
            f"SELECT f.entry_id, f.id, f.form_text, "
            f"       TRIM(COALESCE(f.morph_tags, '')) AS morph_tags, TRIM(COALESCE(f.romanization, '')) AS romanization "
            f"FROM {qa}.forms f "
            f"WHERE f.entry_id IN ({placeholders}) "
            f"  AND f.form_text IS NOT NULL AND TRIM(f.form_text) != '' "
            f"ORDER BY f.entry_id, "
            f"         CASE WHEN LOWER(COALESCE(f.morph_tags, '')) LIKE '%canonical%' THEN 0 ELSE 1 END, "
            f"         CASE WHEN LOWER(COALESCE(f.morph_tags, '')) LIKE '%uppercase%' THEN 1 ELSE 0 END, "
            f"         f.id"
        )
        rows = conn.execute(sql, tuple(chunk)).fetchall()
        norm_cache: dict[tuple[str, str], str] = {}
        if lang_code:
            norm_pairs = [
                (str(row["form_text"] or "").strip(), lang_code)
                for row in rows
                if str(row["form_text"] or "").strip()
            ]
            if norm_pairs:
                norm_cache = _normalize_keys_via_js(norm_pairs)
        for row in rows:
            entry_id = int(row["entry_id"] or 0)
            if entry_id <= 0:
                continue
            form_text = str(row["form_text"] or "").strip()
            morph_tags = str(row["morph_tags"] or "").strip()
            if not _is_promotable_split_page_form(form_text, morph_tags):
                continue
            bucket = out.setdefault(entry_id, [])
            form_key = str(norm_cache.get((form_text, lang_code), "") or "").strip()
            dedupe_key = (
                form_text,
                form_key,
                morph_tags,
                str(row["romanization"] or "").strip(),
            )
            seen = {
                (
                    str(item.get("form_text") or "").strip(),
                    str(item.get("form_key") or "").strip(),
                    str(item.get("morph_tags") or "").strip(),
                    str(item.get("romanization") or "").strip(),
                )
                for item in bucket
            }
            if dedupe_key in seen:
                continue
            bucket.append(
                {
                    "form_id": int(row["id"] or 0),
                    "form_text": form_text,
                    "form_key": form_key,
                    "morph_tags": morph_tags,
                    "romanization": str(row["romanization"] or "").strip(),
                }
            )
    return out


def _build_pruned_survivor_context_for_alias(
    conn: sqlite3.Connection,
    alias: str,
) -> dict[str, Any]:
    qa = '"' + alias.replace('"', '""') + '"'
    sql = (
        f"SELECT id, "
        f"       TRIM(COALESCE(headword, '')) AS headword, "
        f"       TRIM(COALESCE(romanization, '')) AS romanization, "
        f"       TRIM(COALESCE(pos, '')) AS pos, "
        f"       TRIM(COALESCE(glosses, '')) AS glosses "
        f"FROM {qa}.entries "
        f"ORDER BY id"
    )
    key_to_survivor_entry_id: dict[tuple[str, str, str, str], int] = {}
    entry_to_survivor_entry_id: dict[int, int] = {}
    survivor_order: list[int] = []
    survivor_headword_by_entry_id: dict[int, str] = {}
    survivor_pos_by_entry_id: dict[int, str] = {}
    split_page_survivor_ids: set[int] = set()

    for row in _iter_query_rows(conn, sql):
        entry_id = int(row["id"] or 0)
        if entry_id <= 0:
            continue
        headword = str(row["headword"] or "").strip()
        romanization = str(row["romanization"] or "").strip()
        pos = str(row["pos"] or "").strip()
        glosses = str(row["glosses"] or "").strip()
        if entry_cut_reason(glosses):
            continue
        dedupe_key = (headword, romanization, pos, glosses)
        survivor_entry_id = key_to_survivor_entry_id.get(dedupe_key)
        if survivor_entry_id is None:
            survivor_entry_id = entry_id
            key_to_survivor_entry_id[dedupe_key] = survivor_entry_id
            survivor_order.append(survivor_entry_id)
            survivor_headword_by_entry_id[survivor_entry_id] = headword
            survivor_pos_by_entry_id[survivor_entry_id] = pos
            if _is_split_page_headword(headword):
                split_page_survivor_ids.add(survivor_entry_id)
        entry_to_survivor_entry_id[entry_id] = survivor_entry_id

    return {
        "entry_to_survivor_entry_id": entry_to_survivor_entry_id,
        "survivor_order": survivor_order,
        "survivor_headword_by_entry_id": survivor_headword_by_entry_id,
        "survivor_pos_by_entry_id": survivor_pos_by_entry_id,
        "split_page_survivor_ids": split_page_survivor_ids,
    }


def _sort_split_page_promoted_rows(
    rows: Sequence[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return sorted(
        list(rows or []),
        key=lambda row: (
            0 if "canonical" in str(row.get("morph_tags") or "").strip().lower() else 1,
            1 if "uppercase" in str(row.get("morph_tags") or "").strip().lower() else 0,
            int(row.get("form_id") or 0),
        ),
    )


def _collect_pruned_alias_hits(
    conn: sqlite3.Connection,
    alias: str,
    db_name: str,
) -> dict[str, Any]:
    from sqlite_prune_policy import compute_synthetic_collapses

    ctx = _build_pruned_survivor_context_for_alias(conn, alias)
    entry_to_survivor_entry_id = ctx["entry_to_survivor_entry_id"]
    split_page_survivor_ids = ctx["split_page_survivor_ids"]
    survivor_headword_by_entry_id = ctx["survivor_headword_by_entry_id"]

    collapse_info = compute_synthetic_collapses(conn, alias, db_name)
    donor_to_target: dict[int, int] = collapse_info.get("donor_to_target") or {}
    synthetic_tags_by_donor: dict[int, list] = collapse_info.get("synthetic_tags_by_donor") or {}
    donor_surface_by_donor: dict[int, str] = collapse_info.get("donor_surface_by_donor") or {}
    donor_roman_by_donor: dict[int, str] = collapse_info.get("donor_romanization_by_donor") or {}

    if donor_to_target:
        survivor_order = ctx["survivor_order"]
        survivor_pos_by_entry_id = ctx["survivor_pos_by_entry_id"]
        donors_set = set(donor_to_target.keys())
        for entry_id, survivor_id in list(entry_to_survivor_entry_id.items()):
            if survivor_id in donors_set:
                target_id = donor_to_target[survivor_id]
                if target_id in survivor_headword_by_entry_id:
                    entry_to_survivor_entry_id[entry_id] = target_id
        ctx["survivor_order"] = [s for s in survivor_order if s not in donors_set]
        for d in donors_set:
            survivor_headword_by_entry_id.pop(d, None)
            survivor_pos_by_entry_id.pop(d, None)
            split_page_survivor_ids.discard(d)
        ctx["entry_to_survivor_entry_id"] = entry_to_survivor_entry_id
        ctx["survivor_headword_by_entry_id"] = survivor_headword_by_entry_id
        ctx["survivor_pos_by_entry_id"] = survivor_pos_by_entry_id
        ctx["split_page_survivor_ids"] = split_page_survivor_ids
        ctx["synthetic_collapses"] = {
            "donor_to_target": donor_to_target,
            "synthetic_tags_by_donor": synthetic_tags_by_donor,
            "donor_surface_by_donor": donor_surface_by_donor,
            "donor_romanization_by_donor": donor_roman_by_donor,
        }
    qa = '"' + alias.replace('"', '""') + '"'
    sql = (
        f"SELECT f.entry_id, "
        f"       f.id AS form_id, "
        f"       TRIM(COALESCE(f.form_text, '')) AS form_text, "
        f"       TRIM(COALESCE(f.morph_tags, '')) AS morph_tags, "
        f"       TRIM(COALESCE(f.romanization, '')) AS form_romanization "
        f"FROM {qa}.forms f "
        f"WHERE TRIM(COALESCE(f.form_text, '')) != '' "
        f"ORDER BY TRIM(COALESCE(f.form_text, '')), "
        f"         f.entry_id, "
        f"         TRIM(COALESCE(f.morph_tags, '')), "
        f"         TRIM(COALESCE(f.romanization, '')), "
        f"         f.id"
    )

    form_hits: list[tuple[str, int, int]] = []
    promoted_forms_by_survivor: dict[int, list[dict[str, Any]]] = {}

    current_form_text = ""
    seen_variant_keys: set[tuple[int, str, str]] = set()
    candidate_live_survivor_ids: set[int] = set()
    candidate_hits: list[dict[str, Any]] = []
    absolute_keep_hits: list[dict[str, Any]] = []

    def reset_bucket() -> None:
        nonlocal seen_variant_keys
        nonlocal candidate_live_survivor_ids
        nonlocal candidate_hits
        nonlocal absolute_keep_hits
        seen_variant_keys = set()
        candidate_live_survivor_ids = set()
        candidate_hits = []
        absolute_keep_hits = []

    def emit_kept_hits(kept_hits: Sequence[dict[str, Any]]) -> None:
        for hit in kept_hits:
            form_text = str(hit.get("form_text") or "").strip()
            survivor_entry_id = int(hit.get("entry_id") or 0)
            form_id = int(hit.get("form_id") or 0)
            if not form_text or survivor_entry_id <= 0 or form_id <= 0:
                continue
            form_hits.append((form_text, survivor_entry_id, form_id))
            if survivor_entry_id not in split_page_survivor_ids:
                continue
            morph_tags = str(hit.get("morph_tags") or "").strip()
            if not _is_promotable_split_page_form(form_text, morph_tags):
                continue
            promoted_forms_by_survivor.setdefault(survivor_entry_id, []).append(
                {
                    "form_id": form_id,
                    "form_text": form_text,
                    "morph_tags": morph_tags,
                    "romanization": str(hit.get("romanization") or "").strip(),
                }
            )

    def finalize_bucket() -> None:
        if not current_form_text:
            return
        kept_hits = list(absolute_keep_hits)
        if candidate_hits:
            fanout_reason = surface_fanout_cut_reason(
                db_name, current_form_text, len(candidate_live_survivor_ids)
            )
            if fanout_reason != "fanout_gt_10":
                kept_hits.extend(candidate_hits)
        if kept_hits:
            emit_kept_hits(kept_hits)

    for row in _iter_query_rows(conn, sql):
        form_text = str(row["form_text"] or "").strip()
        if not form_text:
            continue
        if current_form_text and form_text != current_form_text:
            finalize_bucket()
            reset_bucket()
        current_form_text = form_text

        entry_id = int(row["entry_id"] or 0)
        survivor_entry_id = entry_to_survivor_entry_id.get(entry_id)
        if survivor_entry_id is None or survivor_entry_id <= 0:
            continue

        morph_tags = str(row["morph_tags"] or "").strip()
        form_romanization = str(row["form_romanization"] or "").strip()
        variant_key = (survivor_entry_id, morph_tags, form_romanization)
        if variant_key in seen_variant_keys:
            continue
        seen_variant_keys.add(variant_key)

        hit = {
            "form_text": form_text,
            "entry_id": survivor_entry_id,
            "form_id": int(row["form_id"] or 0),
            "morph_tags": morph_tags,
            "romanization": form_romanization,
        }
        if has_always_keep_tag(morph_tags):
            absolute_keep_hits.append(hit)
            continue

        headword = str(survivor_headword_by_entry_id.get(survivor_entry_id) or "").strip()
        occurrence_reason = occurrence_cut_reason(db_name, form_text, headword, morph_tags)
        if occurrence_reason:
            continue
        candidate_live_survivor_ids.add(survivor_entry_id)
        candidate_hits.append(hit)

    finalize_bucket()

    for survivor_entry_id, rows in list(promoted_forms_by_survivor.items()):
        deduped_rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for row in _sort_split_page_promoted_rows(rows):
            dedupe_key = (
                str(row.get("form_text") or "").strip(),
                str(row.get("morph_tags") or "").strip(),
                str(row.get("romanization") or "").strip(),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped_rows.append(row)
        promoted_forms_by_survivor[survivor_entry_id] = deduped_rows

    ctx["form_hits"] = form_hits
    ctx["promoted_forms_by_survivor"] = promoted_forms_by_survivor
    return ctx


def _choose_split_page_promoted_form(
    form_rows: Sequence[dict[str, Any]] | None,
    *,
    match_key: str = "",
    form_row_id: int = 0,
) -> dict[str, Any]:
    rows = list(form_rows or [])
    if not rows:
        return {}
    target_key = str(match_key or "").strip()
    target_form_id = int(form_row_id or 0)
    if target_form_id > 0:
        for row in rows:
            if int(row.get("form_id") or 0) == target_form_id:
                return dict(row)
    if target_key:
        for row in rows:
            row_key = str(row.get("form_key") or "").strip()
            if row_key and row_key == target_key:
                return dict(row)
    for row in rows:
        tags = str(row.get("morph_tags") or "").strip().lower()
        if "canonical" in tags:
            return dict(row)
    return dict(rows[0])


def _build_hydrate_lookup_sql(db_aliases: Sequence[str], *, include_custom_entries: bool) -> str:
    branches: list[str] = []
    for alias in list(db_aliases or []):
        qa = '"' + alias.replace('"', '""') + '"'
        branches.append(
            f"""
            SELECT 'sqlite' AS storage_kind,
                   '{alias}' AS db_alias,
                   e.id AS entry_row_id,
                   'headword' AS match_kind,
                   r.match_key AS match_key,
                   0 AS form_row_id,
                   e.headword AS headword,
                   e.glosses AS glosses,
                   '' AS forms,
                   e.romanization AS romanization,
                   e.pos AS pos,
                   e.commentary AS commentary,
                   e.lemma AS lemma,
                   e.etymology AS etymology,
                   e.etymology_number AS etymology_number,
                   e.source AS source,
                   e.entry_id AS entry_id,
                   e.tags AS tags,
                   e.format AS format,
                   '' AS matched_form_text,
                   '' AS matched_form_tags,
                   '' AS matched_form_romanization
            FROM refbag r
            JOIN {qa}.entries e
              ON r.storage_kind = 'sqlite'
             AND r.db_alias = '{alias}'
             AND r.match_kind = 'headword'
             AND r.entry_row_id = e.id
            """
        )
        branches.append(
            f"""
            SELECT 'sqlite' AS storage_kind,
                   '{alias}' AS db_alias,
                   e.id AS entry_row_id,
                   'form' AS match_kind,
                   r.match_key AS match_key,
                   f.id AS form_row_id,
                   e.headword AS headword,
                   e.glosses AS glosses,
                   '' AS forms,
                   e.romanization AS romanization,
                   e.pos AS pos,
                   e.commentary AS commentary,
                   e.lemma AS lemma,
                   e.etymology AS etymology,
                   e.etymology_number AS etymology_number,
                   e.source AS source,
                   e.entry_id AS entry_id,
                   e.tags AS tags,
                   e.format AS format,
                   f.form_text AS matched_form_text,
                   f.morph_tags AS matched_form_tags,
                   f.romanization AS matched_form_romanization
            FROM refbag r
            JOIN {qa}.entries e
              ON r.storage_kind = 'sqlite'
             AND r.db_alias = '{alias}'
             AND r.match_kind = 'form'
             AND r.entry_row_id = e.id
            JOIN {qa}.forms f ON f.id = r.form_row_id
            """
        )
    if include_custom_entries:
        branches.append(
            f"""
            SELECT 'custom' AS storage_kind,
                   '{_AGGREGATE_CUSTOM_ALIAS}' AS db_alias,
                   c.id AS entry_row_id,
                   'headword' AS match_kind,
                   r.match_key AS match_key,
                   0 AS form_row_id,
                   c.headword AS headword,
                   c.glosses_json AS glosses,
                   '' AS forms,
                   c.romanization AS romanization,
                   c.pos AS pos,
                   c.commentary AS commentary,
                   c.lemma AS lemma,
                   '' AS etymology,
                   0 AS etymology_number,
                   c.source AS source,
                   c.entry_id AS entry_id,
                   '' AS tags,
                   'compact' AS format,
                   '' AS matched_form_text,
                   '' AS matched_form_tags,
                   '' AS matched_form_romanization
            FROM refbag r
            JOIN {_AGGREGATE_CUSTOM_ALIAS}.custom_dict_entries c
              ON r.storage_kind = 'custom'
             AND r.db_alias = '{_AGGREGATE_CUSTOM_ALIAS}'
             AND r.match_kind = 'headword'
             AND r.entry_row_id = c.id
             AND c.language = ?
            """
        )
        branches.append(
            f"""
            SELECT 'custom' AS storage_kind,
                   '{_AGGREGATE_CUSTOM_ALIAS}' AS db_alias,
                   c.id AS entry_row_id,
                   'form' AS match_kind,
                   r.match_key AS match_key,
                   f.id AS form_row_id,
                   c.headword AS headword,
                   c.glosses_json AS glosses,
                   '' AS forms,
                   c.romanization AS romanization,
                   c.pos AS pos,
                   c.commentary AS commentary,
                   c.lemma AS lemma,
                   '' AS etymology,
                   0 AS etymology_number,
                   c.source AS source,
                   c.entry_id AS entry_id,
                   '' AS tags,
                   'compact' AS format,
                   f.form_text AS matched_form_text,
                   f.morph_tags AS matched_form_tags,
                   f.romanization AS matched_form_romanization
            FROM refbag r
            JOIN {_AGGREGATE_CUSTOM_ALIAS}.custom_dict_entries c
              ON r.storage_kind = 'custom'
             AND r.db_alias = '{_AGGREGATE_CUSTOM_ALIAS}'
             AND r.match_kind = 'form'
             AND r.entry_row_id = c.id
             AND c.language = ?
            JOIN {_AGGREGATE_CUSTOM_ALIAS}.custom_dict_forms f
              ON f.id = r.form_row_id
             AND f.entry_pk = c.id
             AND f.language = ?
            """
        )
    if not branches:
        return ""
    union_sql = "\nUNION ALL\n".join(branches)
    return f"""
        WITH refbag AS (
            SELECT DISTINCT
                   LOWER(COALESCE(json_extract(value, '$.storage_kind'), '')) AS storage_kind,
                   TRIM(COALESCE(json_extract(value, '$.db_alias'), '')) AS db_alias,
                   CAST(COALESCE(json_extract(value, '$.entry_row_id'), 0) AS INTEGER) AS entry_row_id,
                   LOWER(COALESCE(json_extract(value, '$.match_kind'), 'headword')) AS match_kind,
                   TRIM(COALESCE(json_extract(value, '$.match_key'), '')) AS match_key,
                   CAST(COALESCE(json_extract(value, '$.form_row_id'), 0) AS INTEGER) AS form_row_id
            FROM json_each(?)
            WHERE CAST(COALESCE(json_extract(value, '$.entry_row_id'), 0) AS INTEGER) > 0
        )
        {union_sql}
    """


def build_compact_key_index(
    lang_code: str,
    *,
    db_paths: Sequence[str | Path] | None = None,
    include_custom_entries: bool = True,
) -> dict:
    """
    Build a compact key index for client-side DP segmentation.

    Returns:
    {
      "hw": {"normalized_key": [["db0", entry_row_id], ...]},
      "fw": {"normalized_key": [["db0", entry_row_id, form_row_id], ...]},
      "db_aliases": {"db0": "ar", "db1": "ar-wiktionary", "customdb": "custom"}
    }

    The compact index is built from raw SQLite text and normalized once through
    the JS shim so it stays aligned with static/dictionary_normalization_layer.js.
    """
    if db_paths is not None:
        paths = [Path(p) for p in db_paths]
    else:
        paths = _resolve_all_db_paths(lang_code)

    include_custom = bool(include_custom_entries and APP_DB_PATH.exists())
    conn, alias_by_path = _get_aggregate_conn(paths, include_custom_entries=include_custom)

    db_aliases: dict[str, str] = {}
    for resolved_path_str, alias in alias_by_path.items():
        stem = Path(resolved_path_str).stem
        db_aliases[alias] = stem
    if include_custom:
        db_aliases[_AGGREGATE_CUSTOM_ALIAS] = "custom"

    hw: dict[str, list] = {}
    fw: dict[str, list] = {}
    inject_korean_stems = _is_korean_language_code(lang_code)
    inject_sanskrit_anusvara = _is_sanskrit_language_code(lang_code)

    def _push_hw_hit(match_key: str, alias: str, entry_id: int) -> None:
        key = str(match_key or "").strip()
        if not key or not alias or entry_id <= 0:
            return
        hw.setdefault(key, []).append([alias, entry_id])

    def _korean_stem_text(surface_text: str, pos: str) -> str:
        if not inject_korean_stems:
            return ""
        pos_raw = str(pos or "").strip().lower()
        if pos_raw not in {"verb", "adj"}:
            return ""
        hw_text = str(surface_text or "").strip()
        if not hw_text or not hw_text.endswith("다") or len(hw_text) <= 1:
            return ""
        return hw_text[:-1].strip()

    def _sanskrit_anusvara_text(surface_text: str) -> str:
        if not inject_sanskrit_anusvara:
            return ""
        return _sanskrit_anusvara_canonical(str(surface_text or "").strip())

    if paths:
        norm_texts: set[str] = set()
        pruned_alias_hits: list[tuple[str, dict[str, Any]]] = []

        for p in paths:
            resolved = str(Path(p).resolve())
            alias = alias_by_path.get(resolved)
            if not alias:
                continue
            db_name = db_aliases.get(alias, alias)
            pruned = _collect_pruned_alias_hits(conn, alias, db_name)
            pruned_alias_hits.append((alias, pruned))
            for raw_text, _entry_id, _form_id in list(pruned.get("form_hits") or []):
                raw = str(raw_text or "").strip()
                if raw:
                    norm_texts.add(raw)
            for survivor_entry_id in list(pruned.get("survivor_order") or []):
                raw_headword = str(
                    pruned["survivor_headword_by_entry_id"].get(survivor_entry_id) or ""
                ).strip()
                pos = str(pruned["survivor_pos_by_entry_id"].get(survivor_entry_id) or "").strip()
                promoted_rows = list(
                    pruned.get("promoted_forms_by_survivor", {}).get(survivor_entry_id) or []
                )
                primary_text = (
                    str(promoted_rows[0].get("form_text") or "").strip()
                    if promoted_rows
                    else raw_headword
                )
                if raw_headword:
                    norm_texts.add(raw_headword)
                for promoted in promoted_rows:
                    promoted_text = str(promoted.get("form_text") or "").strip()
                    if promoted_text:
                        norm_texts.add(promoted_text)
                stem_text = _korean_stem_text(primary_text, pos)
                if stem_text:
                    norm_texts.add(stem_text)
                anusvara_text = _sanskrit_anusvara_text(primary_text)
                if anusvara_text:
                    norm_texts.add(anusvara_text)

        norm_pairs = [(text, lang_code) for text in sorted(norm_texts)]
        norm_cache = _normalize_keys_via_js(norm_pairs) if norm_pairs else {}

        for alias, pruned in pruned_alias_hits:
            for raw_text, entry_id, form_id in list(pruned.get("form_hits") or []):
                key = norm_cache.get((str(raw_text or "").strip(), lang_code), "")
                if not key or int(entry_id or 0) <= 0 or int(form_id or 0) <= 0:
                    continue
                fw.setdefault(key, []).append([alias, int(entry_id), int(form_id)])

            for survivor_entry_id in list(pruned.get("survivor_order") or []):
                entry_id = int(survivor_entry_id or 0)
                if entry_id <= 0:
                    continue
                pos = str(pruned["survivor_pos_by_entry_id"].get(entry_id) or "").strip()
                raw_headword = str(
                    pruned["survivor_headword_by_entry_id"].get(entry_id) or ""
                ).strip()
                promoted_form_rows = list(
                    pruned.get("promoted_forms_by_survivor", {}).get(entry_id) or []
                )
                primary_text = raw_headword
                emitted_hw_keys: set[str] = set()

                if promoted_form_rows:
                    primary_text = (
                        str(promoted_form_rows[0].get("form_text") or "").strip() or raw_headword
                    )
                    for promoted in promoted_form_rows:
                        promoted_text = str(promoted.get("form_text") or "").strip()
                        promoted_key = norm_cache.get((promoted_text, lang_code), "")
                        if not promoted_key or promoted_key in emitted_hw_keys:
                            continue
                        emitted_hw_keys.add(promoted_key)
                        _push_hw_hit(promoted_key, alias, entry_id)
                else:
                    base_key = norm_cache.get((raw_headword, lang_code), "")
                    if base_key:
                        emitted_hw_keys.add(base_key)
                        _push_hw_hit(base_key, alias, entry_id)

                stem_text = _korean_stem_text(primary_text, pos)
                if stem_text:
                    stem_key = norm_cache.get((stem_text, lang_code), "")
                    if stem_key and stem_key not in emitted_hw_keys:
                        emitted_hw_keys.add(stem_key)
                        _push_hw_hit(stem_key, alias, entry_id)

                anusvara_text = _sanskrit_anusvara_text(primary_text)
                if anusvara_text:
                    anusvara_key = norm_cache.get((anusvara_text, lang_code), "")
                    if anusvara_key and anusvara_key not in emitted_hw_keys:
                        emitted_hw_keys.add(anusvara_key)
                        _push_hw_hit(anusvara_key, alias, entry_id)

    if include_custom:
        ca = _AGGREGATE_CUSTOM_ALIAS
        hw_rows = conn.execute(
            f"SELECT c.id AS entry_row_id, c.headword, c.pos AS pos FROM {ca}.custom_dict_entries c "
            f"WHERE c.language = ? AND c.headword IS NOT NULL AND c.headword != '' "
            f"AND LOWER(COALESCE(c.source, 'gemini')) = 'gemini'",
            (lang_code,),
        ).fetchall()
        form_rows = conn.execute(
            f"SELECT f.entry_pk AS entry_row_id, f.form_text, f.id AS form_row_id FROM {ca}.custom_dict_forms f "
            f"JOIN {ca}.custom_dict_entries c ON c.id = f.entry_pk "
            f"WHERE c.language = ? AND f.form_text IS NOT NULL AND f.form_text != '' "
            f"AND LOWER(COALESCE(c.source, 'gemini')) = 'gemini'",
            (lang_code,),
        ).fetchall()

        custom_pairs: list[tuple[str, str]] = []
        custom_head_rows: list[tuple[Any, str, str]] = []
        custom_form_rows: list[tuple[Any, str]] = []

        for row in hw_rows:
            raw_text = str(row["headword"] or "").strip()
            if not raw_text:
                continue
            pos = str(row["pos"] or "").strip()
            custom_pairs.append((raw_text, lang_code))
            stem_text = _korean_stem_text(raw_text, pos)
            if stem_text:
                custom_pairs.append((stem_text, lang_code))
            anusvara_text = _sanskrit_anusvara_text(raw_text)
            if anusvara_text:
                custom_pairs.append((anusvara_text, lang_code))
            custom_head_rows.append((row, raw_text, stem_text, anusvara_text))

        for row in form_rows:
            raw_text = str(row["form_text"] or "").strip()
            if not raw_text:
                continue
            custom_pairs.append((raw_text, lang_code))
            custom_form_rows.append((row, raw_text))

        norm_cache = _normalize_keys_via_js(custom_pairs) if custom_pairs else {}

        for row, raw_text, stem_text, anusvara_text in custom_head_rows:
            key = norm_cache.get((raw_text, lang_code), "")
            if not key:
                continue
            entry_id = int(row["entry_row_id"] or 0)
            if entry_id <= 0:
                continue
            _push_hw_hit(key, _AGGREGATE_CUSTOM_ALIAS, entry_id)
            if stem_text:
                stem_key = norm_cache.get((stem_text, lang_code), "")
                if stem_key and stem_key != key:
                    _push_hw_hit(stem_key, _AGGREGATE_CUSTOM_ALIAS, entry_id)
            if anusvara_text:
                anusvara_key = norm_cache.get((anusvara_text, lang_code), "")
                if anusvara_key and anusvara_key != key:
                    _push_hw_hit(anusvara_key, _AGGREGATE_CUSTOM_ALIAS, entry_id)

        for row, raw_text in custom_form_rows:
            key = norm_cache.get((raw_text, lang_code), "")
            if not key:
                continue
            entry_id = int(row["entry_row_id"] or 0)
            form_id = int(row["form_row_id"] or 0)
            if entry_id <= 0 or form_id <= 0:
                continue
            fw.setdefault(key, []).append([_AGGREGATE_CUSTOM_ALIAS, entry_id, form_id])

    return {"hw": hw, "fw": fw, "db_aliases": db_aliases}


def hydrate_winner_refs(
    candidates: Sequence[dict[str, object]],
    lang_code: str,
    *,
    db_paths: Sequence[str | Path] | None = None,
    sources: list[str] | None = None,
    include_custom_entries: bool = True,
) -> dict[tuple[str, str, int], dict]:
    def _run() -> dict[tuple[str, str, int], dict]:
        refs_payload: list[dict[str, Any]] = []
        seen_entry_ids: set[tuple[str, str, int]] = set()
        need_custom = False
        # Collect form_row_ids per entry for batch form lookup after entry fetch.
        # Key: (storage_kind, db_alias, entry_row_id) -> list of (form_row_id, match_key)
        form_refs_by_entry: dict[tuple[str, str, int], list[tuple[int, str]]] = {}
        for candidate in list(candidates or []):
            storage_kind = str(candidate.get("_storage_kind") or "").strip().lower()
            db_alias = str(candidate.get("_storage_db_alias") or "").strip()
            entry_row_id = int(candidate.get("_storage_row_id") or 0)
            match_kind = str(candidate.get("_match_kind") or "headword").strip().lower()
            match_key = str(candidate.get("match_key") or candidate.get("_match_key") or "").strip()
            if not storage_kind or not db_alias or entry_row_id <= 0:
                continue
            if storage_kind == "custom":
                need_custom = True
            ekey = (storage_kind, db_alias, entry_row_id)
            if ekey not in seen_entry_ids:
                seen_entry_ids.add(ekey)
                refs_payload.append(
                    {
                        "storage_kind": storage_kind,
                        "db_alias": db_alias,
                        "entry_row_id": entry_row_id,
                        "match_kind": "headword",
                        "match_key": match_key,
                        "form_row_id": 0,
                    }
                )
            if match_kind == "form":
                matched_ids = [
                    int(raw_id or 0)
                    for raw_id in list(candidate.get("_matched_form_row_ids") or [])
                    if int(raw_id or 0) > 0
                ]
                if not matched_ids:
                    raw_id = int(candidate.get("_form_row_id") or 0)
                    if raw_id > 0:
                        matched_ids = [raw_id]
                if matched_ids:
                    if ekey not in form_refs_by_entry:
                        form_refs_by_entry[ekey] = []
                    seen_fids = {fid for fid, _ in form_refs_by_entry[ekey]}
                    for fid in matched_ids:
                        if fid not in seen_fids:
                            form_refs_by_entry[ekey].append((fid, match_key))
                            seen_fids.add(fid)
        if not refs_payload:
            return {}
        include_custom = bool((include_custom_entries or need_custom) and APP_DB_PATH.exists())
        if db_paths is not None:
            paths = [Path(p) for p in db_paths]
        else:
            all_paths = _resolve_all_db_paths(lang_code)
            paths = (
                _filter_db_paths(all_paths, lang_code, list(sources or []))
                if sources
                else all_paths
            )
        conn, alias_by_path = _get_aggregate_conn(paths, include_custom_entries=include_custom)
        db_aliases = [
            alias_by_path[str(Path(p).resolve())]
            for p in paths
            if str(Path(p).resolve()) in alias_by_path
        ]
        sql = _build_hydrate_lookup_sql(db_aliases, include_custom_entries=include_custom)
        if not sql:
            return {}
        params: list[Any] = [json.dumps(refs_payload, ensure_ascii=False)]
        if include_custom:
            params.extend([lang_code, lang_code, lang_code])
        rows = conn.execute(sql, tuple(params)).fetchall()

        split_page_forms_by_ref: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        split_page_entry_ids_by_alias: dict[str, set[int]] = {}
        for row in rows:
            storage_kind = str(row["storage_kind"] or "").strip().lower()
            if storage_kind != "sqlite":
                continue
            raw_headword = str(row["headword"] or "").strip()
            if not _is_split_page_headword(raw_headword):
                continue
            alias = str(row["db_alias"] or "").strip()
            entry_id = int(row["entry_row_id"] or 0)
            if alias and entry_id > 0:
                split_page_entry_ids_by_alias.setdefault(alias, set()).add(entry_id)
        for alias, entry_ids in split_page_entry_ids_by_alias.items():
            form_rows_by_entry = _fetch_split_page_form_rows_for_entries(
                conn, alias, sorted(entry_ids), lang_code=lang_code
            )
            for entry_id, form_rows in form_rows_by_entry.items():
                split_page_forms_by_ref[("sqlite", alias, entry_id)] = form_rows

        hydrated: dict[tuple[str, str, int], dict] = {}
        for row in rows:
            ref = (
                str(row["storage_kind"] or "").strip().lower(),
                str(row["db_alias"] or "").strip(),
                int(row["entry_row_id"] or 0),
            )
            entry = hydrated.get(ref)
            if entry is None:
                split_page_form_rows = split_page_forms_by_ref.get(ref, [])
                promoted_form = _choose_split_page_promoted_form(
                    split_page_form_rows,
                    match_key=str(row["match_key"] or "").strip(),
                    form_row_id=int(row["form_row_id"] or 0),
                )
                promoted_headword = str(
                    promoted_form.get("form_text") or row["headword"] or ""
                ).strip()
                promoted_romanization = str(
                    promoted_form.get("romanization") or row["romanization"] or ""
                ).strip()
                entry = {
                    "headword": promoted_headword or row["headword"],
                    "glosses": row["glosses"],
                    "forms": [],
                    "romanization": promoted_romanization,
                    "pos": row["pos"] or "",
                    "commentary": row["commentary"] or "",
                    "lemma": row["lemma"] or "",
                    "source": row["source"] or "",
                    "entry_id": row["entry_id"] or "",
                    "tags": row["tags"] or "",
                    "format": row["format"] or "compact",
                    "etymology": row["etymology"] or "",
                    "etymology_number": row["etymology_number"] or 0,
                    "_storage_kind": ref[0],
                    "_storage_db_alias": ref[1],
                    "_storage_row_id": ref[2],
                    "_storage_form_row_id": 0,
                    "_match_kind": "headword"
                    if promoted_form
                    else str(row["match_kind"] or "").strip().lower(),
                    "_hydrated": True,
                    "_matched_forms": [],
                    "_split_page_promoted": bool(promoted_form),
                }
                hydrated[ref] = entry
        # Batch-fetch matched form rows and attach to hydrated entries.
        # Each entry is fetched once; form metadata comes from a single cheap
        # PK-indexed query on the forms table.
        if form_refs_by_entry:
            all_fids: list[int] = []
            fid_to_ekey: dict[int, tuple[str, str, int]] = {}
            fid_to_match_key: dict[int, str] = {}
            for ekey, fid_list in form_refs_by_entry.items():
                for fid, mkey in fid_list:
                    all_fids.append(fid)
                    fid_to_ekey[fid] = ekey
                    fid_to_match_key[fid] = mkey
            if all_fids:
                # Query sqlite forms table and custom forms table separately
                sqlite_fids = [fid for fid in all_fids if fid_to_ekey[fid][0] != "custom"]
                custom_fids = [fid for fid in all_fids if fid_to_ekey[fid][0] == "custom"]
                form_row_map: dict[int, dict] = {}
                if sqlite_fids:
                    # Find which alias each form belongs to — query all attached dbs
                    for alias in db_aliases:
                        qa = '"' + alias.replace('"', '""') + '"'
                        placeholders = ",".join("?" * len(sqlite_fids))
                        form_sql = f"SELECT id, form_text, morph_tags, romanization FROM {qa}.forms WHERE id IN ({placeholders})"
                        frows = conn.execute(
                            form_sql,
                            tuple(sqlite_fids),
                        ).fetchall()
                        for fr in frows:
                            form_row_map[int(fr["id"])] = {
                                "form_text": str(fr["form_text"] or "").strip(),
                                "display_text": str(fr["form_text"] or "").strip(),
                                "form_roman": str(fr["romanization"] or "").strip(),
                                "tags": str(fr["morph_tags"] or "").strip(),
                            }
                if custom_fids and include_custom:
                    placeholders = ",".join("?" * len(custom_fids))
                    form_sql = (
                        f"SELECT id, form_text, morph_tags, romanization FROM {_AGGREGATE_CUSTOM_ALIAS}.custom_dict_forms "
                        f"WHERE id IN ({placeholders})"
                    )
                    frows = conn.execute(
                        form_sql,
                        tuple(custom_fids),
                    ).fetchall()
                    for fr in frows:
                        form_row_map[int(fr["id"])] = {
                            "form_text": str(fr["form_text"] or "").strip(),
                            "display_text": str(fr["form_text"] or "").strip(),
                            "form_roman": str(fr["romanization"] or "").strip(),
                            "tags": str(fr["morph_tags"] or "").strip(),
                        }
                # Attach matched forms to hydrated entries
                for fid in all_fids:
                    ekey = fid_to_ekey[fid]
                    entry = hydrated.get(ekey)
                    if not entry:
                        continue
                    fdata = form_row_map.get(fid)
                    if not fdata:
                        continue
                    matched_form = dict(fdata)
                    mkey = fid_to_match_key.get(fid, "")
                    matched_form["index_keys"] = [mkey] if mkey else []
                    matched_form["_form_row_id"] = fid
                    if mkey and not entry.get("_form_match_key"):
                        entry["_form_match_key"] = mkey
                    if matched_form not in entry["_matched_forms"]:
                        entry["_matched_forms"].append(matched_form)
                    # Mark as form match if any form refs exist
                    if not entry.get("_split_page_promoted"):
                        entry["_match_kind"] = "form"

        # Batch-fetch special-tagged form rows (hanja, hangeul, cjk, etc.)
        # and same-headword morph variants.  These are the only forms needed
        # for the hydration response — the full inflection table is omitted
        # to keep the payload small and can be lazy-loaded on demand.
        _SPECIAL_FORM_TAGS = (
            "hanja",
            "hangeul",
            "cjk",
            "sinitic",
            "hán-nôm",
            "han-nom",
            "hannom",
        )
        _special_tag_clause = " OR ".join(
            f"LOWER(f.morph_tags) LIKE '%{tag}%'" for tag in _SPECIAL_FORM_TAGS
        )
        for alias in db_aliases:
            qa = '"' + alias.replace('"', '""') + '"'
            # Collect entry IDs for this alias
            alias_eids = [ekey[2] for ekey in hydrated if ekey[1] == alias and ekey[0] == "sqlite"]
            if not alias_eids:
                continue
            # Fetch special-tagged forms + same-headword morph variants
            for chunk_start in range(0, len(alias_eids), 900):
                chunk = alias_eids[chunk_start : chunk_start + 900]
                placeholders = ",".join("?" * len(chunk))
                special_sql = (
                    f"SELECT f.entry_id, f.form_text, f.morph_tags, f.romanization"
                    f" FROM {qa}.forms f"
                    f" JOIN {qa}.entries e ON e.id = f.entry_id"
                    f" WHERE f.entry_id IN ({placeholders})"
                    f"   AND ({_special_tag_clause}"
                    f"        OR LOWER(f.form_text) = LOWER(e.headword))"
                )
                srows = conn.execute(special_sql, tuple(chunk)).fetchall()
                for sr in srows:
                    eid = int(sr["entry_id"])
                    ekey = ("sqlite", alias, eid)
                    entry = hydrated.get(ekey)
                    if entry is None:
                        continue
                    form_row = [
                        str(sr["form_text"] or "").strip(),
                        str(sr["morph_tags"] or "").strip(),
                        str(sr["romanization"] or "").strip(),
                    ]
                    # Append to the forms field (which starts as '' from hydration SQL)
                    existing = entry.get("forms")
                    if not existing or existing == "[]":
                        entry["forms"] = [form_row]
                    elif isinstance(existing, list):
                        existing.append(form_row)
                    else:
                        try:
                            parsed = json.loads(existing)
                            parsed.append(form_row)
                            entry["forms"] = parsed
                        except Exception:
                            entry["forms"] = [form_row]

        # Attach community notes from EntryNote table
        try:
            from db import EntryNote

            note_keys = set()
            for ref_key, ent in hydrated.items():
                alias = ent.get("_storage_db_alias", "")
                row_id = ent.get("_storage_row_id", 0)
                if alias and row_id:
                    note_keys.add((alias, row_id))
            if note_keys:
                notes = EntryNote.query.filter(
                    EntryNote.language == lang_code,
                ).all()
                note_map = {}
                for n in notes:
                    note_map[(n.db_alias, n.entry_row_id)] = n.note
                for ref_key, ent in hydrated.items():
                    alias = ent.get("_storage_db_alias", "")
                    row_id = ent.get("_storage_row_id", 0)
                    ntext = note_map.get((alias, row_id))
                    if ntext:
                        ent["note"] = ntext
        except Exception:
            pass

        # Decomps are keyed by (language, surface_form) and attached
        # client-side after hydration via /api/entry_decomp/batch. The server
        # does not know each entry's visible surface at this point, and trying
        # to attach by entry row_id (as earlier versions did) caused inflected
        # decomps to leak onto stem lookups.

        return hydrated

    return _run()


def _normalize_keys_via_js(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Batch-normalize (text, lang_code) pairs via tools/normalize_keys.js.

    This is the sole normalization path. No Python fallback.
    Use at index-build time and custom-entry-save time, not per-query.
    """
    if not pairs:
        return {}
    unique_pairs = list(dict.fromkeys(pairs))  # deduplicate, preserve order
    input_lines = "\n".join(
        json.dumps({"text": t, "lang": l}, ensure_ascii=False) for t, l in unique_pairs
    )
    result = subprocess.run(
        ["node", str(_JS_NORMALIZER)],
        input=input_lines,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"normalize_keys.js exited {result.returncode}: {result.stderr.strip()}")
    out: dict[tuple[str, str], str] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        out[(str(obj.get("text", "")), str(obj.get("lang", "")))] = str(obj.get("key", ""))
    return out




def _iter_custom_forms(
    lang_code: str,
    forms_json: str | list | None,
) -> list[tuple[str, str, str]]:
    """Parse forms JSON and return (form_text, morph_tags, romanization) tuples."""
    records: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    try:
        forms_list = forms_json if isinstance(forms_json, list) else json.loads(forms_json or "[]")
    except Exception:
        return records
    if not isinstance(forms_list, list):
        return records
    for form in forms_list:
        form_text = ""
        morph_tags = ""
        romanization = ""
        if isinstance(form, (list, tuple)):
            form_text = str(form[0] if len(form) > 0 else "").strip()
            morph_tags = str(form[1] if len(form) > 1 else "").strip()
            romanization = str(form[2] if len(form) > 2 else "").strip()
        elif isinstance(form, dict):
            form_text = str(form.get("form") or form.get("text") or "").strip()
            morph_tags = str(
                form.get("tags") or form.get("label") or form.get("commentary") or ""
            ).strip()
            romanization = str(
                form.get("romanization") or form.get("reading") or form.get("pronunciation") or ""
            ).strip()
        if not form_text:
            continue
        ident = (form_text, morph_tags, romanization)
        if ident in seen:
            continue
        seen.add(ident)
        records.append(ident)
    return records


def ensure_custom_form_index(force_rebuild: bool = False) -> None:
    global _custom_form_index_ready
    if _custom_form_index_ready and not force_rebuild:
        return
    if not APP_DB_PATH.exists():
        _custom_form_index_ready = True
        return
    with _custom_form_index_lock:
        if _custom_form_index_ready and not force_rebuild:
            return
        conn = sqlite3.connect(str(APP_DB_PATH))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_dict_forms (
                    id INTEGER PRIMARY KEY,
                    entry_pk INTEGER NOT NULL,
                    language TEXT NOT NULL,
                    form_text TEXT NOT NULL,
                    morph_tags TEXT NOT NULL DEFAULT '',
                    romanization TEXT NOT NULL DEFAULT '',
                    UNIQUE(entry_pk, form_text, morph_tags, romanization)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_custom_dict_forms_entry_pk ON custom_dict_forms (entry_pk)"
            )
            should_rebuild = bool(force_rebuild)
            if not should_rebuild:
                form_count = int(
                    conn.execute("SELECT COUNT(*) FROM custom_dict_forms").fetchone()[0] or 0
                )
                entry_count = int(
                    conn.execute("SELECT COUNT(*) FROM custom_dict_entries").fetchone()[0] or 0
                )
                should_rebuild = form_count == 0 and entry_count > 0
            if should_rebuild:
                conn.execute("DELETE FROM custom_dict_forms")
                rows = conn.execute(
                    "SELECT id, language, forms_json FROM custom_dict_entries"
                ).fetchall()
                for row in rows:
                    lang = str(row[1] or "").strip().lower()
                    for form_text, morph_tags, romanization in _iter_custom_forms(lang, row[2]):
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO custom_dict_forms
                                (entry_pk, language, form_text, morph_tags, romanization)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                int(row[0]),
                                lang,
                                form_text,
                                morph_tags,
                                romanization,
                            ),
                        )
            conn.commit()
            _custom_form_index_ready = True
        finally:
            conn.close()


def sync_custom_form_index_entry(
    entry_pk: int, lang_code: str, forms_json: str | list | None
) -> None:
    if not APP_DB_PATH.exists() or not entry_pk:
        return
    ensure_custom_form_index()
    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        lang = str(lang_code or "").strip().lower()
        conn.execute("DELETE FROM custom_dict_forms WHERE entry_pk = ?", (int(entry_pk),))
        for form_text, morph_tags, romanization in _iter_custom_forms(lang, forms_json):
            conn.execute(
                """
                INSERT OR IGNORE INTO custom_dict_forms
                    (entry_pk, language, form_text, morph_tags, romanization)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(entry_pk), lang, form_text, morph_tags, romanization),
            )
        conn.commit()
    finally:
        conn.close()


def delete_custom_form_index_entry(entry_pk: int) -> None:
    if not APP_DB_PATH.exists() or not entry_pk:
        return
    ensure_custom_form_index()
    conn = sqlite3.connect(str(APP_DB_PATH))
    try:
        conn.execute("DELETE FROM custom_dict_forms WHERE entry_pk = ?", (int(entry_pk),))
        conn.commit()
    finally:
        conn.close()


def is_available(lang_code: str, source: str = "") -> bool:
    """Check if any SQLite dictionary exists for a given language."""
    return len(_resolve_all_db_paths(lang_code)) > 0
