from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "collapse13_seed_coherence_expansion"

SUMMARY_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_tag_map.tsv"
REPORT_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_report.md"
REJECTED_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_rejected.tsv"
ACCEPTED_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_accepted_new_tags.tsv"
FINAL_TAGSETS_OUT = OUT_DIR / "collapse13_seed_coherence_expansion_final_tagsets.md"

EPSILON = 1e-9
TOKEN_RE = re.compile(r"^(.+?)\s*\(\d+\)\s*$")


RAW_SEEDS = {
    "PERSON": """
person (150581); deity (3544); religious figure (1122); character (1052); persons (576); god (422); mythological figure (396); historical figure (370); pessoa (233); politician (227); شخص (210); บุคคล (200); saint (192); fictional character (165); actor (152); political figure (148); football player (144); sage (140); אדם (124); hindu god of friendship (111); hindu god of water (111); mythological creature (110); mythological entity (101)
""",
    "GROUP": """
nationality (2926); group (1835); ethnic group (1777); demographic group (1100); social group (730); group of people (583); religious group (439); people (417); demographic (343); dynasty (252); community (203); social class (196); family (167); demonym (166); age group (123); family name (119); cultural group (115); ethnicity (111); military personnel (106); gender (100)
""",
    "TITLE_ROLE": """
title (4846); profession (2330); position (1850); occupation (1786); job title (1496); political position (1444); role (913); government position (794); religious title (566); military rank (222); political office (185); pope (183); religious leader (160); government official (157); political title (121); family relation (119); political leader (119); police rank (118); social role (107); academic degree (429); educational level (294); degree (164); education level (140)
""",
    "ORGANIZATION": """
organization (98872); media (5386); brand (4549); political party (2657); government organization (2264); political organization (2021); educational institution (1456); sports team (1388); news agency (1063); government agency (994); company (971); government (882); sports league (632); media outlet (573); media organization (568); military organization (537); sports club (521); news organization (447); government ministry (420); university (416); religious organization (409); international organization (382); law enforcement agency (368); court (359); government body (316); legislative body (306); institution (301); military unit (301); financial institution (296); football club (296); political group (296); business type (292); sports organization (257); government department (231); organization type (215); governmental organization (212); team (207); religious institution (200); newspaper (186); องค์กร (180); organização (173); business (163); organization abbreviation (163); political body (161); ארגון (161); political movement (154); terrorist organization (151); سازمان (148); government institution (142); religious order (139); restaurant (136); department (132); academic department (130); school (127); music group (123); bank (122); political alliance (121); establishment (119); social movement (117); news outlet (111); police department (109); legal institution (107); stock exchange (105); magazine (102); news website (101); musical group (100)
""",
    "PLACE": """
location (130242); country (12654); city (5446); region (1886); political entity (1042); infrastructure (984); state (936); continent (731); building (703); province (700); facility (581); district (522); river (475); geographic region (473); administrative region (435); geopolitical entity (392); celestial body (386); administrative division (377); village (360); geographical feature (323); universe (319); geographical region (289); place (289); geopolitical region (282); hospital (276); street (246); diocese (234); address (195); planet (194); police station (187); island (185); geographical location (182); localização (182); body of water (181); religious building (180); road (179); hotel (174); airport (168); mountain (159); مکان (159); natural feature (157); สถานที่ (153); neighborhood (145); astronomical object (143); government building (136); temple (129); world (129); geographic location (127); کشور (120); healthcare facility (117); municipality (117); building type (116); mountain range (111); religious site (109); subdistrict (106); historical region (104)
""",
    "DATE_TIME": """
date (36953); time period (13388); year (3723); time (3376); duration (2944); day of the week (2433); month (1612); time duration (619); historical period (430); date range (270); day of week (262); season (242); temporal expression (185); day (146); time of day (108)
""",
    "VALUE": """
quantity (27990); measurement (6194); currency (3458); percentage (2533); age (2466); statistic (2308); monetary value (1402); score (814); number (787); color (691); price (537); currency amount (445); distance (401); economic indicator (281); statistics (276); quantities (256); ranking (208); ordinal number (206); financial index (202); money (197); financial metric (190); page number (169); unit of measurement (164); tax (163); age range (136); technical indicator (134); rating (126); statistical measurement (123); amount (120); currency pair (120); statistical measure (104)
""",
    "EVENT": """
event (27255); award (1164); historical event (582); cultural event (368); festival (336); sports event (289); political event (259); holiday (229); natural disaster (209); sporting event (205); natural phenomenon (147); exam (135); religious event (122); legal case (121); election (118); เหตุการณ์ (108); health crisis (104); weather event (100)
""",
    "MANMADE_OBJECT": """
product (26201); technology (11976); work of art (2407); website (1973); legal document (1548); film (1443); social media platform (1395); document (1256); food (1113); service (984); financial instrument (907); cryptocurrency (883); literary work (845); game (841); video game (777); financial product (727); platform (697); religious text (678); operating system (668); vehicle (657); legislation (602); weapon (600); publication (546); software (484); product category (477); application (375); law (373); object (368); tv show (365); policy (364); song (335); vehicle type (331); food product (315); regulation (289); musical instrument (287); entity (282); book (253); tv series (249); film title (228); product type (223); transportation (210); محصول (206); dish (198); book title (197); vaccine (184); document type (177); legal code (177); medication (175); vehicle model (172); text (165); beverage (160); television show (159); movie (157); artifact (149); social media (149); food item (147); certification (146); clothing (143); เทคโนโลยี (136); economic policy (135); culinary dish (129); work of literature (126); cultural artifact (124); agreement (122); medical device (121); car model (119); standard (117); military technology (115); television series (115); legal provision (114); cultural work (113); website section (113); song title (109); clothing item (101); product model (100); food category (100)
""",
    "BIO_CHEM_MEDICAL": """
medical condition (3194); disease (3103); material (1479); animal (1405); body part (883); chemical compound (647); species (554); plant (535); substance (428); biological entity (405); ingredient (405); anatomical structure (384); chemical substance (342); virus (331); agricultural product (297); drug (286); fruit (284); commodity (270); nutrient (253); chemical element (252); health condition (236); resource (232); symptom (226); organ (179); plant species (176); animal species (163); organism (157); food ingredient (129); hormone (128); mineral (116); biological structure (114); natural resource (109); chemical (104); element (104); energy source (103)
""",
    "CONCEPT": """
cultural reference (33780); scientific concept (15531); concept (15027); legal concept (2033); economic concept (1873); cultural concept (1789); field of study (1617); industry (1519); financial concept (1444); philosophical concept (1427); political concept (882); religion (693); religious concept (615); social issue (565); financial term (554); financial market (509); social concept (480); music genre (363); academic discipline (359); legal term (353); art form (345); political ideology (343); economic sector (305); abstract concept (294); scientific field (261); medical concept (256); business concept (247); genre (247); field (246); market (237); health concept (218); feature (215); biological concept (201); educational concept (176); political system (174); general concept (161); technological concept (159); media type (156); literary genre (154); sector (152); psychological concept (151); topic (141); medical term (139); media format (138); environmental issue (135); culture (129); game genre (125); medical specialty (125); framework (125); philosophical school (121); economic term (112); symbol (108); film genre (104); legal framework (103); system (103); business model (102); category (208); direction (109); biblical reference (108)
""",
    "LANGUAGE": """
language (3246); nickname (687); phone number (284); pronoun (256); hashtag (216); url (211); acronym (182); email address (175); contact number (172); programming language (172); latin word (154); contact information (153); word (149); identifier (132); abbreviation (125); social media handle (124)
""",
    "ACTIVITY_PROCESS": """
sport (1421); program (1169); activity (944); medical procedure (692); project (600); process (420); crime (391); government program (254); cultural practice (247); educational program (247); action (200); academic program (193); religious practice (178); medical treatment (172); skill (133); economic activity (132); ritual (125); technique (120); biological process (119); infrastructure project (118)
""",
}


