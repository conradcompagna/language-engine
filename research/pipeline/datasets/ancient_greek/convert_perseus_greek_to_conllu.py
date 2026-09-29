from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


APP_ROOT = Path(__file__).resolve().parents[2]
PERSEUS_DIR = APP_ROOT / "training" / "perseus"
DEFAULT_ARCHIVE = PERSEUS_DIR / "latin_greek_treebanks_v2.1_texts.zip"
DEFAULT_EXTRACT_DIR = PERSEUS_DIR / "_tmp_treebanks_inspect"
DEFAULT_OUTPUT_DIR = PERSEUS_DIR / "grc_trankit_minimal"


POS_TO_UPOS = {
    "l": "DET",
    "n": "NOUN",
    "a": "ADJ",
    "p": "PRON",
    "v": "VERB",
    "d": "ADV",
    "r": "ADP",
    "m": "NUM",
    "i": "INTJ",
    "g": "PART",
    "u": "PUNCT",
    "b": "X",
    "k": "X",
    "x": "X",
    "-": "X",
}

PERSON_MAP = {
    "1": "1",
    "2": "2",
    "3": "3",
}

NUMBER_MAP = {
    "s": "Sing",
    "p": "Plur",
    "d": "Dual",
}

TENSE_MAP = {
    "p": "Pres",
    "i": "Imp",
    "r": "Perf",
    "l": "Pqp",
    "t": "FutPerf",
    "f": "Fut",
    "a": "Aor",
}

MOOD_MAP = {
    "i": "Ind",
    "s": "Sub",
    "n": "Inf",
    "m": "Imp",
    "p": "Part",
    "o": "Opt",
}

VOICE_MAP = {
    "a": "Act",
    "p": "Pass",
    "m": "Mid",
    "e": "MidPass",
}

GENDER_MAP = {
    "m": "Masc",
    "f": "Fem",
    "n": "Neut",
}

CASE_MAP = {
    "n": "Nom",
    "g": "Gen",
    "d": "Dat",
    "a": "Acc",
    "v": "Voc",
}

DEGREE_MAP = {
    "p": "Pos",
    "c": "Cmp",
    "s": "Sup",
}

PUNCT_DEPRELS = {"AuxK", "AuxX", "AuxG"}
ROOTISH_DEPRELS = {
    "PRED",
    "PRED_CO",
    "PRED_PA",
    "PRED_AP",
    "PRED_AP_CO",
    "PRED_PA_CO",
}


@dataclass
class ConvertedToken:
    tok_id: int
    form: str
    lemma: str
    upos: str
    xpos: str
    feats: str
    head: int
    deprel: str
    deps: str
    misc: str


def ensure_extracted(archive_path: Path, extract_dir: Path) -> Path:
    greek_dir = extract_dir / "Greek" / "texts"
    if greek_dir.is_dir():
        return extract_dir
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        zf.extractall(extract_dir)
    return extract_dir


def iter_greek_xml_paths(extract_dir: Path) -> list[Path]:
    manifest_path = extract_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ordered = []
        for rel_path in manifest.get("included_files", []):
            if not str(rel_path).startswith("Greek/texts/"):
                continue
            xml_path = extract_dir / Path(rel_path)
            if xml_path.is_file():
                ordered.append(xml_path)
        if ordered:
            return ordered
    return sorted((extract_dir / "Greek" / "texts").glob("*.xml"))


def base_relation(relation: str) -> str:
    relation = (relation or "").strip()
    return relation.split("_", 1)[0] if relation else ""


def map_upos(xpos: str, relation: str, form: str) -> str:
    pos_code = (xpos or "").strip()[:1]
    if not pos_code:
        if form in {".", ",", ";", ":", "·", "(", ")", "[", "]"}:
            return "PUNCT"
        return "X"
    if pos_code == "c":
        base_rel = base_relation(relation)
        if base_rel == "AuxC":
            return "SCONJ"
        return "CCONJ"
    return POS_TO_UPOS.get(pos_code, "X")


