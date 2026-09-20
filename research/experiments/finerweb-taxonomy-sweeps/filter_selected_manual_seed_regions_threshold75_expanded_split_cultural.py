from __future__ import annotations

import compute_latest_seed_coverage_v5 as latest
import filter_selected_manual_seed_regions_threshold60_concept_title_split_cultural as runner


runner.THRESHOLD = 0.75
runner.SUMMARY_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_expanded_split_cultural_summary.tsv"
runner.TAG_MAP_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_expanded_split_cultural_retained_tag_map.tsv"
runner.REPORT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_expanded_split_cultural_report.md"
runner.ASSIGNMENT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_expanded_split_cultural_all_assignments.tsv"


BIOMED_SEEDS = [
    "medical condition",
    "disease",
    "body part",
    "animal",
    "medical procedure",
    "chemical compound",
    "species",
    "biological entity",
    "anatomical structure",
    "virus",
    "drug",
    "plant",
    "nutrient",
    "health condition",
    "symptom",
    "celestial body",
    "hospital",
    "planet",
    "vaccine",
    "organ",
    "plant species",
    "natural disaster",
    "body of water",
    "medication",
    "medical treatment",
    "animal species",
    "organism",
    "medical symptom",
    "health issue",
    "condition",
    "skin condition",
    "mental health condition",
    "biological structure",
    "body_part",
    "biological system",
    "cell type",
    "plant part",
    "anatomy",
    "anatomical system",
    "body fluid",
    "biological taxon",
    "biological classification",
    "bacteria",
    "bacterium",
    "microorganism",
    "animal breed",
    "bird species",
    "plant variety",
    "biological species",
    "fish species",
    "tree species",
    "medical test",
    "medical practice",
    "medical specialty",
    "medical field",
    "medical term",
    "medical concept",
    "health concept",
    "health protocol",
    "health status",
    "drug",
    "vaccine",
    "medication",
    "drug class",
    "pharmaceutical drug",
    "pharmaceutical",
    "pharmaceutical product",
    "medical product",
    "medical device",
    "medical equipment",
    "chemical substance",
    "biological substance",
    "biochemical substance",
    "biological material",
    "biological molecule",
    "biomolecule",
    "protein",
    "biochemical compound",
]


runner.SELECTED_REGIONS = {
    "person": latest.SEEDS["person"],
    "location": latest.SEEDS["location"],
    "organization": latest.SEEDS["organization"],
    "product": latest.SEEDS["product"],
    "money": latest.SEEDS["currency"],
    "time": latest.SEEDS["time"],
    "event": latest.SEEDS["event"],
    "work of art": latest.SEEDS["work of art"],
    "group": latest.SEEDS["group"],
    "language": latest.SEEDS["language"],
    "quantity": latest.SEEDS["quantity"],
    "concept": latest.SEEDS["concept"],
    "title": latest.SEEDS["title"],
    "media": latest.SEEDS["media"],
    "law": latest.SEEDS["document"],
    "religious practice": latest.SEEDS["deity"],
    "biomed": BIOMED_SEEDS,
}


if __name__ == "__main__":
    runner.main()
