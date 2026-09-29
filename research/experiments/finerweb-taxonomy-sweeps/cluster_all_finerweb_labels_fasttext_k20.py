import json

import cluster_all_finerweb_labels_fasttext as base


OUTPUT_DIR = base.OUTPUT_DIR
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k20_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k20_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k20.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_similarity_max_k20.json"


def main():
    original_groups = base.VECTOR_GROUPS
    try:
        base.VECTOR_GROUPS = 20
        base.SUMMARY_OUT = SUMMARY_OUT
        base.TAG_MAP_OUT = TAG_MAP_OUT
        base.REPORT_OUT = REPORT_OUT
        base.JSON_OUT = JSON_OUT
        base.main()

        text = REPORT_OUT.read_text(encoding="utf-8")
        text = text.replace(
            "# All fiNERweb Labels: FastText Similarity-Max K50",
            "# All fiNERweb Labels: FastText Similarity-Max K20",
            1,
        )
        REPORT_OUT.write_text(text, encoding="utf-8")

        payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
        payload["vector_groups"] = 20
        payload["embedding_rule"] = "flat full original_label phrase vector; no parent/child weighting"
        JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        base.VECTOR_GROUPS = original_groups


if __name__ == "__main__":
    main()
