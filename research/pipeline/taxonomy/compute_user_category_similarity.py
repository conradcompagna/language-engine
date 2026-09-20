import csv
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np


BASE = Path(__file__).resolve().parent
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
OUT = BASE / "derived_fasttext_categories" / "user_category_similarity.tsv"

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
    "misc",
    "other",
}

RAW = r"""
PERSON - person; deity; religious figure; character; nickname; persons; god; mythological figure; historical figure; pessoa; politician; شخص; บุคคล; saint; pope; fictional character; religious leader; government official; actor; political figure; football player; sage; אדם; family name; political leader; hindu god of friendship; hindu god of water; military personnel; mythological entity; character name; persona; demon; musician; author; artist; alias; historical person; priest; cardinal; epithet; poet; common name; athlete; king; philosopher; person name; mythological character; police officer; mythological being; deity epithet; surname; cricket player; historical name; person's name; bishop; անձ; composer; person - politician; व्यक्ति; deity name

ORGANIZATION - organization; brand; political party; government organization; political organization; educational institution; sports team; news agency; political entity; government agency; company; government; sports league; media outlet; media organization; military organization; sports club; financial market; news organization; government ministry; university; religious organization; international organization; law enforcement agency; court; government body; legislative body; institution; military unit; financial institution; football club; political group; business type; sports organization; dynasty; market; diocese; government department; organization type; governmental organization; team; religious institution; newspaper; องค์กร; organização; business; organization abbreviation; political body; ארגון; political movement; terrorist organization; سازمان; government institution; religious order; department; academic department; school; music group; bank; political alliance; establishment; social movement; news outlet; police department; legal institution; stock exchange; news website; musical group; government organization abbreviation; police force; legal entity; committee; research institution; military force; judicial institution; television channel; basketball team; government agency abbreviation; music band; organizations; airline; band; political faction; police unit; television network; political institution; government entity; league; cultural institution; football league; government committee; football club nickname; historical entity; political party abbreviation; political coalition; ecclesiastical province; labor union; news source; business entity; regulatory body; ธุรกิจ; archdiocese; criminal organization; sports club nickname; राजनीतिक पार्टी; military; publisher; sports team nickname; governmental body; company type; political organization abbreviation; research institute; central bank; diplomatic mission; economic entity; media channel; regulatory agency; tv channel; संस्थान; educational organization; government office; telecommunications company; radio station; criminal group; emergency service; university abbreviation; religious entity; sports federation; car brand; non-profit organization; parliament; political regime; commercial establishment; national team; military branch; youtube channel; judicial body; terrorist group; cricket team; educational institution type; local government

LOCATION - location; country; city; region; state; continent; province; district; river; geographic region; administrative region; geopolitical entity; celestial body; administrative division; village; geographical feature; geographical region; place; geopolitical region; street; planet; island; geographical location; localização; body of water; mountain; مکان; natural feature; สถานที่; neighborhood; astronomical object; world; geographic location; کشور; municipality; mountain range; subdistrict; historical region; ประเทศ; מיקום; geographic feature; kingdom; lake; locality; regency; town; area; locations; historical site; स्थान; historical location; geographic area; street name; historical empire; geological feature; location type; economic zone; sea; border; county; cultural site; constituency; מדינה; מקום; ocean; river name; province abbreviation; celestial object; space; ภูมิภาค; barangay; beach; country abbreviation

FACILITY - infrastructure; building; facility; hospital; police station; religious building; road; hotel; airport; government building; restaurant; temple; healthcare facility; building type; religious site; casino; church; stadium; museum; monastery; transportation system; medical facility; architectural structure; venue; prison; place of worship; sports venue; structure; park; shopping mall; military base

PRODUCT - product; technology; social media platform; program; service; financial instrument; financial product; platform; operating system; vehicle; weapon; software; product category; application; object; vehicle type; musical instrument; commodity; government program; educational program; product type; محصول; financial index; academic program; vehicle model; artifact; social media; clothing; เทคโนโลยี; cultural artifact; medical device; car model; military technology; clothing item; product model; produto; tool; military equipment; software version; trading platform; medical product; social program; device; stock index; communication technology; app; model; service type; course; מוצר; religious artifact; web browser; ผลิตภัณฑ์; aircraft; component; payment method; gaming console; automobile model; financial service; messaging application; military aircraft; mobile application; mobile phone model; product component; product line; spacecraft; stock; media platform; malware; software application; streaming service; product variant; stock market index; تکنولوژی; smartphone model; vessel; engine type; messaging app; product name; government initiative; טכנולוגיה; display technology; products; version; communication platform; motorcycle model; scientific instrument; religious object; medical equipment; military vessel; software product; e-commerce platform; financial asset; content management system; equipment; financial technology; medical technology; online casino; operating system version

WORK - media; work of art; film; document; literary work; game; video game; religious text; publication; tv show; song; universe; book; tv series; film title; book title; text; television show; movie; work of literature; television series; cultural work; song title; biblical reference; magazine; media program; musical work; album; letter; journal; movie title; tv program; artwork; slogan; casino game; television program; report; art; sacred syllable; religious phrase; video game series; philosophical text; commentary; encyclopedia; card game

EVENT - event; activity; project; historical event; crime; cultural event; festival; sports event; political event; holiday; natural disaster; sporting event; action; natural phenomenon; exam; ritual; religious event; legal case; election; infrastructure project; เหตุการณ์; health crisis; weather event; meteorological phenomenon; weather phenomenon; political process; event type; lottery; campaign; competition; military operation; sports competition; religious ritual; conflict; religious festival; criminal activity; cultural activity; sports tournament; אירוע; phenomenon; educational activity; illegal activity; evento; financial transaction; conference; examination; astronomical event; film festival; pandemic; promotion; رویداد; cultural festival; legal action; military conflict

DATE_TIME - date; time period; year; time; duration; day of the week; month; time duration; historical period; date range; day of week; season; temporal expression; day; time of day; century; date and time; decade; time measurement; زمان; time zone; temporal reference; unit of time; time expression; day_of_week; תאריך; time range; time interval

QUANTITY - quantity; measurement; percentage; age; statistic; score; number; distance; economic indicator; statistics; quantities; ranking; ordinal number; financial metric; page number; unit of measurement; age range; technical indicator; rating; statistical measurement; amount; statistical measure; temperature; population; statistical data; data; ordinal; weight; basketball statistic; statistical reference; sports score; index; مقدار; frequency; quantidade; race time; numerical value; unit of measurement (area); כמות; area measurement; sports statistic; financial indicator; quantitative measurement; chapter number; numerical quantity; cricket score; distance measurement; fraction; volume; football score

MONEY - currency; monetary value; cryptocurrency; price; currency amount; money; currency pair; monetary amount; financial amount; currency value; price range; cryptocurrency token; price level

NORP - nationality; group; ethnic group; demographic group; social group; religion; group of people; religious group; people; demographic; community; social class; family; demonym; culture; age group; cultural group; ethnicity; gender; political affiliation; person group; population group; historical group; kinship; social category; society; sexual orientation

LAW - legal concept; legal document; legislation; law; policy; legal term; regulation; legal code; tax; economic policy; agreement; legal provision; legal framework; legal process; legal article; legal charge; legal status; political agreement; treaty; legislative document; legal reference; license; legal system; legal procedure; international agreement; government policy; legal code section; legislative proposal; tax type

LANGUAGE - language; programming language; language family

SUBSTANCE - material; chemical compound; substance; chemical substance; drug; nutrient; chemical element; resource; vaccine; medication; hormone; mineral; natural resource; chemical; element; energy source; vitamin; fuel type; biological substance; biochemical substance; pharmaceutical product; biological material; precious metal; fuel; pharmaceutical; drug class; natural element; biological molecule; nutritional component; protein; biomolecule; pharmaceutical drug

DISEASE - medical condition; disease; health condition; symptom; medical symptom; health issue; condition; بیماری; health status; skin condition

ORGANISM - animal; species; plant; biological entity; virus; plant species; animal species; organism; mythological creature; mango variety; mythical creature; biological taxon; horse; scientific name; bacteria; insect; tree; flower; bacterium; cows; microorganism; animal breed; bird species; cat breed; plant variety; biological species; fish species

BODY_PART - body part; anatomical structure; organ; biological structure; body_part; biological system; cell type; plant part; anatomy

FOOD - food; ingredient; food product; agricultural product; fruit; dish; beverage; food item; culinary dish; food ingredient; food category; herb; crop; food dish; vegetable; alcoholic beverage; cuisine; spice; grain

CONCEPT - cultural reference; scientific concept; concept; economic concept; cultural concept; field of study; industry; financial concept; philosophical concept; sport; political concept; medical procedure; color; religious concept; social issue; financial term; social concept; process; music genre; academic discipline; art form; political ideology; economic sector; abstract concept; educational level; entity; scientific field; medical concept; pronoun; business concept; cultural practice; genre; field; health concept; feature; transportation; category; biological concept; religious practice; document type; educational concept; political system; medical treatment; general concept; technological concept; media type; latin word; literary genre; sector; psychological concept; word; topic; education level; medical term; media format; environmental issue; skill; economic activity; framework; game genre; medical specialty; philosophical school; technique; biological process; standard; economic term; direction; symbol; film genre; system; business model; architectural feature; statistical concept; adjective; emotion; file format; product feature; general term; astrological sign; trading strategy; procedure; linguistic concept; architectural style; zodiac sign; scientific discipline; environmental concept; physics concept; truth; game mechanic; business sector; phrase; film industry; method; other; grade level; methodology; ideology; philosophical system; political; medical test; subject; physiological process; mathematical concept; musical note; agricultural practice; data type; flavor; historical concept; academic subject; sports term; astrological concept; military concept; nakshatra (lunar mansion); ultimate reality; financial activity; industry sector; quality; attribute; economic system; medium; noun; status; latin phrase; health protocol; life stage; martial art; literary concept; scientific theory; culinary concept; medical field; practice; room type; game feature; marketing strategy; political issue; philosophical concept (power; description; punctuation; relationship; design concept; person type; political term; sports category; technical concept; مفهوم علمی; agricultural concept; anatomy; conceito científico; achievement; diet; emotional state; entity type; property type; specification; descriptive phrase; economic theory; relation; class; contextual reference; game mode; legal field; musical genre; beauty treatment; literary form; theological concept; business category; media genre; placeholder text; term; verb; gaming concept; greeting; lifestyle; spiritual concept; spiritual practice; deity attribute; weight class; business process; crime type; dietary concept; educational stage; medical practice; architecture; business strategy; metaphor

ROLE - title; profession; position; occupation; job title; political position; role; government position; religious title; military rank; political office; political title; family relation; police rank; social role; political role; religious role; academic title; diplomatic title; ecclesiastical title; organization role; papal title; rank; family relationship; family_member; legal profession

IDENTIFIER - website; phone number; hashtag; url; address; acronym; email address; contact number; contact information; identifier; abbreviation; social media handle; website section; initials; postal code; stock ticker; stock symbol; social media account; social media hashtag; username; identification number; code; document identifier

AWARD - award; academic degree; degree; certification; award category; educational qualification; educational degree

DOCUMENT - financial document; government document
"""