def derive_feats(xpos: str) -> str:
    raw = (xpos or "").strip()
    if not raw:
        return "_"
    padded = (raw + "---------")[:9]
    pos, pers, num, tense, mood, voice, gend, case, degree = padded
    feats: list[tuple[str, str]] = []

    if pos == "l":
        feats.append(("Definite", "Def"))
        feats.append(("PronType", "Art"))
    if pers in PERSON_MAP:
        feats.append(("Person", PERSON_MAP[pers]))
    if num in NUMBER_MAP:
        feats.append(("Number", NUMBER_MAP[num]))
    if tense in TENSE_MAP:
        feats.append(("Tense", TENSE_MAP[tense]))
    if mood in MOOD_MAP:
        feats.append(("Mood", MOOD_MAP[mood]))
        if mood == "n":
            feats.append(("VerbForm", "Inf"))
        elif mood == "p":
            feats.append(("VerbForm", "Part"))
        else:
            feats.append(("VerbForm", "Fin"))
    if voice in VOICE_MAP:
        feats.append(("Voice", VOICE_MAP[voice]))
    if gend in GENDER_MAP:
        feats.append(("Gender", GENDER_MAP[gend]))
    if case in CASE_MAP:
        feats.append(("Case", CASE_MAP[case]))
    if degree in DEGREE_MAP:
        feats.append(("Degree", DEGREE_MAP[degree]))

    if not feats:
        return "_"

    seen: set[tuple[str, str]] = set()
    ordered: list[str] = []
    for key, value in feats:
        item = (key, value)
        if item in seen:
            continue
        seen.add(item)
        ordered.append(f"{key}={value}")
    return "|".join(ordered) if ordered else "_"


def choose_primary_root(rows: list[dict]) -> int:
    root_candidates = [row for row in rows if row["parsed_head"] == 0]
    if not root_candidates:
        return rows[0]["tok_id"]

    def rank(row: dict) -> tuple[int, int]:
        xpos = row["xpos"]
        relation = row["relation"]
        pos_code = xpos[:1] if xpos else ""
        if relation in ROOTISH_DEPRELS:
            return (0, row["tok_id"])
        if pos_code == "v":
            return (1, row["tok_id"])
        if relation == "COORD" or pos_code in {"c", "g"}:
            return (2, row["tok_id"])
        if pos_code != "u":
            return (3, row["tok_id"])
        return (4, row["tok_id"])

    return min(root_candidates, key=rank)["tok_id"]


def build_misc(parts: Iterable[str]) -> str:
    values = [part for part in parts if part]
    return "|".join(values) if values else "_"


def sanitize_misc_value(value: str) -> str:
    return (
        str(value or "")
        .replace("%", "%25")
        .replace("|", "%7C")
        .replace(" ", "%20")
    )


def clean_token_text(value: str) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def is_artificial_word(word: ET.Element) -> bool:
    return word.get("artificial") is not None or word.get("insertion_id") is not None


def has_internal_whitespace(value: str) -> bool:
    return any(char.isspace() for char in str(value or ""))


def parse_head_value(raw: str) -> int | None:
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


def resolve_surface_head(
    orig_head: int | None,
    direct_heads: dict[int, int | None],
    kept_ids: set[int],
) -> int | None:
    if orig_head is None:
        return None
    if orig_head == 0:
        return 0

    current = orig_head
    seen: set[int] = set()
    while current not in kept_ids:
        if current in seen:
            return None
        seen.add(current)
        current = direct_heads.get(current)
        if current is None:
            return None
        if current == 0:
            return 0
    return current


def render_text(forms: list[str]) -> str:
    no_space_before = {".", ",", ";", ":", "·", ")", "]"}
    no_space_after = {"(", "["}
    out = ""
    for form in forms:
        if not out:
            out = form
            continue
        if form in no_space_before or out[-1:] in no_space_after:
            out += form
        else:
            out += " " + form
    return out


def validate_sentence(tokens: list[ConvertedToken], sent_label: str) -> None:
    if not tokens:
        raise ValueError(f"{sent_label}: empty sentence")

    expected_ids = list(range(1, len(tokens) + 1))
    actual_ids = [token.tok_id for token in tokens]
    if actual_ids != expected_ids:
        raise ValueError(f"{sent_label}: non-contiguous token ids")

    roots = [token for token in tokens if token.head == 0]
    if len(roots) != 1:
        raise ValueError(f"{sent_label}: expected 1 root, found {len(roots)}")
    if roots[0].deprel != "root":
        raise ValueError(f"{sent_label}: root token does not use deprel=root")

    valid_ids = set(expected_ids)
    for token in tokens:
        if token.head != 0 and token.head not in valid_ids:
            raise ValueError(f"{sent_label}: invalid head {token.head} on token {token.tok_id}")
        if token.head == token.tok_id:
            raise ValueError(f"{sent_label}: self-head on token {token.tok_id}")

    state = {token.tok_id: 0 for token in tokens}
    head_map = {token.tok_id: token.head for token in tokens}

    def visit(tok_id: int) -> None:
        status = state[tok_id]
        if status == 2:
            return
        if status == 1:
            raise ValueError(f"{sent_label}: cycle detected")
        state[tok_id] = 1
        parent = head_map[tok_id]
        if parent != 0:
            visit(parent)
        state[tok_id] = 2

    for tok_id in expected_ids:
        visit(tok_id)


