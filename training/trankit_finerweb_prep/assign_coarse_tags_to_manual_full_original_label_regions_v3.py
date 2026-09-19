from __future__ import annotations

import csv
from pathlib import Path

import assign_coarse_tags_to_manual_full_label_child_regions as base


OUT_DIR = base.OUT_DIR
SUMMARY_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_report.md"
TOP10_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_top10_nonseed_with_seeds.tsv"
BARE_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_bare.tsv"
FORMATTED_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v3_bare_formatted.md"


V3_REGIONS = {
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
        "musician",
        "person group",
        "historical person",
        "athlete",
        "philosopher",
        "person name",
        "person type",
        "անձ",
        "person - politician",
        "व्यक्ति",
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
        "island",
        "geographical location",
        "localização",
        "hotel",
        "airport",
        "mountain",
        "مکان",
        "สถานที่",
        "neighborhood",
        "geographic location",
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
        "diocese",
        "organization type",
        "governmental organization",
        "religious institution",
        "acronym",
        "องค์กร",
        "organização",
        "organization abbreviation",
        "ארגון",
        "political movement",
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
        "time measurement",
        "time zone",
        "unit of time",
        "time expression",
        "race time",
        "day_of_week",
        "תאריך",
        "time range",
        "time interval",
        "วันที่",
    ],
    "cultural reference": [
        "cultural reference",
        "religious text",
        "social issue",
        "historical period",
        "historical figure",
        "cultural practice",
        "religious practice",
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
        "page number",
        "temperature",
        "statistical data",
        "mango variety",
        "ordinal",
        "weight",
        "quality",
        "مقدار",
        "frequency",
        "quantidade",
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
        "evento",
        "conference",
        "astronomical event",
        "election event",
        "conjunction",
        "economic event",
        "incident",
        "disaster",
        "event phase",
        "sports event stage",
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
        "weapon",
        "process",
        "محصول",
        "beverage",
        "food item",
        "เทคโนโลยี",
        "food ingredient",
        "clothing item",
        "product model",
        "produto",
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
        "general concept",
        "technological concept",
        "psychological concept",
        "economic term",
        "statistical concept",
        "meteorological phenomenon",
        "general term",
        "linguistic concept",
        "environmental concept",
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
        "website section",
        "news outlet",
        "news website",
        "media program",
        "television channel",
        "app",
        "television network",
        "web browser",
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
        "political title",
        "family name",
        "police rank",
        "social role",
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
        "religion",
        "sage",
        "demon",
        "زمان",
        "स्थान",
        "priest",
        "cardinal",
        "nakshatra (lunar mansion)",
        "mythical creature",
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
        "bank",
        "stock index",
        "precious metal",
        "financial amount",
        "currency value",
        "stock ticker",
        "index",
        "stock symbol",
        "central bank",
        "financial indicator",
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
        "grammarian",
        "լեզու",
        "שפה",
        "chatbot",
        "idioma",
        "language abbreviation",
        "lugha",
        "زبان",
        "subtitle language",
        "thai regional language",
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
        "age group",
        "family relation",
        "cultural group",
        "ethnicity",
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
        "genre",
        "film title",
        "feature",
        "fictional character",
        "text",
        "television show",
        "movie",
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
        "law",
        "agreement",
        "legal entity",
        "legal process",
        "legal article",
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
        "crime",
        "application",
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
        "plant",
        "nutrient",
        "health condition",
        "symptom",
    ],
    "material": [
        "material",
        "substance",
        "chemical substance",
        "energy source",
        "chemical element",
        "biological substance",
        "biochemical substance",
        "biological material",
        "building material",
        "information",
        "content type",
        "waste material",
        "educational material",
        "पोषण तत्व",
    ],
}


def write_top10() -> None:
    with TAG_MAP_OUT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    by_tag = {row["coarse_tag"]: row for row in rows}
    with TOP10_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["region", "type", "rank", "tag", "freq", "pct", "similarity_pct"])
        for region, seeds in V3_REGIONS.items():
            seed_set = set(seeds)
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


def write_bare() -> None:
    with TOP10_OUT.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    by_region = {}
    for row in rows:
        entry = by_region.setdefault(row["region"], {"seeds": [], "new": []})
        text = f"{row['tag']} ({row['freq']})"
        if row["type"] == "seed":
            entry["seeds"].append(text)
        elif row["type"] == "non_seed_top10":
            entry["new"].append(text)

    with BARE_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["bucket", "seed_tags", "new_tags_top10_by_frequency"])
        for region, entry in by_region.items():
            writer.writerow([region, "; ".join(entry["seeds"]), "; ".join(entry["new"])])

    with FORMATTED_OUT.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# FinerWeb Manual Region Map V3\n\n")
        for region, entry in by_region.items():
            handle.write(f"## {region}\n\n")
            handle.write("### Seed tags\n\n")
            for item in entry["seeds"]:
                handle.write(f"- {item}\n")
            handle.write("\n### New tags pulled in, top 10 by frequency\n\n")
            for item in entry["new"]:
                handle.write(f"- {item}\n")
            handle.write("\n")


def main() -> None:
    base.MANUAL_REGIONS = V3_REGIONS
    base.SUMMARY_OUT = SUMMARY_OUT
    base.TAG_MAP_OUT = TAG_MAP_OUT
    base.REPORT_OUT = REPORT_OUT
    base.main()
    write_top10()
    write_bare()
    print(f"top10={TOP10_OUT}")
    print(f"bare={BARE_OUT}")
    print(f"formatted={FORMATTED_OUT}")


if __name__ == "__main__":
    main()