def strip_accents(text):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def norm_text(text):
    text = strip_accents((text or "").strip().lower())
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


def parse_categories():
    categories = {}
    current = None
    chunks = []
    for line in RAW.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if " - " in line and line.split(" - ", 1)[0].isupper():
            if current:
                categories[current] = " ".join(chunks)
            current, rest = line.split(" - ", 1)
            chunks = [rest]
        elif current:
            chunks.append(line)
    if current:
        categories[current] = " ".join(chunks)
    return categories


def split_items(text):
    return [item.strip() for item in text.split(";") if item.strip()]


def collect_needed_words(categories):
    needed = set()
    for text in categories.values():
        for item in split_items(text):
            for tok in tokens(item):
                needed.update(variants(tok))
    return needed


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


def pairwise_stats(x):
    if len(x) < 2:
        return {
            "mean": 1.0 if len(x) == 1 else 0.0,
            "median": 1.0 if len(x) == 1 else 0.0,
            "p10": 1.0 if len(x) == 1 else 0.0,
            "min": 1.0 if len(x) == 1 else 0.0,
        }
    sims = []
    for start in range(0, len(x), 256):
        block = x[start:start + 256]
        sim = block @ x.T
        for i in range(sim.shape[0]):
            global_i = start + i
            sims.extend(sim[i, global_i + 1:].tolist())
    arr = np.array(sims, dtype=np.float32)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "min": float(np.min(arr)),
    }


