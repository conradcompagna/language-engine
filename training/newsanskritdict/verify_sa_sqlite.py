#!/usr/bin/env python3
"""Manual spot-check: 10 entries in the new sa.sqlite.

For each picked lemma_id:
  1. Print the entry row (headword, pos, glosses).
  2. Print every forms row attached to it.
  3. Grep the raw CSV for the lemma's line and confirm headword/gloss match.
  4. Grep the raw conllu corpus for `LemmaId=<id>|` occurrences and, for a
     sample, print the raw token line so a human can check that:
       (a) every unique (surface, unsandhied, feats) tuple that should have
           generated forms rows actually did,
       (b) no identical-duplicate forms rows leaked through.
"""

import csv
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
DB = ROOT / "dict_sqlite" / "sa.sqlite"
DCS_ROOT = Path(__file__).resolve().parent / "data" / "conllu"
CSV_PATH = DCS_ROOT / "lookup" / "dictionary.csv"
CONLLU_ROOT = DCS_ROOT / "files"

# Mirror the build script's normalize_feats so we can reconstruct the
# exact morph_tags we should expect from each token line.
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
    "Aspect": {"Perf": "perfective", "Imp": "imperfective", "Hab": "habitual", "Iter": "iterative"},
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
    if not feats_field or feats_field == "_":
        return ""
    kv = {}
    for pair in feats_field.split("|"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            kv[k] = v
    out = []
    for key in FEAT_ORDER:
        if key not in kv:
            continue
        raw = kv[key]
        out.append(FEAT_MAP.get(key, {}).get(raw, raw.lower()))
    return ";".join(out)


def norm_cmp(s):
    return unicodedata.normalize("NFKC", (s or "").strip().lower()) if s else ""


def is_junk_form(s):
    if not s:
        return True
    if s == "_":
        return True
    if "]" in s or "[" in s:
        return True
    return False


MISC_LEMMA_RE = re.compile(r"(?:^|\|)LemmaId=(\d+)")
MISC_UNS_RE = re.compile(r"(?:^|\|)Unsandhied=([^|]+)")

# Picked lemma ids: mix of noun / adj / verb / pron / adv.
# Includes the three from the user's examples (169501, 162663, 173892) plus
# seven more chosen to exercise verbs, participles, pronouns, and indeclinables.
# Bound to existing conllu occurrences (sampled before picking).
TARGETS = [
    169501,  # kākacaṇḍīśvara (user's example #1 - noun)
    162663,  # pratiṣṭhā      (user's example #2 - verb)
    173892,  # rasasiddha     (user's example #3 - noun)
    44133,  # namas          (noun)
    148996,  # buddha         (common noun)
    37877,  # yad            (relative pronoun)
    157144,  # ca             (conjunction)
    157282,  # han            (verb, classic root)
    105161,  # sarvathā       (adverb)
    20335,  # andhakāra      (noun)
]


def _open_long(p):
    sp = str(p)
    if os.name == "nt" and not sp.startswith("\\\\?\\"):
        sp = "\\\\?\\" + os.path.abspath(sp)
    return open(sp, encoding="utf-8")


def load_csv_row(lemma_id):
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for r in reader:
            if not r:
                continue
            try:
                if int(r[0]) == lemma_id:
                    return dict(zip(header, r))
            except ValueError:
                continue
    return None


def collect_all_occurrences(target_ids):
    """Single pass over all conllu files; collect matching token lines
    grouped by lemma_id. Avoids re-scanning the whole corpus N times."""
    target_set = set(target_ids)
    needles = {f"LemmaId={lid}|" for lid in target_set}
    by_lemma = {lid: [] for lid in target_set}
    print(f"scanning conllu (single pass) for {len(target_set)} lemmas...", flush=True)
    scanned = 0
    for sub in sorted(os.listdir(CONLLU_ROOT)):
        d = CONLLU_ROOT / sub
        if not d.is_dir():
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".conllu"):
                continue
            scanned += 1
            fp = d / fn
            try:
                with _open_long(fp) as f:
                    for line in f:
                        # Cheap prefilter: must contain at least one needle
                        if "LemmaId=" not in line:
                            continue
                        # Only do the heavier check after cheap one
                        matched_id = None
                        for n in needles:
                            if n in line:
                                matched_id = int(n.split("=")[1].rstrip("|"))
                                break
                        if matched_id is None:
                            continue
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) < 10:
                            continue
                        tok_id = parts[0]
                        if "-" in tok_id or "." in tok_id:
                            continue
                        by_lemma[matched_id].append(
                            {
                                "file": str(fp.relative_to(CONLLU_ROOT)),
                                "surface": parts[1],
                                "lemma_col": parts[2],
                                "upos": parts[3],
                                "feats": parts[5],
                                "misc": parts[9],
                            }
                        )
            except Exception:
                continue
            if scanned % 2000 == 0:
                print(f"  scanned {scanned} files...", flush=True)
    print(f"scan done ({scanned} files)", flush=True)
    return by_lemma


