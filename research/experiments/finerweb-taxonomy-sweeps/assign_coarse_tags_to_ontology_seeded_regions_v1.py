from __future__ import annotations

import csv

import numpy as np

import assign_coarse_tags_to_manual_full_label_child_regions as base


OUT_DIR = base.OUT_DIR
SUMMARY_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_report.md"
PHASE1_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_phase1_category_label_top10.tsv"
PHASE1_FORMATTED_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_phase1_category_label_top10.md"
TOP10_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_top10_nonseed_with_seeds.tsv"
BARE_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_bare.tsv"
FORMATTED_OUT = OUT_DIR / "finerweb_ontology_seeded_region_v1_bare_formatted.md"


ONTOLOGY_REGIONS = {
    "person": [
        "person",
        "persons",
        "people",
        "pessoa",
        "persona",
        "person name",
        "person's name",
        "historical person",
        "person type",
        "person category",
        "person alias",
    ],
    "social role": [
        "title",
        "profession",
        "position",
        "occupation",
        "job title",
        "political position",
        "role",
        "government position",
        "religious title",
        "military rank",
        "political office",
        "political title",
        "police rank",
        "social role",
        "political role",
        "religious role",
        "academic title",
        "diplomatic title",
        "ecclesiastical title",
        "organization role",
        "papal title",
        "rank",
        "legal profession",
        "government official",
        "police officer",
        "politician",
        "actor",
        "musician",
        "author",
        "artist",
        "poet",
        "philosopher",
        "composer",
        "athlete",
        "football player",
        "cricket player",
        "king",
        "priest",
        "bishop",
        "pope",
        "sage",
    ],
    "institution": [
        "organization",
        "political party",
        "government organization",
        "political organization",
        "educational institution",
        "sports team",
        "news agency",
        "government agency",
        "company",
        "media outlet",
        "media organization",
        "military organization",
        "sports club",
        "news organization",
        "government ministry",
        "university",
        "religious organization",
        "international organization",
        "law enforcement agency",
        "court",
        "government body",
        "legislative body",
        "institution",
        "military unit",
        "financial institution",
        "football club",
        "sports organization",
        "diocese",
        "government department",
        "governmental organization",
        "team",
        "religious institution",
        "bank",
        "news outlet",
        "police department",
        "stock exchange",
        "police force",
        "committee",
        "research institution",
        "research institute",
        "military force",
        "judicial institution",
        "basketball team",
        "airline",
        "police unit",
        "television network",
        "government entity",
        "league",
        "cultural institution",
        "football league",
        "government committee",
        "labor union",
        "regulatory body",
        "regulatory agency",
        "archdiocese",
        "criminal organization",
        "central bank",
        "academic department",
        "school",
        "faculty",
        "telecommunications company",
        "radio station",
        "emergency service",
        "sports federation",
        "non-profit organization",
        "parliament",
        "national team",
        "military branch",
        "youtube channel",
        "judicial body",
        "terrorist organization",
        "cricket team",
        "local government",
        "diplomatic mission",
    ],
    "sociopolitical structure": [
        "group",
        "nationality",
        "ethnic group",
        "demographic group",
        "social group",
        "group of people",
        "demographic",
        "community",
        "social class",
        "family",
        "demonym",
        "age group",
        "cultural group",
        "ethnicity",
        "gender",
        "political affiliation",
        "population",
        "population group",
        "person group",
        "historical group",
        "kinship",
        "society",
        "sexual orientation",
    ],
    "economy": [
        "currency",
        "cryptocurrency",
        "financial instrument",
        "financial product",
        "financial market",
        "financial index",
        "commodity",
        "market",
        "financial metric",
        "currency pair",
        "stock index",
        "stock market index",
        "financial asset",
        "cryptocurrency token",
        "stock",
        "stock ticker",
        "stock symbol",
        "business type",
        "business category",
        "business model",
        "business sector",
        "economic sector",
        "industry",
        "industry sector",
        "sector",
        "economic activity",
        "economic system",
        "financial activity",
        "financial transaction",
        "payment method",
        "trading platform",
        "trading strategy",
        "cryptocurrency exchange",
    ],
    "governance": [
        "legal concept",
        "legislation",
        "law",
        "policy",
        "legal term",
        "regulation",
        "legal provision",
        "legal framework",
        "legal process",
        "legal article",
        "legal charge",
        "legal status",
        "political agreement",
        "treaty",
        "legal reference",
        "legal system",
        "legal procedure",
        "international agreement",
        "government policy",
        "legal code section",
        "legislative proposal",
        "legal action",
        "legal field",
        "political system",
        "political ideology",
        "political regime",
        "political concept",
        "political process",
        "government program",
        "government initiative",
        "tax",
        "tax type",
    ],
    "facility": [
        "infrastructure",
        "building",
        "facility",
        "street",
        "address",
        "police station",
        "religious building",
        "road",
        "hotel",
        "airport",
        "government building",
        "restaurant",
        "temple",
        "building type",
        "religious site",
        "casino",
        "church",
        "stadium",
        "museum",
        "monastery",
        "transportation system",
        "architectural structure",
        "venue",
        "prison",
        "place of worship",
        "room type",
        "sports venue",
        "park",
        "shopping mall",
        "military base",
        "hospital",
        "healthcare facility",
        "medical facility",
        "cultural site",
    ],
    "location": [
        "location",
        "country",
        "city",
        "region",
        "state",
        "province",
        "district",
        "geographic region",
        "administrative region",
        "geopolitical entity",
        "administrative division",
        "village",
        "geographical region",
        "place",
        "geopolitical region",
        "geographical location",
        "neighborhood",
        "geographic location",
        "municipality",
        "subdistrict",
        "historical region",
        "locality",
        "regency",
        "town",
        "locations",
        "historical location",
        "geographic area",
        "historical empire",
        "location type",
        "economic zone",
        "border",
        "county",
        "barangay",
        "kingdom",
        "constituency",
    ],
    "natural environment": [
        "continent",
        "river",
        "celestial body",
        "geographical feature",
        "universe",
        "planet",
        "island",
        "body of water",
        "mountain",
        "natural feature",
        "astronomical object",
        "world",
        "mountain range",
        "geographic feature",
        "lake",
        "geological feature",
        "sea",
        "ocean",
        "river name",
        "celestial object",
        "space",
        "beach",
        "natural disaster",
        "natural phenomenon",
        "meteorological phenomenon",
        "weather phenomenon",
        "weather event",
    ],
    "organism": [
        "animal",
        "species",
        "plant",
        "biological entity",
        "virus",
        "plant species",
        "animal species",
        "organism",
        "biological taxon",
        "horse",
        "biological classification",
        "bacteria",
        "insect",
        "tree",
        "flower",
        "bacterium",
        "microorganism",
        "animal breed",
        "bird species",
        "cat breed",
        "plant variety",
        "biological species",
        "fish species",
        "cows",
    ],
    "object": [
        "object",
        "material",
        "substance",
        "chemical compound",
        "chemical substance",
        "nutrient",
        "chemical element",
        "resource",
        "hormone",
        "mineral",
        "natural resource",
        "chemical",
        "element",
        "energy source",
        "fuel type",
        "biological substance",
        "biochemical substance",
        "biological material",
        "precious metal",
        "fuel",
        "natural element",
        "biological molecule",
        "nutritional component",
        "protein",
        "biomolecule",
        "gemstone",
        "fabric",
        "building material",
        "waste material",
        "physical property",
    ],
    "time": [
        "date",
        "time period",
        "year",
        "time",
        "duration",
        "day of the week",
        "month",
        "time duration",
        "historical period",
        "date range",
        "day of week",
        "season",
        "temporal expression",
        "day",
        "time of day",
        "century",
        "date and time",
        "decade",
        "time measurement",
        "time zone",
        "temporal reference",
        "unit of time",
        "time expression",
        "day_of_week",
        "time range",
        "time interval",
        "anniversary",
        "era",
        "fiscal year",
        "academic year",
    ],
    "quantity": [
        "quantity",
        "measurement",
        "percentage",
        "age",
        "statistic",
        "score",
        "number",
        "distance",
        "statistics",
        "quantities",
        "ranking",
        "ordinal number",
        "page number",
        "degree",
        "unit of measurement",
        "rating",
        "statistical measurement",
        "amount",
        "statistical measure",
        "temperature",
        "statistical data",
        "ordinal",
        "cardinal",
        "weight",
        "sports score",
        "index",
        "frequency",
        "race time",
        "numerical value",
        "unit of measurement (area)",
        "area measurement",
        "sports statistic",
        "quantitative measurement",
        "chapter number",
        "numerical quantity",
        "distance measurement",
        "fraction",
        "volume",
        "weight class",
        "identification number",
        "monetary value",
        "currency amount",
        "monetary amount",
        "financial amount",
        "price",
        "price range",
        "price level",
    ],
    "event": [
        "event",
        "historical event",
        "cultural event",
        "festival",
        "sports event",
        "political event",
        "holiday",
        "sporting event",
        "religious event",
        "election",
        "event type",
        "campaign",
        "competition",
        "military operation",
        "sports competition",
        "conflict",
        "religious festival",
        "military conflict",
        "conference",
        "astronomical event",
        "film festival",
        "pandemic",
        "cultural festival",
        "sports tournament",
        "exam",
        "examination",
        "incident",
        "disaster",
    ],
    "action": [
        "activity",
        "action",
        "process",
        "procedure",
        "method",
        "methodology",
        "technique",
        "medical procedure",
        "medical treatment",
        "medical test",
        "biological process",
        "physiological process",
        "agricultural practice",
        "financial service",
        "criminal activity",
        "cultural activity",
        "educational activity",
        "beauty treatment",
        "business process",
        "business strategy",
        "practice",
        "promotion",
        "martial art",
    ],
    "product": [
        "product",
        "technology",
        "brand",
        "platform",
        "operating system",
        "vehicle",
        "weapon",
        "software",
        "product category",
        "application",
        "vehicle type",
        "product type",
        "vehicle model",
        "artifact",
        "clothing",
        "medical device",
        "car model",
        "military technology",
        "clothing item",
        "product model",
        "tool",
        "military equipment",
        "software version",
        "medical product",
        "device",
        "communication technology",
        "app",
        "aircraft",
        "component",
        "automobile model",
        "messaging application",
        "mobile application",
        "mobile phone model",
        "product component",
        "product line",
        "spacecraft",
        "malware",
        "software application",
        "streaming service",
        "product variant",
        "smartphone model",
        "product brand",
        "vessel",
        "engine type",
        "messaging app",
        "product name",
        "display technology",
        "version",
        "communication platform",
        "motorcycle model",
        "scientific instrument",
        "medical equipment",
        "military vessel",
        "software product",
        "e-commerce platform",
        "content management system",
        "equipment",
        "financial technology",
        "medical technology",
        "web browser",
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
        "subtitle language",
        "dialect",
        "translator",
        "figurative language",
    ],
    "concept": [
        "concept",
        "cultural concept",
        "philosophical concept",
        "social concept",
        "abstract concept",
        "general concept",
        "psychological concept",
        "linguistic concept",
        "mathematical concept",
        "truth",
        "ideology",
        "philosophical system",
        "historical concept",
        "literary concept",
        "theological concept",
        "spiritual concept",
        "technical concept",
        "design concept",
        "sports term",
        "general term",
        "topic",
        "framework",
        "system",
        "class",
        "category",
        "entity type",
        "property type",
        "attribute",
        "quality",
        "status",
        "relationship",
        "relation",
        "emotion",
        "emotional state",
        "lifestyle",
        "other",
    ],
    "text": [
        "text",
        "document",
        "legal document",
        "financial document",
        "report",
        "legislative document",
        "license",
        "government document",
        "document type",
        "legal code",
        "biblical reference",
        "biblical verse",
        "commentary",
        "encyclopedia",
        "letter",
        "word",
        "phrase",
        "slogan",
        "term",
        "punctuation",
        "acronym",
        "abbreviation",
        "initials",
        "identifier",
        "url",
        "email address",
        "phone number",
        "contact number",
        "postal code",
        "code",
        "document identifier",
        "username",
        "hashtag",
        "social media hashtag",
        "social media handle",
    ],
    "artwork": [
        "work of art",
        "film",
        "literary work",
        "game",
        "video game",
        "publication",
        "tv show",
        "music genre",
        "art form",
        "song",
        "musical instrument",
        "book",
        "tv series",
        "genre",
        "film title",
        "book title",
        "television show",
        "movie",
        "work of literature",
        "television series",
        "cultural work",
        "song title",
        "media program",
        "musical work",
        "album",
        "movie title",
        "tv program",
        "artwork",
        "casino game",
        "television program",
        "art",
        "video game series",
        "card game",
        "literary genre",
        "film genre",
        "game genre",
        "musical genre",
        "literary form",
        "media genre",
    ],
    "religious practice": [
        "religion",
        "religious concept",
        "religious practice",
        "religious ritual",
        "ritual",
        "deity",
        "god",
        "mythological figure",
        "mythological entity",
        "mythological creature",
        "mythical creature",
        "mythological character",
        "mythological being",
        "demon",
        "saint",
        "sacred syllable",
        "religious phrase",
        "religious text",
        "deity attribute",
        "deity epithet",
        "deity name",
        "nakshatra (lunar mansion)",
        "zodiac sign",
        "astrological sign",
        "astrological concept",
        "spiritual practice",
    ],
    "scientific inquiry": [
        "scientific concept",
        "field of study",
        "academic discipline",
        "scientific field",
        "medical concept",
        "health concept",
        "biological concept",
        "educational concept",
        "technological concept",
        "environmental concept",
        "physics concept",
        "scientific discipline",
        "medical term",
        "medical specialty",
        "scientific theory",
        "medical field",
        "academic subject",
        "academic program",
        "educational program",
        "education level",
        "educational level",
        "educational stage",
        "educational method",
        "academic degree",
        "degree",
        "certification",
        "educational qualification",
        "educational degree",
    ],
}


