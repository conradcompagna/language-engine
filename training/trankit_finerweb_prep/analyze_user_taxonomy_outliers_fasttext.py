from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

import assign_coarse_tags_to_manual_full_label_child_regions as base


OUT_DIR = Path(__file__).resolve().parent / "derived_fasttext_categories"
OUT_TSV = OUT_DIR / "user_13_bucket_fasttext_outliers.tsv"
OUT_MD = OUT_DIR / "user_13_bucket_fasttext_outliers.md"


RAW = r"""
## 1. Location / Spatial Entity

location (39110), location / country (31286), location / city (23849), country (12518), city (5306), location / region (2905), location / province (2874), location / state (2083), region (1625), location / district (1236), location / village (1010), state (801), political entity (790), location / island (766), infrastructure (760), location / building (736), continent (723), location / neighborhood (656), province (638), building (580), location / continent (573), location / administrative region (545), location / street (493), facility (482), district (474), location / municipality (464), river (442), geographic region (437), administrative region (430), location / geographic region (429), location / town (397), location / river (379), village (347), administrative division (342), location / stadium (330), geopolitical entity (323), universe (319), location / airport (287), geopolitical region (253), street (235), geographical feature (231), location / geopolitical entity (229), location / hospital (225), location / administrative division (225), location / geographic location (224), location / road (222), location / us state (220), location / educational institution (212), location / mountain (209), diocese (204), place (195), geographical region (195), celestial body (190), location / body of water (185), location / geopolitical region (184), police station (183), address (178), body of water (175), location / religious building (175), location / regency (175), location / sports venue (174), location / street name (173), religious building (172), location / place (172), location / temple (168), location / diocese (167), airport (166), island (165), cultural reference / building (161), planet (160), location / subdistrict (160), location / university (157), location / political entity (155), location / beach (153), location / mountain range (150), location / hotel (150), location / park (150), location / historical region (145), road (143), location / lake (143), location / school (140), natural feature (139), neighborhood (137), location / geographical region (136), mountain (135), location / police station (133), location / state/province (133), government building (130), location / locality (130), location / government building (125), location / city/town (125), astronomical object (124), world (122), temple (118), establishment (113), municipality (112), location / court (111), کشور / country (110), location / address (109), location / ancient city (107), geographic location (107), mountain range (107)

## 2. Individual Agent

person (123246), deity (2389), person / football player (1548), person / politician (1536), person / actor (1223), religious figure (967), person / religious figure (788), person / character (757), person / athlete (624), character (620), person / musician (602), person / deity (592), person / historical figure (570), person / artist (442), person / author (442), god (417), person / fictional character (353), persons (339), person / basketball player (322), person / cricketer (317), person / political figure (310), cultural reference / deity (301), person / mythological figure (283), cultural reference / religious figure (283), historical figure (274), person / film director (273), mythological figure (266), person / football manager (257), deity / hindu god of thunder (243), politician (227), person / historical person (220), person / cricket player (197), person / saint (190), person / singer (188), saint (188), pope (182), person / pope (182), person / actress (172), person / composer (169), person / poet (158), person / religious leader (154), person / racing driver (151), actor (150), religious leader (148), person / philosopher (148), government official (147), football player (144), person / political leader (141), person / biblical figure (138), political figure (132), شخص / person (132), person / police officer (130), cultural reference / person (129), deity/divine entity (128), pessoa / person (124), fictional character (121), hindu god of friendship (111), hindu god of water (111), person / football coach (110), political leader (110), cultural reference / mythological figure (108), persons / person (107), character / fictional character (105), cultural reference / fictional character (102), person / journalist (100)

## 3. Organization / Collective Agent

organization (39535), organization / company (3785), organization / sports club (3655), organization / government organization (3522), organization / political organization (2271), organization / football club (2167), political party (2114), government organization (1995), organization / government agency (1694), political organization (1535), organization / educational institution (1528), organization / sports team (1398), educational institution (1293), organization / political party (1242), organization / international organization (1188), organization / university (1184), organization / news agency (1103), news agency (1047), government agency (880), company (846), government (839), organization / news organization (804), sports team (753), event / sports league (740), organization / hospital (699), organization / sports organization (658), organization / financial institution (644), organization / government ministry (628), organization / military organization (569), organization / law enforcement agency (518), sports league (520), organization / religious organization (517), military organization (517), organization / social media platform (530), sports club (487), organization / government (477), organization / bank (438), organization / website (435), organization / court (431), news organization (417), political party / political organization (415), government ministry (411), university (410), organization / airline (401), political organization / political party (392), organization / hotel (391), organization / media organization (388), organization / terrorist organization (386), religious organization (380), media / news organization (376), organization / country (374), international organization (369), law enforcement agency (360), organization / television network (348), organization / newspaper (347), court (342), organization / governmental organization (341), location / sports club (308), location / football club (302), location / organization (300), media organization (311), sports team / sports club (289), media outlet (277), legislative body (276), military unit (275), political group (267), government body (267), financial institution (266), organization / basketball team (257), football club (255), hospital (254), media / news agency (245), organization / musical group (243), organization / telecommunications company (242), organization / legislative body (223), organization / police department (209), government department (209), governmental organization (205), event / football league (196), organization / school (199), dynasty (194), religious institution (190), organization / sports league (187), sports organization (184), sports team / football club (181), institution (176), organization / police force (168), organization / restaurant (168), organization / radio station (161), hotel (160), location / sports team (157), organization / streaming service (158), organization / military unit (155), organization / police station (154), organization / research institute (152), organization / pharmaceutical company (147), organization / museum (146), media / media outlet (146), terrorist organization (145), media / media organization (142), organization / government body (140), organization / tv channel (139), organization / labor union (136), organization / game developer (135), religious order (131), organization / religious order (130), organization / government department (127), organization / police unit (127), political body (121), cultural reference / organization (119), academic department (118), organization / central bank (118), political alliance (118), organization / television channel (115), organization / research institution (113), organization / music group (113), school (109), restaurant (108), police department (107), bank (105), organization / racing team (105), stock exchange (104), news outlet (103), organization / cryptocurrency exchange (103), organization / publishing house (101), organization / magazine (101), organization / news website (138)

## 4. Time Expression

date (31621), time period (8353), date / year (3656), year (3292), time (3278), duration (2895), day of the week (2393), month (1571), time period / duration (1048), time period / date (822), time period / month (779), date / day of the week (664), time duration (546), date / month (419), year / date (386), quantity / duration (384), historical period (353), time period / year (319), event / holiday (313), time period / day of the week (308), day of week (257), time period / time duration (256), date range (247), season (224), holiday (214), temporal expression (182), time period / season (172), measurement / duration (171), time period / historical period (162), time period / decade (129), cultural reference / holiday (124), time of day (107)

## 5. Abstract Concept / Mental-Social Construct

cultural reference (15874), concept (12658), scientific concept (9102), language (3184), brand (1921), economic concept (1586), legal concept (1560), field of study (1223), cultural concept (1184), financial concept (1089), philosophical concept (1016), political concept (685), religion (671), color (648), religious concept (498), social issue (477), nickname (476), financial market (454), social concept (415), organization / brand (393), legislation (388), financial term (383), academic discipline (323), political ideology (321), brand / company (281), abstract concept (276), phone number (271), legal term (263), brand / organization (257), philosophical concept/deity / philosophical concept (257), law (253), pronoun (229), policy (224), person / nickname (223), scientific field (219), medical concept (209), entity (206), url (205), hashtag (199), organization / automotive brand (195), market (179), person / character name (188), legal document / law (188), business concept (182), health concept (180), email address (174), cultural reference / sacred symbol/mantra (172), political system (159), organization abbreviation (154), latin word (154), cultural reference / nickname (148), psychological concept (147), biological concept (145), regulation (144), feature (143), legal code (138), organization / organization abbreviation (136), contact number / phone number (136), general concept (135), educational concept (134), cultural reference / religion (134), cultural reference / concept (133), scientific concept / scientific field (130), word (128), tax (124), brand / automotive brand (121), legislation / law (119), field (118), social media handle (117), organization / government organization abbreviation (117), field of study / academic discipline (114), family name (110), legal case (109), environmental issue (107), economic policy (107), philosophical school (107), person / person name (106), cultural reference / religious concept (105), medical term (103), topic (102), skill (101), direction (100)

## 6. Measurement / Quantity Expression

quantity (20583), measurement (2948), age (2443), percentage (2437), quantity / monetary value (2170), monetary value (1367), statistic (927), statistic / percentage (887), number (779), score (692), currency / monetary value (597), price (416), distance (381), quantity / percentage (376), quantity / money (366), measurement / distance (359), quantity / age (318), currency amount (290), measurement / quantity (270), economic indicator (265), currency/amount / monetary value (209), quantity / number (203), money (195), ordinal number (185), quantities (184), ranking (174), statistic / quantity (169), page number (169), quantity / currency amount (165), unit of measurement (159), financial metric (139), quantity / price (135), age range (132), currency/quantity / monetary value (124), financial index / stock market index (123), technical indicator (124), measurement / area (121), statistics (120), currency amount / monetary value (118), quantity / currency (115), currency / currency amount (110)

## 7. Event, Process, Action, Undertaking

event (17186), activity (802), service (672), medical procedure (654), historical event (489), program (426), event / sports event (403), crime (363), process (371), event / sports competition (321), event / festival (318), festival (318), event / historical event (287), project (271), political event (233), government program (209), event / sports tournament (205), cultural practice (204), educational program (202), sports event (199), event / sporting event (198), natural disaster (182), event / award (161), action (156), religious practice (155), cultural event (150), medical treatment (148), cultural reference / event (141), event / football competition (136), program / government program (134), event / political event (132), sporting event (131), economic activity (130), cultural reference / festival (127), event / election (123), natural phenomenon (120), event / ritual/sacrifice (120), election (118), biological process (111), academic program (108), event / organization (107), religious event (104), infrastructure project (104), เหตุการณ์ (103)

## 8. Human-Made Artifact / Technology / Product

product (13714), technology (6510), website (1692), social media platform (1366), vehicle (553), weapon (541), operating system (526), product / food (463), product / car model (366), product / vehicle model (326), product / smartphone model (286), musical instrument (278), platform / social media platform (266), technology / social media platform (257), product / agricultural product (247), drug (250), product / automobile model (222), object (219), software (210), product / food product (183), media / website (176), product / drug (173), application (171), food product (170), vehicle model (166), dish (159), product / mobile phone model (152), programming language (149), media / social media platform (144), beverage (142), product / beverage (140), product / product model (140), product / motorcycle model (136), technology / product (135), technology / operating system (133), artifact (126), product / vehicle (126), product / software (126), media / news website (121), clothing (121), platform (118), product / application (114), transportation (113), vaccine (111), website section (110), product / vaccine (108), car model (103), clothing item (101)

## 9. Organic / Bodily / Natural-Material Entity

disease (2975), medical condition (1908), scientific concept / disease (1333), material (1224), animal (1214), medical condition / disease (1060), food (949), body part (836), chemical compound (503), event / disease (384), biological entity (326), plant (320), anatomical structure (311), chemical substance (302), fruit (278), substance (275), ingredient (245), agricultural product (206), resource (207), virus (205), symptom (204), chemical element (202), scientific concept / medical condition (172), deity / ritual drink (173), animal species (160), organ (157), species (155), species / animal species (153), cultural reference / food (143), scientific concept / chemical substance (116), nutrient (114), hormone (113), plant species (111), scientific concept / virus (110), food ingredient (108), health condition (100)

## 10. Classifier / Category / Role / Status / Type

title (3001), profession (2037), occupation (1634), job title (1457), political position (1405), industry (1370), sport (1279), position (1127), award (1016), government position (734), role (587), religious title (496), product category (440), music genre (349), academic degree (340), vehicle type (322), art form (306), title/position (286), economic sector (285), educational level (246), business type (244), position/title (223), product / product category (223), person / political position (198), organization type (196), genre (183), product type (181), cultural reference / music genre (175), political office (169), military rank (168), document type (155), media type (151), person / occupation (145), title/role (142), person / profession (129), literary genre (123), degree (123), media format (122), medical specialty (120), title / political position (120), building type (113), cultural reference / art form (111), family relation (111), category (111), person / job title (110), title / job title (108), military personnel (105), game genre (108), education level (106), profession / occupation (104), political title (101), food category (100)

## 11. Creative Work

media (1506), legal document (979), document (839), work of art (837), video game (724), film / movie (622), literary work (611), religious text (598), cultural reference / religious text (578), media / newspaper (410), film (378), game (375), publication (308), cultural reference / song (298), cultural reference / movie (297), song (297), tv show (288), cultural reference / tv show (275), cultural reference / work of art (265), cultural reference / book title (215), film / film title (210), cultural reference / literary work (205), media / tv show (193), book title (193), cultural reference / song title (191), cultural reference / tv series (185), work of art / book title (175), tv series (168), work of art / literary work (164), newspaper (163), product / video game (156), movie (146), film title (145), media / magazine (144), work of art / movie (134), media / publication (133), book (129), game / video game (120), cultural artifact (119), cultural reference / film (106), work of literature (102), song title (100)

## 12. Money / Financial Asset / Economic Instrument

currency (1647), cryptocurrency (824), financial instrument (795), financial product (509), commodity (175), currency pair (119)

## 13. Group Identity / Non-Institutional Human Collective

nationality (2652), ethnic group (1614), group (1180), demographic group (1016), social group (623), group of people (547), religious group (405), demographic (223), people (208), cultural reference / ethnic group (200), person / nationality (178), social class (153), community (148), demonym (139), person / ethnic group (139), location / nationality (121), location / ethnic group (118), person / demographic group (105), nationality/ethnic group (102), cultural reference / religious group (102)
"""


