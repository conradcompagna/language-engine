#!/usr/bin/env python3
"""Build Sanskrit SQLite dictionary from DCS sources.

Inputs:
  - training/newsanskritdict/data/conllu/lookup/dictionary.csv  (lemma catalog)
  - training/newsanskritdict/data/conllu/files/**/*.conllu      (~15.9k files; inflections)

Output:
  - dict_sqlite/sa.sqlite  (schema matching other languages in the project)

Pipeline:
  1) Parse dictionary.csv -> entries table.
     entries.id == CSV lemma id  (so LemmaId= in conllu maps 1:1)
     POS is normalized to Wiktionary-style tags (noun/verb/adj/adv/pron/num/part).
     Glosses split on ';' into the JSON array shape used by the app.
  2) Stream every conllu token line, collect per-lemma orthographic variants.
     - Drop surface forms identical to the headword.
     - Drop Unsandhied= forms identical to the headword.
     - Keep surface (no sandhi tag) and Unsandhied (with 'sandhied' tag) when
       they differ from each other.
     - Morph features normalized to semicolon-joined single-word tokens
       (matches other DBs, e.g. 'nominative;masculine;singular').
  3) Dedupe via UNIQUE staging table, then copy into forms.
"""

import csv
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parent.parent  # project root
CSV_PATH = THIS_DIR / "data" / "conllu" / "lookup" / "dictionary.csv"
CONLLU_ROOT = THIS_DIR / "data" / "conllu" / "files"
OUT_PATH = ROOT / "dict_sqlite" / "sa.sqlite"
STAGING_PATH = ROOT / "dict_sqlite" / "sa.sqlite.staging"

# ------------------------------------------------------------------------
# POS normalization
# ------------------------------------------------------------------------
# Dictionary CSV 'grammar' column contains:
#   m, f, n, mn, mf, mfn, fn, nr, djma, djan   -> noun  (gender codes)
#   adj                                        -> adj
#   ind                                        -> adv   (indeclinables; existing DB
#                                                      labels these 'adv')
#   pron                                       -> pron
#   <digit>.P. / <digit>.Ā. / Desid./Denom./Int. combos -> verb
#   ''                                         -> '' (unknown)
NOUN_GRAMS = {"m", "f", "n", "mn", "mf", "mfn", "fn", "nr", "djma", "djan"}
VERB_GRAM_RE = re.compile(r"(?:^|,)\s*(?:\d+\s*\.\s*[PĀ]\.|Denom\.|Desid\.|Int\.)")


def normalize_pos(raw):
    if not raw:
        return ""
    g = raw.strip()
    if g in NOUN_GRAMS:
        return "noun"
    if g == "adj":
        return "adj"
    if g == "ind":
        return "adv"
    if g == "pron":
        return "pron"
    if VERB_GRAM_RE.search(g):
        return "verb"
    # Fall back: anything else we didn't classify
    return ""


# ------------------------------------------------------------------------
# Feature normalization
# ------------------------------------------------------------------------
FEAT_MAP = {
    "Case": {
        "Nom": "nominative",
        "Gen": "genitive",
        "Dat": "dative",
        "Acc": "accusative",
        "Abl": "ablative",
        "Ins": "instrumental",
        "Loc": "locative",
        "Voc": "vocative",
        "Cpd": "compound",
    },
    "Gender": {"Masc": "masculine", "Fem": "feminine", "Neut": "neuter"},
    "Number": {"Sing": "singular", "Dual": "dual", "Plur": "plural"},
    "Mood": {
        "Ind": "indicative",
        "Imp": "imperative",
        "Opt": "optative",
        "Cond": "conditional",
        "Sub": "subjunctive",
        "Jus": "jussive",
        "Prec": "precative",
    },
    "Person": {"1": "first-person", "2": "second-person", "3": "third-person"},
    "Tense": {
        "Pres": "present",
        "Past": "past",
        "Fut": "future",
        "Aor": "aorist",
        "Perf": "perfect",
        "Imp": "imperfect",
        "Impf": "imperfect",
        "Pqp": "pluperfect",
    },
    "Voice": {"Act": "active", "Pass": "passive", "Mid": "middle"},
    "VerbForm": {
        "Part": "participle",
        "Conv": "converb",
        "Fin": "finite",
        "Inf": "infinitive",
        "Ger": "gerundive",
        "Gdv": "gerundive",
        "Vnoun": "verbal-noun",
    },
    "Aspect": {
        "Perf": "perfective",
        "Imp": "imperfective",
        "Hab": "habitual",
        "Iter": "iterative",
    },
    "Degree": {"Cmp": "comparative", "Sup": "superlative", "Pos": "positive"},
    "Definite": {"Def": "definite", "Ind": "indefinite"},
    "Formation": {
        "root": "formation-root",
        "them": "formation-thematic",
        "s": "formation-sigmatic",
        "peri": "formation-periphrastic",
        "red": "formation-reduplicated",
        "is": "formation-is",
        "sa": "formation-sa",
    },
    "PronType": {
        "Dem": "demonstrative",
        "Int": "interrogative",
        "Rel": "relative",
        "Prs": "personal",
        "Neg": "negative",
        "Tot": "total",
        "Ind": "indefinite",
    },
    "NumType": {"Card": "cardinal", "Ord": "ordinal", "Mult": "multiplicative"},
    "Reflex": {"Yes": "reflexive"},
    "Polarity": {"Neg": "negative", "Pos": "positive"},
    "Foreign": {"Yes": "foreign"},
    "Compound": {"Yes": "compound"},
}
# Order of feature categories in the output string (stable across inputs)
FEAT_ORDER = [
    "Case",
    "Gender",
    "Number",
    "Person",
    "Mood",
    "Tense",
    "Voice",
    "VerbForm",
    "Aspect",
    "Degree",
    "Definite",
    "Formation",
    "PronType",
    "NumType",
    "Reflex",
    "Polarity",
    "Foreign",
    "Compound",
]


