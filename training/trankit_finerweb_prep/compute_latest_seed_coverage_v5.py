from __future__ import annotations

import csv
from pathlib import Path


BASE = Path(__file__).resolve().parent
COARSE = BASE / "finerweb_label_inventory_coarse.tsv"
OUT = BASE / "derived_fasttext_categories" / "finerweb_latest_seed_coverage_v5.tsv"


SEEDS = {
    "person": [
        "person", "religious figure", "character", "persons", "people", "pessoa", "politician",
        "شخص", "บุคคล", "pope", "actor", "אדם", "persona", "musician", "person group",
        "historical person", "athlete", "philosopher", "person name", "person type", "անձ",
        "person - politician", "व्यक्ति", "cricketer", "person role", "person - arjuna's epithet",
        "person - historical ruler", "person alias", "պերսոն", "אישיות", "אישיות ציבורית",
        "person - cricketer", "wrestler",
    ],
    "location": [
        "location", "country", "city", "region", "infrastructure", "continent", "building", "province",
        "facility", "district", "river", "geographic region", "administrative region", "village",
        "geographical region", "place", "geopolitical region", "street", "island",
        "geographical location", "localização", "hotel", "airport", "mountain", "مکان", "สถานที่",
        "neighborhood", "geographic location", "police station", "کشور", "direction", "ประเทศ",
        "מיקום", "geographic feature", "locality", "town", "area", "locations", "historical location",
    ],
    "organization": [
        "organization", "political party", "government organization", "political organization",
        "educational institution", "sports team", "news agency", "government agency", "political entity",
        "company", "state", "government", "military organization", "news organization",
        "religious organization", "geopolitical entity", "international organization", "institution",
        "financial institution", "entity", "sports organization", "dynasty", "diocese",
        "organization type", "governmental organization", "religious institution", "acronym", "องค์กร",
        "organização", "organization abbreviation", "ארגון", "political movement",
        "terrorist organization", "سازمان", "government institution", "municipality",
        "government organization abbreviation", "church", "committee", "government agency abbreviation",
        "organizations", "political institution",
    ],
    "time": [
        "time", "date", "time period", "year", "duration", "day of the week", "month",
        "time duration", "date range", "day of week", "day", "age range", "time of day", "century",
        "date and time", "data", "decade", "time measurement", "time zone", "unit of time",
        "time expression", "race time", "day_of_week", "תאריך", "time range", "time interval",
        "วันที่", "anniversary", "تاریخ", "era", "minute of match", "time unit", "time_period",
        "fiscal year", "سال", "तारीख", "birth year",
    ],
    "cultural reference": [
        "cultural reference", "religious text", "social issue", "historical period", "historical figure",
        "cultural practice", "religious practice", "object", "artifact",
    ],
    "quantity": [
        "quantity", "measurement", "percentage", "age", "statistic", "monetary value", "score", "number",
        "price", "distance", "phone number", "quantities", "ordinal number", "contact number",
        "unit of measurement", "statistical measurement", "amount", "statistical measure", "page number",
        "temperature", "statistical data", "mango variety", "ordinal", "weight", "quality", "مقدار",
        "frequency", "quantidade", "numerical value", "כמות", "quantitative measurement", "price range",
        "numerical quantity", "distance measurement", "fraction", "identification number", "volume",
        "price level",
    ],
    "event": [
        "event", "historical event", "cultural event", "festival", "sports event", "political event",
        "sporting event", "religious event", "weather event", "event type", "אירוע", "evento",
        "conference", "astronomical event", "election event", "conjunction", "economic event", "incident",
        "disaster", "event phase", "sports event stage", "meteorological event", "life event",
        "event name", "meeting", "event category", "award event", "event - protest", "event theme",
        "sport event", "events",
    ],
    "product": [
        "product", "technology", "brand", "financial product", "software", "product category",
        "ingredient", "food product", "agricultural product", "product type", "weapon", "process",
        "محصول", "beverage", "food item", "เทคโนโลยี", "food ingredient", "clothing item",
        "product model", "produto", "vehicle model", "fuel type", "product feature", "tool",
        "software version", "pharmaceutical product", "medical product", "device",
        "communication technology", "model",
    ],
    "concept": [
        "concept", "scientific concept", "legal concept", "economic concept", "cultural concept",
        "financial concept", "philosophical concept", "political concept", "religious concept",
        "financial term", "social concept", "abstract concept", "medical concept", "business concept",
        "health concept", "biological concept", "educational concept", "political system",
        "general concept", "technological concept", "psychological concept", "economic term",
        "statistical concept", "meteorological phenomenon", "general term", "linguistic concept",
        "environmental concept", "physics concept", "method", "methodology", "philosophical system",
        "mathematical concept", "historical concept", "astrological concept", "military concept",
    ],
    "media": [
        "media", "social media platform", "website", "platform", "media outlet", "media organization",
        "hashtag", "newspaper", "media type", "social media", "media format", "social media handle",
        "website section", "news outlet", "news website", "media program", "television channel", "app",
        "television network", "web browser", "news source", "medium", "messaging application",
        "media platform", "social media account", "media channel", "tv channel", "messaging app",
    ],
    "title": [
        "title", "profession", "position", "occupation", "job title", "political position", "award",
        "role", "government position", "religious title", "administrative division", "military rank",
        "ranking", "book title", "political office", "political title", "family name", "police rank",
        "social role", "government official", "nickname", "political role",
    ],
    "deity": [
        "deity", "god", "mythological figure", "saint", "temple", "ritual",
        "hindu god of friendship", "hindu god of water", "mythological creature", "mythological entity",
        "religion", "sage", "demon", "زمان", "स्थान", "priest", "cardinal",
        "nakshatra (lunar mansion)", "mythical creature", "zodiac sign", "ธุรกิจ", "religious ritual",
        "राजनीतिक पार्टी", "sacred syllable",
    ],
    "currency": [
        "currency", "cryptocurrency", "financial instrument", "currency amount", "commodity",
        "financial index", "money", "financial metric", "tax", "currency pair", "stock exchange",
        "monetary amount", "bank", "stock index", "precious metal", "financial amount", "currency value",
        "stock ticker", "index", "stock symbol", "central bank", "financial indicator", "stock",
        "stock market index", "financial transaction", "financial asset", "cryptocurrency token", "grain",
        "stock price", "gemstone", "blockchain technology", "cryptocurrency exchange",
    ],
    "language": [
        "language", "programming language", "language family", "idiom", "language proficiency level",
        "idiomatic expression", "constructed language", "markup language", "language code", "language level",
        "language skill", "grammarian", "լեզու", "שפה", "chatbot", "idioma", "language abbreviation",
        "lugha", "زبان", "subtitle language", "thai regional language", "زبان رسمی", "dialect",
        "language learning", "language proficiency test", "name in another language", "translator",
        "figurative language", "foreign language name", "language - english", "language course",
    ],
    "group": [
        "group", "nationality", "ethnic group", "demographic group", "social group", "group of people",
        "religious group", "demographic", "political group", "social class", "family", "demonym",
        "age group", "family relation", "cultural group", "ethnicity", "political ideology", "category",
        "gender", "political affiliation", "population",
    ],
    "work of art": [
        "work of art", "film", "literary work", "video game", "publication", "tv show", "music genre",
        "art form", "song", "book", "tv series", "genre", "film title", "feature", "fictional character",
        "text", "television show", "movie", "literary genre", "work of literature", "game genre",
    ],
    "document": [
        "document", "legal document", "legal term", "document type", "legal code", "legal case",
        "legal provision", "legal institution", "legal framework", "law", "agreement", "legal entity",
        "legal process", "legal article", "legislation", "court", "financial document", "procedure",
        "judicial institution", "legal charge", "legal status",
    ],
    "medical condition": [
        "medical condition", "disease", "body part", "animal", "medical procedure", "chemical compound",
        "species", "biological entity", "anatomical structure", "virus", "drug", "plant", "nutrient",
        "health condition", "symptom", "celestial body", "hospital", "planet", "vaccine", "organ",
        "plant species",
    ],
    "material": [
        "material", "substance", "chemical substance", "energy source", "chemical element",
        "biological substance", "biochemical substance", "biological material", "building material",
        "information", "content type", "waste material", "educational material", "पोषण तत्व", "mineral",
        "chemical", "element", "fuel", "biomolecule", "fabric", "physical property", "evidence",
        "illegal substance", "renewable energy source",
    ],
}