def convert_sentence(
    sent: ET.Element,
    counters: Counter,
    source_name: str,
) -> tuple[list[str], list[ConvertedToken], str]:
    raw_rows: list[dict] = []
    all_words = sent.findall("word")
    words = [word for word in all_words if not is_artificial_word(word)]
    counters["dropped_artificial_tokens"] += len(all_words) - len(words)
    if not words:
        raise ValueError(f"{source_name}@{sent.get('id') or ''}: empty surface sentence")
    if any(has_internal_whitespace(word.get("form") or "") for word in words):
        raise ValueError(f"{source_name}@{sent.get('id') or ''}: whitespace in surface form")

    valid_ids: set[int] = set()
    orig_to_new: dict[int, int] = {}
    kept_ids: set[int] = set()
    direct_heads = {
        int(word.get("id")): parse_head_value(word.get("head") or "")
        for word in all_words
    }
    for word in words:
        orig_tok_id = int(word.get("id"))
        valid_ids.add(orig_tok_id)
        kept_ids.add(orig_tok_id)
        orig_to_new[orig_tok_id] = len(orig_to_new) + 1

    for word in words:
        orig_tok_id = int(word.get("id"))
        tok_id = orig_to_new[orig_tok_id]
        form = clean_token_text(word.get("form") or "")
        lemma = clean_token_text(word.get("lemma") or "")
        xpos_raw = clean_token_text(word.get("postag") or "")
        relation_raw = clean_token_text(word.get("relation") or "")
        head_raw = clean_token_text(word.get("head") or "")

        direct_head = parse_head_value(head_raw)
        parsed_head = resolve_surface_head(direct_head, direct_heads, kept_ids)
        if parsed_head == orig_tok_id:
            parsed_head = None
        if parsed_head is not None and parsed_head not in valid_ids and parsed_head != 0:
            parsed_head = None

        upos = map_upos(xpos_raw, relation_raw, form)
        feats = derive_feats(xpos_raw)
        if not relation_raw:
            counters["empty_relation_tokens"] += 1
            relation = "punct" if upos == "PUNCT" else "dep"
        else:
            relation = relation_raw

        raw_rows.append(
            {
                "tok_id": tok_id,
                "orig_tok_id": orig_tok_id,
                "form": form,
                "lemma": lemma or "_",
                "xpos": xpos_raw or "_",
                "upos": upos,
                "feats": feats,
                "relation": relation,
                "relation_raw": relation_raw,
                "head_raw": head_raw,
                "direct_head": direct_head,
                "parsed_head": parsed_head,
            }
        )

    primary_root = choose_primary_root(raw_rows)
    root_count = sum(1 for row in raw_rows if row["parsed_head"] == 0)
    if root_count > 1:
        counters["multi_root_sentences"] += 1

    converted: list[ConvertedToken] = []
    for row in raw_rows:
        misc_parts: list[str] = []
        final_head = row["parsed_head"]
        final_deprel = row["relation"]

        if row["orig_tok_id"] != row["tok_id"]:
            misc_parts.append(f"OrigId={row['orig_tok_id']}")
        if (
            row["direct_head"] not in {None, 0}
            and row["direct_head"] != row["parsed_head"]
            and row["head_raw"]
        ):
            counters["resolved_artificial_heads"] += 1
            misc_parts.append(f"OrigHead={sanitize_misc_value(row['head_raw'])}")

        if row["tok_id"] == primary_root:
            if row["relation_raw"] and row["relation_raw"] != "root":
                misc_parts.append(f"OrigDeprel={sanitize_misc_value(row['relation_raw'])}")
            if row["head_raw"] and row["head_raw"] != "0":
                misc_parts.append(f"OrigHead={sanitize_misc_value(row['head_raw'])}")
            final_head = 0
            final_deprel = "root"
        else:
            if final_head is None:
                counters["repaired_invalid_heads"] += 1
                misc_parts.append(f"OrigHead={sanitize_misc_value(row['head_raw'] or 'EMPTY')}")
                final_head = primary_root
            elif final_head == 0:
                counters["reattached_extra_roots"] += 1
                misc_parts.append("OrigHead=0")
                final_head = primary_root
            else:
                final_head = orig_to_new[final_head]

        converted.append(
            ConvertedToken(
                tok_id=row["tok_id"],
                form=row["form"] or "_",
                lemma=row["lemma"] or "_",
                upos=row["upos"] or "X",
                xpos=row["xpos"] or "_",
                feats=row["feats"] or "_",
                head=final_head if final_head is not None else primary_root,
                deprel=final_deprel or "dep",
                deps="_",
                misc=build_misc(misc_parts),
            )
        )

    sent_id = sent.get("id") or ""
    subdoc = sent.get("subdoc") or ""
    text_value = render_text([token.form for token in converted])
    validate_sentence(converted, f"{source_name}@{sent_id}")
    comments = [
        f"# sent_id = {source_name}@{sent_id}",
        f"# text = {text_value}",
    ]
    if subdoc:
        comments.append(f"# orig_subdoc = {subdoc}")
    return comments, converted, text_value


