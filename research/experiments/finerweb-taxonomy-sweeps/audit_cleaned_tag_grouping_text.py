from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
INVENTORY = BASE / "finerweb_label_inventory.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_MD = OUT_DIR / "cleaned_tag_grouping_ge100_audit.md"
OUT_TSV = OUT_DIR / "cleaned_tag_grouping_ge100_occurrences.tsv"

RAW = r"""
# Cleaned tag grouping

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
- administrative division
- religious building
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
- geographical feature
- astronomical object
- natural feature
- location / town

- location / river
- organization / country
- village
- location / stadium

- location / sports club
- location / football club
- location / airport
- geopolitical region
- street
- location / geopolitical entity
- location / hospital
- location / administrative division
- location / geographic location
- location / road
- location / us state
- location / educational institution
- celestial body
- body of water
- location / mountain
- diocese
- place
- geographical region
- location / body of water
- location / geopolitical region
- police station
- location / religious building
- location / regency
- location / sports venue
- location / street name
- location / place
- location / temple
- location / diocese
- government building
- airport
- island
- cultural reference / building
- hotel
- planet
- location / subdistrict
- location / university
- location / sports team
- location / political entity
- universe
- location / beach
- location / mountain range
- location / hotel
- location / park
- location / historical region
- road
- location / lake
- location / school
- neighborhood
- location / geographical region
- mountain
- location / police station
- location / state/province
- location / locality
- location / government building
- location / city/town
- world
- temple
- municipality
- location / court
- کشور / country
- location / address
- restaurant
- location / ancient city
- geographic location
- mountain range
- bank
- building type
- hospital
- infrastructure project

## Individual Agent

- person
- person / football player
- person / politician
- person / actor
- religious figure
- person / athlete
- person / musician
fictional character
character
character / fictional character
person / fictional character
person / character
- military personnel
- person / artist
- person / author
person / historical figure
historical figure


- political leader
- person / political leader
- person / basketball player
- person / cricketer




- politician
- person / historical person
- people
- person / cricket player
- person / saint
- person / singer
- saint
- pope
- person / pope
- person / actress
- person / composer
- religious leader
- person / poet
- actor
- person / philosopher
- شخص / person
- person / police officer
- cultural reference / person
- pessoa / person
- persons / person
- person / person name
cultural reference / fictional character

- person / religious figure
- person / political figure
- person / film director
- person / football manager
- person / nickname
- person / character name
- person / racing driver
- government official
- football player

- political figure

- person / football coach

## Organization / Collective Agent

- organization
- organization / company
- organization / sports club
- organization / government organization
- organization / political organization
- political system
- organization / football club
- political party
- government organization
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
- religious order
- brand / company
- government agency
- company
- government
- organization / news organization
- political entity
- organization / hospital
- organization / sports organization
- organization / financial institution
- organization / government ministry
- organization / military organization
- organization / social media platform
- organization / law enforcement agency
- organization / religious organization
- military organization
- sports club
- organization / government
- organization / bank
- organization / website
- organization / court
- news organization
- political party / political organization
- government ministry
- organization / airline
- organization / brand
- political organization / political party
- organization / hotel
- organization / media organization
- organization / terrorist organization
- religious organization
- media / news organization
- international organization
- organization / television network
- organization / newspaper
- organization / governmental organization
- geopolitical entity
- media organization
- location / organization
- sports team / sports club

- organization / basketball team
- brand / organization
- football club
- organization / musical group
- organization / telecommunications company
- organization / legislative body
- organization / police department
- government department
- governmental organization
- organization / school
- organization type
- organization / automotive brand
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
- organization abbreviation
- organization / police station
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

- organization / religious order
- organization / government department
- organization / police unit
- cultural reference / organization
- organization / central bank
- political alliance
- organization / government organization abbreviation
- organization / television channel
- establishment
- organization / research institution
- organization / music group
- police department
- event / organization
- organization / racing team
- organization / publishing house
- organization / magazine
- sports team
- university
- law enforcement agency
- court
- legislative body
- military unit
- government body
- business type
- dynasty
- political body
- academic department
- school
- event / sports league
- sports league
- event / football league

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
- temporal expression
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
- holiday
- time period / season
- season
- time period / historical period
- time period / decade
- time of day

## cultural reference (RELIGION)


Religion
religious text
cultural reference / religious text
cultural reference / deity
cultural reference / religious figure
hindu god of water
cultural reference / religion
cultural reference / sacred symbol/mantra
god
deity / hindu god of thunder
deity / ritual drink
hindu god of friendship
person / biblical figure
deity/divine entity
person / deity
deity
mythological figure
cultural reference / mythological figure
person / mythological figure
- philosophical concept/deity / philosophical concept

## Abstract Concept / Mental-Social Construct

- concept
social issue
- scientific concept
- economic concept
- legal concept
- cultural concept
- financial concept
- philosophical concept
- entity
- object
- feature
- category
- political concept
- religious concept
- social concept
- abstract concept
- medical concept
- business concept
- health concept
- psychological concept
- political ideology
- political group
- philosophical school
- biological concept
- general concept
- educational concept
- cultural reference / concept
- scientific concept / scientific field
- cultural reference / religious concept
- environmental issue
- natural phenomenon
- scientific concept / chemical substance
- biological process
category
skill
topic


## LANGUAGE

- language
- programming language

## Measurement / Quantity Expression

- quantity
- measurement
- age
- percentage
- quantity / monetary value
- monetary value
- measurement / duration
- age range
- measurement / area
- statistic / percentage
- number
- price
- quantity / duration
- quantity / percentage
- quantity / money
- measurement / distance
- quantity / age
- measurement / quantity
- quantity / number
- ordinal number
- quantities
- statistic / quantity
- quantity / currency amount
- unit of measurement
- quantity / price
- currency/quantity / monetary value
- statistic
- distance
ranking
financial metric

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
- cultural event
- cultural reference / event
- event / political event
- sporting event
- event / election
- event / ritual/sacrifice
- religious event
- election
- event / football competition
- natural disaster

## Human-Made Artifact / Technology / Product

- product
- technology
- website
- social media platform
- vehicle
- vehicle model
- car model
- financial product
- product / food
- product category
- product / car model
- product / vehicle model
- product / smartphone model
- product / agricultural product
- ingredient
- product / product category
- product / automobile model
- software
- agricultural product
- product / food product
- product type
- operating system
- media / website
- website section
- product / drug
- application
- food product
- product / video game
- product / mobile phone model
- beverage
- product / beverage
- product / product model
- product / motorcycle model
- technology / product
- technology / operating system
- product / vehicle
- product / software
- brand / automotive brand
- platform
- product / application
- product / vaccine
- food ingredient
- food
- musical instrument
- transportation
- weapon
- dish
- clothing item
- vehicle type
fruit


## Organic / Bodily / Natural-Material Entity

disease
medical condition
scientific concept / disease
medical condition / disease
medical procedure
event / disease
virus
symptom
medical treatment
medical specialty
vaccine
medical term
scientific concept / medical condition
scientific concept / virus
drug
anatomical structure
organ
body part
nutrient
hormone
animal
biological entity
plant
animal species
species
species / animal species
plant species

Other
chemical compound
chemical substance
chemical element
resource
substance
material

## Classifier / Category / Role / Status / Type

- title
- profession
- occupation
- job title
- political position
- person / occupation
- person / profession
- person / political position
- person / job title
- profession / occupation
- position
- government position
- role
- religious title
- title/position
- position/title
- political office
- military rank
- title/role
- title / political position
- title / job title
- political title

## Creative Work

- media
- media / newspaper
- media outlet
- platform / social media platform
- technology / social media platform
- media / news agency
- media / tv show
- media type
- media / media outlet
- media / magazine
- media / social media platform
- media / media organization
- media format
- media / news website
- social media handle
- news outlet
- publication

ART

- work of art
- video game
- film / movie
- literary work
- film
- game
- song
- tv show
- cultural reference / work of art
- cultural reference / book title
- film / film title
- book title
- cultural reference / song title
- genre
- work of art / book title
- tv series
- work of art / literary work
- movie
- film title
- work of art / movie
- media / publication
- book
- literary genre
- game / video game
- game genre
- work of literature
- music genre
- art form
cultural reference / song
cultural reference / movie
cultural reference / tv show
cultural reference / literary work
cultural reference / tv series
cultural reference / music genre
cultural reference / art form
cultural reference / film


## Money / Financial Asset / Economic Instrument

- currency
- cryptocurrency
- currency / monetary value
- currency amount
- currency/amount / monetary value
- currency pair
- currency amount / monetary value
- quantity / currency
- currency / currency amount
- stock exchange
- organization / cryptocurrency exchange
money

## Group Identity / Non-Institutional Human Collective

- nationality
- ethnic group
- group
- demographic group
- community
- persons
- religion
- color
- social group
- group of people
- religious group
- demographic
- cultural reference / ethnic group
- person / nationality
- person / religious leader
- social class
- demonym
- person / ethnic group
- location / nationality
- location / ethnic group
- family relation
- person / demographic group
- nationality/ethnic group
- cultural reference / religious group


Law / Government / Policy

legislation
legal term
law
policy
legal document / law
regulation
legal code
legislation / law
legal case
government program
program / government program
legal document
document
- crime

Economy / Finance


economic policy
Economy / Finance
financial instrument
financial term
economic sector
tax
financial index / stock market index
economic activity
economic indicator
technical indicator
financial market
market
commodity
industry

Science / Knowledge / Academic

academic degree
academic discipline
scientific field
scientific concept / field of study
educational program
educational level
field
field of study / academic discipline
academic program
philosophical school
education level
degree

Identifier / Contact / Reference

nickname
phone number
url
page number
contact number / phone number
family name
word
latin word
pronoun
hashtag
- address
- email address


Action / Process
action
activity
process
project
service
- program



----------


cultural reference

cultural practice
cultural reference / nickname
cultural reference / food
cultural reference / festival
artifact
cultural reference / holiday

cultural artifact





## NO_VECTOR

- เหตุการณ์ (103) --- again tell me, are all present? any duplicates?
"""

