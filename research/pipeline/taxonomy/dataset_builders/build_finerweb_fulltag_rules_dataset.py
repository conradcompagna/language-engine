import csv
import json
import math
import os
import re
import shutil
import stat
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
INPUT_ROOT = DATASETS / "finerweb_bucketed_fulltag_fasttext_by_language"
OUTPUT_ROOT = DATASETS / "finerweb_bucketed_fulltag_hybrid_v13_by_language"
ZIP_PATH = OUTPUT_ROOT.with_suffix(".zip")
FULLTAG_MAP = INPUT_ROOT / "fine_tag_fasttext_bucket_map.tsv"
TOP500_MAP = BASE / "revamped_top500_coarse_tag_map.tsv"
LABEL_INVENTORY = BASE / "finerweb_label_inventory.tsv"
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
SPLITS = ("train", "dev", "test", "all")
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
EXPECTED_BUCKETS = {
    "PERSON",
    "ROLE_TITLE",
    "NORP",
    "ORG",
    "LOC",
    "FAC",
    "DATE_TIME",
    "NUMBER",
    "STATISTIC",
    "MONEY",
    "EVENT",
    "WORK_OF_ART",
    "LEGAL_POLITICAL",
    "LANGUAGE",
    "PRODUCT",
    "BIOMED",
    "NATURAL_OBJECT",
    "ACTIVITY_PROCESS",
    "SYMBOL_IDENTIFIER",
    "SYSTEM",
    "GENRE_FORM",
    "CULTURE_RELIGION",
    "CONCEPT",
    "MISC",
}
LABEL_RE = re.compile(r"^(?:O|[BI]-[A-Z_]+)$")


BUCKET_PROTOTYPES = {
    "PERSON": [
        "person",
        "individual",
        "fictional character",
        "historical figure",
        "named person",
        "character in tv series",
        "character in film",
        "nickname of person",
    ],
    "ROLE_TITLE": [
        "profession",
        "occupation",
        "job title",
        "political title",
        "military rank",
        "religious title",
        "composer",
        "singer",
        "journalist",
        "film director",
        "judge",
        "politician",
    ],
    "NORP": [
        "ethnic group",
        "religious group",
        "demographic group",
        "social group",
        "community",
        "population",
        "nationality",
        "political affiliation",
        "refugees",
        "feminists",
    ],
    "ORG": [
        "organization",
        "company",
        "government agency",
        "musical group",
        "rock band",
        "hacker group",
        "terrorist group",
        "rebel group",
        "military unit",
        "sports club",
        "sports team",
        "publisher",
        "newspaper",
        "tv network",
        "record label",
        "research institute",
        "religious order",
        "court",
        "regulatory agency",
        "stock exchange",
    ],
    "LOC": [
        "location",
        "country",
        "city",
        "region",
        "province",
        "district",
        "village",
        "neighborhood",
        "river",
        "mountain",
        "forest",
        "island",
        "political entity",
        "empire",
        "kingdom",
        "economic zone",
    ],
    "FAC": [
        "facility",
        "building",
        "hotel",
        "restaurant",
        "market",
        "bazaar",
        "museum",
        "library",
        "theater",
        "stadium",
        "bridge",
        "airport",
        "train station",
        "police station",
        "hospital",
        "temple",
        "church",
        "mosque",
        "monument",
        "tower",
        "castle",
        "park",
        "cemetery",
        "resort",
        "passenger lounge",
    ],
    "DATE_TIME": [
        "date",
        "time",
        "year",
        "month",
        "day",
        "duration",
        "time period",
        "century",
        "season",
        "holiday",
    ],
    "NUMBER": [
        "number",
        "quantity",
        "measurement",
        "age",
        "distance",
        "weight",
        "height",
        "storage capacity",
        "ordinal number",
    ],
    "STATISTIC": [
        "statistic",
        "score",
        "ranking",
        "rating",
        "percentage",
        "rate",
        "index value",
        "economic indicator",
        "metric",
    ],
    "MONEY": [
        "money",
        "currency",
        "price",
        "monetary value",
        "currency amount",
        "financial instrument",
        "financial product",
        "cryptocurrency",
    ],
    "EVENT": [
        "event",
        "sports event",
        "competition",
        "championship",
        "tournament",
        "festival",
        "election",
        "conference",
        "war",
        "battle",
        "disaster",
        "health crisis",
    ],
    "WORK_OF_ART": [
        "work of art",
        "film",
        "movie",
        "tv show",
        "television series",
        "song",
        "book",
        "literary work",
        "album",
        "video game",
        "publication",
        "newspaper article",
    ],
    "LEGAL_POLITICAL": [
        "law",
        "legal document",
        "contract",
        "agreement",
        "decree",
        "regulation",
        "policy",
        "court case",
        "legal framework",
        "political system",
        "political process",
        "customs declaration",
    ],
    "LANGUAGE": [
        "language",
        "dialect",
        "word",
        "phrase",
        "idiom",
        "slogan",
        "mantra",
        "abbreviation",
        "programming language",
    ],
    "PRODUCT": [
        "product",
        "software",
        "application",
        "operating system",
        "website",
        "platform",
        "vehicle",
        "phone model",
        "food product",
        "brand",
        "medical device",
        "weapon",
        "technology product",
    ],
    "BIOMED": [
        "disease",
        "medical condition",
        "symptom",
        "body part",
        "anatomical structure",
        "drug",
        "medication",
        "vaccine",
        "virus",
        "hormone",
        "organism",
        "animal",
        "plant",
        "species",
    ],
    "NATURAL_OBJECT": [
        "material",
        "substance",
        "chemical compound",
        "chemical element",
        "mineral",
        "natural resource",
        "planet",
        "star",
        "galaxy",
        "asteroid",
        "comet",
        "celestial body",
        "northern lights",
    ],
    "ACTIVITY_PROCESS": [
        "activity",
        "process",
        "procedure",
        "technique",
        "sport",
        "medical treatment",
        "security check",
        "transportation",
        "service",
        "skill",
    ],
    "SYMBOL_IDENTIFIER": [
        "identifier",
        "id number",
        "passport",
        "license",
        "certificate",
        "academic degree",
        "award",
        "citation",
        "reference",
        "url",
        "email address",
        "phone number",
        "hashtag",
        "stock ticker",
    ],
    "SYSTEM": [
        "system",
        "program",
        "project",
        "market",
        "industry",
        "sector",
        "framework",
        "educational program",
        "government program",
        "business model",
        "standard",
    ],
    "GENRE_FORM": [
        "genre",
        "music genre",
        "film genre",
        "game genre",
        "literary genre",
        "art form",
        "media format",
        "media type",
    ],
    "CULTURE_RELIGION": [
        "religion",
        "religious concept",
        "deity",
        "god",
        "goddess",
        "mythological figure",
        "ritual",
        "religious practice",
        "cultural practice",
        "astrological sign",
    ],
    "CONCEPT": [
        "concept",
        "abstract concept",
        "scientific concept",
        "philosophical concept",
        "social concept",
        "social issue",
        "emotion",
        "academic discipline",
        "field of study",
        "mathematics",
        "business administration",
        "nudity",
        "friendship",
    ],
}

