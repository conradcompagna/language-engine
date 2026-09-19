#!/usr/bin/env python3
"""Convert the Monier-Williams Sanskrit dictionary (mw.txt) to the legacy TSV format.

Output TSV columns match the WiktionaryDict TSV schema:
  headword  pos_raw  reading  glosses  tags  etymology
  etymology_number  alt_forms  synonyms  antonyms  derived  related  grammar

Usage:
    python convert_mw_to_tsv.py
"""

import re
import sys
from pathlib import Path


# ── MW tag patterns ──────────────────────────────────────────────────────

RE_L_HEADER = re.compile(
    r"<L>(?P<lid>[^<]+)"
    r"<pc>(?P<pc>[^<]+)"
    r"<k1>(?P<k1>[^<]+)"
    r"<k2>(?P<k2>[^<]+)"
    r"(?:<h>(?P<hom>[^<]+))?"
    r"<e>(?P<etype>[^<\n]+)"
)
RE_LEX = re.compile(r"<lex>([^<]+)</lex>")
RE_INFO_LEX = re.compile(r'<info\s+lex="([^"]+)"')
RE_INFO_VERB = re.compile(r'<info\s+verb="([^"]*)"')
RE_HOM = re.compile(r"<hom>(\d+)\.</hom>")
RE_LBODY_REF = re.compile(r"\{\{Lbody=[\d.]+\}\}")

# Tags to strip from definition text
RE_STRIP_TAGS = re.compile(
    r"</?(?:s|s1|s2|ab|ls|ns|etym|lang|gk|srs|bot|bio|hom|lex|"
    r"info[^>]*|listinfo[^>]*|pcol|cf|fs|is|lbinfo[^>]*)/?>"
)
RE_ANGLE_TAGS = re.compile(r"<[^>]+>")
RE_MULTI_SPACE = re.compile(r"  +")


# ── POS mapping ──────────────────────────────────────────────────────────


def map_lex_to_pos(lex_str: str, info_lex: str, info_verb: str) -> str:
    """Map MW lex/info tags to Kaikki-style pos_raw strings."""
    lex = lex_str.strip().rstrip(".")

    if info_verb:
        return "verb"

    # Direct lex tag
    if lex in ("m", "mn", "m.(n.)"):
        return "noun"
    if lex == "f":
        return "noun"
    if lex == "n":
        return "noun"
    if lex in ("mfn", "mf", "mf.", "m.f.n."):
        return "adj"
    if lex in ("ind", "ind."):
        return "adv"

    # info lex= attribute
    il = info_lex.lower().replace(" ", "")
    if il in ("m", "m.", "m:f:n", "m:f:n:"):
        if "mfn" in lex_str.lower() or "mfn" in il:
            return "adj"
        return "noun"
    if il in ("f", "f."):
        return "noun"
    if il in ("n", "n."):
        return "noun"
    if "inh" in il:
        return ""  # inherited sense — no separate POS
    if il in ("ind", "ind."):
        return "adv"

    # Parse compound info lex strings like "m:f:n"
    if ":" in il:
        parts = [p.strip().rstrip(".") for p in il.split(":") if p.strip()]
        genders = {"m", "f", "n"}
        if set(parts) <= genders:
            if len(parts) >= 2:
                return "adj"
            return "noun"

    if lex:
        # Fallback heuristics
        if "mfn" in lex:
            return "adj"
        if lex.startswith("m") or lex.startswith("f") or lex.startswith("n"):
            return "noun"

    return ""


def clean_definition(text: str) -> str:
    """Strip MW XML tags from definition text, producing clean English."""
    # Remove specific MW tags but keep their text content
    out = RE_STRIP_TAGS.sub("", text)
    # Remove any remaining angle-bracket tags
    out = RE_ANGLE_TAGS.sub("", out)
    # Clean up
    out = out.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    out = out.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    out = out.replace("¦", "").strip()
    out = RE_MULTI_SPACE.sub(" ", out)
    # Remove leading/trailing punctuation artifacts
    out = out.strip(" ,;.")
    return out