def render_token(token: ConvertedToken) -> str:
    return "\t".join(
        [
            str(token.tok_id),
            token.form or "_",
            token.lemma or "_",
            token.upos or "X",
            token.xpos or "_",
            token.feats or "_",
            str(token.head),
            token.deprel or "dep",
            token.deps or "_",
            token.misc or "_",
        ]
    )


def convert_document(xml_path: Path, counters: Counter) -> tuple[list[str], list[str], dict]:
    tree = ET.parse(xml_path)
    rendered_sentences: list[str] = []
    raw_text_lines: list[str] = []
    local = Counter()

    for sent_index, sent in enumerate(tree.iterfind(".//sentence")):
        try:
            comments, converted, text_value = convert_sentence(sent, counters, xml_path.name)
        except ValueError as exc:
            if "cycle detected" in str(exc):
                counters["dropped_cyclic_sentences"] += 1
                local["dropped_cyclic_sentences"] += 1
                continue
            if "empty surface sentence" in str(exc):
                counters["dropped_empty_surface_sentences"] += 1
                local["dropped_empty_surface_sentences"] += 1
                continue
            if "whitespace in surface form" in str(exc):
                counters["dropped_bad_form_sentences"] += 1
                local["dropped_bad_form_sentences"] += 1
                continue
            raise
        local["sentences"] += 1
        local["tokens"] += len(converted)
        for token in converted:
            counters[f"upos::{token.upos}"] += 1
            if token.xpos == "_":
                counters["empty_xpos_tokens"] += 1
            if token.upos == "X":
                counters["x_upos_tokens"] += 1
        prefix: list[str] = []
        if sent_index == 0:
            prefix.append(f"# newdoc id = {xml_path.name}")
        sentence_block = "\n".join(prefix + comments + [render_token(token) for token in converted])
        rendered_sentences.append(sentence_block)
        raw_text_lines.append(text_value)

    doc_stats = {
        "document": xml_path.name,
        "sentences": local["sentences"],
        "tokens": local["tokens"],
        "dropped_cyclic_sentences": local["dropped_cyclic_sentences"],
        "dropped_empty_surface_sentences": local["dropped_empty_surface_sentences"],
        "dropped_bad_form_sentences": local["dropped_bad_form_sentences"],
    }
    return rendered_sentences, raw_text_lines, doc_stats