def phrase_vector(text: str, vectors: dict[str, np.ndarray]) -> tuple[np.ndarray | None, str]:
    item = {"tokens": base.text_tokens(text)}
    vec, matched = base.label_vector(item, vectors)
    return vec, "; ".join(matched)


def collect_needed_words(label_sets):
    needed = base.collect_needed_words(label_sets)
    for region, seeds in ONTOLOGY_REGIONS.items():
        for text in [region, *seeds]:
            for token in base.text_tokens(text):
                needed.update(base.vector_variants(token))
    return needed


def build_region_vectors(label_sets, vectors):
    region_vectors = {}
    region_evidence = {}
    missing = {}

    for region, seeds in ONTOLOGY_REGIONS.items():
        items = []
        missing_seeds = []
        for seed in seeds:
            seed_items = label_sets.get(seed, [])
            if not seed_items:
                missing_seeds.append(seed)
            items.extend(seed_items)

        seed_vec, vectorized_count, vectorized_mentions, matched = base.pooled_vector(items, vectors)
        label_vec, label_matched = phrase_vector(region, vectors)

        components = []
        weights = []
        if label_vec is not None:
            components.append(label_vec)
            weights.append(2.0)
        if seed_vec is not None:
            components.append(seed_vec)
            weights.append(1.0)
        if not components:
            raise RuntimeError(f"No vectorized evidence for region {region!r}")

        pooled = np.average(np.stack(components).astype(np.float32), axis=0, weights=np.array(weights))
        norm = np.linalg.norm(pooled)
        if not norm:
            raise RuntimeError(f"Zero vector for region {region!r}")

        region_vectors[region] = (pooled / norm).astype(np.float32)
        region_evidence[region] = {
            "original_label_count": len(items),
            "vectorized_original_label_count": vectorized_count,
            "vectorized_original_label_mentions": vectorized_mentions,
            "matched_words": f"category_label: {label_matched}; seeded_tags: {matched}",
        }
        if missing_seeds:
            missing[region] = missing_seeds

    return region_vectors, region_evidence, missing