def main() -> None:
    csv.field_size_limit(2**31 - 1)
    counts = {}
    with COARSE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            counts[row["coarse_label"]] = int(row["total_count"])

    total = sum(counts.values())
    seen = set()
    rows = []
    missing = []
    duplicate_count = 0
    for bucket, tags in SEEDS.items():
        bucket_total = 0
        bucket_unique_total = 0
        bucket_missing = []
        for tag in tags:
            count = counts.get(tag)
            if count is None:
                bucket_missing.append(tag)
                missing.append((bucket, tag))
                continue
            bucket_total += count
            if tag in seen:
                duplicate_count += count
            else:
                seen.add(tag)
                bucket_unique_total += count
        rows.append(
            {
                "bucket": bucket,
                "seed_tag_count": len(tags),
                "matched_seed_tag_count": len(tags) - len(bucket_missing),
                "seed_mentions": bucket_total,
                "percent_of_total": bucket_total / total * 100.0,
                "new_unique_seed_mentions": bucket_unique_total,
                "new_unique_percent_of_total": bucket_unique_total / total * 100.0,
                "missing_tags": "; ".join(bucket_missing),
            }
        )

    rows.sort(key=lambda row: -row["seed_mentions"])
    unique_total = sum(counts[tag] for tag in seen)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=[
                "bucket",
                "seed_tag_count",
                "matched_seed_tag_count",
                "seed_mentions",
                "percent_of_total",
                "new_unique_seed_mentions",
                "new_unique_percent_of_total",
                "missing_tags",
            ],
        )
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["percent_of_total"] = f"{row['percent_of_total']:.6f}"
            row["new_unique_percent_of_total"] = f"{row['new_unique_percent_of_total']:.6f}"
            writer.writerow(row)

    print(f"total_mentions\t{total}")
    print(f"unique_seed_tags\t{len(seen)}")
    print(f"unique_seed_mentions\t{unique_total}")
    print(f"unique_seed_percent\t{unique_total / total * 100:.6f}")
    print(f"duplicate_seed_mentions\t{duplicate_count}")
    print(f"missing_seed_tags\t{len(missing)}")
    print(f"wrote\t{OUT}")
    print()
    print("bucket\tseed_mentions\tpercent_of_total\tmatched/seed")
    for row in rows:
        print(
            f"{row['bucket']}\t{row['seed_mentions']}\t{row['percent_of_total']:.6f}\t"
            f"{row['matched_seed_tag_count']}/{row['seed_tag_count']}"
        )
    if missing:
        print()
        print("missing")
        for bucket, tag in missing:
            print(f"{bucket}\t{tag}")


if __name__ == "__main__":
    main()