ITEM_RE = re.compile(r"^(?P<tag>.+?)\s*\((?P<count>\d+)\)$")


def parse_raw() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current = ""
    for raw_line in RAW.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = re.sub(r"^##\s+\d+\.\s+", "", line).strip()
            continue
        for piece in line.split(", "):
            match = ITEM_RE.match(piece.strip())
            if not match:
                raise ValueError(f"Could not parse item: {piece!r}")
            rows.append(
                {
                    "bucket": current,
                    "tag": match.group("tag"),
                    "count": int(match.group("count")),
                    "tokens": base.text_tokens(match.group("tag")),
                }
            )
    return rows


def fine_vector_text(tag: str) -> str:
    if "/" not in tag:
        return tag
    return tag.split("/", 1)[1].strip()


def vectorize_rows(rows: list[dict[str, object]]) -> None:
    needed = set()
    for row in rows:
        for token in row["tokens"]:
            needed.update(base.vector_variants(token))
    vectors = base.ft.load_fasttext(needed)
    for row in rows:
        vec, matched = base.label_vector(row, vectors)
        row["vector"] = vec
        row["matched_words"] = "; ".join(matched)


def build_centroids(rows: list[dict[str, object]]) -> dict[str, np.ndarray]:
    centroids = {}
    by_bucket: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_bucket[row["bucket"]].append(row)
    for bucket, bucket_rows in by_bucket.items():
        vecs = []
        weights = []
        for row in bucket_rows:
            if row["vector"] is None:
                continue
            vecs.append(row["vector"])
            weights.append(float(row["count"]))
        centroid = np.average(np.stack(vecs).astype(np.float32), axis=0, weights=np.array(weights))
        norm = np.linalg.norm(centroid)
        if not norm:
            raise RuntimeError(bucket)
        centroids[bucket] = (centroid / norm).astype(np.float32)
    return centroids


