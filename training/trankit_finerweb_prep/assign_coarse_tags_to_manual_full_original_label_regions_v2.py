from __future__ import annotations

import csv
from pathlib import Path

import assign_coarse_tags_to_manual_full_label_child_regions as base


OUT_DIR = base.OUT_DIR
SUMMARY_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v2_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v2_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v2_report.md"
TOP10_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v2_top10_nonseed_with_seeds.tsv"


V2_REGIONS = {
    "person": [
        "person",
        "religious figure",
        "character",
        "persons",
        "people",
        "pessoa",
        "politician",
        "شخص",
        "บุคคล",
        "pope",
        "actor",
        "אדם",
        "persona",
    ],
    "location": [
        "location",
        "country",
        "city",
        "region",
        "infrastructure",
        "continent",
        "building",
        "province",
        "facility",
        "district",
        "river",
        "geographic region",
        "administrative region",
        "village",
        "geographical region",
        "place",
        "geopolitical region",
        "street",
    ],
    "organization": [
        "organization",
        "political party",
        "government organization",
        "political organization",
        "educational institution",
        "sports team",
        "news agency",
        "government agency",
        "political entity",
        "company",
        "state",
        "government",
        "military organization",
        "news organization",
        "religious organization",
        "geopolitical entity",
        "international organization",
        "institution",
        "financial institution",
        "entity",
        "sports organization",
        "dynasty",
    ],
    "time": [
        "time",
        "date",
        "time period",
        "year",
        "duration",
        "day of the week",
        "month",
        "time duration",
        "date range",
        "day of week",
        "day",
        "age range",
        "time of day",
        "century",
        "date and time",
        "data",
        "decade",
    ],
    "cultural reference": [
        "cultural reference",
        "religious text",
        "social issue",
        "historical period",
        "historical figure",
        "cultural practice",
    ],
    "quantity": [
        "quantity",
        "measurement",
        "percentage",
        "age",
        "statistic",
        "monetary value",
        "score",
        "number",
        "price",
        "distance",
        "phone number",
        "quantities",
        "ordinal number",
        "contact number",
        "unit of measurement",
        "statistical measurement",
        "amount",
        "statistical measure",
    ],
    "event": [
        "event",
        "historical event",
        "cultural event",
        "festival",
        "sports event",
        "political event",
        "sporting event",
        "religious event",
        "weather event",
        "event type",
        "אירוע",
    ],
    "product": [
        "product",
        "technology",
        "brand",
        "financial product",
        "software",
        "product category",
        "ingredient",
        "food product",
        "agricultural product",
        "product type",
    ],
    "concept": [
        "concept",
        "scientific concept",
        "legal concept",
        "economic concept",
        "cultural concept",
        "financial concept",
        "philosophical concept",
        "political concept",
        "religious concept",
        "financial term",
        "social concept",
        "abstract concept",
        "medical concept",
        "business concept",
        "health concept",
        "biological concept",
        "educational concept",
        "political system",
    ],
    "media": [
        "media",
        "social media platform",
        "website",
        "platform",
        "media outlet",
        "media organization",
        "hashtag",
        "newspaper",
        "media type",
        "social media",
        "media format",
        "social media handle",
    ],
    "title": [
        "title",
        "profession",
        "position",
        "occupation",
        "job title",
        "political position",
        "award",
        "role",
        "government position",
        "religious title",
        "administrative division",
        "military rank",
        "ranking",
        "book title",
        "political office",
    ],
    "deity": [
        "deity",
        "god",
        "mythological figure",
        "saint",
        "temple",
        "ritual",
        "hindu god of friendship",
        "hindu god of water",
        "mythological creature",
        "mythological entity",
    ],
    "currency": [
        "currency",
        "cryptocurrency",
        "financial instrument",
        "currency amount",
        "commodity",
        "financial index",
        "money",
        "financial metric",
        "tax",
        "currency pair",
        "stock exchange",
        "monetary amount",
    ],
    "language": [
        "language",
        "programming language",
        "language family",
        "idiom",
        "language proficiency level",
        "idiomatic expression",
        "constructed language",
        "markup language",
        "language code",
        "language level",
        "language skill",
    ],
    "group": [
        "group",
        "nationality",
        "ethnic group",
        "demographic group",
        "social group",
        "group of people",
        "religious group",
        "demographic",
        "political group",
        "social class",
        "family",
        "demonym",
    ],
    "work of art": [
        "work of art",
        "film",
        "literary work",
        "video game",
        "publication",
        "tv show",
        "music genre",
        "art form",
        "song",
        "book",
        "tv series",
    ],
    "document": [
        "document",
        "legal document",
        "legal term",
        "document type",
        "legal code",
        "legal case",
        "legal provision",
        "legal institution",
        "legal framework",
    ],
    "program": [
        "program",
        "service",
        "activity",
        "field of study",
        "industry",
        "sport",
        "game",
        "sports league",
        "project",
        "financial market",
    ],
    "medical condition": [
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
    ],
    "material": [
        "material",
        "substance",
        "chemical substance",
        "energy source",
    ],
}


def write_top10() -> None:
    with TAG_MAP_OUT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    with TOP10_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["region", "type", "rank", "tag", "freq", "pct", "similarity_pct"])
        for region, seeds in V2_REGIONS.items():
            seed_set = set(seeds)
            by_tag = {row["coarse_tag"]: row for row in rows}
            for rank, seed in enumerate(seeds, start=1):
                row = by_tag.get(seed)
                if row is None:
                    writer.writerow([region, "seed", rank, seed, "MISSING", "", ""])
                else:
                    writer.writerow(
                        [
                            region,
                            "seed",
                            rank,
                            row["coarse_tag"],
                            row["count"],
                            row["percent_of_total"],
                            row["similarity_to_region_pct"],
                        ]
                    )
            candidates = [
                row
                for row in rows
                if row["assigned_region"] == region and row["coarse_tag"] not in seed_set
            ]
            candidates.sort(key=lambda row: (-int(row["count"]), row["coarse_tag"]))
            for rank, row in enumerate(candidates[:10], start=1):
                writer.writerow(
                    [
                        region,
                        "non_seed_top10",
                        rank,
                        row["coarse_tag"],
                        row["count"],
                        row["percent_of_total"],
                        row["similarity_to_region_pct"],
                    ]
                )


def main() -> None:
    base.MANUAL_REGIONS = V2_REGIONS
    base.SUMMARY_OUT = SUMMARY_OUT
    base.TAG_MAP_OUT = TAG_MAP_OUT
    base.REPORT_OUT = REPORT_OUT
    base.main()
    write_top10()
    print(f"top10={TOP10_OUT}")


if __name__ == "__main__":
    main()