def write_phase1_category_label_top10(rows, vectors) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PHASE1_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["category_label", "rank", "coarse_tag", "freq", "pct", "similarity_pct"])
        phase_rows = []
        for region in ONTOLOGY_REGIONS:
            label_vec, _matched = phrase_vector(region, vectors)
            if label_vec is None:
                continue
            candidates = []
            for row in rows:
                vec = row.get("vector")
                if vec is None:
                    continue
                candidates.append((float(np.dot(label_vec, vec)), row))
            candidates.sort(key=lambda item: (-item[0], -int(item[1]["count"]), str(item[1]["coarse_tag"])))
            for rank, (sim, row) in enumerate(candidates[:10], start=1):
                out = [
                    region,
                    rank,
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    f"{sim * 100:.2f}",
                ]
                writer.writerow(out)
                phase_rows.append(out)

    by_region = {}
    for row in phase_rows:
        by_region.setdefault(row[0], []).append(row)
    with PHASE1_FORMATTED_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Category Label Only Top 10 Coarse Tags\n\n")
        handle.write(
            "Each region here is represented only by the literal category-label phrase, before the extra certain-fit "
            "seed tags are added.\n\n"
        )
        for region in ONTOLOGY_REGIONS:
            handle.write(f"## {region}\n\n")
            for row in by_region.get(region, []):
                handle.write(f"- {row[1]}. {row[2]} ({row[3]}, sim {row[5]}%)\n")
            handle.write("\n")


