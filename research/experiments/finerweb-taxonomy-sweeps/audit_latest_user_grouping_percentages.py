from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
INVENTORY = BASE / "finerweb_label_inventory.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_MD = OUT_DIR / "latest_user_grouping_percentages_audit.md"
OUT_TSV = OUT_DIR / "latest_user_grouping_percentages.tsv"

RAW = r"""
# Cleaned Tag Grouping Corrected

All FinerWeb labels with count >100 are present exactly once.

## Location / Spatial Entity

- location
- location / country
- location / city
- country
- city
- location / region
- location / province
- location / state
- region
- location / district
- location / village
- state
- location / island
- infrastructure
- location / building
- continent
- location / neighborhood
- province
- building
- location / continent
- location / administrative region
- location / street
- facility
- district
- location / municipality
- river
- geographic region
- administrative region
- location / geographic region
- location / town
- location / river
- village
- administrative division
- location / stadium
- location / airport
- hospital
- geopolitical region
- street
- geographical feature
- location / geopolitical entity
- location / administrative division
- location / hospital
- location / geographic location
- location / road
- location / us state
- location / educational institution
- location / mountain
- diocese
- geographical region
- place
- location / body of water
- location / geopolitical region
- police station
- body of water
- location / regency
- location / religious building
- location / sports venue
- location / street name
- location / place
- religious building
- location / temple
- location / diocese
- airport
- island
- cultural reference / building
- hotel
- location / subdistrict
- location / university
- location / political entity
- location / beach
- location / hotel
- location / mountain range
- location / park
- location / historical region
- location / lake
- road
- location / school
- natural feature
- neighborhood
- location / geographical region
- mountain
- location / police station
- location / state/province
- government building
- location / locality
- location / city/town
- location / government building
- temple
- building type
- municipality
- location / court
- کشور / country
- location / address
- restaurant
- geographic location
- location / ancient city
- mountain range
- establishment
- infrastructure project
- geopolitical entity

## Individual Agent

- person
- person / football player
- person / politician
- person / actor
- religious figure
- person / religious figure
- person / character
- person / athlete
- character
- person / musician
- person / historical figure
- person / religious leader
- person / artist
- person / author
- person / fictional character
- person / basketball player
- person / cricketer
- person / political figure
- historical figure
- person / film director
- person / football manager
- politician
- person / nickname
- person / historical person
- person / cricket player
- person / saint
- person / character name
- person / singer
- saint
- person / pope
- pope
- person / actress
- person / composer
- person / poet
- person / racing driver
- actor
- person / philosopher
- religious leader
- government official
- football player
- person / political leader
- political figure
- شخص / person
- person / police officer
- cultural reference / person
- pessoa / person
- fictional character
- person / football coach
- political leader
- persons / person
- person / person name
- character / fictional character
- military personnel
- cultural reference / fictional character
- persons

## Organization / Collective Agent

- organization
- organization / company
- organization / sports club
- organization / government organization
- organization / country
- organization / political organization
- organization / football club
- political party
- government organization
- media / media organization
- brand
- organization / government agency
- political organization
- organization / educational institution
- organization / sports team
- educational institution
- organization / political party
- organization / international organization
- organization / university
- organization / news agency
- news agency
- government agency
- company
- government
- organization / news organization
- political entity
- sports team
- event / sports league
- organization / hospital
- organization / sports organization
- organization / financial institution
- organization / government ministry
- organization / military organization
- organization / social media platform
- sports league
- organization / law enforcement agency
- military organization
- political group
- organization / religious organization
- sports club
- organization / government
- organization / bank
- organization / website
- organization / court
- news organization
- political party / political organization
- government ministry
- university
- organization / airline
- organization / brand
- political organization / political party
- organization / hotel
- organization / media organization
- organization / terrorist organization
- religious organization
- media / news organization
- international organization
- law enforcement agency
- organization / television network
- organization / newspaper
- court
- organization / governmental organization
- media / media outlet
- news outlet
- media organization
- location / organization
- sports team / sports club
- brand / company
- legislative body
- military unit
- government body
- financial institution
- brand / organization
- organization / basketball team
- football club
- business type
- organization / musical group
- organization / telecommunications company
- organization / legislative body
- stock exchange
- organization / cryptocurrency exchange
- government department
- organization / police department
- governmental organization
- organization / school
- event / football league
- organization type
- organization / automotive brand
- dynasty
- religious institution
- organization / sports league
- sports organization
- sports team / football club
- institution
- organization / police force
- organization / restaurant
- newspaper
- organization / radio station
- organization / streaming service
- organization / military unit
- organization / police station
- organization abbreviation
- organization / research institute
- organization / pharmaceutical company
- organization / museum
- terrorist organization
- organization / government body
- organization / tv channel
- organization / news website
- organization / labor union
- organization / organization abbreviation
- organization / game developer
- religious order
- organization / religious order
- organization / government department
- organization / police unit
- political body
- cultural reference / organization
- academic department
- organization / central bank
- political alliance
- organization / government organization abbreviation
- organization / television channel
- organization / music group
- organization / research institution
- school
- police department
- organization / racing team
- organization / magazine
- organization / publishing house
- location / sports club
- location / football club
- location / sports team
- bank
- media outlet
- media / news agency

## Time Expression

- date
- time period
- date / year
- year
- time
- duration
- day of the week
- month
- time period / duration
- time period / date
- time period / month
- date / day of the week
- time duration
- date / month
- year / date
- historical period
- time period / year
- time period / day of the week
- day of week
- time period / time duration
- date range
- season
- holiday
- temporal expression
- cultural reference / holiday
- cultural reference / festival
- time period / season
- time period / historical period
- time period / decade
- time of day

## cultural reference (RELIGION)

- deity
- religion
- religious text
- person / deity
- cultural reference / religious text
- god
- cultural reference / deity
- cultural reference / religious figure
- person / mythological figure
- mythological figure
- philosophical concept/deity / philosophical concept
- deity / hindu god of thunder
- deity / ritual drink
- cultural reference / sacred symbol/mantra
- religious practice
- person / biblical figure
- cultural reference / religion
- deity/divine entity
- hindu god of friendship
- hindu god of water
- cultural reference / mythological figure

## Abstract Concept / Mental-Social Construct

- concept
- scientific concept
- economic concept
- legal concept
- cultural concept
- financial concept
- political system
- cultural practice
- philosophical concept
- political concept
- religious concept
- social issue
- social concept
- political ideology
- abstract concept
- medical concept
- business concept
- health concept
- psychological concept
- feature
- educational concept
- cultural reference / concept
- scientific concept / scientific field
- biological process
- environmental issue
- cultural reference / religious concept

## LANGUAGE

- language
- programming language
- latin word
- word
- pronoun

## Measurement / Quantity Expression

- quantity
- measurement
- age
- percentage
- quantity / monetary value
- monetary value
- statistic
- statistic / percentage
- number
- score
- price
- quantity / duration
- distance
- quantity / percentage
- quantity / money
- measurement / distance
- quantity / age
- measurement / quantity
- quantity / number
- ordinal number
- quantities
- ranking
- measurement / duration
- statistic / quantity
- quantity / currency amount
- unit of measurement
- financial metric
- quantity / price
- age range
- currency/quantity / monetary value
- measurement / area
- statistics
- currency / monetary value
- currency amount
- currency/amount / monetary value
- money
- currency pair
- currency amount / monetary value
- quantity / currency
- currency / currency amount

## Event, Process, Action, Undertaking

- event
- historical event
- event / sports event
- event / sports competition
- event / festival
- festival
- event / holiday
- event / historical event
- political event
- event / sports tournament
- sports event
- event / sporting event
- natural disaster
- event / award
- cultural event
- cultural reference / event
- event / football competition
- event / political event
- sporting event
- event / election
- event / ritual/sacrifice
- election
- religious event
- event / organization
- natural phenomenon
- เหตุการณ์

## Human-Made Artifact / Technology / Product

- product
- technology
- website
- social media platform
- food
- vehicle
- weapon
- operating system
- financial product
- product / food
- product category
- product / car model
- product / vehicle model
- vehicle type
- product / smartphone model
- musical instrument
- ingredient
- product / product category
- product / automobile model
- software
- agricultural product
- product / food product
- product type
- object
- cultural reference / food
- media / website
- product / drug
- application
- food product
- vehicle model
- dish
- product / video game
- product / mobile phone model
- beverage
- product / beverage
- product / product model
- artifact
- cultural artifact
- product / motorcycle model
- technology / product
- technology / operating system
- product / software
- product / vehicle
- brand / automotive brand
- clothing
- platform
- product / application
- transportation
- website section
- food ingredient
- product / vaccine
- car model
- clothing item
- platform / social media platform
- technology / social media platform
- media / social media platform

## Organic / Bodily / Natural-Material Entity

- disease
- medical condition
- scientific concept / disease
- animal
- medical condition / disease
- body part
- fruit
- event / disease
- biological entity
- plant
- anatomical structure
- drug
- virus
- symptom
- product / agricultural product
- scientific concept / medical condition
- animal species
- organ
- species
- species / animal species
- nutrient
- hormone
- plant species
- vaccine
- scientific concept / virus
- medical term
- scientific concept / chemical substance
- chemical compound
- chemical substance
- substance
- resource
- chemical element
- material
- biological concept
- universe
- planet
- astronomical object
- world
- celestial body

## Classifier / Category / Role / Status / Type

- title
- profession
- occupation
- job title
- political position
- position
- government position
- role
- religious title
- title/position
- award
- position/title
- person / political position
- political office
- military rank
- person / occupation
- title/role
- family relation
- person / profession
- title / political position
- person / job title
- title / job title
- profession / occupation
- political title

## Creative Work

- media
- work of art
- video game
- film / movie
- literary work
- media / newspaper
- film
- music genre
- publication
- art form
- cultural reference / song
- cultural reference / movie
- song
- tv show
- cultural reference / tv show
- cultural reference / work of art
- cultural reference / book title
- film / film title
- cultural reference / literary work
- book title
- media / tv show
- cultural reference / song title
- cultural reference / tv series
- genre
- cultural reference / music genre
- work of art / book title
- tv series
- work of art / literary work
- media type
- movie
- film title
- media / magazine
- work of art / movie
- media / publication
- book
- literary genre
- media format
- media / news website
- game / video game
- cultural reference / art form
- game genre
- cultural reference / film
- work of literature

## Group Identity / Non-Institutional Human Collective

- nationality
- ethnic group
- group
- demographic group
- social group
- group of people
- religious group
- demographic
- cultural reference / ethnic group
- person / nationality
- social class
- community
- demonym
- person / ethnic group
- location / nationality
- location / ethnic group
- person / demographic group
- cultural reference / religious group
- nationality/ethnic group
- people

## Law / Government / Policy

- legal document
- document
- legislation
- crime
- legal term
- law
- policy
- government program
- legal document / law
- document type
- regulation
- legal code
- program / government program
- legislation / law
- legal case

## Economy / Finance

- industry
- financial instrument
- financial market
- financial term
- currency
- cryptocurrency
- economic sector
- economic indicator
- market
- commodity
- economic activity
- tax
- technical indicator
- financial index / stock market index
- economic policy

## Science / Knowledge / Academic

- field of study
- academic degree
- academic discipline
- educational level
- scientific field
- scientific concept / field of study
- educational program
- degree
- field
- field of study / academic discipline
- academic program
- philosophical school
- education level
- medical specialty

## Identifier / Contact / Reference

- nickname
- phone number
- url
- hashtag
- address
- email address
- page number
- contact number / phone number
- social media handle
- cultural reference / nickname
- family name

## Action / Process

- activity
- service
- program
- process
- project
- action
- medical procedure
- medical treatment
- sport
- game

## Other

- cultural reference
- entity
- general concept
- color
- category
- topic
- skill
"""