@dataclass
class BucketState:
    label: str
    seed_indices: list[int]
    accepted_indices: list[int]
    seed_no_vector: list[int]
    base_weighted: float
    base_unweighted: float
    center: np.ndarray
    count: int

    @property
    def indices(self) -> list[int]:
        return self.seed_indices + self.accepted_indices


def normalize_label(label: str) -> str:
    return " ".join(label.strip().casefold().split())


def parse_seed_labels() -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for bucket, raw in RAW_SEEDS.items():
        labels = []
        for piece in raw.replace("\n", " ").split(";"):
            value = piece.strip()
            if not value:
                continue
            match = TOKEN_RE.match(value)
            if match:
                value = match.group(1).strip()
            key = normalize_label(value)
            if key in seen:
                raise ValueError(f"Duplicate seed tag {value!r} in {bucket}; first seen in {seen[key]}")
            seen[key] = bucket
            labels.append(value)
        parsed[bucket] = labels
    return parsed


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def weighted_center(indices: list[int], rows: list[dict[str, object]]) -> np.ndarray:
    vectors = np.stack([rows[idx]["vector"] for idx in indices]).astype(np.float32)
    weights = np.array([float(rows[idx]["count"]) for idx in indices], dtype=np.float64)
    return normalize(np.average(vectors, axis=0, weights=weights))