def score_rows(rows: list[dict[str, object]], centroids: dict[str, np.ndarray]) -> None:
    buckets = list(centroids)
    matrix = np.stack([centroids[bucket] for bucket in buckets]).astype(np.float32)
    for row in rows:
        vec = row["vector"]
        if vec is None:
            row["own_similarity"] = ""
            row["nearest_bucket"] = "NO_VECTOR"
            row["nearest_similarity"] = ""
            row["runner_up_bucket"] = ""
            row["runner_up_similarity"] = ""
            row["margin_to_nearest_other"] = ""
            continue
        sims = matrix @ vec
        order = np.argsort(-sims)
        nearest = buckets[int(order[0])]
        runner = buckets[int(order[1])]
        own = float(np.dot(centroids[row["bucket"]], vec))
        nearest_sim = float(sims[int(order[0])])
        nearest_other_sim = next(float(sims[int(idx)]) for idx in order if buckets[int(idx)] != row["bucket"])
        row["own_similarity"] = own
        row["nearest_bucket"] = nearest
        row["nearest_similarity"] = nearest_sim
        row["runner_up_bucket"] = runner
        row["runner_up_similarity"] = float(sims[int(order[1])])
        row["margin_to_nearest_other"] = own - nearest_other_sim


def pct(value: object) -> str:
    if value == "":
        return ""
    return f"{float(value) * 100:.2f}"


