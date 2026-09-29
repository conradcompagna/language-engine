from __future__ import annotations

import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
IN_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples.tsv"
OUT_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples_under25_map.tsv"
SCHEME_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_under25_mapping_scheme.tsv"


SCHEME = {
    "PERSON_OR_BEING": "Named or typed humans, deities, saints, fictional characters, and mythological beings.",
    "ROLE_TITLE_STATUS": "Human titles, offices, ranks, professions, kinship roles, and formal statuses.",
    "GROUP_POPULATION": "Human populations, social groups, identities, families, communities, and demographics.",
    "ORGANIZATION": "Institutions, companies, parties, agencies, teams, media outlets, courts, schools, and organized bodies.",
    "GEOPOLITICAL_PLACE": "Countries, cities, regions, administrative divisions, neighborhoods, and political territories.",
    "NATURAL_PLACE": "Natural or astronomical places and features, including rivers, mountains, planets, oceans, and islands.",
    "FACILITY_INFRASTRUCTURE": "Built places, buildings, roads, infrastructure, venues, facilities, and physical sites.",
    "TIME_DATE": "Dates, times, durations, periods, seasons, and calendar expressions.",
    "EVENT_HAPPENING": "Events, holidays, competitions, disasters, elections, projects, campaigns, and crises.",
    "QUANTITY_MEASURE": "Numbers, measurements, scores, rankings, statistics, units, ratings, ages, and indicators.",
    "MONEY_FINANCE": "Currencies, prices, money amounts, markets, instruments, commodities, crypto, and financial assets.",
    "IDENTIFIER_CONTACT": "URLs, websites as addresses, handles, hashtags, phone numbers, emails, codes, acronyms, and IDs.",
    "LANGUAGE_TEXT_NAME": "Languages, words, names, nicknames, references, symbols, slogans, labels, and text fragments.",
    "WORK_MEDIA_ART": "Films, books, songs, games, documents, publications, genres, artworks, media formats, and cultural works.",
    "PRODUCT_TECH_OBJECT": "Products, services, tools, software, platforms, vehicles, weapons, devices, artifacts, and equipment.",
    "MATERIAL_SUBSTANCE": "Materials, chemicals, drugs, medications, minerals, nutrients, elements, resources, and fuels.",
    "FOOD_AGRICULTURE": "Foods, dishes, drinks, ingredients, crops, culinary categories, and agricultural products.",
    "ORGANISM_TAXON": "Animals, plants, viruses, bacteria, species, breeds, taxa, and other living organisms.",
    "ANATOMY_BIOLOGY": "Body parts, organs, anatomical structures, biological structures, biological systems, and cells.",
    "HEALTH_MEDICINE": "Diseases, symptoms, medical conditions, health issues, and health statuses.",
    "CONCEPT_FIELD_DOMAIN": "Abstract concepts, fields, disciplines, ideologies, sectors, systems, issues, theories, and domains.",
    "LAW_POLICY_NORM": "Laws, policies, legal concepts, crimes, regulations, agreements, taxes, standards, and legal processes.",
    "ACTION_PROCESS": "Activities, procedures, methods, practices, treatments, tests, rituals, processes, and transactions.",
    "ATTRIBUTE_PROPERTY": "Colors, features, categories, relationships, qualities, properties, statuses, specifications, and emotions.",
    "EDUCATION_AWARD": "Awards, degrees, certifications, qualifications, education levels, and academic programs.",
}


TAG_TRANSLATIONS = {
    "pessoa": "person",
    "\u0634\u062e\u0635": "person",
    "\u0e1a\u0e38\u0e04\u0e04\u0e25": "person",
    "\u05d0\u05d3\u05dd": "person",
    "localização": "location",
    "\u0645\u06a9\u0627\u0646": "place",
    "\u0e2a\u0e16\u0e32\u0e19\u0e17\u0e35\u0e48": "place",
    "organização": "organization",
    "\u0e2d\u0e07\u0e04\u0e4c\u0e01\u0e23": "organization",
    "\u05d0\u05e8\u05d2\u05d5\u05df": "organization",
    "\u0633\u0627\u0632\u0645\u0627\u0646": "organization",
    "\u0645\u062d\u0635\u0648\u0644": "product",
    "\u0e40\u0e17\u0e04\u0e42\u0e19\u0e42\u0e25\u0e22\u0e35": "technology",
    "\u06a9\u0634\u0648\u0631": "country",
    "\u0e40\u0e2b\u0e15\u0e38\u0e01\u0e32\u0e23\u0e13\u0e4c": "event",
}