COUNT_RE = re.compile(r"^(?P<tag>.+?)\s*\((?P<count>\d+)\)")


def load_required() -> dict[str, int]:
    required = {}
    with INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["count"])
            if count > 100:
                required[row["original_label"]] = count
    return required


def clean(line: str) -> str:
    line = line.strip()
    if line.startswith("- "):
        line = line[2:].strip()
    match = COUNT_RE.match(line)
    if match:
        line = match.group("tag").strip()
    return line


def main() -> None:
    required = load_required()
    occurrences = []
    current_bucket = ""
    ignored = []
    for lineno, raw_line in enumerate(RAW.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            continue
        if line.startswith("All FinerWeb "):
            continue
        if line.startswith("## "):
            current_bucket = line[3:].strip()
            continue
        tag = clean(line)
        if tag in required:
            occurrences.append({"tag": tag, "bucket": current_bucket, "line": lineno})
        else:
            ignored.append((lineno, current_bucket, tag))

    counts = Counter(str(item["tag"]) for item in occurrences)
    duplicates = sorted(tag for tag, count in counts.items() if count > 1)
    missing = sorted(set(required) - set(counts))
    by_bucket: dict[str, list[str]] = defaultdict(list)
    for item in occurrences:
        by_bucket[str(item["bucket"])].append(str(item["tag"]))

    required_total = sum(required.values())
    occurrence_total = sum(required[item["tag"]] for item in occurrences)

    rows = []
    for bucket, tags in by_bucket.items():
        tag_count = len(tags)
        unique_tags = len(set(tags))
        mentions = sum(required[tag] for tag in tags)
        unique_mentions = sum(required[tag] for tag in set(tags))
        rows.append((bucket, tag_count, unique_tags, mentions, unique_mentions))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "tag_occurrences",
                "unique_tags",
                "mention_count_occurrence_sum",
                "mention_count_unique_sum",
                "pct_of_required_total_occurrence_sum",
                "pct_of_required_total_unique_sum",
            ]
        )
        for bucket, tag_count, unique_tags, mentions, unique_mentions in rows:
            writer.writerow(
                [
                    bucket,
                    tag_count,
                    unique_tags,
                    mentions,
                    unique_mentions,
                    f"{mentions / required_total * 100:.4f}",
                    f"{unique_mentions / required_total * 100:.4f}",
                ]
            )

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Latest User Grouping Category Percentages\n\n")
        handle.write(f"- Required labels >100: {len(required)}\n")
        handle.write(f"- Required mention total: {required_total}\n")
        handle.write(f"- Recognized occurrences: {len(occurrences)}\n")
        handle.write(f"- Recognized unique labels: {len(counts)}\n")
        handle.write(f"- Occurrence mention total: {occurrence_total}\n")
        handle.write(f"- Missing labels: {len(missing)}\n")
        handle.write(f"- Duplicate labels: {len(duplicates)}\n\n")
        handle.write("| Bucket | Tags | Count | % of required total |\n")
        handle.write("|---|---:|---:|---:|\n")
        for bucket, tag_count, unique_tags, mentions, unique_mentions in rows:
            handle.write(f"| {bucket} | {tag_count} | {mentions:,} | {mentions / required_total * 100:.2f}% |\n")
        handle.write("\n## Missing Labels\n\n")
        if missing:
            for tag in missing:
                handle.write(f"- `{tag}` ({required[tag]})\n")
        else:
            handle.write("None.\n")
        handle.write("\n## Duplicate Labels\n\n")
        if duplicates:
            for tag in duplicates:
                handle.write(f"- `{tag}` ({required[tag]})\n")
                for item in occurrences:
                    if item["tag"] == tag:
                        handle.write(f"  - line {item['line']}, bucket `{item['bucket']}`\n")
        else:
            handle.write("None.\n")

    print(f"required_labels_gt100\t{len(required)}")
    print(f"required_total_mentions\t{required_total}")
    print(f"recognized_occurrences\t{len(occurrences)}")
    print(f"recognized_unique_labels\t{len(counts)}")
    print(f"occurrence_total_mentions\t{occurrence_total}")
    print(f"missing\t{len(missing)}")
    print(f"duplicates\t{len(duplicates)}")
    print(f"md\t{OUT_MD}")
    print(f"tsv\t{OUT_TSV}")
    if missing:
        print("\nMISSING")
        for tag in missing:
            print(f"{tag}\t{required[tag]}")
    if duplicates:
        print("\nDUPLICATES")
        for tag in duplicates:
            print(tag)


if __name__ == "__main__":
    main()