def write_outputs(rows: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "tag",
                "count",
                "own_similarity_pct",
                "nearest_bucket",
                "nearest_similarity_pct",
                "margin_to_nearest_other_pct",
                "matched_words",
            ]
        )
        for row in sorted(rows, key=lambda r: (r["bucket"], float(r["own_similarity"] or -1), -int(r["count"]))):
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["count"],
                    pct(row["own_similarity"]),
                    row["nearest_bucket"],
                    pct(row["nearest_similarity"]),
                    pct(row["margin_to_nearest_other"]),
                    row["matched_words"],
                ]
            )

    by_bucket: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_bucket[row["bucket"]].append(row)
    collisions = [
        row for row in rows if row["vector"] is not None and row["nearest_bucket"] != row["bucket"]
    ]
    collisions.sort(key=lambda row: (float(row["margin_to_nearest_other"]), -int(row["count"])))

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# 13-Bucket fastText Outlier Check\n\n")
        handle.write(
            "Each tag is embedded from its full label text. Bucket centroids are frequency-weighted by the counts "
            "in the prompt. Outliers are tags with low similarity to their assigned bucket centroid or whose nearest "
            "centroid is another bucket.\n\n"
        )
        handle.write(f"- Parsed rows: {len(rows)}\n")
        handle.write(f"- Vectorized rows: {sum(1 for row in rows if row['vector'] is not None)}\n")
        handle.write(f"- No-vector rows: {sum(1 for row in rows if row['vector'] is None)}\n")
        handle.write(f"- Cross-bucket nearest-centroid collisions: {len(collisions)}\n\n")

        handle.write("## Strongest Cross-Bucket Outliers\n\n")
        for row in collisions[:60]:
            handle.write(
                f"- `{row['tag']}` ({row['count']}) in **{row['bucket']}** -> nearest "
                f"**{row['nearest_bucket']}**; own {pct(row['own_similarity'])}%, "
                f"nearest {pct(row['nearest_similarity'])}%\n"
            )
        handle.write("\n")

        handle.write("## Lowest Own-Bucket Similarity By Bucket\n\n")
        for bucket in by_bucket:
            bucket_rows = [row for row in by_bucket[bucket] if row["vector"] is not None]
            bucket_rows.sort(key=lambda row: (float(row["own_similarity"]), -int(row["count"])))
            handle.write(f"### {bucket}\n\n")
            for row in bucket_rows[:12]:
                nearest = ""
                if row["nearest_bucket"] != row["bucket"]:
                    nearest = f" -> nearest **{row['nearest_bucket']}** {pct(row['nearest_similarity'])}%"
                handle.write(
                    f"- `{row['tag']}` ({row['count']}): own {pct(row['own_similarity'])}%{nearest}\n"
                )
            handle.write("\n")

    print(f"rows\t{len(rows)}")
    print(f"vectorized\t{sum(1 for row in rows if row['vector'] is not None)}")
    print(f"cross_bucket_collisions\t{len(collisions)}")
    print(f"tsv\t{OUT_TSV}")
    print(f"report\t{OUT_MD}")


def main() -> None:
    rows = parse_raw()
    vectorize_rows(rows)
    centroids = build_centroids(rows)
    score_rows(rows, centroids)
    write_outputs(rows)


if __name__ == "__main__":
    main()
