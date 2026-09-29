import csv
import re
import zipfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
OUT = BASE / "derived_fasttext_categories" / "user_category_top_words.tsv"

TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "about",
    "related",
    "type",
    "types",
    "category",
    "categories",
    "item",
    "items",
    "other",
    "misc",
}

CATEGORIES = {
    "People / persons": """person, persons, people, pessoa, شخص, บุคคล, אדם, persona, անձ, व्यक्ति, politician, political figure, political leader, government official, police officer, actor, musician, author, artist, poet, philosopher, composer, sage, athlete, football player, cricket player, king, religious figure, religious leader, deity, god, saint, pope, priest, bishop, historical figure, historical person, mythological figure, mythological creature, mythological entity, mythical creature, mythological character, mythological being, demon, character, fictional character, person - politician, religious entity, hindu god of friendship, hindu god of water""",
    "Roles / titles / statuses": """title, profession, position, occupation, job title, political position, role, government position, religious title, military rank, political office, skill, political title, police rank, social role, military personnel, political role, religious role, academic title, diplomatic title, ecclesiastical title, organization role, papal title, rank, legal profession""",
    "Human groups / populations": """group, group of people, social group, demographic group, demographic, ethnic group, ethnicity, nationality, demonym, gender, sexual orientation, age group, age range, social class, family, family relation, family relationship, family_member, kinship, community, population, population group, person group, historical group, cultural group, social category, society""",
    "Organizations / institutions": """organization, political party, government organization, political organization, educational institution, sports team, news agency, government agency, company, sports league, media outlet, media organization, military organization, sports club, news organization, government ministry, university, religious organization, international organization, law enforcement agency, court, government body, legislative body, institution, military unit, financial institution, football club, sports organization, diocese, government department, organization type, governmental organization, team, religious institution, องค์กร, organização, business, political body, ארגון, terrorist organization, سازمان, government institution, department, academic department, school, bank, establishment, news outlet, police department, legal institution, stock exchange, police force, committee, research institution, military force, judicial institution, basketball team, organizations, airline, police unit, television network, political institution, government entity, league, cultural institution, football league, government committee, labor union, business entity, regulatory body, archdiocese, criminal organization, governmental body, company type, research institute, central bank, faculty, media channel, regulatory agency, tv channel, संस्थान, educational organization, government office, telecommunications company, radio station, emergency service, sports federation, non-profit organization, parliament, business category, commercial establishment, national team, military branch, youtube channel, judicial body, cricket team, educational institution type, local government, religious order, political alliance, political faction, political coalition, military, publisher, diplomatic mission, economic entity, political group, terrorist group, criminal group, राजनैतिक पार्टी, ธุรกิจ""",
    "Administrative / geopolitical places": """location, country, city, region, state, province, district, geographic region, administrative region, geopolitical entity, administrative division, village, geographical region, place, geopolitical region, geographical location, localização, مکان, สถานที่, neighborhood, geographic location, کشور, municipality, subdistrict, historical region, ประเทศ, מיקום, locality, regency, town, locations, स्थान, historical location, geographic area, historical empire, location type, economic zone, border, county, מדינה, מקום, ภูมิภาค, barangay, kingdom, constituency""",
    "Natural / physical places": """continent, river, celestial body, geographical feature, universe, planet, island, body of water, mountain, natural feature, astronomical object, world, mountain range, direction, geographic feature, lake, area, geological feature, sea, natural element, ocean, river name, celestial object, space, beach""",
    "Built places / facilities": """infrastructure, building, facility, street, transportation, address, police station, religious building, road, hotel, airport, government building, restaurant, temple, infrastructure project, building type, religious site, casino, architectural feature, church, architectural style, stadium, museum, historical site, monastery, transportation system, street name, architectural structure, venue, prison, place of worship, room type, sports venue, park, shopping mall, military base, architecture, hospital, healthcare facility, medical facility, cultural site""",
    "Time / temporal expressions": """date, time period, year, time, duration, day of the week, month, time duration, historical period, date range, day of week, season, temporal expression, day, time of day, century, date and time, decade, time measurement, زمان, time zone, temporal reference, frequency, unit of time, time expression, day_of_week, תאריך, time range, time interval""",
    "Events / happenings": """event, historical event, cultural event, festival, sports event, political event, holiday, natural disaster, sporting event, religious event, election, เหตุการณ์, weather event, event type, campaign, competition, military operation, sports competition, conflict, religious festival, military conflict, אירוע, evento, conference, astronomical event, film festival, pandemic, رویداد, cultural festival, sports tournament, exam, examination""",
    "Quantities / measurements / scores": """quantity, measurement, percentage, statistic, score, number, distance, statistics, quantities, ranking, ordinal number, page number, degree, unit of measurement, rating, statistical measurement, amount, statistical measure, statistical concept, temperature, statistical data, ordinal, cardinal, weight, basketball statistic, statistical reference, sports score, index, مقدار, quantidade, race time, numerical value, unit of measurement (area), כמות, area measurement, sports statistic, quantitative measurement, chapter number, numerical quantity, cricket score, distance measurement, fraction, volume, weight class, football score, economic indicator, financial indicator, technical indicator""",
    "Money / financial values / assets": """currency, monetary value, financial instrument, cryptocurrency, price, financial market, currency amount, commodity, market, financial index, money, financial metric, currency pair, monetary amount, stock index, precious metal, financial amount, payment method, currency value, stock, stock ticker, stock symbol, stock market index, financial asset, cryptocurrency token, price range, price level""",
    "Identifiers / handles / codes": """website, social media platform, phone number, hashtag, url, acronym, email address, contact number, organization abbreviation, contact information, identifier, abbreviation, social media handle, website section, symbol, news website, initials, postal code, social media account, social media hashtag, username, identification number, code, document identifier, country abbreviation, province abbreviation, university abbreviation, government organization abbreviation, government agency abbreviation, political party abbreviation, political organization abbreviation, football club nickname, sports club nickname, sports team nickname""",
    "Names / words / labels": """language, nickname, pronoun, text, latin word, word, adjective, character name, general term, letter, linguistic concept, phrase, slogan, academic subject, epithet, common name, noun, latin phrase, sacred syllable, religious phrase, scientific name, biblical reference, biblical verse, description, punctuation, surname, historical name, commentary, descriptive phrase, contextual reference, placeholder text, term, verb, greeting, deity attribute, deity epithet, deity name, metaphor, programming language, language family, alias, family name, person name, person's name""",
    "Works / media / art": """cultural reference, media, work of art, film, literary work, game, video game, religious text, publication, tv show, music genre, art form, song, musical instrument, book, tv series, genre, film title, book title, newspaper, television show, movie, media type, literary genre, social media, media format, work of literature, game genre, cultural artifact, television series, cultural work, song title, film genre, magazine, media program, musical work, album, television channel, journal, movie title, tv program, game mechanic, film industry, lottery, artwork, casino game, musical note, television program, art, medium, gaming console, media platform, streaming service, game feature, video game series, slot game, card game, game mode, musical genre, literary form, media genre, gaming concept, online casino""",
    "Musical groups / bands": """music group, musical group, music band, band""",
    "Documents / texts": """legal document, document, document type, financial document, report, legislative document, license, philosophical text, government document, encyclopedia""",
    "Products / tools / devices": """product, technology, brand, program, service, platform, operating system, vehicle, weapon, software, product category, application, object, vehicle type, government program, educational program, resource, product type, محصول, academic program, vehicle model, artifact, clothing, เทคโนโลยี, medical device, car model, military technology, clothing item, product model, produto, file format, product feature, tool, military equipment, software version, medical product, social program, device, communication technology, app, aircraft model, invention, web browser, ผลิตภัณฑ์, aircraft, component, automobile model, messaging application, military aircraft, mobile application, mobile phone model, product component, product line, spacecraft, malware, software application, product variant, تکنولوژی, smartphone model, product brand, vessel, engine type, messaging app, product name, structure, טכנולוגיה, display technology, products, version, communication platform, motorcycle model, scientific instrument, car brand, medical equipment, military vessel, software product, e-commerce platform, content management system, operating system version, equipment, financial technology, medical technology, מוצר, religious artifact, religious object""",
    "Substances / foods / materials": """material, food, chemical compound, substance, ingredient, chemical substance, food product, agricultural product, drug, fruit, nutrient, chemical element, dish, vaccine, medication, beverage, food item, culinary dish, food ingredient, hormone, mineral, natural resource, chemical, element, energy source, food category, vitamin, fuel type, biological substance, biochemical substance, pharmaceutical product, biological material, mango variety, crop, food dish, vegetable, alcoholic beverage, flavor, fuel, culinary concept, pharmaceutical, drug class, cuisine, diet, biological molecule, nutritional component, protein, biomolecule, pharmaceutical drug, dietary concept, spice, grain""",
    "Living organisms / taxa": """animal, species, plant, biological entity, virus, plant species, animal species, organism, herb, biological taxon, horse, biological classification, bacteria, insect, tree, flower, bacterium, microorganism, animal breed, bird species, cat breed, plant variety, biological species, fish species, cows""",
    "Anatomical / biological structures": """body part, anatomical structure, organ, body_part, biological structure, biological system, cell type, plant part, anatomy""",
    "Health conditions": """medical condition, disease, health condition, symptom, health crisis, medical symptom, health issue, condition, بیماری, health status, skin condition""",
    "Concepts / fields / domains": """scientific concept, concept, economic concept, cultural concept, field of study, financial concept, philosophical concept, sport, political entity, government, political concept, religion, religious concept, social issue, financial term, social concept, academic degree, academic discipline, political ideology, economic sector, business type, business concept, scientific field, medical concept, field, biological concept, educational concept, political system, general concept, technological concept, political movement, psychological concept, topic, education level, medical term, medical specialty, economic policy, economic activity, culture, framework, economic term, system, business model, political affiliation, astrological sign, zodiac sign, data, scientific discipline, environmental concept, physics concept, truth, business sector, ideology, philosophical system, political, subject, mathematical concept, data type, historical concept, philosophical school, astrological concept, military concept, nakshatra (lunar mansion), ultimate reality, economic system, literary concept, scientific theory, medical field, marketing strategy, political issue, philosophical concept (power, design concept, political term, sports term, technical concept, مفهوم علمی, agricultural concept, conceito علمی, conceito científico, entity type, phenomenon, natural phenomenon, meteorological phenomenon, weather phenomenon, economic theory, class, political regime, theological concept, spiritual concept, sports category, award category, industry, industry sector, sector""",
    "Legal / normative concepts": """legal concept, legislation, crime, law, policy, legal term, regulation, legal code, agreement, legal case, standard, legal provision, legal framework, legal entity, legal process, legal article, legal charge, legal status, political agreement, treaty, legal reference, legal system, legal procedure, international agreement, illegal activity, legal field, government policy, crime type, legal code section, legislative proposal, legal action, tax, tax type, health protocol""",
    "Actions / procedures / processes": """activity, medical procedure, process, cultural practice, action, religious practice, medical treatment, technique, biological process, political process, procedure, method, methodology, educational method, medical test, physiological process, agricultural practice, financial activity, financial transaction, financial service, practice, criminal activity, cultural activity, educational activity, beauty treatment, spiritual practice, business process, medical practice, promotion, business strategy, ritual, religious ritual, martial art""",
    "Attributes / properties / qualities": """age, color, feature, category, social class, demonym, educational level, grade level, educational stage, educational degree, educational qualification, course, relationship, relation, emotion, emotional state, service type, quality, attribute, status, property type, specification, lifestyle, model, other""",
    "Awards / achievements / projects": """award, certification, achievement, project, government initiative""",
    "Entity": """entity""",
}