MANUAL_LABEL_OVERRIDES = {
    "academic program": "EDUCATION_AWARD",
    "agricultural product": "FOOD_AGRICULTURE",
    "anatomical structure": "ANATOMY_BIOLOGY",
    "abstract concept": "CONCEPT_FIELD_DOMAIN",
    "artifact": "PRODUCT_TECH_OBJECT",
    "beverage": "FOOD_AGRICULTURE",
    "biblical reference": "LANGUAGE_TEXT_NAME",
    "biological concept": "CONCEPT_FIELD_DOMAIN",
    "biological entity": "ORGANISM_TAXON",
    "biological structure": "ANATOMY_BIOLOGY",
    "body of water": "NATURAL_PLACE",
    "body part": "ANATOMY_BIOLOGY",
    "book title": "WORK_MEDIA_ART",
    "business concept": "CONCEPT_FIELD_DOMAIN",
    "business model": "CONCEPT_FIELD_DOMAIN",
    "celestial body": "NATURAL_PLACE",
    "concept": "CONCEPT_FIELD_DOMAIN",
    "contact number": "IDENTIFIER_CONTACT",
    "currency amount": "MONEY_FINANCE",
    "cultural artifact": "PRODUCT_TECH_OBJECT",
    "cultural concept": "CONCEPT_FIELD_DOMAIN",
    "cultural reference": "WORK_MEDIA_ART",
    "disease": "HEALTH_MEDICINE",
    "document type": "WORK_MEDIA_ART",
    "economic concept": "CONCEPT_FIELD_DOMAIN",
    "economic term": "CONCEPT_FIELD_DOMAIN",
    "educational concept": "CONCEPT_FIELD_DOMAIN",
    "educational program": "EDUCATION_AWARD",
    "email address": "IDENTIFIER_CONTACT",
    "entity": "CONCEPT_FIELD_DOMAIN",
    "family name": "LANGUAGE_TEXT_NAME",
    "film title": "WORK_MEDIA_ART",
    "financial index": "MONEY_FINANCE",
    "food product": "FOOD_AGRICULTURE",
    "framework": "CONCEPT_FIELD_DOMAIN",
    "general concept": "CONCEPT_FIELD_DOMAIN",
    "geopolitical entity": "GEOPOLITICAL_PLACE",
    "government building": "FACILITY_INFRASTRUCTURE",
    "government program": "ACTION_PROCESS",
    "health concept": "CONCEPT_FIELD_DOMAIN",
    "holiday": "EVENT_HAPPENING",
    "infrastructure project": "EVENT_HAPPENING",
    "language": "LANGUAGE_TEXT_NAME",
    "legal code": "LAW_POLICY_NORM",
    "legal document": "LAW_POLICY_NORM",
    "legal framework": "LAW_POLICY_NORM",
    "medical term": "CONCEPT_FIELD_DOMAIN",
    "military technology": "PRODUCT_TECH_OBJECT",
    "news website": "WORK_MEDIA_ART",
    "newspaper": "WORK_MEDIA_ART",
    "operating system": "PRODUCT_TECH_OBJECT",
    "philosophical concept": "CONCEPT_FIELD_DOMAIN",
    "philosophical school": "CONCEPT_FIELD_DOMAIN",
    "phone number": "IDENTIFIER_CONTACT",
    "political concept": "CONCEPT_FIELD_DOMAIN",
    "political group": "ORGANIZATION",
    "political system": "CONCEPT_FIELD_DOMAIN",
    "police station": "FACILITY_INFRASTRUCTURE",
    "program": "ACTION_PROCESS",
    "programming language": "LANGUAGE_TEXT_NAME",
    "psychological concept": "CONCEPT_FIELD_DOMAIN",
    "ranking": "QUANTITY_MEASURE",
    "religious concept": "CONCEPT_FIELD_DOMAIN",
    "religious text": "WORK_MEDIA_ART",
    "scientific concept": "CONCEPT_FIELD_DOMAIN",
    "season": "TIME_DATE",
    "social concept": "CONCEPT_FIELD_DOMAIN",
    "social media platform": "PRODUCT_TECH_OBJECT",
    "song title": "WORK_MEDIA_ART",
    "technological concept": "CONCEPT_FIELD_DOMAIN",
    "website": "IDENTIFIER_CONTACT",
    "website section": "IDENTIFIER_CONTACT",
}


