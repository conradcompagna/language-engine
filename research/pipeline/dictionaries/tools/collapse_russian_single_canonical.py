import argparse
import csv
import json
import os
import tempfile
import unicodedata
from collections import defaultdict

INFLECTION_HINT_TAGS = {
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "prepositional",
    "locative",
    "partitive",
    "vocative",
    "singular",
    "plural",
    "masculine",
    "feminine",
    "neuter",
    "animate",
    "inanimate",
    "first-person",
    "second-person",
    "third-person",
    "present",
    "past",
    "future",
    "imperative",
    "participle",
    "gerund",
    "short-form",
}


def split_tags(raw):
    return [tag for tag in str(raw or "").split(";") if tag]


def strip_marks(text):
    decomposed = unicodedata.normalize("NFD", str(text or ""))
    out = []
    for ch in decomposed:
        if unicodedata.category(ch).startswith("M"):
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def load_forms(raw):
    try:
        value = json.loads(raw or "[]")
    except Exception:
        return []
    return value if isinstance(value, list) else []


def extract_single_canonical_form(forms):
    canonical = []
    for item in forms:
        if not isinstance(item, list) or len(item) < 2:
            continue
        tags = split_tags(item[1])
        if "canonical" in tags:
            canonical.append(str(item[0] or ""))
    if len(canonical) != 1:
        return ""
    return canonical[0]


def extract_first_gloss_text(glosses_raw):
    try:
        parsed = json.loads(glosses_raw or "[]")
    except Exception:
        return ""
    if not isinstance(parsed, list) or not parsed:
        return ""
    first = parsed[0]
    if not isinstance(first, dict):
        return ""
    glosses = first.get("glosses") or []
    if not isinstance(glosses, list) or not glosses:
        return ""
    return str(glosses[0] or "")


def is_form_of_gloss(gloss_text):
    return " of " in str(gloss_text or "").strip().lower()


def choose_group_keeper(rows, canonical_form):
    canonical_base = strip_marks(canonical_form)

    def rank(item):
        head = str(item.get("headword") or "")
        head_base = strip_marks(head)
        return (
            0 if head_base == canonical_base else 1,
            abs(len(head_base) - len(canonical_base)),
            item["line_no"],
        )

    return min(rows, key=rank)


def choose_owner(rows):
    def rank(item):
        return (
            0 if not item.get("is_form_of") else 1,
            -int(item.get("forms_count", 0) or 0),
            item["line_no"],
        )

    return min(rows, key=rank)


def build_collapse_plan(path):
    groups = defaultdict(list)
    owner_candidates = defaultdict(list)
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for line_no, row in enumerate(reader, 2):
            forms = load_forms(row.get("forms"))
            canonical_form = extract_single_canonical_form(forms)
            if not canonical_form:
                continue
            item = {
                "line_no": line_no,
                "headword": str(row.get("headword") or ""),
                "romanization": str(row.get("romanization") or ""),
                "pos": str(row.get("pos") or ""),
                "canonical_form": canonical_form,
                "forms_count": len(forms),
                "is_form_of": is_form_of_gloss(extract_first_gloss_text(row.get("glosses") or "")),
            }
            groups[(canonical_form, item["pos"])].append(item)
            for form_item in forms:
                if not isinstance(form_item, list) or len(form_item) < 2:
                    continue
                form_text = str(form_item[0] or "")
                if not form_text:
                    continue
                tags = set(split_tags(form_item[1]))
                if not (tags & INFLECTION_HINT_TAGS):
                    continue
                owner_candidates[(form_text, item["pos"])].append(item)

    keepers = {}
    dropped = set()
    dropped_rows = 0

    for (canonical_form, pos), rows in groups.items():
        source_rows = [row for row in rows if row.get("is_form_of")]
        source_line_nos = {row["line_no"] for row in source_rows}
        owners = [
            owner
            for owner in owner_candidates.get((canonical_form, pos), [])
            if owner["line_no"] not in source_line_nos
        ]

        if owners and source_rows:
            keeper = choose_owner(owners)
            keep_payload = keepers.setdefault(
                keeper["line_no"],
                {
                    "new_headword": "",
                    "variant_forms": [],
                },
            )
            seen_variant_texts = {
                str(item[0] or "")
                for item in keep_payload["variant_forms"]
                if isinstance(item, list) and item
            }
            for row in source_rows:
                variant_text = row["headword"]
                if variant_text and variant_text not in seen_variant_texts:
                    keep_payload["variant_forms"].append([variant_text, "", row["romanization"]])
                    seen_variant_texts.add(variant_text)
                dropped.add(row["line_no"])
                dropped_rows += 1
            continue

        if len(rows) <= 1:
            continue

        keeper = choose_group_keeper(rows, canonical_form)
        keep_payload = keepers.setdefault(
            keeper["line_no"],
            {
                "new_headword": "",
                "variant_forms": [],
            },
        )
        seen_variant_texts = {
            str(item[0] or "")
            for item in keep_payload["variant_forms"]
            if isinstance(item, list) and item
        }
        for row in rows:
            if row["line_no"] == keeper["line_no"]:
                continue
            variant_text = row["headword"]
            if variant_text and variant_text not in seen_variant_texts:
                keep_payload["variant_forms"].append([variant_text, "", row["romanization"]])
                seen_variant_texts.add(variant_text)
            dropped.add(row["line_no"])
            dropped_rows += 1

    return keepers, dropped, dropped_rows


def rewrite_tsv(path, keepers, dropped):
    fd, tmp_path = tempfile.mkstemp(prefix="ru_canonical_collapse_", suffix=".tsv", dir=os.path.dirname(path))
    os.close(fd)
    written_rows = 0
    with open(path, "r", encoding="utf-8", newline="") as src, open(
        tmp_path, "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        dst.write("\t".join(fieldnames) + "\n")

        for line_no, row in enumerate(reader, 2):
            if line_no in dropped:
                continue

            payload = keepers.get(line_no)
            if payload:
                if payload.get("new_headword"):
                    row["headword"] = payload["new_headword"]
                forms = load_forms(row.get("forms"))
                seen_form_texts = set()
                merged_forms = []
                for item in forms:
                    if not isinstance(item, list) or not item:
                        continue
                    text = str(item[0] or "")
                    if not text or text in seen_form_texts:
                        continue
                    seen_form_texts.add(text)
                    merged_forms.append(item)
                for item in payload["variant_forms"]:
                    text = str(item[0] or "")
                    if not text or text in seen_form_texts:
                        continue
                    seen_form_texts.add(text)
                    merged_forms.append(item)
                row["forms"] = json.dumps(merged_forms, ensure_ascii=False)

            out_fields = []
            for field in fieldnames:
                value = str(row.get(field, "") or "")
                value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
                out_fields.append(value)
            dst.write("\t".join(out_fields) + "\n")
            written_rows += 1

    os.replace(tmp_path, path)
    return written_rows


def main():
    parser = argparse.ArgumentParser(
        description="Collapse Russian TSV rows that share a single canonical form into one canonical headword row."
    )
    parser.add_argument("path", help="Path to dict-russian.tsv")
    args = parser.parse_args()

    keepers, dropped, dropped_rows = build_collapse_plan(args.path)
    written_rows = rewrite_tsv(args.path, keepers, dropped)
    print(
        json.dumps(
            {
                "dropped_rows": dropped_rows,
                "keepers_updated": len(keepers),
                "rows_written": written_rows,
                "output_path": args.path,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
