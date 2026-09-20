from __future__ import annotations

import assign_coarse_tags_to_manual_full_original_label_regions_v3 as runner


OUT_DIR = runner.OUT_DIR
runner.SUMMARY_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_summary.tsv"
runner.TAG_MAP_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_tag_map.tsv"
runner.REPORT_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_report.md"
runner.TOP10_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_top10_nonseed_with_seeds.tsv"
runner.BARE_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_bare.tsv"
runner.FORMATTED_OUT = OUT_DIR / "finerweb_manual_full_original_label_region_v4_no_program_bare_formatted.md"


V4_REGIONS = {
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
        "cultural practice", "religious practice", "object", "geographical feature", "economic indicator",
        "resource", "url", "temporal expression", "religious building", "natural feature", "artifact",
        "political figure",
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
    runner.V3_REGIONS = V4_REGIONS
    runner.base.MANUAL_REGIONS = V4_REGIONS
    runner.main()
    text = runner.FORMATTED_OUT.read_text(encoding="utf-8")
    runner.FORMATTED_OUT.write_text(text.replace("FinerWeb Manual Region Map V3", "FinerWeb Manual Region Map V4 No Program", 1), encoding="utf-8")


if __name__ == "__main__":
    main()
