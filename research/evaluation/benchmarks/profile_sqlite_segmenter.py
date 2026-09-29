"""
profile_sqlite_segmenter.py
----------------------------
Profiles the SQLite segmenter pipeline for Arabic text.
Instruments: Trankit tokenization, key normalization, SQLite lookups,
greedy DP algorithm, entry hydration, and per-token segmentation.

Usage (from PowerShell):
    python profile_sqlite_segmenter.py
"""

from __future__ import annotations

import sys
import os
import time
import functools
import json
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager

# ── ensure project root is on sys.path ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── The Arabic paragraph (stored as a variable to avoid shell encoding woes) ─
TEXT = (
    "\u062a\u0623\u0633\u0633\u062a \u0627\u0644\u0628\u0644\u0627\u062f"
    " \u0639\u0646 \u0637\u0631\u064a\u0642"
    " \u062b\u0644\u0627\u062b\u0629 \u0639\u0634\u0631\u064e"
    " \u0645\u064f\u0633\u062a\u0639\u0645\u0631\u0629"
    " \u0628\u0631\u064a\u0637\u0627\u0646\u064a\u0629"
    " \u0639\u0644\u0649 \u0637\u0648\u0644"
    " \u0633\u0627\u062d\u0644"
    " \u0627\u0644\u0645\u062d\u064a\u0637"
    " \u0627\u0644\u0623\u0637\u0644\u0633\u064a\u060c"
    " \u0643\u0627\u0646\u062a \u0623\u0648\u0644\u0627\u0647\u0627"
    " \u0645\u0633\u062a\u0639\u0645\u0631\u0629"
    " \u00ab\u0641\u0631\u062c\u064a\u0646\u064a\u0627\u00bb"
    " \u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a\u0629\u060c"
    " \u0627\u0644\u062a\u064a \u0623\u0637\u0644\u0642"
    " \u0639\u0644\u064a\u0647\u0627"
    " \u0645\u0643\u062a\u0634\u0641\u0647\u0627\u060c"
    " \u0627\u0644\u0633\u064a\u0631 \u0648\u0627\u0644\u062a\u0631"
    " \u0631\u0627\u0644\u064a \u0647\u0630\u0627"
    " \u0627\u0644\u0627\u0633\u0645"
    " \u062a\u064a\u0645\u0646\u064b\u0627"
    " \u0628\u0627\u0644\u0645\u0644\u0643\u0629"
    " \u0627\u0644\u0639\u0630\u0631\u0627\u0621"
    " \u0625\u0644\u064a\u0632\u0627\u0628\u064a\u062b."
    " \u0627\u0632\u062f\u0627\u062f\u062a \u0648\u062a\u064a\u0631\u0629"
    " \u0627\u0644\u0627\u0633\u062a\u064a\u0637\u0627\u0646"
    " \u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a"
    " \u0639\u0644\u0649"
    " \u0627\u0644\u0633\u0627\u062d\u0644"
    " \u0627\u0644\u0634\u0631\u0642\u064a"
    " \u0628\u0639\u062f \u0638\u0647\u0648\u0631"
    " \u0634\u0631\u0643\u0627\u062a \u0647\u062f\u0641\u062a"
    " \u0625\u0644\u0649 \u062a\u0634\u062c\u064a\u0639"
    " \u062d\u0631\u0643\u0629"
    " \u0627\u0644\u0627\u0633\u062a\u064a\u0637\u0627\u0646"
    " \u0641\u064a \u0623\u0631\u0627\u0636\u064a"
    " \u0645\u0627 \u0648\u0631\u0627\u0621"
    " \u0627\u0644\u0628\u062d\u0627\u0631\u060c"
    " \u0627\u0644\u062a\u064a \u0644\u0627\u0642\u062a"
    " \u0631\u0648\u0627\u062c\u064b\u0627"
    " \u0645\u0646 \u0627\u0644\u0646\u0627\u0633"
    " \u0628\u0633\u0628\u0628"
    " \u0627\u0644\u0623\u0632\u0645\u0627\u062a"
    " \u0627\u0644\u0627\u0642\u062a\u0635\u0627\u062f\u064a\u0629"
    " \u0648\u0627\u0644\u0628\u0637\u0627\u0644\u0629"
    " \u0648\u0627\u0644\u0627\u0636\u0637\u0647\u0627\u062f"
    " \u0627\u0644\u062f\u064a\u0646\u064a."
    " \u062a\u0623\u0633\u0633\u062a \u0645\u062f\u064a\u0646\u0629"
    " \u062c\u064a\u0645\u0633\u062a\u0627\u0648\u0646"
    " \u0633\u0646\u0629 1607 \u0641\u064a"
    " \u0623\u0631\u0627\u0636\u064a"
    " \u0641\u0631\u062c\u064a\u0646\u064a\u0627\u060c"
    " \u0641\u0643\u0627\u0646\u062a"
    " \u0623\u0648\u0651\u0644"
    " \u0627\u0633\u062a\u064a\u0637\u0627\u0646"
    " \u0625\u0646\u062c\u0644\u064a\u0632\u064a"
    " \u0646\u0627\u062c\u062d"
    " \u0641\u064a \u0623\u0631\u0627\u0636\u064a"
    " \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a"
    " \u0627\u0644\u0645\u062a\u062d\u062f\u0629"
    " \u0627\u0644\u0645\u0633\u062a\u0642\u0628\u0644\u064a\u0629."
    " \u062a\u0644\u0649 \u0630\u0644\u0643"
    " \u062a\u0623\u0633\u064a\u0633"
    " \u0645\u0633\u062a\u0639\u0645\u0631\u0627\u062a"
    " \u0623\u062e\u0631\u0649 \u0647\u064a:"
    " \u0646\u064a\u0648\u0647\u0627\u0645\u0634\u064a\u0631\u060c"
    " \u0648\u0645\u0627\u0633\u0627\u062a\u0634\u0648\u0633\u062a\u0633\u060c"
    " \u0648\u0643\u0648\u0646\u062a\u064a\u0643\u062a\u060c"
    " \u0648\u0631\u0648\u062f \u0622\u064a\u0644\u0627\u0646\u062f\u060c"
    " \u0648\u0645\u0631\u064a\u0644\u0627\u0646\u062f\u060c"
    " \u0648\u0643\u0627\u0631\u0648\u0644\u064a\u0646\u0627"
    " \u0627\u0644\u062c\u0646\u0648\u0628\u064a\u0629\u060c"
    " \u0648\u0643\u0627\u0631\u0648\u0644\u064a\u0646\u0627"
    " \u0627\u0644\u0634\u0645\u0627\u0644\u064a\u0629\u060c"
    " \u0648\u0646\u064a\u0648\u064a\u0648\u0631\u0643\u060c"
    " \u0648\u0646\u064a\u0648\u062c\u064a\u0631\u0633\u064a\u060c"
    " \u0648\u062f\u064a\u0644\u0627\u0648\u064a\u0631\u060c"
    " \u0648\u0628\u0646\u0633\u0644\u0641\u0627\u0646\u064a\u0627."
    " \u0648\u0643\u0627\u0646 \u0623\u0628\u0646\u0627\u0621"
    " \u0647\u0630\u0647"
    " \u0627\u0644\u0645\u0633\u062a\u0639\u0645\u0631\u0627\u062a"
    " \u064a\u0634\u062a\u063a\u0644\u0648\u0646"
    " \u0628\u0627\u0644\u0632\u0631\u0627\u0639\u0629"
    " \u0648\u0627\u0644\u062a\u062d\u0637\u064a\u0628"
    " \u0648\u0627\u0644\u062a\u0639\u062f\u064a\u0646"
    " \u0648\u0627\u0644\u062a\u062c\u0627\u0631\u0629"
    " \u0648\u062a\u0631\u0628\u064a\u0629"
    " \u0627\u0644\u0645\u0648\u0627\u0634\u064a\u060c"
    " \u0648\u0642\u062f \u062a\u0634\u0643\u0651\u0644"
    " \u0633\u0643\u0627\u0646\u0647\u0627"
    " \u0645\u0646 \u062e\u0644\u064a\u0637"
    " \u0625\u0646\u062c\u0644\u064a\u0632\u064a"
    " \u0648\u0623\u0648\u0631\u0648\u0628\u064a"
    " \u0628\u0633\u0628\u0628 \u062a\u062f\u0641\u0642"
    " \u0627\u0644\u0645\u0647\u0627\u062c\u0631\u064a\u0646"
    " \u0627\u0644\u0623\u0648\u0631\u0648\u0628\u064a\u064a\u0646"
    " \u0627\u0644\u0622\u062e\u0631\u064a\u0646"
    " \u0625\u0644\u064a\u0647\u0627."
    " \u0623\u0635\u062f\u0631\u062a \u0647\u0630\u0647"
    " \u0627\u0644\u0645\u0633\u062a\u0639\u0645\u0631\u0627\u062a"
    " \u0625\u0639\u0644\u0627\u0646"
    " \u0627\u0644\u0627\u0633\u062a\u0642\u0644\u0627\u0644"
    " \u0641\u064a \u0627\u0644\u0631\u0627\u0628\u0639"
    " \u0645\u0646 \u064a\u0648\u0644\u064a\u0648"
    " \u0639\u0627\u0645 1776\u060c"
    " \u0648\u0627\u0644\u0630\u064a \u0623\u0642\u0631"
    " \u0628\u0627\u0633\u062a\u0642\u0644\u0627\u0644\u0647\u0645"
    " \u0639\u0646 \u0628\u0631\u064a\u0637\u0627\u0646\u064a\u0627"
    " \u0627\u0644\u0639\u0638\u0645\u0649"
    " \u0648\u062a\u0634\u0643\u064a\u0644"
    " \u062d\u0643\u0648\u0645\u0629"
    " \u0627\u062a\u062d\u0627\u062f\u064a\u0629."
    " \u0647\u0632\u0645\u062a"
    " \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a"
    " \u0627\u0644\u0645\u062a\u0645\u0631\u062f\u0629"
    " \u0628\u0631\u064a\u0637\u0627\u0646\u064a\u0627"
    " \u0627\u0644\u0639\u0638\u0645\u0649"
    " \u0641\u064a \u0627\u0644\u062d\u0631\u0628"
    " \u0627\u0644\u062b\u0648\u0631\u064a\u0629"
    " \u0627\u0644\u0623\u0645\u0631\u064a\u0643\u064a\u0629\u060c"
    " \u0648\u0647\u064a \u0623\u0648\u0644"
    " \u062d\u0631\u0628"
    " \u0627\u0633\u062a\u0639\u0645\u0627\u0631\u064a\u0629"
    " \u0646\u0627\u062c\u062d\u0629"
    " \u062a\u062d\u0635\u0644"
    " \u0639\u0644\u0649"
    " \u0627\u0644\u0627\u0633\u062a\u0642\u0644\u0627\u0644."
    " \u0627\u0639\u062a\u0645\u062f\u062a"
    " \u0627\u062a\u0641\u0627\u0642\u064a\u0629"
    " \u0641\u064a\u0644\u0627\u062f\u0644\u0641\u064a\u0627"
    " \u0627\u0644\u062f\u0633\u062a\u0648\u0631"
    " \u0627\u0644\u0623\u0645\u064a\u0631\u0643\u064a"
    " \u0627\u0644\u062d\u0627\u0644\u064a"
    " \u0641\u064a \u0627\u0644\u0633\u0627\u0628\u0639"
    " \u0639\u0634\u0631"
    " \u0645\u0646 \u0633\u0628\u062a\u0645\u0628\u0631"
    " \u0639\u0627\u0645 1787\u061b"
    " \u0648\u062a\u0645"
    " \u0627\u0644\u062a\u0635\u062f\u064a\u0642"
    " \u0639\u0644\u064a\u0647"
    " \u0641\u064a \u0627\u0644\u0639\u0627\u0645"
    " \u0627\u0644\u062a\u0627\u0644\u064a"
    " \u0645\u0645\u0627 \u062c\u0639\u0644"
    " \u062a\u0644\u0643"
    " \u0627\u0644\u0648\u0644\u0627\u064a\u0627\u062a"
    " \u062c\u0632\u0621\u064b\u0627"
    " \u0645\u0646 \u062c\u0645\u0647\u0648\u0631\u064a\u0629"
    " \u0648\u0627\u062d\u062f\u0629"
    " \u0644\u0647\u0627 \u062d\u0643\u0648\u0645\u0629"
    " \u0645\u0631\u0643\u0632\u064a\u0629 \u0642\u0648\u064a\u0629."
    " \u0643\u0645\u0627 \u062a\u0645"
    " \u0627\u0644\u062a\u0635\u062f\u064a\u0642"
    " \u0639\u0644\u0649 \u0648\u062b\u064a\u0642\u0629"
    " \u0627\u0644\u062d\u0642\u0648\u0642"
    " \u0641\u064a \u0639\u0627\u0645 1791\u060c"
    " \u0648\u062a\u0636\u0645"
    " \u0639\u0634\u0631\u0629"
    " \u062a\u0639\u062f\u064a\u0644\u0627\u062a"
    " \u062f\u0633\u062a\u0648\u0631\u064a\u0629"
    " \u0644\u062a\u0636\u0645\u0646"
    " \u0627\u0644\u0643\u062b\u064a\u0631"
    " \u0645\u0646 \u0627\u0644\u062d\u0642\u0648\u0642"
    " \u0627\u0644\u0645\u062f\u0646\u064a\u0629"
    " \u0627\u0644\u0623\u0633\u0627\u0633\u064a\u0629"
    " \u0648\u0627\u0644\u062d\u0631\u064a\u0627\u062a."
)

