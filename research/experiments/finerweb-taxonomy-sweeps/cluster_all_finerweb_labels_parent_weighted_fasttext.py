import json

import numpy as np

import cluster_all_finerweb_labels_fasttext as base


OUTPUT_DIR = base.OUTPUT_DIR
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k50_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k50_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k50.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k50.json"


def phrase_vector(text, vectors):
    found = []
    matched = []
    for token in base.text_tokens(text):
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


def parent_child_weighted_vector(row, vectors):
    label = row["original_label"]
    if "/" not in label:
        return phrase_vector(label, vectors)

    parent, child = label.split("/", 1)
    parent_vec, parent_matched = phrase_vector(parent, vectors)
    child_vec, child_matched = phrase_vector(child, vectors)

    if parent_vec is not None and child_vec is not None:
        vec = (2.0 * parent_vec + child_vec) / 3.0
        norm = np.linalg.norm(vec)
        if norm:
            return vec / norm, parent_matched + child_matched
    if parent_vec is not None:
        return parent_vec, parent_matched
    if child_vec is not None:
        return child_vec, child_matched
    return None, parent_matched + child_matched


def prepend_weighting_note():
    text = REPORT_OUT.read_text(encoding="utf-8")
    text = text.replace(
        "# All fiNERweb Labels: FastText Similarity-Max K50\n\n",
        "# All fiNERweb Labels: Parent-Weighted FastText K50\n\n"
        "- Embedding rule: labels with `/` use parent text before the first slash at weight 2 "
        "and child text after the first slash at weight 1, then normalize.\n"
        "- Existing unweighted `all_finerweb_similarity_max_k50.*` outputs were not overwritten.\n\n",
        1,
    )
    REPORT_OUT.write_text(text, encoding="utf-8")


def add_json_metadata():
    payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    payload["embedding_rule"] = "parent_before_first_slash weight 2; child_after_first_slash weight 1; normalized"
    payload["previous_unweighted_outputs_preserved"] = True
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    base.SUMMARY_OUT = SUMMARY_OUT
    base.TAG_MAP_OUT = TAG_MAP_OUT
    base.REPORT_OUT = REPORT_OUT
    base.JSON_OUT = JSON_OUT

    rows = base.load_rows()
    vectors = base.load_fasttext(base.collect_needed_words(rows))
    vector_positions = []
    vecs = []
    for pos, row in enumerate(rows):
        vec, matched = parent_child_weighted_vector(row, vectors)
        row["matched_tokens"] = matched
        if vec is None:
            continue
        vector_positions.append(pos)
        vecs.append(vec)

    x = np.vstack(vecs).astype(np.float32)
    labels, centers, sims, best_state, attempts = base.choose_best_fit(x)
    base.write_outputs(rows, vector_positions, x, labels, centers, sims, best_state, attempts, vectors)
    prepend_weighting_note()
    add_json_metadata()


if __name__ == "__main__":
    main()