def write_outputs(
    output_dir: Path,
    per_document: dict[str, str],
    per_document_text: dict[str, str],
    combined_sentences: list[str],
    combined_text_lines: list[str],
    summary: dict,
    splits: dict[str, list[str]],
) -> None:
    by_document_dir = output_dir / "by_document"
    by_document_text_dir = output_dir / "by_document_txt"
    split_conllu_dir = output_dir / "splits"
    split_txt_dir = output_dir / "splits_txt"
    by_document_dir.mkdir(parents=True, exist_ok=True)
    by_document_text_dir.mkdir(parents=True, exist_ok=True)
    split_conllu_dir.mkdir(parents=True, exist_ok=True)
    split_txt_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in per_document.items():
        (by_document_dir / f"{Path(name).stem}.conllu").write_text(payload, encoding="utf-8")
    for name, payload in per_document_text.items():
        (by_document_text_dir / f"{Path(name).stem}.txt").write_text(payload, encoding="utf-8")
    for split_name, doc_names in splits.items():
        split_conllu = [per_document[name].rstrip() for name in doc_names]
        split_text = [per_document_text[name].rstrip() for name in doc_names]
        (split_conllu_dir / f"{split_name}.conllu").write_text(
            "\n\n".join(part for part in split_conllu if part).rstrip() + "\n\n",
            encoding="utf-8",
        )
        (split_txt_dir / f"{split_name}.txt").write_text(
            "\n".join(part for part in split_text if part).rstrip() + "\n",
            encoding="utf-8",
        )

    (output_dir / "grc_perseus_minimal_all.conllu").write_text(
        "\n\n".join(combined_sentences).rstrip() + "\n\n",
        encoding="utf-8",
    )
    (output_dir / "grc_perseus_minimal_all.txt").write_text(
        "\n".join(combined_text_lines).rstrip() + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Perseus Greek treebank XML into minimal Trankit-ready CoNLL-U."
    )
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--extract-dir", type=Path, default=DEFAULT_EXTRACT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    extract_dir = ensure_extracted(args.archive, args.extract_dir)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    counters = Counter()
    combined_sentences: list[str] = []
    combined_text_lines: list[str] = []
    per_document_payloads: dict[str, str] = {}
    per_document_text: dict[str, str] = {}
    doc_stats: list[dict] = []

    for xml_path in iter_greek_xml_paths(extract_dir):
        rendered_sentences, raw_text_lines, stats = convert_document(xml_path, counters)
        doc_stats.append(stats)
        payload = "\n\n".join(rendered_sentences).rstrip() + "\n"
        per_document_payloads[xml_path.name] = payload
        per_document_text[xml_path.name] = "\n".join(raw_text_lines).rstrip() + "\n"
        combined_sentences.extend(rendered_sentences)
        combined_text_lines.extend(raw_text_lines)

    counts = [item["sentences"] for item in doc_stats]
    total_sentences = sum(counts)
    prefix = [0]
    for count in counts:
        prefix.append(prefix[-1] + count)
    best_split: tuple[float, int, int] | None = None
    for train_end in range(1, len(doc_stats) - 1):
        for dev_end in range(train_end + 1, len(doc_stats)):
            train_ratio = prefix[train_end] / total_sentences
            dev_ratio = (prefix[dev_end] - prefix[train_end]) / total_sentences
            test_ratio = (total_sentences - prefix[dev_end]) / total_sentences
            score = abs(train_ratio - 0.80) + abs(dev_ratio - 0.10) + abs(test_ratio - 0.10)
            candidate = (score, train_end, dev_end)
            if best_split is None or candidate < best_split:
                best_split = candidate
    assert best_split is not None
    _, train_end, dev_end = best_split
    ordered_doc_names = [item["document"] for item in doc_stats]
    splits = {
        "train": ordered_doc_names[:train_end],
        "dev": ordered_doc_names[train_end:dev_end],
        "test": ordered_doc_names[dev_end:],
    }

    summary = {
        "source_archive": str(args.archive),
        "extract_dir": str(extract_dir),
        "output_dir": str(output_dir),
        "documents": doc_stats,
        "document_count": len(doc_stats),
        "sentence_count": sum(item["sentences"] for item in doc_stats),
        "token_count": sum(item["tokens"] for item in doc_stats),
        "multi_root_sentences": counters["multi_root_sentences"],
        "reattached_extra_roots": counters["reattached_extra_roots"],
        "repaired_invalid_heads": counters["repaired_invalid_heads"],
        "dropped_cyclic_sentences": counters["dropped_cyclic_sentences"],
        "dropped_empty_surface_sentences": counters["dropped_empty_surface_sentences"],
        "dropped_bad_form_sentences": counters["dropped_bad_form_sentences"],
        "dropped_artificial_tokens": counters["dropped_artificial_tokens"],
        "resolved_artificial_heads": counters["resolved_artificial_heads"],
        "empty_relation_tokens": counters["empty_relation_tokens"],
        "empty_xpos_tokens": counters["empty_xpos_tokens"],
        "x_upos_tokens": counters["x_upos_tokens"],
        "upos_counts": {
            key.split("::", 1)[1]: value
            for key, value in sorted(counters.items())
            if key.startswith("upos::")
        },
        "splits": {
            split_name: {
                "documents": doc_names,
                "sentence_count": sum(
                    item["sentences"] for item in doc_stats if item["document"] in set(doc_names)
                ),
                "token_count": sum(
                    item["tokens"] for item in doc_stats if item["document"] in set(doc_names)
                ),
            }
            for split_name, doc_names in splits.items()
        },
    }

    write_outputs(
        output_dir,
        per_document_payloads,
        per_document_text,
        combined_sentences,
        combined_text_lines,
        summary,
        splits,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