HARD_HEAD_BUCKETS = {
    "person": "PERSON",
    "persons": "PERSON",
    "people": "NORP",
    "individual": "PERSON",
    "organization": "ORG",
    "organisation": "ORG",
    "agency": "ORG",
    "institution": "ORG",
    "committee": "ORG",
    "company": "ORG",
    "location": "LOC",
    "place": "LOC",
    "country": "LOC",
    "city": "LOC",
    "region": "LOC",
    "state": "LOC",
    "province": "LOC",
    "district": "LOC",
    "village": "LOC",
    "event": "EVENT",
    "date": "DATE_TIME",
    "time": "DATE_TIME",
    "year": "DATE_TIME",
    "month": "DATE_TIME",
    "day": "DATE_TIME",
    "language": "LANGUAGE",
    "dialect": "LANGUAGE",
    "currency": "MONEY",
    "money": "MONEY",
    "building": "FAC",
    "facility": "FAC",
    "infrastructure": "FAC",
    "deity": "CULTURE_RELIGION",
    "god": "CULTURE_RELIGION",
    "goddess": "CULTURE_RELIGION",
    "disease": "BIOMED",
    "condition": "BIOMED",
    "virus": "BIOMED",
    "drug": "BIOMED",
    "medication": "BIOMED",
}

WEAK_HEADS = {
    "cultural reference",
    "media",
    "work",
    "document",
    "scientific concept",
    "technology",
    "product",
    "thing",
    "item",
    "entity",
    "category",
    "topic",
    "concept",
}

HEAD_TRANSLATIONS = {
    "pessoa": "person",
    "บุคคล": "person",
    "شخص": "person",
    "אדם": "person",
    "องค์กร": "organization",
    "organização": "organization",
    "سازمان": "organization",
    "สถานที่": "location",
    "مکان": "location",
    "کشور": "country",
    "ประเทศ": "country",
    "محصول": "product",
    "เทคโนโลยี": "technology",
    "จำนวน": "quantity",
    "เวลา": "time",
    "ปี": "year",
    "رویداد": "event",
    "مفهوم": "concept",
    "מוצר": "product",
    "אירוע": "event",
    "מקום": "location",
}

MONEY_RE = re.compile(
    r"(?i)(?:[$€£¥₹₩₪₽]|(?:\b\d[\d,.]*\s*(?:usd|eur|gbp|inr|jpy|krw|ils|rub|dollar|dollars|euro|euros|rupee|rupees|shilling|shillings|won|yuan|yen|lira|krona|baht|peso|pesos|real|reais|lev|บาท|ریال|تومان|руб)\b))"
)
TIME_UNIT_RE = re.compile(
    r"(?i)\b\d[\d,.]*\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|secs?|mins?|hrs?|"
    r"secondi|minuti|ore|giorni|settimane|mesi|anni|"
    r"minutos?|horas?|dias?|semanas?|mes(?:es)?|anos?|"
    r"phút|giờ|ngày|tuần|tháng|năm|"
    r"سال|ماه|روز|ساعت|دقیقه|"
    r"वर्ष|साल|महीने?|दिन|घंटे?|मिनट|"
    r"χρόνια|χρόνος|έτη|μήνες|ημέρες|ώρες|λεπτά|"
    r"yıl|ay|gün|saat|dakika|"
    r"เดือน|วัน|ชั่วโมง|นาที)\b"
)
YEAR_RE = re.compile(r"(?<!\d)(?:1[5-9]\d{2}|20\d{2})(?!\d)")
PERCENT_RE = re.compile(r"(?<!\w)\d[\d,.]*\s*%")
URL_EMAIL_RE = re.compile(r"(?i)(?:https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,})")
CELESTIAL_RE = re.compile(
    r"(?i)\b(?:sun|moon|earth|mars|venus|jupiter|saturn|mercury|uranus|neptune|pluto|planet|star|galaxy|asteroid|comet|nebula|ryugu|خورشید|زمین|مریخ)\b"
)


