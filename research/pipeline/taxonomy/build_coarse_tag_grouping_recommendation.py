from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import cluster_all_finerweb_labels_fasttext as ft


BASE_DIR = Path(__file__).resolve().parent
IN_MAP = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples_under25_map.tsv"
IN_COUNTS = BASE_DIR / "finerweb_label_inventory_coarse.tsv"
IN_PAIRS = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_tag_pairwise_fasttext_similarity.tsv"
OUT_MD = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_tag_grouping_recommendation.md"
OUT_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_tag_grouping_recommendation.tsv"
OUT_TAG_MAP = BASE_DIR / "derived_fasttext_categories" / "finerweb_recommended_tag_to_parent.tsv"


PARENT_DESCRIPTIONS = {
    "PERSON_OR_BEING": "humans, person-like beings, deities, fictional/mythic figures",
    "ROLE_TITLE_STATUS": "titles, ranks, offices, jobs, kinship/status roles",
    "GROUP_POPULATION": "human populations, identities, communities, families, demographics",
    "ORGANIZATION": "institutions, companies, agencies, parties, teams, media orgs, courts, schools",
    "GEOPOLITICAL_PLACE": "countries, cities, regions, administrative divisions, territories",
    "NATURAL_PLACE": "natural and astronomical places/features",
    "FACILITY_INFRASTRUCTURE": "built places, facilities, roads, buildings, venues, sites",
    "TIME_DATE": "dates, times, durations, periods, seasons",
    "EVENT_HAPPENING": "events, disasters, elections, competitions, projects, crises",
    "QUANTITY_MEASURE": "numbers, scores, measures, statistics, ratings, quantities",
    "MONEY_FINANCE": "money, prices, currencies, financial markets/assets/terms",
    "IDENTIFIER_CONTACT": "URLs, handles, contact info, codes, acronyms, identifiers",
    "LANGUAGE_TEXT_NAME": "languages, words, names, symbols, text references",
    "WORK_MEDIA_ART": "works, media, art, books, films, songs, games, publications, genres",
    "PRODUCT_TECH_OBJECT": "products, software, services, platforms, vehicles, tools, devices, artifacts",
    "MATERIAL_SUBSTANCE": "materials, chemicals, drugs, elements, nutrients, fuels, resources",
    "FOOD_AGRICULTURE": "foods, dishes, drinks, ingredients, crops",
    "ORGANISM_TAXON": "organisms, species, plants, animals, viruses, taxa",
    "ANATOMY_BIOLOGY": "body parts, organs, anatomical/biological structures",
    "HEALTH_MEDICINE": "diseases, conditions, symptoms, health states",
    "CONCEPT_FIELD_DOMAIN": "abstract concepts, domains, disciplines, ideologies, sectors, systems",
    "LAW_POLICY_NORM": "laws, legal concepts, policies, crimes, regulations, agreements, standards",
    "ACTION_PROCESS": "activities, procedures, practices, methods, treatments, rituals, processes",
    "ATTRIBUTE_PROPERTY": "properties, colors, features, categories, qualities, directions",
    "EDUCATION_AWARD": "awards, degrees, certifications, qualifications, education/program levels",
}


PARENT_REFINEMENTS = {
    "business type": "CONCEPT_FIELD_DOMAIN",
}


def load_counts() -> dict[str, int]:
    csv.field_size_limit(2**31 - 1)
    counts: dict[str, int] = {}
    with IN_COUNTS.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            counts[row["coarse_label"]] = int(row["total_count"])
    return counts


def load_rows(counts: dict[str, int]) -> list[dict[str, str]]:
    rows = []
    with IN_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            parent = PARENT_REFINEMENTS.get(row["coarse_tag"], row["mapped_label"])
            item = dict(row)
            item["recommended_parent"] = parent
            item["count"] = counts.get(row["coarse_tag"], 0)
            rows.append(item)
    return rows


def load_pairs() -> list[dict[str, str]]:
    with IN_PAIRS.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def top_unigrams(rows: list[dict[str, str]], limit: int = 10) -> str:
    tag_counts: Counter[str] = Counter()
    mention_counts: Counter[str] = Counter()
    for row in rows:
        text = row["coarse_tag_english"] or row["coarse_tag"]
        for token in ft.text_tokens(text):
            tag_counts[token] += 1
            mention_counts[token] += int(row["count"])
    ranked = sorted(
        tag_counts,
        key=lambda tok: (tag_counts[tok], mention_counts[tok], tok),
        reverse=True,
    )
    return "; ".join(
        f"{tok} ({tag_counts[tok]} tags, {mention_counts[tok]} mentions)"
        for tok in ranked[:limit]
    )


def pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def build_similarity_helpers(rows: list[dict[str, str]], pairs: list[dict[str, str]]):
    parent_by_tag = {row["coarse_tag"]: row["recommended_parent"] for row in rows}
    score_by_pair: dict[tuple[str, str], float] = {}
    internal: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    cross = []
    for pair in pairs:
        a = pair["coarse_tag_a"]
        b = pair["coarse_tag_b"]
        score = float(pair["similarity_pct"])
        score_by_pair[pair_key(a, b)] = score
        pa = parent_by_tag.get(a)
        pb = parent_by_tag.get(b)
        if not pa or not pb:
            continue
        if pa == pb:
            internal[pa].append(pair)
        elif score >= 85:
            cross.append((score, a, pa, b, pb))
    return score_by_pair, internal, sorted(cross, reverse=True)