def main():
    categories = parse_categories()
    vectors = load_fasttext(collect_needed_words(categories))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []

    for category, text in categories.items():
        items = split_items(text)
        item_rows = []
        vecs = []
        for item in items:
            vec, matched = phrase_vector(item, vectors)
            if vec is None:
                item_rows.append((item, matched, None, None))
                continue
            item_rows.append((item, matched, vec, len(vecs)))
            vecs.append(vec)

        if vecs:
            x = np.vstack(vecs).astype(np.float32)
            centroid = np.mean(x, axis=0)
            centroid = centroid / np.linalg.norm(centroid)
            centroid_sims = x @ centroid
            stats = pairwise_stats(x)
            weakest = []
            for item, matched, _vec, idx in item_rows:
                if idx is not None:
                    weakest.append((float(centroid_sims[idx]), item))
            weakest.sort()
            weakest_items = " | ".join(f"{item} ({score * 100:.1f}%)" for score, item in weakest[:5])
        else:
            stats = {"mean": 0.0, "median": 0.0, "p10": 0.0, "min": 0.0}
            weakest_items = ""

        rows.append(
            [
                category,
                len(items),
                len(vecs),
                f"{stats['mean'] * 100:.2f}",
                f"{stats['median'] * 100:.2f}",
                f"{stats['p10'] * 100:.2f}",
                f"{stats['min'] * 100:.2f}",
                weakest_items,
                " | ".join(item for item, matched, vec, _idx in item_rows if vec is None)[:500],
            ]
        )

    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "category",
                "items",
                "vectorized_items",
                "mean_pairwise_similarity_pct",
                "median_pairwise_similarity_pct",
                "p10_pairwise_similarity_pct",
                "min_pairwise_similarity_pct",
                "weakest_to_centroid",
                "unvectorized_items",
            ]
        )
        writer.writerows(rows)


if __name__ == "__main__":
    main()