def write_top10() -> None:
    with TAG_MAP_OUT.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    by_tag = {row["coarse_tag"]: row for row in rows}
    with TOP10_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["region", "type", "rank", "tag", "freq", "pct", "similarity_pct"])
        for region, seeds in ONTOLOGY_REGIONS.items():
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
        handle.write("# FinerWeb Ontology Seeded Region Map V1\n\n")
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
    base.MANUAL_REGIONS = ONTOLOGY_REGIONS
    base.SUMMARY_OUT = SUMMARY_OUT
    base.TAG_MAP_OUT = TAG_MAP_OUT
    base.REPORT_OUT = REPORT_OUT
    label_sets = base.load_label_sets()
    rows, total_count = base.load_rows(label_sets)
    vectors = base.ft.load_fasttext(collect_needed_words(label_sets))

    for row in rows:
        vec, vectorized_count, vectorized_mentions, matched = base.pooled_vector(row["original_labels"], vectors)
        row["vector"] = vec
        row["vectorized_original_label_count"] = vectorized_count
        row["vectorized_original_label_mentions"] = vectorized_mentions
        row["matched_words"] = matched

    write_phase1_category_label_top10(rows, vectors)
    region_vectors, region_evidence, missing = build_region_vectors(label_sets, vectors)
    base.assign_rows(rows, region_vectors)
    base.write_outputs(rows, total_count, region_evidence, missing)
    write_top10()
    write_bare()
    print(f"phase1={PHASE1_OUT}")
    print(f"phase1_formatted={PHASE1_FORMATTED_OUT}")
    print(f"top10={TOP10_OUT}")
    print(f"bare={BARE_OUT}")
    print(f"formatted={FORMATTED_OUT}")


if __name__ == "__main__":
    main()