LEXICAL_FALLBACKS = {
    # Armenian
    "կերպար": "PERSON",
    "անձ": "PERSON",
    "գրականություն": "WORK_OF_ART",
    "գրական ստեղծագործություն": "WORK_OF_ART",
    "գիրք": "WORK_OF_ART",
    "աշխարհագրական տարածք": "LOC",
    "հայտնի աշխարհագրական վայր": "LOC",
    "պատկերարի անուն": "PERSON",
    "քանակ": "NUMBER",
    "թիվ": "NUMBER",
    "տարեթիվ": "DATE_TIME",
    "ամսաթիվ": "DATE_TIME",
    "ժամանակ": "DATE_TIME",
    "ժամանակահատված": "DATE_TIME",
    "հոգեկան խանգարում": "BIOMED",
    "անատոմիա": "BIOMED",
    "գրող": "ROLE_TITLE",
    "արձակագիր": "ROLE_TITLE",
    "գիտնական": "ROLE_TITLE",
    "անդամ": "ROLE_TITLE",
    "վերահսկիչ": "ROLE_TITLE",
    "քաղաքական գաղափար": "LEGAL_POLITICAL",
    "հանցագործություն": "LEGAL_POLITICAL",
    "իրաւական": "LEGAL_POLITICAL",
    "կազմակերպություն": "ORG",
    "կայք": "PRODUCT",
    "արտադրանք": "PRODUCT",
    "ընթացակարգ": "ACTIVITY_PROCESS",
    "հանդիպում": "EVENT",
    "հոգեբանություն": "SYSTEM",
    "լոկացիա": "LOC",
    # Thai
    "ธุรกิจ": "SYSTEM",
    "เทคโนโลยี": "PRODUCT",
    "สัตว์เลี้ยง": "BIOMED",
    "กลุ่มบุคคล": "NORP",
    "กลุ่มคน": "NORP",
    "กลุ่ม": "NORP",
    "คอนเซปต์ทางการเงิน": "CONCEPT",
    "แนวคิดทางเศรษฐศาสตร์": "CONCEPT",
    "แนวคิดทางสังคม": "CONCEPT",
    "แนวคิดทางศาสนา": "CULTURE_RELIGION",
    "แนวคิดทางการเมือง": "LEGAL_POLITICAL",
    "งานวิจัย": "SYSTEM",
    "ผลิตภัณฑ์": "PRODUCT",
    "ผลิตภัณฑ์สุขภาพ": "PRODUCT",
    "ประเภทซอฟต์แวร์": "PRODUCT",
    "ประเภทเกมคาสิโน": "GENRE_FORM",
    "ประเภทเกม": "GENRE_FORM",
    "ผลลัพธ์เกม": "STATISTIC",
    "ปี": "DATE_TIME",
    "ช่วงเวลา": "DATE_TIME",
    "เวลา": "DATE_TIME",
    "ปรสิต": "BIOMED",
    "แนวคิด": "CONCEPT",
    "จำนวน": "NUMBER",
    "จำนวนโครงการ": "NUMBER",
    "ปริมาณ": "NUMBER",
    "ปริมาณเงิน": "MONEY",
    "หน่วยวัด": "NUMBER",
    "ภูมิภาค": "LOC",
    "การเงิน": "CONCEPT",
    "เกม": "WORK_OF_ART",
    "กิจกรรม": "ACTIVITY_PROCESS",
    "อุตสาหกรรม": "SYSTEM",
    "ตำแหน่ง": "ROLE_TITLE",
    "ส่วนผสม": "PRODUCT",
    "สื่อ": "WORK_OF_ART",
    # Persian / Arabic script tags seen in the inventory.
    "زمان": "DATE_TIME",
    "تاریخ": "DATE_TIME",
    "سال": "DATE_TIME",
    "تکنولوژی": "PRODUCT",
    "فن آوری": "PRODUCT",
    "مفهوم علمی": "CONCEPT",
    "مفهوم": "CONCEPT",
    "مفهوم اقتصادی": "CONCEPT",
    "مفهوم فرهنگی": "CULTURE_RELIGION",
    "مفهوم پزشکی": "CONCEPT",
    "رویداد": "EVENT",
    "رسانه": "WORK_OF_ART",
    "اثر ادبی": "WORK_OF_ART",
    "عدد": "NUMBER",
    "کمیت": "NUMBER",
    "مقدار": "NUMBER",
    "خدمات": "ACTIVITY_PROCESS",
    "علائم پزشکی": "BIOMED",
    "بیماری": "BIOMED",
    "غذا": "PRODUCT",
    "محل": "LOC",
    "جاندار": "BIOMED",
    "زیست شناسی": "SYSTEM",
    "منبع طبیعی": "NATURAL_OBJECT",
    "سازمان دولتی": "ORG",
    "پروژه": "SYSTEM",
    # Hebrew
    "מוצר": "PRODUCT",
    "טכנולוגיה": "PRODUCT",
    "אירוע": "EVENT",
    "אנשים": "NORP",
    "כמות": "NUMBER",
    "זמן": "DATE_TIME",
    "תקופה": "DATE_TIME",
    "מקום": "LOC",
    "קונספט": "CONCEPT",
    "מושג": "CONCEPT",
    "מושג חברתי": "CONCEPT",
    "מושג כלכלי": "CONCEPT",
    "מושג פילוסופי": "CONCEPT",
    "מונח רפואי": "CONCEPT",
    "אנטומיה": "BIOMED",
    "תסמין": "BIOMED",
    "הליך משפטי": "LEGAL_POLITICAL",
    "ז'אנר": "GENRE_FORM",
    "סוג יצירה": "GENRE_FORM",
    "תהליך": "ACTIVITY_PROCESS",
    "תיאוריה": "CONCEPT",
    "עוסקים מקצועיים": "ROLE_TITLE",
    # Hindi / Devanagari
    "व्यक्ति": "PERSON",
    "स्थान": "LOC",
    "वाहन": "PRODUCT",
    "संस्थान": "ORG",
    "उद्योग": "SYSTEM",
    "जलीय जीव": "BIOMED",
    "फसल": "BIOMED",
    # Romance leftovers
    "conceito": "CONCEPT",
    "quantidade": "NUMBER",
    "quantità": "NUMBER",
    "ingrediente": "PRODUCT",
    "sintomo": "BIOMED",
}


def remove_tree(path):
    def onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onexc=onexc)


def norm(text):
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return text


def compact(text):
    return norm(text).replace(" / ", " ")


def contains_any(text, words):
    for word in words:
        word = word.strip()
        if re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text):
            return True
    return False


def split_original_label(label):
    value = norm(label)
    if " / " not in value:
        return value, "", False
    coarse, fine = value.split(" / ", 1)
    return coarse.strip(), fine.strip(), True