EXAMPLE_TRANSLATION_OVERRIDES = {
    "Selasa, 15 November 2016": "Tuesday, November 15, 2016",
    "Masker": "Mask",
    "Prokes": "health protocols",
    "Jepang": "Japan",
    "Adipati Edinburgh": "Duke of Edinburgh",
    "Togel Hongkong": "Hong Kong lottery",
    "Allah Subhanahu wa ta'ala": "Allah, may He be glorified and exalted",
    "Jerman": "German",
    "Selasa": "Tuesday",
    "Menteri Keuangan": "Minister of Finance",
    "Pemimpinan Pemerintah": "government leadership",
    "Mei": "May",
    "UU": "law",
    "Walikota": "mayor",
    "perduaan": "pairing",
    "Kepala Daerah": "regional head",
    "Hadiah Nobel": "Nobel Prize",
    "Rasulullah": "the Messenger of God",
    "Orang Indonesia": "Indonesian people",
    "Proyek Jalan": "road project",
    "Runtuhnya Majapahit": "the fall of Majapahit",
    "Tiga Siswi SMP": "three junior high school students",
    "POJOKJABAR.com": "POJOKJABAR.com",
    "Kiai Ma'ruf": "Kiai Ma'ruf",
    "Tentara Nasional Indonesia (TNI)": "Indonesian National Armed Forces (TNI)",
    "ÕŠÕ¸Õ½Õ¥ÕµÕ¤Õ¸Õ¶": "Poseidon",
    "tepung terigu": "wheat flour",
    "Iblis": "the Devil",
    "Tanah Air": "homeland",
    "Organisasi Kesehatan Dunia (WHO)": "World Health Organization (WHO)",
    "Kecamatan Pamboang": "Pamboang District",
    "Rasulullah SAW": "the Messenger of God",
    "dangdut": "dangdut music",
    "Pengadilan Negeri": "District Court",
    "Inkrah": "final and binding",
    "Sastra": "literature",
    "Republikan": "Republican",
    "Sungai Kapuas": "Kapuas River",
    "\u0e08\u0e31\u0e01\u0e23\u0e27\u0e32\u0e25\u0e2a\u0e32\u0e21\u0e1e\u0e34\u0e20\u0e1e": "three-world universe",
    "Senat": "Senate",
    "Kongres": "Congress",
    "padi sawah": "paddy rice",
    "SD": "elementary school",
    "Nusantara": "Indonesian archipelago",
    "Barat": "West",
    "Minggu": "Sunday",
    "nuklir": "nuclear",
    "Gizi": "nutrition",
    "Kita": "we",
    "Warna: Sejarah Alam Palet": "Color: A Natural History of the Palette",
    "Dinasti Joseon": "Joseon Dynasty",
    "Tahun Baru Imlek 2020": "Chinese New Year 2020",
    "Serma TNI": "TNI sergeant major",
    "\u0627\u0628\u0631\u0633": "Abrus",
    "\u0627\u0633\u0644\u062d\u0647 \u0634\u06a9\u0627\u0631\u06cc": "hunting weapon",
    "\u0e04\u0e38\u0e13\u0e41\u0e21\u0e48": "mother",
    "ayam suwir pedas": "spicy shredded chicken",
    "Jl godean km 15": "Godean Road km 15",
    "SÃ£o Pedro": "Saint Peter",
    "Presiden": "president",
    "Mushola â€œ ATH THOYYIBU â€": "Ath Thoyyibu prayer room",
    "\u0e0a\u0e21\u0e23\u0e21\u0e41\u0e1a\u0e14\u0e21\u0e34\u0e19\u0e15\u0e31\u0e19": "badminton club",
    "umroh": "umrah",
    "Jalan Raya": "main road",
    "Hotel sinar mas": "Sinar Mas Hotel",
    "Keluarga Akidi Tio": "Akidi Tio family",
    "Arek Suroboyo": "Surabaya people",
    "Alquran": "Quran",
    "menjangan": "deer",
    "cafe": "cafe",
    "× ×™×•-×™×•×¨×§ ×˜×™×™×ž×¡": "New York Times",
    "\u0627\u0633\u062a\u062e\u0631\u0647\u0627\u06cc \u0630\u062e\u06cc\u0631\u0647 \u0622\u0628 \u06a9\u0634\u0627\u0648\u0631\u0632\u06cc": "agricultural water reservoirs",
    "kepompong nyamuk": "mosquito pupa",
    "romanzo distopico": "dystopian novel",
    "\u0e2d\u0e32\u0e04\u0e32\u0e23\u0e1e\u0e32\u0e13\u0e34\u0e0a\u0e22\u0e4c": "commercial building",
    "kepariwisataan": "tourism",
    "baccarat": "baccarat",
    "\u0633\u0627\u0632\u0645\u0627\u0646 \u062f\u0627\u0645\u067e\u0632\u0634\u06a9\u06cc": "veterinary organization",
    "Kamis": "Thursday",
    "\u092f\u093e\u091c\u094d\u091e\u0935\u0932\u094d\u0915\u094d\u092f": "Yajnavalkya",
    "Pasien IGD": "emergency room patient",
    "\u0e01\u0e32\u0e23\u0e1e\u0e19\u0e31\u0e19\u0e1a\u0e25\u0e47\u0e2d\u0e04\u0e40\u0e0a\u0e19": "blockchain gambling",
    "Jurusan Teknik Mesin": "Mechanical Engineering Department",
    "Bagian Biologi": "Biology Department",
    "nasi tumpeng": "tumpeng rice",
    "toscana": "Tuscan",
    "Candi Cangkuang": "Cangkuang Temple",
    "Ulimwengu": "world",
    "SDN Pranti": "Pranti public elementary school",
    "Shahih Bukhori": "Sahih Bukhari",
    "prokes": "health protocols",
    "otolaringologi": "otolaryngology",
    "onen tfe kio": "ritual",
    "bibliss": "bibliss",
    "×‘×¨× ×“×Ÿ ×¨×•×’'×¨×¡": "Brendan Rodgers",
    "Menteri Luar Negeri AS": "U.S. Secretary of State",
    "\u0622\u0644\u0645\u0627\u0646": "Germany",
    "Gebernur Riau": "Governor of Riau",
    "Pemilihan Gubenur Kalbar": "West Kalimantan gubernatorial election",
    "ruko": "shop-house",
    "olivin": "olivine",
    "Pasal 81 Ayat (1)": "Article 81 paragraph (1)",
    "Belanda-Tionghoa-Jawa": "Dutch-Chinese-Javanese",
    "\u092e\u093f\u0924\u094d\u0930": "Mitra",
    "\u0935\u0930\u0941\u0923": "Varuna",
    "Pirenei": "Pyrenees",
    "Kejari": "District Prosecutor's Office",
    "amaf": "social role",
    "UU ITE": "Electronic Information and Transactions Law",
    "NusaBali.com": "NusaBali.com",
    "99 Tahun": "99 years",
    "Asia Tenggara": "Southeast Asia",
    "Pemerintah": "government",
    "Eropa": "Europe",
    "Gedung Rektorat": "Rectorate Building",
    "Intervensi": "intervention",
    "Pergub 46 Tahun 2020": "Governor Regulation 46 of 2020",
    "Masyarakat": "community",
    "Program Studi Akuntansi": "Accounting Study Program",
    "Divisi Pemasyarakatan": "Corrections Division",
    "S.H.": "Bachelor of Laws",
    "Mushola “ ATH THOYYIBU ”": "Ath Thoyyibu prayer room",
    "São Pedro": "Saint Peter",
    "Media Online": "online media",
    "Halaman Pembicaraan": "talk page",
    "021-70416745–085283045333": "021-70416745–085283045333",
    "http: //184.108.40.206/": "http: //184.108.40.206/",
    "vestibular": "entrance exam",
    "\u05d1\u05e8\u05e0\u05d3\u05df \u05e8\u05d5\u05d2'\u05e8\u05e1": "Brendan Rodgers",
    "Devastavismo®": "Devastavismo",
}