def normalize_feats(feats_field):
    """'Case=Nom|Gender=Masc|Number=Sing' -> 'nominative;masculine;singular'"""
    if not feats_field or feats_field == "_":
        return ""
    kv = {}
    for pair in feats_field.split("|"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        kv[k] = v
    parts = []
    for key in FEAT_ORDER:
        if key not in kv:
            continue
        raw_val = kv[key]
        mapped = FEAT_MAP.get(key, {}).get(raw_val)
        if mapped is None:
            mapped = raw_val.lower()
        parts.append(mapped)
    return ";".join(parts)


# ------------------------------------------------------------------------
# String normalization for headword vs surface comparison
# ------------------------------------------------------------------------
def norm_cmp(s):
    """NFKC + lowercase for comparing surface/unsandhied/headword strings."""
    if not s:
        return ""
    return unicodedata.normalize("NFKC", s).strip().lower()


def is_junk_form(s):
    """True if the surface/unsandhied string is clearly DCS annotation junk
    and not a real Sanskrit orthographic form. Kept deliberately narrow so
    we don't drop legitimate forms that happen to look unusual."""
    if not s:
        return True
    if s == "_":
        # CoNLL-U placeholder for 'no data'
        return True
    # Annotation brackets never appear in real Sanskrit surface text.
    # E.g. 'Zeichenjh]', 'letterausjhjh]', '[footnote]'.
    if "]" in s or "[" in s:
        return True
    return False


# ------------------------------------------------------------------------
# Phase 1: parse dictionary.csv -> entries
# ------------------------------------------------------------------------
def build_entries(conn):
    print("=== Phase 1: dictionary.csv -> entries ===", flush=True)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE entries (
            id          INTEGER PRIMARY KEY,
            headword    TEXT NOT NULL,
            romanization TEXT NOT NULL DEFAULT '',
            pos         TEXT NOT NULL DEFAULT '',
            glosses     TEXT NOT NULL DEFAULT '[]',
            forms       TEXT NOT NULL DEFAULT '[]',
            commentary  TEXT NOT NULL DEFAULT '',
            lemma       TEXT NOT NULL DEFAULT '',
            etymology   TEXT NOT NULL DEFAULT '',
            etymology_number INTEGER NOT NULL DEFAULT 0,
            source      TEXT NOT NULL DEFAULT '',
            entry_id    TEXT NOT NULL DEFAULT '',
            tags        TEXT NOT NULL DEFAULT '',
            format      TEXT NOT NULL DEFAULT 'compact'
        );
        """
    )

    t0 = time.time()
    rows = []
    headwords_by_id = {}
    pos_counter = {}

    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        # expected: id  word  grammar  preverbs  meanings
        idx_id = header.index("id")
        idx_word = header.index("word")
        idx_gram = header.index("grammar")
        idx_mean = header.index("meanings")
        for r in reader:
            if len(r) < len(header):
                # pad short rows
                r = r + [""] * (len(header) - len(r))
            try:
                lemma_id = int(r[idx_id])
            except ValueError:
                continue
            word = r[idx_word].strip()
            if not word:
                continue
            pos = normalize_pos(r[idx_gram])
            pos_counter[pos] = pos_counter.get(pos, 0) + 1

            meanings_raw = r[idx_mean] or ""
            # Split on ';' into discrete senses
            senses = [s.strip() for s in meanings_raw.split(";") if s.strip()]
            if senses:
                glosses_json = json.dumps([{"glosses": [s]} for s in senses], ensure_ascii=False)
            else:
                glosses_json = "[]"

            rows.append(
                (
                    lemma_id,
                    word,
                    "",  # romanization
                    pos,
                    glosses_json,
                    "[]",  # forms (attachment field, unused)
                    "",  # commentary
                    "",  # lemma (headword serves as lemma)
                    "",  # etymology
                    0,  # etymology_number
                    "dcs",  # source
                    str(lemma_id),  # entry_id (string of lemma_id)
                    "",  # tags
                    "compact",  # format
                )
            )
            headwords_by_id[lemma_id] = norm_cmp(word)

    cur.executemany(
        "INSERT INTO entries (id, headword, romanization, pos, glosses, forms, "
        "commentary, lemma, etymology, etymology_number, source, entry_id, tags, format) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"  inserted {len(rows)} entries in {time.time() - t0:.1f}s", flush=True)
    print("  POS distribution:", pos_counter, flush=True)
    return headwords_by_id


# ------------------------------------------------------------------------
# Phase 2: scan conllu files and populate staging table
# ------------------------------------------------------------------------
MISC_RE = re.compile(r"(?:^|\|)LemmaId=(\d+)")
UNSANDHIED_RE = re.compile(r"(?:^|\|)Unsandhied=([^|]+)")

# staging schema: unique constraint dedupes at insert time
STAGING_SCHEMA = """
CREATE TABLE forms_stage (
    entry_id   INTEGER NOT NULL,
    form_text  TEXT NOT NULL,
    morph_tags TEXT NOT NULL,
    UNIQUE(entry_id, form_text, morph_tags)
);
"""


def scan_conllu(conn, headwords_by_id):
    print("=== Phase 2: scan conllu files -> forms_stage ===", flush=True)
    cur = conn.cursor()
    cur.executescript("DROP TABLE IF EXISTS forms_stage; " + STAGING_SCHEMA)
    conn.commit()

    # collect file list
    files = []
    for sub in sorted(os.listdir(CONLLU_ROOT)):
        d = CONLLU_ROOT / sub
        if not d.is_dir():
            continue
        for fn in os.listdir(d):
            if fn.endswith(".conllu"):
                files.append(d / fn)
    total = len(files)
    print(f"  {total} conllu files to scan", flush=True)

    batch = []
    BATCH = 20000
    stats = {"tokens": 0, "recorded": 0, "skipped_missing_lemma": 0}
    t0 = time.time()

    # Tune pragmas for speed (staging only; we recreate the main DB file anyway)
    cur.execute("PRAGMA synchronous=OFF")
    cur.execute("PRAGMA journal_mode=MEMORY")
    cur.execute("PRAGMA temp_store=MEMORY")

    def flush():
        if not batch:
            return
        cur.executemany(
            "INSERT OR IGNORE INTO forms_stage (entry_id, form_text, morph_tags) VALUES (?,?,?)",
            batch,
        )
        batch.clear()

    SANDHIED_TAG = "sandhied"

    def _open_long_path(p):
        # Windows MAX_PATH (~260) bites us on deep DCS folders. Use the
        # extended-length \\?\ prefix for absolute paths on Windows.
        sp = str(p)
        if os.name == "nt" and not sp.startswith("\\\\?\\"):
            sp = "\\\\?\\" + os.path.abspath(sp)
        return open(sp, encoding="utf-8")

    for idx, fp in enumerate(files):
        try:
            with _open_long_path(fp) as f:
                for line in f:
                    if not line or line[0] == "#" or line[0] == "\n":
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 10:
                        continue
                    tok_id = parts[0]
                    # skip multi-word range tokens like "1-4"
                    if "-" in tok_id or "." in tok_id:
                        continue
                    surface = parts[1]
                    # parts[2] is lemma field (ignored per spec; may be '_' too)
                    feats = parts[5]
                    misc = parts[9]

                    m = MISC_RE.search(misc)
                    if not m:
                        continue
                    lemma_id = int(m.group(1))
                    stats["tokens"] += 1
                    headword_norm = headwords_by_id.get(lemma_id)
                    if headword_norm is None:
                        stats["skipped_missing_lemma"] += 1
                        continue

                    um = UNSANDHIED_RE.search(misc)
                    unsandhied = um.group(1) if um else ""

                    morph = normalize_feats(feats)

                    surface_n = norm_cmp(surface)
                    unsandhied_n = norm_cmp(unsandhied)

                    surface_keep = (
                        bool(surface) and surface_n != headword_norm and not is_junk_form(surface)
                    )
                    unsandhied_keep = (
                        bool(unsandhied)
                        and unsandhied_n != headword_norm
                        and unsandhied_n != surface_n
                        and not is_junk_form(unsandhied)
                    )

                    if surface_keep:
                        batch.append((lemma_id, surface, morph))
                        stats["recorded"] += 1
                    if unsandhied_keep:
                        # Tag as 'sandhied' per user's convention for the
                        # orthographic counterpart of the surface form.
                        tags_with_sandhi = morph + ";" + SANDHIED_TAG if morph else SANDHIED_TAG
                        batch.append((lemma_id, unsandhied, tags_with_sandhi))
                        stats["recorded"] += 1

                    if len(batch) >= BATCH:
                        flush()
                        conn.commit()
        except Exception as e:
            print(f"  !! error in {fp}: {e}", flush=True)

        if (idx + 1) % 500 == 0:
            flush()
            conn.commit()
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            eta = (total - idx - 1) / rate if rate > 0 else 0
            print(
                f"  {idx + 1}/{total} files  tokens={stats['tokens']:,}  "
                f"recorded={stats['recorded']:,}  elapsed={elapsed:.0f}s  eta={eta:.0f}s",
                flush=True,
            )

    flush()
    conn.commit()
    print(f"  scan complete in {time.time() - t0:.0f}s", flush=True)
    print(f"  stats: {stats}", flush=True)
    # post count
    row = cur.execute("SELECT COUNT(*) FROM forms_stage").fetchone()
    print(f"  forms_stage rows (deduped): {row[0]:,}", flush=True)
    return stats


# ------------------------------------------------------------------------
# Phase 3: copy staging -> forms, create indexes, write meta
# ------------------------------------------------------------------------
def finalize(conn, scan_stats):
    print("=== Phase 3: finalize forms + indexes + meta ===", flush=True)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE forms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id    INTEGER NOT NULL REFERENCES entries(id),
            form_text   TEXT NOT NULL,
            morph_tags  TEXT NOT NULL DEFAULT '',
            romanization TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    # Copy staging into forms, grouped by entry_id so forms for a lemma cluster
    cur.execute(
        "INSERT INTO forms (entry_id, form_text, morph_tags, romanization) "
        "SELECT s.entry_id, s.form_text, s.morph_tags, '' "
        "FROM forms_stage s "
        "JOIN entries e ON e.id = s.entry_id "
        "ORDER BY s.entry_id, s.form_text, s.morph_tags"
    )
    conn.commit()

    print("  creating indexes...", flush=True)
    cur.executescript(
        """
        CREATE INDEX idx_entries_lemma ON entries(lemma) WHERE lemma != '';
        CREATE INDEX idx_forms_entry_id ON forms(entry_id);
        """
    )

    ec = cur.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    fc = cur.execute("SELECT COUNT(*) FROM forms").fetchone()[0]
    print(f"  entries: {ec:,}  forms: {fc:,}", flush=True)

    # meta
    import datetime

    meta = [
        ("lang_code", "sa"),
        ("source_label", "default"),
        ("source_tsv", "DCS: training/newsanskritdict/data/conllu"),
        ("entry_count", str(ec)),
        ("form_count", str(fc)),
        ("created_at", datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
    ]
    cur.executemany("INSERT INTO meta (key, value) VALUES (?,?)", meta)

    # drop staging, analyze, vacuum
    cur.execute("DROP TABLE forms_stage")
    conn.commit()
    print("  ANALYZE...", flush=True)
    cur.execute("ANALYZE")
    conn.commit()
    return ec, fc


def main():
    if STAGING_PATH.exists():
        STAGING_PATH.unlink()
    conn = sqlite3.connect(str(STAGING_PATH))
    conn.execute("PRAGMA page_size=4096")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")
    conn.execute("PRAGMA temp_store=MEMORY")

    headwords = build_entries(conn)
    scan_stats = scan_conllu(conn, headwords)
    finalize(conn, scan_stats)

    conn.execute("VACUUM")
    conn.close()

    # swap
    if OUT_PATH.exists():
        # Keep a safety copy in case swap fails partway
        safety = OUT_PATH.with_suffix(".sqlite.old_preswap")
        if safety.exists():
            safety.unlink()
        os.replace(str(OUT_PATH), str(safety))
    os.replace(str(STAGING_PATH), str(OUT_PATH))
    # remove preswap safety if everything ok
    safety = OUT_PATH.with_suffix(".sqlite.old_preswap")
    if safety.exists():
        safety.unlink()
    print(f"DONE -> {OUT_PATH}")


if __name__ == "__main__":
    main()