def merge_families(parent_rows: list[dict[str, str]], score_by_pair: dict[tuple[str, str], float], threshold: float = 90.0) -> list[list[str]]:
    tags = [row["coarse_tag"] for row in parent_rows]
    parent = {tag: tag for tag in tags}

    def find(tag: str) -> str:
        while parent[tag] != tag:
            parent[tag] = parent[parent[tag]]
            tag = parent[tag]
        return tag

    def union(a: str, b: str) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    tag_set = set(tags)
    for (a, b), score in score_by_pair.items():
        if score >= threshold and a in tag_set and b in tag_set:
            union(a, b)

    groups: defaultdict[str, list[str]] = defaultdict(list)
    for tag in tags:
        groups[find(tag)].append(tag)
    families = [sorted(group) for group in groups.values() if len(group) > 1]
    families.sort(key=lambda group: (-len(group), group[0]))
    return families


def strongest_links(parent: str, internal_pairs: list[dict[str, str]], limit: int = 12) -> str:
    links = []
    for pair in internal_pairs[:limit]:
        links.append(f"{pair['coarse_tag_a']} <-> {pair['coarse_tag_b']} ({pair['similarity_pct']}%)")
    return "; ".join(links)


def format_families(families: list[list[str]], limit: int = 10) -> str:
    return " | ".join("; ".join(group) for group in families[:limit])


def write_outputs(rows: list[dict[str, str]], pairs: list[dict[str, str]]) -> None:
    by_parent: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_parent[row["recommended_parent"]].append(row)
    for parent_rows in by_parent.values():
        parent_rows.sort(key=lambda row: (-int(row["count"]), row["coarse_tag_english"], row["coarse_tag"]))

    score_by_pair, internal, cross = build_similarity_helpers(rows, pairs)
    parent_order = sorted(
        by_parent,
        key=lambda parent: (-sum(int(row["count"]) for row in by_parent[parent]), parent),
    )

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "recommended_parent",
                "description",
                "coarse_tag_count",
                "mention_count",
                "top_unigrams",
                "strong_similarity_families_90pct",
                "strongest_internal_links",
                "coarse_tags",
            ]
        )
        for parent in parent_order:
            parent_rows = by_parent[parent]
            families = merge_families(parent_rows, score_by_pair)
            writer.writerow(
                [
                    parent,
                    PARENT_DESCRIPTIONS[parent],
                    len(parent_rows),
                    sum(int(row["count"]) for row in parent_rows),
                    top_unigrams(parent_rows),
                    format_families(families),
                    strongest_links(parent, internal[parent]),
                    "; ".join(row["coarse_tag"] for row in parent_rows),
                ]
            )

    with OUT_TAG_MAP.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["coarse_tag", "coarse_tag_english", "count", "recommended_parent"])
        for row in sorted(rows, key=lambda item: (-int(item["count"]), item["coarse_tag_english"], item["coarse_tag"])):
            writer.writerow([row["coarse_tag"], row["coarse_tag_english"], row["count"], row["recommended_parent"]])

    global_unigrams = top_unigrams(rows, limit=25)
    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# FinerWeb Coarse Tag Grouping Recommendation\n\n")
        handle.write(
            "This is a processed grouping recommendation for the 453 coarse tags with >100 mentions. "
            "Parent buckets are manually calibrated from the ontology, then checked against fastText pairwise similarity. "
            "Unigram evidence is counted over canonical English coarse-tag text and weighted by the original coarse-tag mention counts.\n\n"
        )
        handle.write(f"- Coarse tags grouped: {len(rows)}\n")
        handle.write(f"- Recommended parents: {len(parent_order)}\n")
        handle.write(f"- Global high-frequency unigrams: {global_unigrams}\n\n")
        handle.write("## Boundary Notes From Cross-Parent Similarity\n\n")
        handle.write(
            "These are high-similarity cross-parent collisions. Most are shared modifier words "
            "(`political`, `government`, `media`, `legal`, etc.), so they should not automatically be merged.\n\n"
        )
        for score, a, pa, b, pb in cross[:30]:
            handle.write(f"- {score:.2f}%: `{a}` ({pa}) <-> `{b}` ({pb})\n")
        handle.write("\n## Recommended Parent Buckets\n\n")
        for parent in parent_order:
            parent_rows = by_parent[parent]
            mention_count = sum(int(row["count"]) for row in parent_rows)
            families = merge_families(parent_rows, score_by_pair)
            handle.write(f"### {parent}\n\n")
            handle.write(f"Description: {PARENT_DESCRIPTIONS[parent]}\n\n")
            handle.write(f"Tags: {len(parent_rows)}; mentions represented: {mention_count}\n\n")
            handle.write(f"Top unigram evidence: {top_unigrams(parent_rows)}\n\n")
            if families:
                handle.write("Strong similarity families (>=90%):\n")
                for family in families[:12]:
                    handle.write(f"- {', '.join(f'`{tag}`' for tag in family)}\n")
                handle.write("\n")
            if internal[parent]:
                handle.write("Strongest internal links:\n")
                for pair in internal[parent][:8]:
                    handle.write(
                        f"- {pair['similarity_pct']}%: `{pair['coarse_tag_a']}` <-> `{pair['coarse_tag_b']}`\n"
                    )
                handle.write("\n")
            handle.write("Child coarse tags:\n\n")
            handle.write(", ".join(f"`{row['coarse_tag']}`" for row in parent_rows))
            handle.write("\n\n")


def main() -> None:
    counts = load_counts()
    rows = load_rows(counts)
    pairs = load_pairs()
    write_outputs(rows, pairs)
    print(f"rows={len(rows)}")
    print(f"parents={len(set(row['recommended_parent'] for row in rows))}")
    print(f"wrote={OUT_MD}")
    print(f"groups_tsv={OUT_TSV}")
    print(f"tag_map={OUT_TAG_MAP}")


if __name__ == "__main__":
    main()