def coherence(indices: list[int], rows: list[dict[str, object]], center: np.ndarray) -> tuple[float, float]:
    if not indices:
        return 0.0, 0.0
    sims = np.array([float(np.dot(rows[idx]["vector"], center)) for idx in indices], dtype=np.float64)
    weights = np.array([float(rows[idx]["count"]) for idx in indices], dtype=np.float64)
    return float(np.average(sims, weights=weights)), float(np.mean(sims))


def proposed_coherence(
    current: BucketState,
    candidate_idx: int,
    rows: list[dict[str, object]],
) -> tuple[np.ndarray, float, float]:
    indices = current.indices + [candidate_idx]
    center = weighted_center(indices, rows)
    weighted, unweighted = coherence(indices, rows, center)
    return center, weighted, unweighted


def initialize_buckets(
    seed_labels: dict[str, list[str]],
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
) -> tuple[dict[str, BucketState], set[int], set[int], list[str]]:
    vector_by_label: dict[str, list[int]] = {}
    no_vector_by_label: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        vector_by_label.setdefault(normalize_label(str(row["coarse_tag"])), []).append(idx)
    for idx, row in enumerate(unvectorized):
        no_vector_by_label.setdefault(normalize_label(str(row["coarse_tag"])), []).append(idx)
    seeded_vector_indices: set[int] = set()
    seeded_no_vector_indices: set[int] = set()
    missing = []
    buckets: dict[str, BucketState] = {}

    for bucket, labels in seed_labels.items():
        vector_indices = []
        no_vector_indices = []
        for label in labels:
            key = normalize_label(label)
            if key in vector_by_label:
                for idx in vector_by_label[key]:
                    if idx in seeded_vector_indices:
                        continue
                    vector_indices.append(idx)
                    seeded_vector_indices.add(idx)
            elif key in no_vector_by_label:
                for idx in no_vector_by_label[key]:
                    if idx in seeded_no_vector_indices:
                        continue
                    no_vector_indices.append(idx)
                    seeded_no_vector_indices.add(idx)
            else:
                missing.append(f"{bucket}\t{label}")
        if not vector_indices:
            raise ValueError(f"No vectorized seed tags for {bucket}")
        center = weighted_center(vector_indices, rows)
        base_weighted, base_unweighted = coherence(vector_indices, rows, center)
        buckets[bucket] = BucketState(
            label=bucket,
            seed_indices=vector_indices,
            accepted_indices=[],
            seed_no_vector=no_vector_indices,
            base_weighted=base_weighted,
            base_unweighted=base_unweighted,
            center=center,
            count=sum(int(rows[idx]["count"]) for idx in vector_indices)
            + sum(int(unvectorized[idx]["count"]) for idx in no_vector_indices),
        )
    return buckets, seeded_vector_indices, seeded_no_vector_indices, missing