def canonical_text(text):
    value = norm(text).replace("_", " ")
    for src, dst in HEAD_TRANSLATIONS.items():
        value = value.replace(src, f" {dst} ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def text_tokens(text):
    return TOKEN_RE.findall(canonical_text(text))


def variants(token):
    yielded = set()
    for cand in (token,):
        if cand and cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("ies") and len(token) > 4:
        cand = token[:-3] + "y"
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("es") and len(token) > 3:
        cand = token[:-2]
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("s") and len(token) > 3:
        cand = token[:-1]
        if cand not in yielded:
            yield cand


def phrase_vector(text, vectors):
    toks = text_tokens(text)
    found = []
    for tok in toks:
        vec = None
        for cand in variants(tok):
            vec = vectors.get(cand)
            if vec is not None:
                break
        if vec is not None:
            found.append(vec)
    if not found:
        return None, 0, len(toks)
    vec = np.mean(found, axis=0)
    mag = np.linalg.norm(vec)
    if not mag:
        return None, len(found), len(toks)
    return vec / mag, len(found), len(toks)


def load_top500():
    rows = []
    with TOP500_MAP.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rows.append(
                {
                    "bucket": row["new_main_bucket"].strip(),
                    "label": norm(row["coarse_label"]),
                    "freq": int(row["coarse_freq"]),
                    "source": "manual_top500",
                }
            )
    return rows


def load_inventory_rows():
    rows = []
    with LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            coarse, fine, has_fine = split_original_label(row["original_label"])
            rows.append(
                {
                    "original_label": row["original_label"],
                    "count": int(row["count"]),
                    "coarse_label": coarse,
                    "fine_label": fine,
                    "has_fine": has_fine,
                }
            )
    return rows


def collect_needed_words(top500_rows, inventory_rows):
    needed = set()
    for row in top500_rows:
        for tok in text_tokens(row["label"]):
            needed.update(variants(tok))
    for bucket, labels in BUCKET_PROTOTYPES.items():
        for label in labels:
            for tok in text_tokens(label):
                needed.update(variants(tok))
    for row in inventory_rows:
        candidates = [
            row["original_label"],
            row["coarse_label"],
            row["fine_label"],
            f"{row['coarse_label']} {row['fine_label']}",
        ]
        for candidate in candidates:
            for tok in text_tokens(candidate):
                needed.update(variants(tok))
    return needed


def load_needed_fasttext(needed):
    vectors = {}
    needed_bytes = {w.encode("utf-8") for w in needed}
    with zipfile.ZipFile(FASTTEXT_ZIP, "r") as zf:
        vec_name = next(name for name in zf.namelist() if name.endswith(".vec"))
        with zf.open(vec_name, "r") as f:
            f.readline()
            for line in f:
                word, _, rest = line.partition(b" ")
                if word not in needed_bytes:
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                if arr.size:
                    mag = np.linalg.norm(arr)
                    if mag:
                        vectors[word.decode("utf-8")] = arr / mag
    return vectors


class KnnMatcher:
    def __init__(self, top500_rows, vectors):
        anchors = []
        for row in top500_rows:
            vec, hits, toks = phrase_vector(row["label"], vectors)
            if vec is not None:
                anchors.append(
                    {
                        "bucket": row["bucket"],
                        "label": row["label"],
                        "source": row["source"],
                        "weight": math.log1p(row["freq"]),
                        "vec": vec,
                        "hits": hits,
                        "tokens": toks,
                    }
                )
        for bucket, labels in BUCKET_PROTOTYPES.items():
            for label in labels:
                vec, hits, toks = phrase_vector(label, vectors)
                if vec is not None:
                    anchors.append(
                        {
                            "bucket": bucket,
                            "label": label,
                            "source": "prototype",
                            "weight": 4.0,
                            "vec": vec,
                            "hits": hits,
                            "tokens": toks,
                        }
                    )
        self.anchors = anchors
        self.matrix = np.vstack([a["vec"] for a in anchors]) if anchors else np.zeros((0, 300), dtype=np.float32)
        self.vectors = vectors

    def choose_text(self, label):
        coarse, fine, has_fine = split_original_label(label)
        if has_fine and coarse in WEAK_HEADS:
            return fine, "weak_head_fine_knn"
        if has_fine and coarse in {"scientific concept", "technology", "product", "document", "media", "work"}:
            return fine, "weak_head_fine_knn"
        if has_fine:
            return f"{coarse} {fine}", "fulltag_gold_knn"
        return coarse, "coarse_gold_knn"

    def best_bucket(self, text, k=15):
        vec, hits, toks = phrase_vector(text, self.vectors)
        if vec is None or not len(self.anchors):
            return None, {
                "vector_hits": hits,
                "vector_tokens": toks,
                "similarity": "",
                "second_bucket": "",
                "second_similarity": "",
                "margin": "",
                "top_neighbors": "",
            }
        scores = self.matrix @ vec
        n = min(k, len(scores))
        idxs = np.argpartition(-scores, n - 1)[:n]
        idxs = idxs[np.argsort(-scores[idxs])]
        votes = defaultdict(float)
        top_neighbors = []
        for idx in idxs:
            anchor = self.anchors[int(idx)]
            score = float(scores[int(idx)])
            votes[anchor["bucket"]] += max(score, 0.0) * anchor["weight"]
            top_neighbors.append(f"{anchor['bucket']}:{anchor['label']}:{score:.3f}")
        ranked = sorted(votes.items(), key=lambda x: (-x[1], x[0]))
        best, best_vote = ranked[0]
        second, second_vote = ranked[1] if len(ranked) > 1 else ("", 0.0)
        top_score = float(scores[int(idxs[0])])
        return best, {
            "vector_hits": hits,
            "vector_tokens": toks,
            "similarity": f"{top_score:.6f}",
            "second_bucket": second,
            "second_similarity": f"{second_vote:.6f}",
            "margin": f"{best_vote - second_vote:.6f}",
            "top_neighbors": "; ".join(top_neighbors[:5]),
        }

    def map_label(self, label, current_bucket):
        text, source = self.choose_text(label)
        bucket, meta = self.best_bucket(text)
        if bucket is None:
            return current_bucket, "knn_no_vector_fallback", text, meta
        if meta["similarity"] and float(meta["similarity"]) < 0.16:
            return "MISC", "knn_low_confidence_misc", text, meta
        return bucket, source, text, meta


def hard_head_override(label):
    coarse, fine, has_fine = split_original_label(label)
    text = f"{coarse} | {fine}"
    if coarse in {"person", "persons", "pessoa", "บุคคล", "شخص", "אדם", "individual"}:
        if contains_any(text, ["deity", "god", "goddess", "orix", "mythological", "avatar", "saint"]):
            return "CULTURE_RELIGION", "hard_head_person_myth_exception"
        return "PERSON", "hard_head_person"
    if coarse in HARD_HEAD_BUCKETS:
        if coarse in WEAK_HEADS and has_fine:
            return None, None
        return HARD_HEAD_BUCKETS[coarse], f"hard_head_{HARD_HEAD_BUCKETS[coarse].lower()}"
    return None, None


def load_fulltag_map():
    label_map = {}
    with FULLTAG_MAP.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            row["count"] = int(row["count"])
            label_map[row["original_label"]] = row
    return label_map


def lexical_fallback(label, mapping_text):
    candidates = [norm(label), norm(mapping_text), compact(label), compact(mapping_text)]
    parts = []
    for value in candidates:
        parts.extend([p.strip() for p in value.split(" / ") if p.strip()])
        parts.append(value)
    for part in parts:
        if part in LEXICAL_FALLBACKS:
            return LEXICAL_FALLBACKS[part], f"lexical_fallback:{part}"
    return None, None


def override_bucket(label, mapping_text, current_bucket):
    text = f"{compact(label)} | {compact(mapping_text)}"
    coarse, fine, has_fine = split_original_label(label)

    if coarse in {"person", "persons", "pessoa", "บุคคล", "شخص", "אדם", "individual"}:
        if contains_any(text, ["deity", "god", "goddess", "orix", "mythological", "avatar", "saint"]):
            return "CULTURE_RELIGION", "hard_head_person_myth_exception"
        return "PERSON", "hard_head_person"

    # Identifiers and ratings before facility words.
    if contains_any(text, ["hotel code", "airport code", "airline code", "code/identifier", "document identifier"]):
        return "SYMBOL_IDENTIFIER", "rule_identifier_code"
    if contains_any(text, ["abbreviation", "acronym"]):
        return "SYMBOL_IDENTIFIER", "rule_abbreviation_identifier"
    if contains_any(text, ["hotel rating", "rating hotel", "earthquake magnitude", "magnitude earthquake"]):
        return "STATISTIC", "rule_statistic_rating_magnitude"
    if "street number" in text:
        return "NUMBER", "rule_street_number"
    if contains_any(text, ["street address", "address street"]):
        return "SYMBOL_IDENTIFIER", "rule_address_identifier"

    if contains_any(text, ["award category", "film award category", "award / film award", "film award", "music award"]):
        return "SYMBOL_IDENTIFIER", "rule_award_identifier"
    if contains_any(text, ["award ceremony", "award show"]):
        return "EVENT", "rule_award_event"

    if contains_any(text, ["highway code", "legal code", "law code"]):
        return "LEGAL_POLITICAL", "rule_legal_code"

    if contains_any(text, ["passport", "identity document", "id card", "government id", "citation", "biblical verse", "verse reference", "article id", "document id", "reference number"]):
        return "SYMBOL_IDENTIFIER", "rule_document_identifier"

    if contains_any(text, ["customs document", "customs declaration", "warning letter", "decree", "contract", "legal document", "regulatory document", "medical report", "hospital report", "quarantine pass", "policy document", "curriculum guideline"]):
        return "LEGAL_POLITICAL", "rule_document_legal_admin"

    if contains_any(text, ["academic discipline", "field of study", "business administration", "mathematics", "sociology", "philosophy", "literature studies"]):
        return "CONCEPT", "rule_academic_discipline_concept"

    if contains_any(text, ["economic indicator", "financial metric", "statistical measure", "statistical measurement"]):
        return "STATISTIC", "rule_statistic"

    if contains_any(text, ["government title and person", "title and person", "role and person"]):
        return "PERSON", "rule_title_plus_person"

    if contains_any(text, ["geological feature"]):
        return "LOC", "rule_geological_location"

    if contains_any(text, ["natural formation"]):
        return "NATURAL_OBJECT", "rule_natural_object"

    if contains_any(text, ["shooting technique", "technique", "skill"]):
        return "ACTIVITY_PROCESS", "rule_activity_technique"

    if contains_any(text, ["distance", "storage capacity", "engine displacement"]):
        return "NUMBER", "rule_measurement_number"

    if contains_any(text, ["legal concept", "legal term"]):
        return "LEGAL_POLITICAL", "rule_legal_political"

    if contains_any(text, ["medical specialty"]):
        return "SYSTEM", "rule_medical_specialty_system"

    if contains_any(text, ["musical instrument"]):
        return "PRODUCT", "rule_product_instrument"

    if contains_any(text, ["imaginary object"]):
        return "CONCEPT", "rule_imaginary_object_concept"

    if contains_any(text, ["object"]) and not contains_any(text, ["natural object", "astronomical object", "celestial object", "celestial body"]):
        return "PRODUCT", "rule_product_object"

    if contains_any(text, ["security check", "airport procedure", "medical procedure", "legal procedure", "procedure", "checkup", "test procedure"]):
        if contains_any(text, ["legal procedure"]):
            return "LEGAL_POLITICAL", "rule_legal_process"
        if contains_any(text, ["medical procedure"]):
            return "ACTIVITY_PROCESS", "rule_medical_process"
        return "ACTIVITY_PROCESS", "rule_procedure_process"

    if contains_any(text, ["terminal illness", "terminal disease", "terminal condition"]):
        return "BIOMED", "rule_biomed_entity"

    if contains_any(text, ["radio station", "tv station", "television station", "news station", "broadcasting station"]):
        return "ORG", "rule_media_station_org"

    if contains_any(text, ["cave chamber", "cave room", "cave passage"]):
        return "LOC", "rule_cave_location"

    if contains_any(text, ["economic policy", "legal framework", "political system", "legal process", "political process"]):
        return "LEGAL_POLITICAL", "rule_legal_political"

    if contains_any(text, ["wage", "salary", "income amount", "payment amount"]):
        return "MONEY", "rule_money_compensation"

    if contains_any(text, ["betting system", "market system", "transport system"]):
        return "SYSTEM", "rule_named_system"

    if contains_any(text, ["industrial complex", "bus operator", "rail operator", "airport operator"]):
        return "ORG", "rule_operator_org"

    if contains_any(text, ["musical group", "music group", "rock band", "hacker group", "terrorist group", "rebel group", "militant group", "religious order", "military unit"]):
        return "ORG", "rule_organized_group_org"

    if contains_any(text, ["streaming service", "online service", "social media platform", "gaming service", "online platform", "website"]):
        return "PRODUCT", "rule_digital_product_service"

    if contains_any(text, ["operating system"]):
        return "PRODUCT", "rule_software_product"

    if contains_any(text, ["online casino"]):
        return "PRODUCT", "rule_digital_product_service"

    if contains_any(text, ["casino game", "game category casino"]):
        return "GENRE_FORM", "rule_genre_form"

    if contains_any(text, ["health emergency", "health crisis", "environmental disaster", "environmental damage", "natural disaster", "war", "battle"]):
        return "EVENT", "rule_event_crisis_conflict"

    if contains_any(text, ["music genre", "film genre", "movie genre", "game genre", "manga genre", "art form", "animation genre", "media type", "media format"]):
        return "GENRE_FORM", "rule_genre_form"

    if contains_any(text, ["character in", "fictional character", "mythological character"]):
        if contains_any(text, ["mythological character"]):
            return "CULTURE_RELIGION", "rule_deity_myth_religion"
        return "PERSON", "rule_person_character"

    if contains_any(text, ["professional organization", "professional association", "professional body"]):
        return "ORG", "rule_professional_org"

    if contains_any(text, ["profession", "occupation", "composer", "musician", "singer", "writer", "author", "journalist", "scientist", "researcher", "correspondent", "professional", "director"]):
        return "ROLE_TITLE", "rule_profession_role"

    if contains_any(text, ["location community"]) and not contains_any(text, ["organization"]):
        return "LOC", "rule_location_community"

    if contains_any(text, ["community", "ethnic group", "demographic group", "social group", "population group", "lgbtq"]):
        if not contains_any(text, ["community organization", "community centre", "community center", "community building"]):
            return "NORP", "rule_people_group"

    if contains_any(text, ["empire", "kingdom", "historical region"]):
        return "LOC", "rule_geopolitical_location"

    if contains_any(text, ["political entity"]):
        if contains_any(text, ["government"]):
            return "ORG", "rule_government_org"
        if not contains_any(text, ["organization", "company", "party"]):
            return "LOC", "rule_geopolitical_location"

    if contains_any(text, ["idiom", "phrase", "word form"]):
        return "LANGUAGE", "rule_language_expression"

    # Physical facilities and infrastructure.
    if contains_any(text, ["location school", "school ward", "school building"]):
        return "FAC", "rule_physical_facility"

    if contains_any(
        text,
        [
            "road",
            "highway",
            "street",
            "bridge",
            "tunnel",
            "railway station",
            "train station",
            "station",
            "airport",
            "terminal",
            "port",
            "harbor",
            "pier",
            "temple",
            "church",
            "mosque",
            "shrine",
            "cathedral",
            "monastery",
            "hotel",
            "resort",
            "casino",
            "school building",
            "architectural element",
            "architectural feature",
        ],
    ):
        if not contains_any(
            text,
            [
                "company",
                "authority",
                "operator",
                "congregation",
                "political",
                "school of thought",
                "educational institution",
                "philosophical school",
                "broadcasting organization",
                "media organization",
                "government organization",
                "church organization",
                "hotel chain",
            ],
        ):
            return "FAC", "rule_physical_facility"

    if contains_any(text, ["temple name", "church name", "mosque name", "shrine name"]):
        return "FAC", "rule_religious_building_name"

    if contains_any(text, ["philosophical concept deity"]):
        return "CONCEPT", "rule_philosophical_concept"

    if contains_any(text, ["deity", "god", "goddess", "orix", "mythological", "divine figure", "divine entity", "religious figure", "saint"]):
        return "CULTURE_RELIGION", "rule_deity_myth_religion"

    if contains_any(text, ["championship", "tournament", "competition", "sports match", "football match", "basketball championship", "cup final", "grand prix", "race stage"]):
        if not contains_any(text, ["organization", "club", "league ranking", "ranking", "score", "format", "category"]):
            return "EVENT", "rule_competition_event"

    if contains_any(text, ["record label", "music label", "film studio", "music studio"]):
        return "ORG", "rule_label_studio_org"

    if contains_any(text, ["video game company", "game company", "game developer"]):
        return "ORG", "rule_game_company_org"

    if contains_any(text, ["publisher", "publishing house"]):
        if not contains_any(text, ["self-publishing", "publishing format"]):
            return "ORG", "rule_publisher_org"

    if contains_any(text, ["father of", "founder of"]):
        return "ROLE_TITLE", "rule_role_epithet"

    if contains_any(text, ["building material", "construction material", "cement", "bronze alloy", "alloy", "mineral", "material/resource"]):
        return "NATURAL_OBJECT", "rule_material_natural_object"

    if contains_any(text, ["patronage", "ritual", "religious practice", "cultural practice"]):
        return "CULTURE_RELIGION", "rule_cultural_religious_practice"

    if contains_any(text, ["body part", "anatomical", "organ", "symptom", "disease", "medical condition", "mental disorder", "parasite"]):
        return "BIOMED", "rule_biomed_entity"

    if contains_any(text, ["song", "movie", "film title", "tv show", "television drama", "book title", "literary work", "work of art", "manga", "anime title", "video game", "game"]):
        return "WORK_OF_ART", "rule_artwork_media"

    if contains_any(text, ["music genre", "film genre", "game genre", "art form", "animation genre", "media type", "media format"]):
        return "GENRE_FORM", "rule_genre_form"

    if contains_any(text, ["currency amount", "monetary amount", "monetary value"]):
        return "MONEY", "rule_money"

    if contains_any(text, ["score", "ranking", "statistic", "index value", "metric"]):
        return "STATISTIC", "rule_statistic"

    bucket, source = lexical_fallback(label, mapping_text)
    if bucket:
        return bucket, source

    return current_bucket, "fulltag_base"


def build_rule_map(label_map, matcher):
    out = {}
    for label, row in label_map.items():
        meta = {
            "semantic_mapping_text": "",
            "vector_hits": "",
            "vector_tokens": "",
            "similarity": "",
            "second_bucket": "",
            "second_similarity": "",
            "margin": "",
            "top_neighbors": "",
        }
        bucket, source = override_bucket(label, row["mapping_text"], row["new_main_bucket"])
        coarse, fine, has_fine = split_original_label(label)
        if source == "fulltag_base":
            hard_bucket, hard_source = hard_head_override(label)
            if hard_bucket is not None and not has_fine:
                bucket, source = hard_bucket, hard_source
        if source == "fulltag_base" and has_fine and coarse in WEAK_HEADS:
            bucket, source, semantic_text, knn_meta = matcher.map_label(label, row["new_main_bucket"])
            meta["semantic_mapping_text"] = semantic_text
            meta.update(knn_meta)
        new = dict(row)
        new["previous_bucket"] = row["new_main_bucket"]
        new["new_main_bucket"] = bucket
        new["rule_source"] = source
        new.update(meta)
        out[label] = new
    return out


def is_single_thai_char(token):
    return len(token) == 1 and "\u0e00" <= token <= "\u0e7f"


def surface_bucket_override(lang, surface, original_label, mapped_bucket):
    text = surface.strip()
    label = norm(original_label)
    if not text:
        return None, None
    if URL_EMAIL_RE.search(text):
        return "SYMBOL_IDENTIFIER", "surface_url_email_identifier"
    if MONEY_RE.search(text):
        return "MONEY", "surface_money_regex"
    if TIME_UNIT_RE.search(text):
        return "DATE_TIME", "surface_duration_regex"
    if YEAR_RE.fullmatch(text.strip()):
        return "DATE_TIME", "surface_year_regex"
    if PERCENT_RE.search(text):
        if contains_any(label, ["statistic", "rate", "indicator", "metric"]):
            return "STATISTIC", "surface_percent_statistic_regex"
        return "NUMBER", "surface_percent_number_regex"
    if CELESTIAL_RE.search(text) or contains_any(label, ["celestial body", "astronomical object", "planet", "asteroid", "galaxy", "nebula"]):
        return "NATURAL_OBJECT", "surface_celestial_regex"
    return None, None


def convert_split(src, dst_bio, dst_side, rule_map, lang):
    stats = Counter()
    bucket_tokens = Counter()
    bucket_spans = Counter()
    original_counts = Counter()

    with src.open("r", encoding="utf-8", newline="") as fin, dst_bio.open("w", encoding="utf-8", newline="") as fbio, dst_side.open("w", encoding="utf-8", newline="") as fside:
        reader = csv.reader(fin, delimiter="\t")
        header = next(reader)
        idx = {name: i for i, name in enumerate(header)}
        writer = csv.writer(fside, delimiter="\t", lineterminator="\n")
        writer.writerow(["token", "original_bio", "mapping_text", "assignment_source", "previous_bucket_bio", "bucket_bio"])

        sentence_rows = []

        def flush_sentence():
            if not sentence_rows:
                return
            # Filter only whole-span one-character Thai-script entities.
            span_ids_to_filter = set()
            if lang == "tha":
                i = 0
                while i < len(sentence_rows):
                    row = sentence_rows[i]
                    orig = row["original_bio"]
                    if orig == "O":
                        i += 1
                        continue
                    pref, label = orig.split("-", 1)
                    if pref != "B":
                        i += 1
                        continue
                    j = i + 1
                    while j < len(sentence_rows) and sentence_rows[j]["original_bio"].startswith("I-"):
                        j += 1
                    tokens = [sentence_rows[k]["token"] for k in range(i, j)]
                    if len(tokens) == 1 and is_single_thai_char(tokens[0]):
                        span_ids_to_filter.update(range(i, j))
                    i = j

            span_bucket_overrides = {}
            i = 0
            while i < len(sentence_rows):
                row = sentence_rows[i]
                orig = row["original_bio"]
                if orig == "O" or not orig.startswith("B-"):
                    i += 1
                    continue
                _, label = orig.split("-", 1)
                j = i + 1
                while j < len(sentence_rows) and sentence_rows[j]["original_bio"] == f"I-{label}":
                    j += 1
                if not any(k in span_ids_to_filter for k in range(i, j)):
                    mapped = rule_map.get(label.strip())
                    if mapped is None:
                        raise KeyError(f"Missing label map for {label!r}")
                    surface = " ".join(sentence_rows[k]["token"] for k in range(i, j))
                    override_bucket, override_source = surface_bucket_override(lang, surface, label, mapped["new_main_bucket"])
                    if override_bucket:
                        for k in range(i, j):
                            span_bucket_overrides[k] = (override_bucket, override_source)
                i = j

            for row_idx, row in enumerate(sentence_rows):
                token = row["token"]
                orig = row["original_bio"]
                previous = row["bucket_bio"]
                if row_idx in span_ids_to_filter or orig == "O":
                    bucket_bio = "O"
                    mapping_text = "_"
                    source = "thai_single_char_span_filter" if row_idx in span_ids_to_filter else "_"
                    if row_idx in span_ids_to_filter:
                        stats["thai_single_char_span_tokens_filtered"] += 1
                else:
                    pref, label = orig.split("-", 1)
                    label_key = label.strip()
                    mapped = rule_map.get(label_key)
                    if mapped is None:
                        raise KeyError(f"Missing label map for {label!r}")
                    if row_idx in span_bucket_overrides:
                        bucket, source = span_bucket_overrides[row_idx]
                    else:
                        bucket = mapped["new_main_bucket"]
                        source = mapped["rule_source"]
                    bucket_bio = f"{pref}-{bucket}"
                    mapping_text = mapped["mapping_text"]
                    bucket_tokens[bucket] += 1
                    if pref == "B":
                        bucket_spans[bucket] += 1
                        original_counts[(mapped["original_label"], bucket, mapped["previous_bucket"], source)] += 1
                fbio.write(f"{token}\t{bucket_bio}\n")
                writer.writerow([token, orig, mapping_text, source, previous, bucket_bio])
                stats["tokens"] += 1
            fbio.write("\n")
            fside.write("\n")
            stats["sentences"] += 1
            sentence_rows.clear()

        for row in reader:
            if not row:
                flush_sentence()
                continue
            sentence_rows.append({
                "token": row[idx["token"]],
                "original_bio": row[idx["original_bio"]],
                "bucket_bio": row[idx["bucket_bio"]],
            })
        flush_sentence()

    return stats, bucket_tokens, bucket_spans, original_counts


def convert_dataset(rule_map):
    remove_tree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)

    map_path = OUTPUT_ROOT / "fulltag_rules_bucket_map.tsv"
    with map_path.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "new_main_bucket",
            "previous_bucket",
            "original_label",
            "count",
            "mapping_text",
            "semantic_mapping_text",
            "rule_source",
            "vector_hits",
            "vector_tokens",
            "similarity",
            "second_bucket",
            "second_similarity",
            "margin",
            "top_neighbors",
        ]
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in sorted(rule_map.values(), key=lambda r: (-r["count"], r["original_label"])):
            writer.writerow({field: row[field] for field in fields})

    langs = sorted(p.name for p in INPUT_ROOT.iterdir() if p.is_dir())
    root_stats = Counter()
    root_bucket_tokens = Counter()
    root_bucket_spans = Counter()
    root_original_counts = Counter()
    root_rule_sources = Counter()

    for lang in langs:
        out_lang = OUTPUT_ROOT / lang
        out_lang.mkdir()
        lang_stats = Counter()
        lang_bucket_tokens = Counter()
        lang_bucket_spans = Counter()
        lang_original_counts = Counter()

        for split in SPLITS:
            stats, bucket_tokens, bucket_spans, original_counts = convert_split(
                INPUT_ROOT / lang / f"{split}.original_vs_bucket.tsv",
                out_lang / f"{split}.bio",
                out_lang / f"{split}.original_vs_bucket.tsv",
                rule_map,
                lang,
            )
            with (out_lang / "split_summary.tsv").open("a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                if f.tell() == 0:
                    writer.writerow(["split", "sentences", "tokens", "entity_spans", "entity_tokens", "thai_single_char_span_tokens_filtered"])
                writer.writerow([split, stats["sentences"], stats["tokens"], sum(bucket_spans.values()), sum(bucket_tokens.values()), stats["thai_single_char_span_tokens_filtered"]])
            if split == "all":
                lang_stats.update(stats)
                lang_bucket_tokens.update(bucket_tokens)
                lang_bucket_spans.update(bucket_spans)
                lang_original_counts.update(original_counts)
                root_stats.update(stats)
                root_bucket_tokens.update(bucket_tokens)
                root_bucket_spans.update(bucket_spans)
                root_original_counts.update(original_counts)
                for (_, _, _, source), count in original_counts.items():
                    root_rule_sources[source] += count

        write_counts(out_lang, lang_bucket_tokens, lang_bucket_spans, lang_original_counts)
        (out_lang / "dataset_report.json").write_text(
            json.dumps(
                {
                    "lang": lang,
                    "sentences": lang_stats["sentences"],
                    "tokens": lang_stats["tokens"],
                    "entity_spans": sum(lang_bucket_spans.values()),
                    "entity_tokens": sum(lang_bucket_tokens.values()),
                    "thai_single_char_span_tokens_filtered": lang_stats["thai_single_char_span_tokens_filtered"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    write_counts(OUTPUT_ROOT, root_bucket_tokens, root_bucket_spans, root_original_counts)
    with (OUTPUT_ROOT / "rule_source_summary.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rule_source", "span_count"])
        for source, count in root_rule_sources.most_common():
            writer.writerow([source, count])

    report = {
        "input_root": str(INPUT_ROOT),
        "output_root": str(OUTPUT_ROOT),
        "method": "Fulltag fastText baseline plus deterministic ontological override rules and small multilingual no-vector fallbacks. Previous datasets are not modified.",
        "languages": langs,
        "sentences": root_stats["sentences"],
        "tokens": root_stats["tokens"],
        "entity_spans": sum(root_bucket_spans.values()),
        "entity_tokens": sum(root_bucket_tokens.values()),
        "thai_single_char_span_tokens_filtered": root_stats["thai_single_char_span_tokens_filtered"],
    }
    (OUTPUT_ROOT / "dataset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_ROOT / "README.md").write_text(
        "# fiNERweb fulltag-hybrid-v9 bucketed Trankit NER BIO datasets by language\n\n"
        "Baseline: `finerweb_bucketed_fulltag_fasttext_by_language`.\n"
        "This version keeps the same tokens and original labels, then remaps buckets with deterministic ontological rules, "
        "compound-label head policy, weak-head fine-tag masking, k-NN over manual/prototype anchors, and surface regex guards. "
        "Thai standalone one-character Thai-script entity spans are filtered to `O`; single-character tokens inside larger spans are preserved.\n",
        encoding="utf-8",
    )
    return report


def write_counts(root, bucket_tokens, bucket_spans, original_counts):
    with (root / "label_token_counts.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["new_main_bucket", "entity_token_count", "entity_span_count"])
        for bucket in sorted(set(bucket_tokens) | set(bucket_spans)):
            writer.writerow([bucket, bucket_tokens[bucket], bucket_spans[bucket]])
    with (root / "original_label_bucket_counts.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["original_label", "new_main_bucket", "previous_bucket", "rule_source", "span_count"])
        for key, count in sorted(original_counts.items(), key=lambda x: (-x[1], x[0])):
            writer.writerow([*key, count])


def validate():
    issues = []
    langs = sorted(p.name for p in OUTPUT_ROOT.iterdir() if p.is_dir())
    for lang in langs:
        for split in SPLITS:
            bio = OUTPUT_ROOT / lang / f"{split}.bio"
            side = OUTPUT_ROOT / lang / f"{split}.original_vs_bucket.tsv"
            bio_rows = []
            with bio.open("r", encoding="utf-8", newline="") as f:
                for lineno, raw in enumerate(f, 1):
                    line = raw.rstrip("\n")
                    if not line:
                        bio_rows.append(("", ""))
                        continue
                    parts = line.split("\t")
                    if len(parts) != 2:
                        issues.append([lang, split, str(bio), lineno, "bad_bio_columns", line[:80]])
                        continue
                    if not LABEL_RE.match(parts[1]):
                        issues.append([lang, split, str(bio), lineno, "bad_bio_label", parts[1]])
                    if parts[1] != "O" and parts[1].split("-", 1)[1] not in EXPECTED_BUCKETS:
                        issues.append([lang, split, str(bio), lineno, "unexpected_bucket", parts[1]])
                    bio_rows.append(tuple(parts))

            side_rows = []
            with side.open("r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                header = next(reader, [])
                if header != ["token", "original_bio", "mapping_text", "assignment_source", "previous_bucket_bio", "bucket_bio"]:
                    issues.append([lang, split, str(side), 1, "bad_side_header", "\t".join(header)])
                for lineno, row in enumerate(reader, 2):
                    if not row:
                        side_rows.append(("", ""))
                        continue
                    if len(row) != 6:
                        issues.append([lang, split, str(side), lineno, "bad_side_columns", "\t".join(row)[:80]])
                        continue
                    if not LABEL_RE.match(row[5]):
                        issues.append([lang, split, str(side), lineno, "bad_side_bucket", row[5]])
                    side_rows.append((row[0], row[5]))

            if bio_rows != side_rows:
                issues.append([lang, split, str(side), 0, "bio_side_sequence_mismatch", f"{len(bio_rows)} vs {len(side_rows)}"])

            prev = "O"
            for idx, (_, label) in enumerate(bio_rows, 1):
                if not label or label == "O":
                    prev = "O"
                    continue
                pref, bucket = label.split("-", 1)
                if pref == "I" and prev not in {f"B-{bucket}", f"I-{bucket}"}:
                    issues.append([lang, split, str(bio), idx, "invalid_i_transition", label])
                prev = label

    with (OUTPUT_ROOT / "archive_health_issues.tsv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["lang", "split", "file", "line", "issue", "detail"])
        writer.writerows(issues)
    report = {"files_checked": len(langs) * len(SPLITS) * 2, "issue_count": len(issues), "issues_tsv": str(OUTPUT_ROOT / "archive_health_issues.tsv")}
    (OUTPUT_ROOT / "archive_health_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def make_zip():
    tmp = ZIP_PATH.with_suffix(".zip.tmp")
    if tmp.exists():
        tmp.unlink()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(OUTPUT_ROOT.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(OUTPUT_ROOT.parent).as_posix())
    os.replace(tmp, ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        return {"zip": str(ZIP_PATH), "members": len(zf.namelist()), "size_bytes": ZIP_PATH.stat().st_size}


def main():
    top500_rows = load_top500()
    inventory_rows = load_inventory_rows()
    needed = collect_needed_words(top500_rows, inventory_rows)
    vectors = load_needed_fasttext(needed)
    matcher = KnnMatcher(top500_rows, vectors)
    fulltag_map = load_fulltag_map()
    rule_map = build_rule_map(fulltag_map, matcher)
    report = convert_dataset(rule_map)
    report["method"] = (
        "Fulltag fastText baseline remapped with deterministic ontological guards, compound-label head policy, "
        "weak-head fine-tag masking, k-NN against top-500 manual anchors plus curated prototypes, span-surface "
        "regex overrides for money/duration/URLs/years/percent/celestial bodies, and Thai standalone one-character filtering."
    )
    report["knn_anchor_count"] = len(matcher.anchors)
    report["fasttext_loaded_words"] = len(vectors)
    (OUTPUT_ROOT / "dataset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    health = validate()
    zip_info = make_zip()
    summary = {"dataset": str(OUTPUT_ROOT), "zip": zip_info, "report": report, "health": health}
    (OUTPUT_ROOT / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_info = make_zip()
    summary["zip"] = zip_info
    (OUTPUT_ROOT / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