LANG_CODE = "ar"

# ═══════════════════════════════════════════════════════════════════════════════
# Timing infrastructure
# ═══════════════════════════════════════════════════════════════════════════════

_timings: dict[str, list[float]] = defaultdict(list)


@contextmanager
def timed(label: str):
    """Context manager that records wall-clock time under *label*."""
    t0 = time.perf_counter()
    yield
    _timings[label].append(time.perf_counter() - t0)


def patch_function(module, func_name: str, label: str):
    """Monkey-patch *module.func_name* so every call is timed under *label*."""
    original = getattr(module, func_name)

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = original(*args, **kwargs)
        _timings[label].append(time.perf_counter() - t0)
        return result

    setattr(module, func_name, wrapper)
    return original


def patch_method(cls, method_name: str, label: str):
    """Monkey-patch an unbound method on *cls* so every call is timed."""
    original = getattr(cls, method_name)

    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        t0 = time.perf_counter()
        result = original(self, *args, **kwargs)
        _timings[label].append(time.perf_counter() - t0)
        return result

    setattr(cls, method_name, wrapper)
    return original


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 78)
    print("  SQLite Segmenter Pipeline Profiler")
    print("=" * 78)
    print(f"\nText length: {len(TEXT)} chars")
    print(f"Language: {LANG_CODE}\n")

    # ── 1. Import & instrument ──────────────────────────────────────────────
    print("[1/5] Importing modules ...")
    with timed("import_modules"):
        from language_registry import init_all, run_trankit, LANGUAGE_REGISTRY
        from universal_normalization import run_with_universal_normalization
        from pipeline_common import process_lookup_nlp_only
        from sqlite_segmenter import SQLiteDictionarySegmenter
        import dict_lookup_sqlite

    # Monkey-patch the hot functions BEFORE anything runs
    print("[2/5] Instrumenting functions ...")

    import sqlite_segmenter as _seg_mod

    # Key normalization — patch on BOTH modules (sqlite_segmenter imports its own copy)
    patch_function(dict_lookup_sqlite, "_normalize_key", "dict:_normalize_key")
    patch_function(_seg_mod, "_normalize_key", "dict:_normalize_key")  # re-exported binding

    # SQLite query layer — patch on BOTH the source module AND the segmenter's local binding
    patch_function(dict_lookup_sqlite, "probe_lookup_keys", "dict:probe_lookup_keys")
    patch_function(_seg_mod, "probe_lookup_keys", "dict:probe_lookup_keys")

    patch_function(dict_lookup_sqlite, "hydrate_winner_refs", "dict:hydrate_winner_refs")
    patch_function(_seg_mod, "hydrate_winner_refs", "dict:hydrate_winner_refs")

    # Segmenter methods
    patch_method(SQLiteDictionarySegmenter, "lookup_all", "seg:lookup_all")
    patch_method(SQLiteDictionarySegmenter, "build_surface_lemma_aware_lookup", "seg:build_surface_lemma_aware_lookup")
    patch_method(SQLiteDictionarySegmenter, "_greedy_fill_simple", "seg:_greedy_fill_simple")
    patch_method(SQLiteDictionarySegmenter, "segment_token", "seg:segment_token")
    patch_method(SQLiteDictionarySegmenter, "_normalize_cached", "seg:_normalize_cached")
    patch_method(SQLiteDictionarySegmenter, "_prefetch_candidate_keys", "seg:_prefetch_candidate_keys")
    patch_method(SQLiteDictionarySegmenter, "_build_span_key_matrix", "seg:_build_span_key_matrix")
    patch_method(SQLiteDictionarySegmenter, "_materialize_candidates_for_lookup", "seg:_materialize_candidates")

    # Also patch fill_token if it exists
    if hasattr(SQLiteDictionarySegmenter, "fill_token"):
        patch_method(SQLiteDictionarySegmenter, "fill_token", "seg:fill_token")

    # ── 2. Init Trankit ─────────────────────────────────────────────────────
    print("[3/5] Initializing Trankit + dictionaries (one-time cost) ...")
    with timed("init_all"):
        init_all()
    print(f"       init_all took {_timings['init_all'][0]:.3f}s\n")

    # ── 3. Run Trankit tokenizer ────────────────────────────────────────────
    print("[4/5] Running Trankit tokenizer on Arabic text ...")
    with timed("trankit_tokenize"):
        trankit_doc = run_trankit(TEXT, LANG_CODE)
    print(f"       Trankit took {_timings['trankit_tokenize'][0]:.3f}s")

    sentences = trankit_doc.get("sentences", [])
    token_count = sum(len(s.get("tokens", [])) for s in sentences)
    print(f"       Tokens produced: {token_count}\n")

    # ── 4. Build NLP overlay (process_lookup_nlp_only) ──────────────────────
    print("[5/5] Running SQLite segmenter pipeline per token ...")

    with timed("process_lookup_nlp_only"):
        nlp_result = process_lookup_nlp_only(
            TEXT, trankit_doc, trankit_lang=LANG_CODE, enable_debug_capture=False,
        )

    # Now run the segmenter on every token
    segmenter = SQLiteDictionarySegmenter(LANG_CODE)

    segments = nlp_result.get("segments", [])
    ud_tokens = []
    ud_overlay = nlp_result.get("ud_overlay", {})
    for tok in ud_overlay.get("tokens", []):
        ud_tokens.append(tok)

    token_details = []

    with timed("total_segmentation_loop"):
        for i, seg_text in enumerate(segments):
            word = str(seg_text or "")
            if not word.strip():
                continue
            tok_info = ud_tokens[i] if i < len(ud_tokens) else {}
            lemma = str(tok_info.get("lemma") or "")
            upos = str(tok_info.get("upos") or "X")
            xpos = str(tok_info.get("tag") or "")

            t0 = time.perf_counter()
            result = segmenter.build_surface_lemma_aware_lookup(
                word, lemma, upos=upos, xpos=xpos, debug=False,
            )
            elapsed = time.perf_counter() - t0
            fill = result.get("fill", {})
            mode = fill.get("mode", "?")
            n_entries = len(result.get("all_entries", []))
            token_details.append({
                "token": word,
                "lemma": lemma,
                "upos": upos,
                "elapsed_ms": elapsed * 1000,
                "mode": mode,
                "entries": n_entries,
            })

    # ═══════════════════════════════════════════════════════════════════════
    # Report
    # ═══════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 78)
    print("  TIMING REPORT")
    print("=" * 78)

    # Top-level phases
    phase_order = [
        ("init_all",                "Init Trankit + dicts"),
        ("trankit_tokenize",        "Trankit tokenization"),
        ("process_lookup_nlp_only", "process_lookup_nlp_only"),
        ("total_segmentation_loop", "Segmentation loop (all tokens)"),
    ]
    print("\n--- Top-level phases ---")
    print(f"  {'Phase':<40} {'Total (s)':>10}  {'Calls':>6}")
    print(f"  {'-'*40} {'-'*10}  {'-'*6}")
    for key, desc in phase_order:
        vals = _timings.get(key, [])
        total = sum(vals)
        print(f"  {desc:<40} {total:>10.4f}  {len(vals):>6}")

    # Per-function breakdown
    func_keys = [
        ("dict:_normalize_key",                "Key normalization (_normalize_key)"),
        ("dict:probe_lookup_keys",             "SQLite probe (probe_lookup_keys)"),
        ("dict:hydrate_winner_refs",           "Entry hydration (hydrate_winner_refs)"),
        ("seg:_normalize_cached",              "Cached normalization (_normalize_cached)"),
        ("seg:lookup_all",                     "Segmenter lookup_all"),
        ("seg:_prefetch_candidate_keys",       "Prefetch candidates (batch SQLite)"),
        ("seg:_build_span_key_matrix",         "Build span key matrix"),
        ("seg:_materialize_candidates",        "Materialize candidates for lookup"),
        ("seg:build_surface_lemma_aware_lookup", "build_surface_lemma_aware_lookup"),
        ("seg:segment_token",                  "segment_token"),
        ("seg:_greedy_fill_simple",            "Greedy DP (_greedy_fill_simple)"),
        ("seg:fill_token",                     "fill_token"),
    ]

    print("\n--- Per-function breakdown (across all tokens) ---")
    print(f"  {'Function':<45} {'Total (s)':>10}  {'Avg (ms)':>10}  {'Calls':>6}")
    print(f"  {'-'*45} {'-'*10}  {'-'*10}  {'-'*6}")
    for key, desc in func_keys:
        vals = _timings.get(key, [])
        if not vals:
            continue
        total = sum(vals)
        avg_ms = (total / len(vals)) * 1000
        print(f"  {desc:<45} {total:>10.4f}  {avg_ms:>10.3f}  {len(vals):>6}")

    # Sorted by total time descending
    print("\n--- Functions ranked by total time ---")
    ranked = []
    for key, desc in func_keys:
        vals = _timings.get(key, [])
        if vals:
            ranked.append((desc, sum(vals), len(vals)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    for i, (desc, total, calls) in enumerate(ranked, 1):
        pct = (total / sum(v for _, v, _ in ranked)) * 100 if ranked else 0
        bar = "#" * int(pct / 2)
        print(f"  {i}. {desc:<45} {total:>8.4f}s  ({pct:5.1f}%)  {bar}")

    # Per-token details (top 20 slowest)
    print("\n--- Top 20 slowest tokens ---")
    token_details.sort(key=lambda x: x["elapsed_ms"], reverse=True)
    print(f"  {'#':<4} {'Token':<25} {'Lemma':<20} {'UPOS':<6} {'Time (ms)':>10} {'Mode':<10} {'Entries':>7}")
    print(f"  {'-'*4} {'-'*25} {'-'*20} {'-'*6} {'-'*10} {'-'*10} {'-'*7}")
    for i, d in enumerate(token_details[:20], 1):
        tok_display = d["token"][:24]
        lem_display = d["lemma"][:19]
        print(f"  {i:<4} {tok_display:<25} {lem_display:<20} {d['upos']:<6} {d['elapsed_ms']:>10.3f} {d['mode']:<10} {d['entries']:>7}")

    # Summary
    total_seg_time = sum(d["elapsed_ms"] for d in token_details)
    print(f"\n  Total segmentation time: {total_seg_time:.1f} ms across {len(token_details)} tokens")
    if token_details:
        print(f"  Average per token:       {total_seg_time / len(token_details):.3f} ms")

    print("\n" + "=" * 78)
    print("  Done.")
    print("=" * 78)


if __name__ == "__main__":
    main()