def norm_tag(tag: str) -> str:
    return (tag or "").strip().lower().replace("_", " ")


def tag_english(tag: str) -> str:
    return TAG_TRANSLATIONS.get(tag, tag.replace("_", " "))


def classify(tag: str) -> str:
    t = norm_tag(tag)
    en = norm_tag(tag_english(tag))

    if tag in TAG_TRANSLATIONS:
        en = TAG_TRANSLATIONS[tag]
    if en in MANUAL_LABEL_OVERRIDES:
        return MANUAL_LABEL_OVERRIDES[en]

    if en in {
        "person", "persons", "pessoa", "persona", "deity", "god", "saint", "pope",
        "religious figure", "religious leader", "government official", "actor",
        "politician", "political figure", "football player", "cricket player", "sage",
        "historical figure", "historical person", "fictional character", "character",
        "mythological figure", "mythological entity", "mythological character",
        "mythological being", "mythological creature", "mythical creature", "demon",
        "hindu god of friendship", "hindu god of water", "military personnel",
        "police officer", "political leader",
    }:
        return "PERSON_OR_BEING"

    if any(key in en for key in ["title", "rank", "office", "position", "profession", "occupation"]):
        return "ROLE_TITLE_STATUS"
    if en in {"role", "social role", "family relation", "family relationship", "family_member", "legal profession"}:
        return "ROLE_TITLE_STATUS"

    if en in {
        "group", "group of people", "social group", "demographic group", "demographic",
        "ethnic group", "ethnicity", "nationality", "demonym", "gender",
        "sexual orientation", "age group", "social class", "family", "community",
        "people", "person group", "population group", "religious group", "cultural group",
        "historical group", "society", "kinship",
    }:
        return "GROUP_POPULATION"

    if any(key in en for key in [
        "organization", "institution", "company", "agency", "party", "ministry", "department",
        "committee", "team", "club", "league", "federation", "court", "bank", "exchange",
        "university", "school", "diocese", "archdiocese", "order", "parliament", "senate",
        "congress", "alliance", "faction", "coalition", "union", "network", "channel",
        "outlet", "newspaper", "publisher", "business", "government", "police", "military",
        "terrorist", "criminal", "faculty", "body", "entity", "establishment", "movement",
        "dynasty", "band", "music group", "musical group",
    ]):
        if en in {"political entity", "government", "legal entity", "economic entity"}:
            return "ORGANIZATION"
        return "ORGANIZATION"

    if en in {"brand", "car brand", "product brand"}:
        return "PRODUCT_TECH_OBJECT"

    if any(key in en for key in [
        "country", "city", "region", "state", "province", "district", "division",
        "village", "municipality", "neighborhood", "locality", "subdistrict", "county",
        "kingdom", "empire", "zone", "constituency", "barangay", "place", "location",
    ]):
        if any(key in en for key in ["street", "road", "building", "site", "facility"]):
            return "FACILITY_INFRASTRUCTURE"
        return "GEOPOLITICAL_PLACE"

    if any(key in en for key in [
        "continent", "river", "celestial", "geographical feature", "geographic feature",
        "planet", "island", "body of water", "mountain", "natural feature",
        "astronomical object", "world", "lake", "sea", "ocean", "beach", "space",
        "universe", "geological feature", "natural element",
    ]):
        return "NATURAL_PLACE"
    if en == "direction":
        return "ATTRIBUTE_PROPERTY"

    if any(key in en for key in [
        "infrastructure", "building", "facility", "hospital", "station", "road",
        "hotel", "airport", "restaurant", "temple", "site", "casino", "church",
        "stadium", "museum", "monastery", "venue", "prison", "park", "mall",
        "base", "structure", "architecture", "address", "street",
    ]):
        if en == "address":
            return "IDENTIFIER_CONTACT"
        return "FACILITY_INFRASTRUCTURE"

    if any(key in en for key in [
        "date", "time", "year", "duration", "day", "month", "period", "season",
        "century", "decade", "temporal",
    ]):
        return "TIME_DATE"

    if any(key in en for key in [
        "event", "festival", "holiday", "disaster", "election", "campaign",
        "competition", "operation", "conflict", "conference", "pandemic", "crisis",
        "project", "lottery", "exam", "examination", "phenomenon",
    ]):
        return "EVENT_HAPPENING"

    if any(key in en for key in [
        "quantity", "quantities", "measurement", "percentage", "statistic", "score", "number",
        "distance", "ranking", "ordinal", "page number", "unit of", "rating",
        "amount", "temperature", "population", "data", "weight", "indicator",
        "metric", "index", "frequency", "fraction", "volume", "age", "range",
    ]):
        return "QUANTITY_MEASURE"

    if any(key in en for key in [
        "currency", "monetary", "cryptocurrency", "price", "money", "financial",
        "commodity", "market", "stock", "payment", "asset",
    ]):
        if any(key in en for key in ["institution", "exchange"]):
            return "ORGANIZATION"
        if any(key in en for key in ["ticker", "symbol"]):
            return "IDENTIFIER_CONTACT"
        return "MONEY_FINANCE"

    if any(key in en for key in [
        "website", "phone", "hashtag", "url", "acronym", "email", "contact",
        "identifier", "abbreviation", "handle", "initials", "postal code",
        "username", "code", "document identifier", "account",
    ]):
        return "IDENTIFIER_CONTACT"

    if any(key in en for key in [
        "language", "word", "text", "pronoun", "phrase", "slogan", "letter",
        "concept", "term", "name", "nickname", "alias", "surname", "epithet",
        "reference", "verse", "description", "punctuation", "symbol", "greeting",
    ]):
        if en in {"legal concept", "legal term", "legal reference"}:
            return "LAW_POLICY_NORM"
        if "medical" in en or "health" in en or "biological concept" in en:
            return "CONCEPT_FIELD_DOMAIN"
        return "LANGUAGE_TEXT_NAME"

    if any(key in en for key in [
        "media", "work", "film", "document", "literary", "game", "video game",
        "religious text", "publication", "tv", "television", "song", "book",
        "movie", "magazine", "journal", "album", "artwork", "art", "genre",
        "format", "program", "show", "casino game", "card game", "commentary",
        "encyclopedia", "biblical",
    ]):
        if en in {"government program", "educational program", "social program"}:
            return "ACTION_PROCESS"
        if en in {"programming language"}:
            return "LANGUAGE_TEXT_NAME"
        return "WORK_MEDIA_ART"

    if any(key in en for key in [
        "product", "technology", "platform", "operating system", "vehicle", "weapon",
        "software", "application", "object", "instrument", "program", "service",
        "artifact", "clothing", "device", "model", "tool", "equipment", "app",
        "browser", "aircraft", "component", "console", "phone", "spacecraft",
        "malware", "vessel", "engine", "version", "e-commerce", "system",
    ]):
        if en in {"system", "framework"}:
            return "CONCEPT_FIELD_DOMAIN"
        return "PRODUCT_TECH_OBJECT"

    if any(key in en for key in [
        "material", "chemical", "substance", "drug", "nutrient", "element",
        "resource", "vaccine", "medication", "hormone", "mineral", "energy source",
        "vitamin", "fuel", "pharmaceutical", "metal", "protein", "biomolecule",
    ]):
        return "MATERIAL_SUBSTANCE"

    if any(key in en for key in [
        "food", "ingredient", "agricultural product", "fruit", "dish", "beverage",
        "culinary", "herb", "crop", "vegetable", "cuisine", "spice", "grain",
    ]):
        return "FOOD_AGRICULTURE"

    if any(key in en for key in [
        "animal", "species", "plant", "biological entity", "virus", "organism",
        "taxon", "bacteria", "insect", "tree", "flower", "bacterium",
        "microorganism", "breed", "bird", "cat breed", "fish",
    ]):
        return "ORGANISM_TAXON"

    if any(key in en for key in [
        "body part", "anatomical", "organ", "biological structure",
        "biological system", "cell type", "plant part", "anatomy",
    ]):
        return "ANATOMY_BIOLOGY"

    if any(key in en for key in [
        "medical condition", "disease", "health condition", "symptom",
        "medical symptom", "health issue", "condition", "health status",
        "skin condition",
    ]):
        return "HEALTH_MEDICINE"

    if any(key in en for key in [
        "law", "legal", "legislation", "crime", "policy", "regulation", "tax",
        "agreement", "treaty", "standard", "license", "illegal",
    ]):
        return "LAW_POLICY_NORM"

    if any(key in en for key in [
        "activity", "procedure", "process", "practice", "action", "treatment",
        "technique", "method", "methodology", "test", "transaction", "service",
        "promotion", "ritual", "martial art", "strategy",
    ]):
        if "business model" in en:
            return "CONCEPT_FIELD_DOMAIN"
        return "ACTION_PROCESS"

    if any(key in en for key in [
        "award", "degree", "certification", "qualification", "education level",
        "educational level", "grade level", "educational stage", "academic program",
        "course",
    ]):
        return "EDUCATION_AWARD"

    if any(key in en for key in [
        "color", "feature", "category", "relationship", "relation", "emotion",
        "quality", "attribute", "status", "property", "specification", "lifestyle",
        "class", "other", "skill",
    ]):
        return "ATTRIBUTE_PROPERTY"

    if any(key in en for key in [
        "scientific", "economic", "cultural", "culture", "field", "industry", "philosophical",
        "medical", "health",
        "sport", "political", "religion", "social issue", "academic discipline",
        "ideology", "sector", "abstract", "entity", "discipline", "topic",
        "framework", "environmental", "physics", "truth", "subject", "theory",
        "school", "domain", "business type",
    ]):
        return "CONCEPT_FIELD_DOMAIN"

    raise ValueError(f"Unclassified tag: {tag!r}")


def clean_translation(example: str, translation: str) -> str:
    return EXAMPLE_TRANSLATION_OVERRIDES.get(example, (translation or example).strip())


def main() -> None:
    with IN_TSV.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    labeled = []
    labels_used = set()
    for row in rows:
        label = classify(row["coarse_tag"])
        labels_used.add(label)
        labeled.append(
            {
                "example": row["example"],
                "example_english": clean_translation(row["example"], row.get("translation") or row["example"]),
                "coarse_tag": row["coarse_tag"],
                "coarse_tag_english": tag_english(row["coarse_tag"]),
                "mapped_label": label,
            }
        )

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["example", "example_english", "coarse_tag", "coarse_tag_english", "mapped_label"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(labeled)

    with SCHEME_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["mapped_label", "description"])
        for label, description in SCHEME.items():
            if label in labels_used:
                writer.writerow([label, description])

    print(f"rows={len(labeled)}")
    print(f"labels_used={len(labels_used)}")
    for label in SCHEME:
        count = sum(1 for row in labeled if row["mapped_label"] == label)
        if count:
            print(f"{label}\t{count}")
    print(f"wrote={OUT_TSV}")
    print(f"scheme={SCHEME_TSV}")


if __name__ == "__main__":
    main()
