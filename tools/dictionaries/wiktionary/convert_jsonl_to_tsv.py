"""
Convert Wiktionary Kaikki JSONL dictionaries into slim TSV files.

Output columns (tab-separated):
  headword  pos  romanization  glosses  forms

- headword: the lemma word
- pos: raw Kaikki POS string
- romanization: from the forms array entry tagged ["romanization"]
- glosses: JSON array of sense objects [{glosses:[...], tags:[...], qualifier:...}, ...]
- forms: JSON array of [form_string, "tag1;tag2;tag3", romanization] triples

Form-of / alt-of entries are preserved as normal rows so relation senses
remain directly visible in the exported TSV.

Usage:
    python convert_jsonl_to_tsv.py                   # convert all JSONL files
    python convert_jsonl_to_tsv.py Turkish            # convert one language
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, "rawjsonforconversion")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "converted_tsv")

# Tags on form entries that are metadata, not actual word forms
_SKIP_FORM_TAGS = frozenset(["table-tags", "inflection-template"])

# Tags that indicate this entry is just a redirect to a lemma
_FORM_OF_TAGS = frozenset(["form-of", "alt-of"])


def is_form_of_entry(raw: dict) -> bool:
    """True if every sense in this entry is a form-of/alt-of reference."""
    senses = raw.get("senses", [])
    if not senses:
        return False
    for s in senses:
        has_form_of = bool(s.get("form_of") or s.get("alt_of"))
        tags = set(s.get("tags", []))
        has_form_tag = bool(tags & _FORM_OF_TAGS)
        if not has_form_of and not has_form_tag:
            return False
    return True


def extract_relation_parents(raw: dict, relation_keys: tuple) -> list:
    """Collect unique parent lemma words from sense relation fields."""
    out = []
    seen = set()
    senses = raw.get("senses", [])
    if not isinstance(senses, list):
        return out

    for s in senses:
        if not isinstance(s, dict):
            continue
        for rel_key in relation_keys:
            rel = s.get(rel_key, [])
            if not isinstance(rel, list):
                continue
            for rel_obj in rel:
                if not isinstance(rel_obj, dict):
                    continue
                parent = str(rel_obj.get("word", "")).strip()
                if not parent or parent in seen:
                    continue
                seen.add(parent)
                out.append(parent)

    return out


def should_skip_language_pos_entry(raw: dict, pos: str) -> bool:
    """Language-specific POS skip rules for cleaner TSV output."""
    # Keep all POS categories in converter output. Language-specific filtering
    # belongs in runtime/UI rules, not TSV generation.
    return False


def extract_romanization(forms: list) -> str:
    """Pull the romanization string from the forms array."""
    for f in forms:
        tags = f.get("tags", [])
        if tags == ["romanization"]:
            return f.get("form", "")
    return ""


def _clean_zh_pron(text: str) -> str:
    """Normalize zh_pron text into a compact romanization string."""
    value = str(text or "").strip()
    if not value:
        return ""
    # Common Kaikki shape: "shì (shi⁴)" -> keep "shì"
    if "(" in value:
        value = value.split("(", 1)[0].strip()
    return value


def extract_romanization_from_sounds(raw_sounds: list, lang_code: str) -> str:
    """Fallback romanization extraction from sounds payload.

    For Chinese, prefer Mandarin+Pinyin zh_pron entries when forms do not
    contain a dedicated romanization row.
    """
    if str(lang_code or "").strip().lower() != "zh":
        return ""
    best = ""
    best_score = -1
    for s in raw_sounds or []:
        if not isinstance(s, dict):
            continue
        tags = [str(t or "").strip().lower() for t in (s.get("tags") or [])]
        tag_set = set(t for t in tags if t)
        candidate = _clean_zh_pron(s.get("zh_pron", ""))
        if not candidate:
            continue

        # Prefer Standard Mandarin Pinyin.
        score = 0
        if "pinyin" in tag_set:
            score += 4
        if "mandarin" in tag_set:
            score += 3
        if "standard" in tag_set:
            score += 2

        if score > best_score:
            best_score = score
            best = candidate

    return best


def extract_glosses(raw_senses: list) -> list:
    """Build compact senses list from raw Kaikki senses."""

    def _norm_len(items: list) -> int:
        total = 0
        for x in items or []:
            text = " ".join(str(x or "").split()).strip()
            if text:
                total += len(text)
        return total

    out = []
    for s in raw_senses:
        glosses = s.get("glosses", [])
        raw_glosses = s.get("raw_glosses", [])
        use = []
        if isinstance(glosses, list):
            use = [str(g).strip() for g in glosses if str(g or "").strip()]
        if isinstance(raw_glosses, list):
            raw_use = [str(g).strip() for g in raw_glosses if str(g or "").strip()]
        else:
            raw_use = []

        # Prefer the shorter non-empty payload between glosses/raw_glosses.
        if use and raw_use:
            if _norm_len(raw_use) < _norm_len(use):
                use = raw_use
        elif raw_use and not use:
            use = raw_use

        if not use:
            continue

        sense = {"glosses": use}

        q = s.get("qualifier")
        if q:
            sense["qualifier"] = q

        out.append(sense)
    return out


def dedupe_glosses_per_entry(senses: list) -> list:
    """No-op: converter-side dedupe disabled; keep original gloss ordering."""
    return list(senses or [])


def extract_forms(raw_forms: list) -> list:
    """Build compact forms list: [[form, "tag1;tag2", roman], ...]"""
    out = []
    for f in raw_forms:
        form_text = str(f.get("form", "") or "").strip()
        if not form_text:
            continue
        tags = f.get("tags", [])
        if not isinstance(tags, list):
            continue
        # Skip metadata entries
        if any(t in _SKIP_FORM_TAGS for t in tags):
            continue
        # Skip romanization-only (we store that in its own column)
        if tags == ["romanization"]:
            continue

        tags_str = ";".join(sorted(tags))
        roman = f.get("roman", "") or ""

        out.append([form_text, tags_str, roman])
    return out


def convert_file(input_path: str, output_path: str) -> dict:
    """Convert one JSONL file to TSV. Returns stats dict."""
    stats = {
        "total_lines": 0,
        "lemma_entries": 0,
        "form_of_entries_seen": 0,
        "language_pos_skipped": 0,
        "empty_skipped": 0,
        "total_forms": 0,
        "redirect_links_seen": 0,
        "redirect_forms_added": 0,
    }

    # First pass: collect lemma entries, track form/alt-of entries with their
    # own inflection tables so we can merge them
    lemmas = []
    # For merging: headword_lower -> list of indices into lemmas list
    lemma_word_index = {}
    relation_with_tables = []
    relation_with_redirects = []

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["total_lines"] += 1

            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                stats["empty_skipped"] += 1
                continue

            word = raw.get("word", "").strip()
            if not word:
                stats["empty_skipped"] += 1
                continue

            # Capture explicit redirect relationships (word -> target lemma(s)).
            redirects = raw.get("redirects", [])
            if isinstance(redirects, list):
                for target in redirects:
                    parent = str(target or "").strip()
                    if not parent or parent == word:
                        continue
                    relation_with_redirects.append((parent, word))
                    stats["redirect_links_seen"] += 1

            # Keep form-of / alt-of rows in lemma output, but still collect
            # their parent relationships for form-index enrichment.
            if is_form_of_entry(raw):
                stats["form_of_entries_seen"] += 1

                # Preserve alternative-form redirects.
                alt_parents = extract_relation_parents(raw, ("alt_of",))
                for parent in alt_parents:
                    if parent == word:
                        continue
                    relation_with_redirects.append((parent, word))
                    stats["redirect_links_seen"] += 1

                # Check if it has its own inflection table forms to merge
                raw_forms = raw.get("forms", [])
                table_forms = [
                    ff
                    for ff in raw_forms
                    if ff.get("source") in ("conjugation", "declension", "inflection")
                ]
                if table_forms:
                    # Find parent lemma(s) from form_of / alt_of references.
                    parent_words = extract_relation_parents(raw, ("form_of", "alt_of"))
                    for parent in parent_words:
                        relation_with_tables.append((parent, table_forms))

            pos = raw.get("pos", "")
            if should_skip_language_pos_entry(raw, pos):
                stats["language_pos_skipped"] += 1
                continue

            raw_forms = raw.get("forms", [])
            roman = extract_romanization(raw_forms)
            if not roman:
                roman = extract_romanization_from_sounds(
                    raw.get("sounds", []),
                    raw.get("lang_code", ""),
                )

            raw_senses = raw.get("senses", [])
            glosses = extract_glosses(raw_senses)
            if not glosses:
                stats["empty_skipped"] += 1
                continue

            forms = extract_forms(raw_forms)
            stats["total_forms"] += len(forms)

            idx = len(lemmas)
            lemmas.append(
                {
                    "headword": word,
                    "pos": pos,
                    "roman": roman,
                    "glosses": glosses,
                    "forms": forms,
                }
            )
            lemma_word_index.setdefault(word.lower(), []).append(idx)
            stats["lemma_entries"] += 1

    # Merge pass 1: attach orphan inflection table forms to parent lemmas
    merged_form_of_count = 0
    for parent_word, extra_forms in relation_with_tables:
        indices = lemma_word_index.get(parent_word.lower(), [])
        if not indices:
            continue
        extra = extract_forms(extra_forms)
        if not extra:
            continue
        for idx in indices:
            existing = lemmas[idx]
            for ef in extra:
                existing["forms"].append(ef)
                stats["total_forms"] += 1
        merged_form_of_count += 1

    # Merge pass 2: attach redirect variants as synthetic forms.
    # Example: 国 -> 國, 着 -> 著.
    redirect_tag = "redirect;alternative"
    merged_redirect_links = 0
    for parent_word, variant_word in relation_with_redirects:
        indices = lemma_word_index.get(parent_word.lower(), [])
        if not indices:
            continue
        added_any = False
        for idx in indices:
            existing = lemmas[idx]
            existing["forms"].append([variant_word, redirect_tag, ""])
            stats["total_forms"] += 1
            stats["redirect_forms_added"] += 1
            added_any = True
        if added_any:
            merged_redirect_links += 1

    # Write pass
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as out:
        # Header
        out.write("headword\tpos\tromanization\tglosses\tforms\n")
        for entry in lemmas:
            # Escape any tabs/newlines in text fields
            hw = entry["headword"].replace("\t", " ").replace("\n", " ")
            pos = entry["pos"].replace("\t", " ").replace("\n", " ")
            roman = entry["roman"].replace("\t", " ").replace("\n", " ")
            glosses_json = json.dumps(entry["glosses"], ensure_ascii=False)
            forms_json = json.dumps(entry["forms"], ensure_ascii=False)
            out.write(f"{hw}\t{pos}\t{roman}\t{glosses_json}\t{forms_json}\n")

    input_size = os.path.getsize(input_path)
    output_size = os.path.getsize(output_path)
    stats["input_size_mb"] = round(input_size / 1024 / 1024, 1)
    stats["output_size_mb"] = round(output_size / 1024 / 1024, 1)
    stats["reduction_pct"] = round((1 - output_size / input_size) * 100, 1)
    stats["merged_form_of"] = merged_form_of_count
    stats["merged_redirects"] = merged_redirect_links

    return stats


def main():
    target_lang = None
    if len(sys.argv) > 1:
        target_lang = sys.argv[1].lower()

    if not os.path.isdir(INPUT_DIR):
        print(f"Input directory not found: {INPUT_DIR}")
        sys.exit(1)

    files = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".jsonl"))
    if not files:
        print(f"No .jsonl files found in {INPUT_DIR}")
        sys.exit(1)

    for fname in files:
        # Extract language name from filename like "kaikki.org-dictionary-Turkish (1).jsonl"
        lang = fname.replace("kaikki.org-dictionary-", "").replace(".jsonl", "").strip()
        # Remove parenthetical suffixes like " (1)"
        if "(" in lang:
            lang = lang[: lang.index("(")].strip()

        if target_lang and target_lang not in lang.lower():
            continue

        input_path = os.path.join(INPUT_DIR, fname)
        output_name = f"dict-{lang.lower()}.tsv"
        output_path = os.path.join(OUTPUT_DIR, output_name)

        print(f"\nConverting {lang}...")
        stats = convert_file(input_path, output_path)

        print(f"  Input:  {stats['input_size_mb']} MB ({stats['total_lines']:,} lines)")
        print(f"  Output: {stats['output_size_mb']} MB ({stats['lemma_entries']:,} lemma entries)")
        print(
            f"  Form/alt-of rows kept: {stats['form_of_entries_seen']:,}; "
            f"Skipped: "
            f"{stats['language_pos_skipped']:,} language-pos, "
            f"{stats['empty_skipped']:,} empty/bad"
        )
        print(f"  Forms indexed: {stats['total_forms']:,}")
        if stats["merged_form_of"]:
            print(
                f"  Merged {stats['merged_form_of']} form/alt-of inflection tables "
                f"into parent lemmas"
            )
        if stats["redirect_links_seen"]:
            print(
                f"  Redirects: {stats['redirect_links_seen']:,} links seen, "
                f"{stats['merged_redirects']:,} merged, "
                f"{stats['redirect_forms_added']:,} form rows added"
            )
        print(f"  Size reduction: {stats['reduction_pct']}%")

    print("\nDone.")


if __name__ == "__main__":
    main()