def expand_buckets(
    buckets: dict[str, BucketState],
    rows: list[dict[str, object]],
    seeded_vector_indices: set[int],
) -> list[dict[str, object]]:
    unassigned = set(range(len(rows))) - seeded_vector_indices
    pass_log = []
    pass_num = 0

    while True:
        pass_num += 1
        labels = list(buckets)
        centers = np.stack([buckets[label].center for label in labels]).astype(np.float32)
        candidates = []
        for idx in unassigned:
            sims = centers @ rows[idx]["vector"]
            order = np.argsort(-sims)
            best_pos = int(order[0])
            second_pos = int(order[1]) if len(order) > 1 else best_pos
            candidates.append(
                (
                    float(sims[best_pos]),
                    int(rows[idx]["count"]),
                    idx,
                    labels[best_pos],
                    labels[second_pos],
                    float(sims[second_pos]),
                )
            )
        candidates.sort(key=lambda item: (-item[0], -item[1], str(rows[item[2]]["coarse_tag"])))

        accepted_this_pass = 0
        blocked_this_pass = 0
        for best_sim, _count, idx, label, second_label, second_sim in candidates:
            if idx not in unassigned:
                continue
            bucket = buckets[label]
            center, next_weighted, next_unweighted = proposed_coherence(bucket, idx, rows)
            if (
                next_weighted + EPSILON >= bucket.base_weighted
                and next_unweighted + EPSILON >= bucket.base_unweighted
            ):
                bucket.accepted_indices.append(idx)
                bucket.center = center
                bucket.count += int(rows[idx]["count"])
                unassigned.remove(idx)
                accepted_this_pass += 1
            else:
                blocked_this_pass += 1
        pass_log.append(
            {
                "pass": pass_num,
                "accepted": accepted_this_pass,
                "blocked": blocked_this_pass,
                "remaining": len(unassigned),
            }
        )
        if accepted_this_pass == 0:
            return pass_log


def bucket_final_metrics(bucket: BucketState, rows: list[dict[str, object]]) -> tuple[float, float]:
    return coherence(bucket.indices, rows, bucket.center)


def best_final_label(row: dict[str, object], buckets: dict[str, BucketState]) -> tuple[str, float, str, float]:
    labels = list(buckets)
    centers = np.stack([buckets[label].center for label in labels]).astype(np.float32)
    sims = centers @ row["vector"]
    order = np.argsort(-sims)
    best_pos = int(order[0])
    second_pos = int(order[1]) if len(order) > 1 else best_pos
    return labels[best_pos], float(sims[best_pos]), labels[second_pos], float(sims[second_pos])