def parse_mw_file(path: Path):
    """Parse mw.txt and yield (headword, k1, hom, pos_raw, glosses, grammar) tuples."""

    with path.open("r", encoding="utf-8") as f:
        raw_text = f.read()

    # Split into entries by <L> markers
    entries_raw = raw_text.split("<LEND>")

    # Group entries by (k1, hom) — continuation entries (e=...A) append glosses
    grouped = {}  # (k1, hom) -> {headword, pos_raw, glosses, grammar}
    order = []

    for block in entries_raw:
        block = block.strip()
        if not block:
            continue

        # Parse header
        m = RE_L_HEADER.search(block)
        if not m:
            continue

        lid = m.group("lid")
        k1 = m.group("k1")
        k2 = m.group("k2")
        hom = m.group("hom") or ""
        etype = m.group("etype")

        # Skip cross-reference entries
        if RE_LBODY_REF.search(block):
            continue

        # Extract body (everything after the header line)
        lines = block.split("\n")
        body_lines = lines[1:] if len(lines) > 1 else []
        if not body_lines and len(lines) == 1:
            # Single-line entry: extract after the header tags
            header_end = block.find(">", block.rfind("<e>")) + 1
            if header_end > 0:
                body_lines = [block[header_end:]]

        body = "\n".join(body_lines).strip()

        # Extract headword from <s> tag or k2
        headword_match = re.search(r"<s>([^<]+)</s>", body)
        if headword_match:
            headword = headword_match.group(1).replace("—", "-").strip()
        else:
            headword = k2.replace("—", "-").replace("/", "").strip()
        # Clean accent marks from headword
        headword = headword.replace("/", "")

        # Extract POS
        lex_match = RE_LEX.search(body)
        lex_str = lex_match.group(1) if lex_match else ""
        info_lex_match = RE_INFO_LEX.search(body)
        info_lex = info_lex_match.group(1) if info_lex_match else ""
        info_verb_match = RE_INFO_VERB.search(body)
        info_verb = info_verb_match.group(1) if info_verb_match else ""

        pos_raw = map_lex_to_pos(lex_str, info_lex, info_verb)

        # Extract definition — text after ¦
        def_text = ""
        sep_idx = body.find("¦")
        if sep_idx >= 0:
            def_text = body[sep_idx + 1 :]
        else:
            # Some entries have no ¦ — use the whole body
            def_text = body

        def_text = clean_definition(def_text)
        if not def_text:
            continue

        # Build grammar info from lex tag
        grammar = ""
        if lex_str:
            grammar = lex_str.strip().rstrip(".")

        # Check if this is a continuation entry
        is_continuation = etype.endswith("A") or etype.endswith("B")

        key = (k1, hom)
        if is_continuation and key in grouped:
            # Append as additional gloss
            grouped[key]["glosses"].append(def_text)
        else:
            if key in grouped:
                # New homonym — use a unique key
                key = (k1, hom + "_" + lid)
            grouped[key] = {
                "lid": lid,
                "headword": headword,
                "k1": k1,
                "pos_raw": pos_raw,
                "glosses": [def_text],
                "grammar": grammar,
                "hom": hom,
            }
            order.append(key)

    return grouped, order


def main():
    mw_path = Path(__file__).resolve().parent / "txt" / "mw.txt"
    if not mw_path.exists():
        print(f"Error: {mw_path} not found", file=sys.stderr)
        sys.exit(1)

    out_path = Path(__file__).resolve().parent / "sanskrit_mw.tsv"

    print(f"Parsing {mw_path}...")
    grouped, order = parse_mw_file(mw_path)
    print(f"Parsed {len(grouped)} entry groups from {len(order)} ordered keys")

    # Write TSV
    headers = [
        "headword",
        "pos_raw",
        "reading",
        "glosses",
        "tags",
        "etymology",
        "etymology_number",
        "alt_forms",
        "synonyms",
        "antonyms",
        "derived",
        "related",
        "grammar",
    ]

    written = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write("\t".join(headers) + "\n")
        for key in order:
            entry = grouped[key]
            headword = entry["headword"]
            glosses = entry["glosses"]
            pos_raw = entry["pos_raw"]
            grammar = entry["grammar"]

            # Filter out empty/trivial glosses
            clean_glosses = []
            for g in glosses:
                g = g.strip()
                if g and len(g) > 1:
                    clean_glosses.append(g)
            if not clean_glosses:
                continue

            row = [
                headword,  # headword
                pos_raw,  # pos_raw
                "",  # reading (MW doesn't have IPA)
                "; ".join(clean_glosses),  # glosses
                "",  # tags
                "",  # etymology
                "",  # etymology_number
                "",  # alt_forms
                "",  # synonyms
                "",  # antonyms
                "",  # derived
                "",  # related
                grammar,  # grammar
            ]
            f.write("\t".join(row) + "\n")
            written += 1

    print(f"Written {written} entries to {out_path}")


if __name__ == "__main__":
    main()