def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    print("=" * 90)
    print(f"DB: {DB}")
    print(f"Entries: {cur.execute('SELECT COUNT(*) FROM entries').fetchone()[0]:,}")
    print(f"Forms:   {cur.execute('SELECT COUNT(*) FROM forms').fetchone()[0]:,}")
    print("=" * 90)

    overall_ok = True
    occurrences_by_lemma = collect_all_occurrences(TARGETS)

    for lid in TARGETS:
        print()
        print("#" * 90)
        print(f"## lemma_id = {lid}")
        print("#" * 90)

        # --- 1. entry row ---
        row = cur.execute(
            "SELECT id, headword, pos, glosses, entry_id FROM entries WHERE id=?", (lid,)
        ).fetchone()
        if not row:
            print(f"!! MISSING entry in new DB for id={lid}")
            overall_ok = False
            continue
        print(f"entry: id={row[0]} headword={row[1]!r} pos={row[2]!r} entry_id={row[4]!r}")
        print(f"glosses: {row[3]}")

        # --- 2. csv row ---
        csv_row = load_csv_row(lid)
        if csv_row is None:
            print(f"!! MISSING in CSV (unexpected)")
            overall_ok = False
        else:
            print(
                f"csv:   word={csv_row['word']!r} grammar={csv_row['grammar']!r} "
                f"meanings={csv_row['meanings']!r}"
            )
            if csv_row["word"].strip() != row[1]:
                print(f"!! HEADWORD MISMATCH csv={csv_row['word']!r} db={row[1]!r}")
                overall_ok = False

        # --- 3. forms rows ---
        forms_rows = cur.execute(
            "SELECT id, form_text, morph_tags FROM forms WHERE entry_id=? "
            "ORDER BY form_text, morph_tags",
            (lid,),
        ).fetchall()
        print(f"db forms ({len(forms_rows)} rows):")
        for fr in forms_rows:
            print(f"  [{fr[0]}] {fr[1]!r}  tags={fr[2]!r}")

        # dedupe check
        key_counts = defaultdict(int)
        for fr in forms_rows:
            key_counts[(fr[1], fr[2])] += 1
        dups = [k for k, v in key_counts.items() if v > 1]
        if dups:
            print(f"!! DUPLICATE forms rows (same text + tags):")
            for k in dups:
                print(f"   {k} x{key_counts[k]}")
            overall_ok = False
        else:
            print("  dedupe: OK (no exact duplicate forms rows)")

        # --- 4. derive expected form keys from raw conllu ---
        occs = occurrences_by_lemma.get(lid, [])
        print(f"conllu occurrences found: {len(occs)}")
        if occs[:3]:
            print("  first 3 raw occurrences:")
            for o in occs[:3]:
                print(f"    {o['file']}")
                print(f"      surface={o['surface']!r} feats={o['feats']!r} misc={o['misc']!r}")

        headword_n = norm_cmp(row[1])
        headword_charset = set(unicodedata.normalize("NFC", row[1] or ""))
        raw_expected = set()  # pre-cleanup expected set
        surface_variants = set()
        unsandhied_variants = set()
        for o in occs:
            morph = normalize_feats(o["feats"])
            surf = o["surface"]
            um = MISC_UNS_RE.search(o["misc"])
            uns = um.group(1) if um else ""
            s_n = norm_cmp(surf)
            u_n = norm_cmp(uns)
            if surf and s_n != headword_n and not is_junk_form(surf):
                raw_expected.add((surf, morph))
                surface_variants.add(surf)
            if uns and u_n != headword_n and u_n != s_n and not is_junk_form(uns):
                tag = morph + ";sandhied" if morph else "sandhied"
                raw_expected.add((uns, tag))
                unsandhied_variants.add(uns)

        # Apply the same 3 cleanup filters used on the DB:
        #   (a) drop empty form_text or empty morph_tags
        #   (b) drop forms with no char overlap with headword
        #   (c) drop sandhied rows whose (form, base_tags) already exists plain
        filtered_empty = {(f, t) for (f, t) in raw_expected if f and f.strip() and f != "_" and t}
        filtered_chars = {
            (f, t)
            for (f, t) in filtered_empty
            if set(unicodedata.normalize("NFC", f)) & headword_charset
        }
        # sandhied-dup filter
        plain_set = {
            (f, t) for (f, t) in filtered_chars if not (t == "sandhied" or t.endswith(";sandhied"))
        }
        expected = set()
        for f, t in filtered_chars:
            if t == "sandhied":
                if (f, "") in plain_set:
                    continue
            elif t.endswith(";sandhied"):
                base = t[: -len(";sandhied")]
                if (f, base) in plain_set:
                    continue
            expected.add((f, t))

        db_keys = {(fr[1], fr[2]) for fr in forms_rows}
        missing = expected - db_keys
        extra = db_keys - expected
        print(f"expected unique (form,tags) pairs from conllu: {len(expected)}")
        print(f"  surface variants seen: {sorted(surface_variants)[:15]}")
        print(f"  unsandhied variants seen: {sorted(unsandhied_variants)[:15]}")
        if missing:
            print(f"!! MISSING from DB ({len(missing)}):")
            for m in sorted(missing)[:20]:
                print(f"   -> {m}")
            overall_ok = False
        else:
            print("  completeness: OK (every distinct (form,tags) from conllu is in DB)")
        if extra:
            # extras shouldn't happen — every DB form must trace back
            print(f"!! EXTRA DB forms not derived from conllu ({len(extra)}):")
            for m in sorted(extra)[:20]:
                print(f"   -> {m}")
            overall_ok = False

    print()
    print("=" * 90)
    print("OVERALL:", "PASS" if overall_ok else "FAIL")
    print("=" * 90)


if __name__ == "__main__":
    main()
