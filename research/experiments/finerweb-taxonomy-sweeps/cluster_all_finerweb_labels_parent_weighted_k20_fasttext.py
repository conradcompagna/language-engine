import json

import cluster_all_finerweb_labels_parent_weighted_fasttext as weighted
import cluster_all_finerweb_labels_fasttext as base


OUTPUT_DIR = base.OUTPUT_DIR
SUMMARY_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k20_summary.tsv"
TAG_MAP_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k20_tag_map.tsv"
REPORT_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k20.md"
JSON_OUT = OUTPUT_DIR / "all_finerweb_parent_weighted_k20.json"


def main():
    original_groups = base.VECTOR_GROUPS
    try:
        base.VECTOR_GROUPS = 20
        weighted.SUMMARY_OUT = SUMMARY_OUT
        weighted.TAG_MAP_OUT = TAG_MAP_OUT
        weighted.REPORT_OUT = REPORT_OUT
        weighted.JSON_OUT = JSON_OUT
        weighted.main()
        text = REPORT_OUT.read_text(encoding="utf-8")
        text = text.replace(
            "# All fiNERweb Labels: Parent-Weighted FastText K50",
            "# All fiNERweb Labels: Parent-Weighted FastText K20",
            1,
        )
        REPORT_OUT.write_text(text, encoding="utf-8")
        payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
        payload["vector_groups"] = 20
        JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        base.VECTOR_GROUPS = original_groups


if __name__ == "__main__":
    main()