HEADING_LINES = {
    "ART",
    "Other",
    "Law / Government / Policy",
    "Economy / Finance",
    "Science / Knowledge / Academic",
    "Identifier / Contact / Reference",
    "Action / Process",
}
COUNT_RE = re.compile(r"^(?P<tag>.+?)\s*\((?P<count>\d+)\)")


def load_required() -> dict[str, int]:
    required = {}
    with INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["count"])
            if count > 100:
                required[row["original_label"]] = count
    return required


def clean_line(line: str) -> tuple[str, str]:
    style = "bare"
    line = line.strip()
    if line.startswith("- "):
        style = "bullet"
        line = line[2:].strip()
    elif line.startswith("* "):
        style = "bullet"
        line = line[2:].strip()
    match = COUNT_RE.match(line)
    if match:
        line = match.group("tag").strip()
    return line.strip(), style


def parse(required: dict[str, int]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    occurrences = []
    ignored = []
    case_only = []
    current_bucket = ""
    for lineno, raw_line in enumerate(RAW.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            current_bucket = line[3:].strip()
            continue
        if set(line) <= {"-"}:
            continue
        candidate, style = clean_line(line)
        if not candidate:
            continue
        if candidate in HEADING_LINES:
            current_bucket = candidate
            continue
        if candidate in required:
            occurrences.append(
                {
                    "tag": candidate,
                    "bucket": current_bucket,
                    "line": lineno,
                    "style": style,
                    "match_type": "exact",
                }
            )
            continue
        lowered = candidate.lower()
        if lowered in required and candidate != lowered:
            occurrences.append(
                {
                    "tag": lowered,
                    "bucket": current_bucket,
                    "line": lineno,
                    "style": style,
                    "match_type": "case_normalized",
                    "original_text": candidate,
                }
            )
            case_only.append(
                {
                    "tag": lowered,
                    "original_text": candidate,
                    "bucket": current_bucket,
                    "line": lineno,
                }
            )
            continue
        ignored.append({"text": candidate, "bucket": current_bucket, "line": lineno, "style": style})
    return occurrences, ignored, case_only


def main() -> None:
    required = load_required()
    occurrences, ignored, case_only = parse(required)
    counts = Counter(str(item["tag"]) for item in occurrences)
    unique_tags = set(counts)
    missing = sorted(set(required) - unique_tags)
    duplicates = sorted(tag for tag, count in counts.items() if count > 1)
    by_bucket = defaultdict(list)
    for item in occurrences:
        by_bucket[str(item["bucket"])].append(item)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["tag", "bucket", "line", "style", "match_type", "original_text", "required_count"])
        for item in occurrences:
            writer.writerow(
                [
                    item["tag"],
                    item["bucket"],
                    item["line"],
                    item["style"],
                    item["match_type"],
                    item.get("original_text", ""),
                    required[str(item["tag"])],
                ]
            )

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Cleaned Tag Grouping >100 Audit\n\n")
        handle.write("- Parsed this pasted list directly.\n")
        handle.write("- Bullet and bare standalone lines count as tags when they match the inventory.\n")
        handle.write("- Obvious section labels like `ART`, `Other`, and `Law / Government / Policy` are headings, not tags.\n")
        handle.write("- Case-only tag lines are counted but flagged.\n\n")
        handle.write(f"- Required inventory tags >100: {len(required)}\n")
        handle.write(f"- Recognized occurrences: {len(occurrences)}\n")
        handle.write(f"- Recognized unique tags: {len(unique_tags)}\n")
        handle.write(f"- Missing required tags: {len(missing)}\n")
        handle.write(f"- Duplicate tags: {len(duplicates)}\n")
        handle.write(f"- Case-only matches: {len(case_only)}\n\n")
        handle.write("## Missing Tags\n\n")
        if missing:
            for tag in missing:
                handle.write(f"- `{tag}` ({required[tag]})\n")
        else:
            handle.write("None.\n")
        handle.write("\n## Duplicate Tags\n\n")
        if duplicates:
            for tag in duplicates:
                handle.write(f"- `{tag}` ({required[tag]})\n")
                for item in occurrences:
                    if item["tag"] == tag:
                        original = f", original `{item.get('original_text')}`" if item.get("original_text") else ""
                        handle.write(f"  - line {item['line']}, bucket `{item['bucket']}`, {item['match_type']}{original}\n")
        else:
            handle.write("None.\n")
        handle.write("\n## Case-Only Matches\n\n")
        if case_only:
            for item in case_only:
                handle.write(f"- `{item['original_text']}` -> `{item['tag']}` at line {item['line']}, bucket `{item['bucket']}`\n")
        else:
            handle.write("None.\n")
        handle.write("\n## Recognized Tags By Bucket\n\n")
        for bucket, items in by_bucket.items():
            handle.write(f"- `{bucket}`: {len(items)} occurrences, {len({item['tag'] for item in items})} unique\n")
        handle.write("\n## Ignored Candidate Lines\n\n")
        for item in ignored:
            handle.write(f"- line {item['line']}, bucket `{item['bucket']}`: `{item['text']}`\n")

    print(f"required_gt100\t{len(required)}")
    print(f"recognized_occurrences\t{len(occurrences)}")
    print(f"recognized_unique\t{len(unique_tags)}")
    print(f"missing\t{len(missing)}")
    print(f"duplicates\t{len(duplicates)}")
    print(f"case_only_matches\t{len(case_only)}")
    print(f"report\t{OUT_MD}")
    print(f"occurrences_tsv\t{OUT_TSV}")
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