def write_outputs(
    buckets: dict[str, BucketState],
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    seeded_vector_indices: set[int],
    seeded_no_vector_indices: set[int],
    missing: list[str],
    pass_log: list[dict[str, object]],
    total_count: int,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    accepted_by_idx = {}
    seed_by_idx = {}
    no_vector_seed_by_idx = {}
    for label, bucket in buckets.items():
        for idx in bucket.seed_indices:
            seed_by_idx[idx] = label
        for idx in bucket.accepted_indices:
            accepted_by_idx[idx] = label
        for idx in bucket.seed_no_vector:
            no_vector_seed_by_idx[idx] = label

    sorted_buckets = sorted(buckets.values(), key=lambda bucket: (-bucket.count, bucket.label))
    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "label",
                "seed_vectorized_tags",
                "seed_no_vector_tags",
                "seed_frequency_mass",
                "seed_pct_total",
                "base_weighted_coherence_pct",
                "base_unweighted_coherence_pct",
                "accepted_new_tags",
                "accepted_new_frequency_mass",
                "accepted_new_pct_total",
                "final_vectorized_tags",
                "final_total_tags_including_no_vector_seeds",
                "final_frequency_mass",
                "final_pct_total",
                "final_weighted_coherence_pct",
                "final_unweighted_coherence_pct",
            ]
        )
        for bucket in sorted_buckets:
            final_weighted, final_unweighted = bucket_final_metrics(bucket, rows)
            seed_mass = sum(int(rows[idx]["count"]) for idx in bucket.seed_indices) + sum(
                int(unvectorized[idx]["count"]) for idx in bucket.seed_no_vector
            )
            accepted_mass = sum(int(rows[idx]["count"]) for idx in bucket.accepted_indices)
            writer.writerow(
                [
                    bucket.label,
                    len(bucket.seed_indices),
                    len(bucket.seed_no_vector),
                    seed_mass,
                    f"{seed_mass / total_count * 100.0:.6f}",
                    f"{bucket.base_weighted * 100.0:.2f}",
                    f"{bucket.base_unweighted * 100.0:.2f}",
                    len(bucket.accepted_indices),
                    accepted_mass,
                    f"{accepted_mass / total_count * 100.0:.6f}",
                    len(bucket.indices),
                    len(bucket.indices) + len(bucket.seed_no_vector),
                    bucket.count,
                    f"{bucket.count / total_count * 100.0:.6f}",
                    f"{final_weighted * 100.0:.2f}",
                    f"{final_unweighted * 100.0:.2f}",
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "source_kind",
                "source_labels",
                "count",
                "pct_total",
                "label",
                "status",
                "similarity_to_label_centroid_pct",
                "nearest_other_label",
                "nearest_other_similarity_pct",
                "margin_pct",
            ]
        )
        for idx, row in sorted(
            enumerate(rows),
            key=lambda item: (-int(item[1]["count"]), str(item[1]["coarse_tag"])),
        ):
            if idx in seed_by_idx:
                label = seed_by_idx[idx]
                status = "seed"
            elif idx in accepted_by_idx:
                label = accepted_by_idx[idx]
                status = "accepted"
            else:
                label, _sim, _second_label, _second_sim = best_final_label(row, buckets)
                status = "rejected"
            sims = {bucket.label: float(np.dot(row["vector"], bucket.center)) for bucket in buckets.values()}
            ranked = sorted(sims.items(), key=lambda item: -item[1])
            current_sim = sims[label]
            nearest_other = next((item for item in ranked if item[0] != label), ranked[0])
            writer.writerow(
                    [
                        row["coarse_tag"],
                        row.get("source_kind", "coarse"),
                        row.get("source_labels", row["coarse_tag"]),
                        row["count"],
                        f"{row['percent']:.6f}",
                        label,
                    status,
                    f"{current_sim * 100.0:.2f}",
                    nearest_other[0],
                    f"{nearest_other[1] * 100.0:.2f}",
                    f"{(current_sim - nearest_other[1]) * 100.0:.2f}",
                ]
            )
        for idx, row in sorted(
            enumerate(unvectorized),
            key=lambda item: (-int(item[1]["count"]), str(item[1]["coarse_tag"])),
        ):
            if idx in no_vector_seed_by_idx:
                label = no_vector_seed_by_idx[idx]
                status = "seed_no_vector"
            else:
                label = ""
                status = "no_vector"
            writer.writerow(
                [
                    row["coarse_tag"],
                    row.get("source_kind", "coarse"),
                    row.get("source_labels", row["coarse_tag"]),
                    row["count"],
                    f"{row['percent']:.6f}",
                    label,
                    status,
                    "",
                    "",
                    "",
                    "",
                ]
            )

    with REJECTED_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "source_kind",
                "source_labels",
                "count",
                "pct_total",
                "best_label",
                "best_similarity_pct",
                "second_label",
                "second_similarity_pct",
                "margin_pct",
            ]
        )
        for idx, row in sorted(
            enumerate(rows),
            key=lambda item: (-int(item[1]["count"]), str(item[1]["coarse_tag"])),
        ):
            if idx in seed_by_idx or idx in accepted_by_idx:
                continue
            best, best_sim, second, second_sim = best_final_label(row, buckets)
            writer.writerow(
                [
                    row["coarse_tag"],
                    row.get("source_kind", "coarse"),
                    row.get("source_labels", row["coarse_tag"]),
                    row["count"],
                    f"{row['percent']:.6f}",
                    best,
                    f"{best_sim * 100.0:.2f}",
                    second,
                    f"{second_sim * 100.0:.2f}",
                    f"{(best_sim - second_sim) * 100.0:.2f}",
                ]
            )

    with ACCEPTED_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "label",
                "coarse_tag",
                "source_kind",
                "source_labels",
                "count",
                "pct_total",
                "similarity_to_label_centroid_pct",
            ]
        )
        for bucket in sorted_buckets:
            for idx in sorted(
                bucket.accepted_indices,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
            ):
                writer.writerow(
                    [
                        bucket.label,
                        rows[idx]["coarse_tag"],
                        rows[idx].get("source_kind", "coarse"),
                        rows[idx].get("source_labels", rows[idx]["coarse_tag"]),
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        f"{float(np.dot(rows[idx]['vector'], bucket.center)) * 100.0:.2f}",
                    ]
                )

    with FINAL_TAGSETS_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Collapse-13 Final Coherence-Gated Tagsets\n\n")
        handle.write(
            "`cultural reference` is only used as a standalone parent row. "
            "`cultural reference / child` rows are listed by masked child text, with the original source label shown after it.\n\n"
        )
        for bucket in sorted_buckets:
            final_weighted, final_unweighted = bucket_final_metrics(bucket, rows)
            handle.write(f"## {bucket.label}\n\n")
            handle.write(
                f"{len(bucket.indices) + len(bucket.seed_no_vector)} tags; {bucket.count} mentions; "
                f"{bucket.count / total_count * 100.0:.6f}% total; "
                f"weighted coherence {final_weighted * 100.0:.2f}%; "
                f"unweighted coherence {final_unweighted * 100.0:.2f}%.\n\n"
            )
            for idx in sorted(
                bucket.indices,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
            ):
                status = "seed" if idx in seed_by_idx else "new"
                source = rows[idx].get("source_labels", rows[idx]["coarse_tag"])
                if source == rows[idx]["coarse_tag"]:
                    handle.write(f"- {rows[idx]['coarse_tag']} ({rows[idx]['count']}) [{status}]\n")
                else:
                    handle.write(
                        f"- {rows[idx]['coarse_tag']} ({rows[idx]['count']}) [{status}; source: {source}]\n"
                    )
            for idx in sorted(
                bucket.seed_no_vector,
                key=lambda row_idx: (-int(unvectorized[row_idx]["count"]), str(unvectorized[row_idx]["coarse_tag"])),
            ):
                handle.write(f"- {unvectorized[idx]['coarse_tag']} ({unvectorized[idx]['count']}) [seed_no_vector]\n")
            handle.write("\n")

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Collapse-13 Seed Taxonomy Coherence Expansion\n\n")
        handle.write(
            "Seed buckets are fixed to the 13 labels supplied in the prompt. "
            "All vectorized coarse tags outside the seed set are considered as strays. "
            "The `cultural reference` parent is split before vectorization: standalone parent rows remain as "
            "`cultural reference`, while `cultural reference / child` rows are matched using child text only. "
            "A stray is attached to its nearest current seed-bucket centroid only if adding it keeps both "
            "the bucket's frequency-weighted and unweighted member-to-centroid coherence at or above that "
            "bucket's starting seed coherence. No per-tag rules are used.\n\n"
        )
        handle.write("## Run Summary\n\n")
        handle.write(f"- Total coarse frequency mass: {total_count}\n")
        handle.write(f"- Vectorized tags: {len(rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Seed vectorized tags: {len(seeded_vector_indices)}\n")
        handle.write(f"- Seed no-vector tags: {len(seeded_no_vector_indices)}\n")
        handle.write(f"- Missing seed labels: {len(missing)}\n")
        handle.write(f"- Accepted stray tags: {sum(len(bucket.accepted_indices) for bucket in buckets.values())}\n")
        handle.write(
            f"- Accepted stray frequency mass: {sum(sum(int(rows[idx]['count']) for idx in bucket.accepted_indices) for bucket in buckets.values())}\n"
        )
        handle.write("\n")
        if missing:
            handle.write("## Missing Seed Labels\n\n")
            for item in missing:
                bucket, label = item.split("\t", 1)
                handle.write(f"- `{label}` in `{bucket}`\n")
            handle.write("\n")
        handle.write("## Pass Log\n\n")
        for item in pass_log:
            handle.write(
                f"- pass {item['pass']}: accepted {item['accepted']}, blocked {item['blocked']}, remaining {item['remaining']}\n"
            )
        handle.write("\n")

        handle.write("## Buckets\n\n")
        for bucket in sorted_buckets:
            final_weighted, final_unweighted = bucket_final_metrics(bucket, rows)
            seed_mass = sum(int(rows[idx]["count"]) for idx in bucket.seed_indices) + sum(
                int(unvectorized[idx]["count"]) for idx in bucket.seed_no_vector
            )
            accepted_mass = sum(int(rows[idx]["count"]) for idx in bucket.accepted_indices)
            handle.write(f"### {bucket.label}\n\n")
            handle.write(
                f"Seed: {len(bucket.seed_indices) + len(bucket.seed_no_vector)} tags, "
                f"{seed_mass} mentions ({seed_mass / total_count * 100.0:.4f}%).\n\n"
            )
            handle.write(
                f"Initial coherence: weighted {bucket.base_weighted * 100.0:.2f}%, "
                f"unweighted {bucket.base_unweighted * 100.0:.2f}%.\n\n"
            )
            handle.write(
                f"Accepted: {len(bucket.accepted_indices)} tags, {accepted_mass} mentions "
                f"({accepted_mass / total_count * 100.0:.4f}%).\n\n"
            )
            handle.write(
                f"Final: {len(bucket.indices) + len(bucket.seed_no_vector)} tags, {bucket.count} mentions "
                f"({bucket.count / total_count * 100.0:.4f}%), "
                f"weighted coherence {final_weighted * 100.0:.2f}%, "
                f"unweighted coherence {final_unweighted * 100.0:.2f}%.\n\n"
            )
            if bucket.accepted_indices:
                handle.write("Top accepted tags:\n\n")
                for idx in sorted(
                    bucket.accepted_indices,
                    key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
                )[:40]:
                    sim = float(np.dot(rows[idx]["vector"], bucket.center))
                    handle.write(f"- `{rows[idx]['coarse_tag']}` ({rows[idx]['count']}), sim {sim * 100.0:.2f}%\n")
                handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count, standalone_cultural_count = split_cultural.load_rows_no_cultural_parent()
    rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    unvectorized.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    seed_labels = parse_seed_labels()
    buckets, seeded_vector_indices, seeded_no_vector_indices, missing = initialize_buckets(seed_labels, rows, unvectorized)
    pass_log = expand_buckets(buckets, rows, seeded_vector_indices)
    write_outputs(
        buckets,
        rows,
        unvectorized,
        seeded_vector_indices,
        seeded_no_vector_indices,
        missing,
        pass_log,
        total_count,
    )

    accepted_tags = sum(len(bucket.accepted_indices) for bucket in buckets.values())
    accepted_mass = sum(sum(int(rows[idx]["count"]) for idx in bucket.accepted_indices) for bucket in buckets.values())
    final_mass = sum(bucket.count for bucket in buckets.values())
    print(f"vectorized_tags={len(rows)}")
    print(f"unvectorized_tags={len(unvectorized)}")
    print(f"standalone_cultural_reference_mentions={standalone_cultural_count}")
    print(f"seed_vectorized_tags={len(seeded_vector_indices)}")
    print(f"seed_no_vector_tags={len(seeded_no_vector_indices)}")
    print(f"missing_seed_labels={len(missing)}")
    print(f"accepted_stray_tags={accepted_tags}")
    print(f"accepted_stray_mass={accepted_mass}")
    print(f"accepted_stray_pct={accepted_mass / total_count * 100.0:.6f}")
    print(f"final_assigned_mass={final_mass}")
    print(f"final_assigned_pct={final_mass / total_count * 100.0:.6f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"accepted={ACCEPTED_OUT}")
    print(f"final_tagsets={FINAL_TAGSETS_OUT}")
    print(f"rejected={REJECTED_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
