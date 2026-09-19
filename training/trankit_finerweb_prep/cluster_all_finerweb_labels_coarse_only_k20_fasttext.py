import json

import numpy as np

import cluster_all_finerweb_labels_fasttext as base


OUTPUT_DIR = base.OUTPUT_DIR
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_unique_coarse_k20_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_unique_coarse_k20_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_unique_coarse_k20.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_unique_coarse_k20.json"


def coarse_text(label):
    return label.split("/", 1)[0].strip()


def load_unique_coarse_rows():
    seen = set()
    rows = []
    for row in base.load_rows():
        coarse = coarse_text(row["original_label"])
        key = base.norm_text(coarse)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "original_label": coarse,
                "tokens": base.text_tokens(coarse),
            }
        )
    return rows


def collect_needed_words(rows):
    needed = set()
    for row in rows:
        for token in row["tokens"]:
            needed.update(base.variants(token))
    return needed


def coarse_only_vector(row, vectors):
    found = []
    matched = []
    for token in row["tokens"]:
        word, vec = base.token_vector(token, vectors)
        if vec is not None:
            found.append(vec)
            matched.append(word)
    if not found:
        return None, matched
    vec = np.mean(found, axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return None, matched
    return vec / norm, matched


def fix_report_and_metadata():
    text = REPORT_OUT.read_text(encoding="utf-8")
    text = text.replace(
        "# All fiNERweb Labels: FastText Similarity-Max K50\n\n",
        "# All fiNERweb Labels: Coarse-Only FastText K20\n\n"
        "- Input rule: deduped unique coarse labels extracted from `original_label` before the first slash; "
        "labels without `/` use the whole label as their coarse label.\n"
        "- Existing unweighted and parent-weighted outputs were not overwritten.\n\n",
        1,
    )
    REPORT_OUT.write_text(text, encoding="utf-8")

    payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    payload["input_rule"] = "deduped unique coarse labels from original_label before first slash"
    payload["embedding_rule"] = "coarse label only; child text ignored; normalized"
    payload["vector_groups"] = 20
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    original_groups = base.VECTOR_GROUPS
    try:
        base.VECTOR_GROUPS = 20
        base.SUMMARY_OUT = SUMMARY_OUT
        base.TAG_MAP_OUT = TAG_MAP_OUT
        base.REPORT_OUT = REPORT_OUT
        base.JSON_OUT = JSON_OUT

        rows = load_unique_coarse_rows()
        vectors = base.load_fasttext(collect_needed_words(rows))
        vector_positions = []
        vecs = []
        for pos, row in enumerate(rows):
            vec, matched = coarse_only_vector(row, vectors)
            row["matched_tokens"] = matched
            if vec is None:
                continue
            vector_positions.append(pos)
            vecs.append(vec)

        x = np.vstack(vecs).astype(np.float32)
        labels, centers, sims, best_state, attempts = base.choose_best_fit(x)
        base.write_outputs(rows, vector_positions, x, labels, centers, sims, best_state, attempts, vectors)
        fix_report_and_metadata()
    finally:
        base.VECTOR_GROUPS = original_groups


if __name__ == "__main__":
    main()