def norm_text(text):
    text = (text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def tokens(text):
    return [tok for tok in TOKEN_RE.findall(norm_text(text)) if tok not in STOPWORDS and len(tok) > 1]


def variants(token):
    yielded = {token}
    yield token
    if token.endswith("ies") and len(token) > 4:
        candidate = token[:-3] + "y"
        if candidate not in yielded:
            yielded.add(candidate)
            yield candidate
    if token.endswith("es") and len(token) > 3:
        candidate = token[:-2]
        if candidate not in yielded:
            yielded.add(candidate)
            yield candidate
    if token.endswith("s") and len(token) > 3:
        candidate = token[:-1]
        if candidate not in yielded:
            yield candidate


def split_items(text):
    return [item.strip() for item in text.split(",") if item.strip()]


def collect_needed_words():
    words = set()
    for text in CATEGORIES.values():
        for tok in tokens(text):
            words.update(variants(tok))
    return words


def load_fasttext(needed):
    needed_bytes = {word.encode("utf-8") for word in needed}
    vectors = {}
    with zipfile.ZipFile(FASTTEXT_ZIP, "r") as zf:
        vec_name = next(name for name in zf.namelist() if name.endswith(".vec"))
        with zf.open(vec_name, "r") as f:
            f.readline()
            for line in f:
                word, _, rest = line.partition(b" ")
                if word not in needed_bytes:
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm:
                    vectors[word.decode("utf-8")] = arr / norm
    return vectors


def token_vector(token, vectors):
    for candidate in variants(token):
        vec = vectors.get(candidate)
        if vec is not None:
            return candidate, vec
    return "", None


def phrase_vector(text, vectors):
    found = []
    matched = []
    for tok in tokens(text):
        word, vec = token_vector(tok, vectors)
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


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    vectors = load_fasttext(collect_needed_words())
    rows = []
    for category, raw_items in CATEGORIES.items():
        items = split_items(raw_items)
        phrase_vectors = []
        category_tokens = []
        token_support = {}
        for item in items:
            vec, matched = phrase_vector(item, vectors)
            if vec is not None:
                phrase_vectors.append(vec)
            for word in matched:
                category_tokens.append(word)
                token_support[word] = token_support.get(word, 0) + 1
        centroid = np.mean(phrase_vectors, axis=0)
        centroid_norm = np.linalg.norm(centroid)
        if not centroid_norm:
            rows.append([category, "", "", len(items), 0, ""])
            continue
        centroid = centroid / centroid_norm
        candidates = []
        for word in sorted(set(category_tokens)):
            vec = vectors[word]
            cosine = float(np.dot(centroid, vec))
            support = token_support[word]
            candidates.append((cosine + 0.015 * np.log1p(support), cosine, support, word))
        candidates.sort(reverse=True)
        best = candidates[0]
        rows.append(
            [
                category,
                best[3],
                f"{best[1]:.4f}",
                len(items),
                len(phrase_vectors),
                ", ".join(item[3] for item in candidates[:8]),
            ]
        )

    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(["category", "top_word", "cosine", "items", "vectorized_items", "top_8"])
        writer.writerows(rows)


if __name__ == "__main__":
    main()
