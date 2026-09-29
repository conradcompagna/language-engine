from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
INVENTORY = BASE / "finerweb_label_inventory.tsv"
OUT_DIR = BASE / "derived_fasttext_categories"
OUT_MD = OUT_DIR / "pasted_revamped_ge100_audit.md"
OUT_TSV = OUT_DIR / "pasted_revamped_ge100_audit_occurrences.tsv"

RAW = r"""
# Revamped Seed Region Assignment, Tags >100 Mentions

Seed regions come from the revamped list in the prompt. All labels in `finerweb_label_inventory.tsv` with count >100 are assigned to the nearest seed-region centroid. Slash labels use the current 25% parent / 75% child vector rule.

- Input tags >100: 693
- Input mention count: 700065
- Seed buckets: 15
- Seed tags: 86

## Location / Spatial Entity

101 tags, 147494 mentions

### Seed tags

- location (39110), sim 87.31%
- location / country (31286), sim 92.01%
- location / city (23849), sim 89.91%
- country (12518), sim 80.85%
- city (5306), sim 80.36%
- location / region (2905), sim 84.52%
- location / province (2874), sim 79.46%
- location / state (2083), sim 79.37%
- region (1625), sim 73.62%
- location / district (1236), sim 76.28%
- location / village (1010), sim 76.31%
administrative division
### New tags included

religious building

- state (801), sim 65.14%
- location / island (766), sim 75.50%
- infrastructure (760), sim 58.51%
- location / building (736), sim 75.39%
- continent (723), sim 62.99%
- location / neighborhood (656), sim 77.34%
- province (638), sim 65.02%
- building (580), sim 62.26%
- location / continent (573), sim 78.12%
- location / administrative region (545), sim 83.80%
- location / street (493), sim 74.69%
- facility (482), sim 64.16%
- district (474), sim 61.47%
- location / municipality (464), sim 72.20%
- river (442), sim 60.08%
- geographic region (437), sim 77.94%
- administrative region (430), sim 73.02%
- location / geographic region (429), sim 85.92%
- geographical feature (231), sim 68.76%
- astronomical object (124), sim 62.27%
- natural feature (139), sim 62.15%
- location / town (397), sim 84.72%
- distance (381), sim 54.84%
- location / river (379), sim 74.92%
- organization / country (374), sim 83.59%
- village (347), sim 61.88%
- location / stadium (330), sim 70.79%
- vehicle type (322), sim 66.40%
- location / sports club (308), sim 76.59%
- location / football club (302), sim 76.06%
- location / airport (287), sim 74.77%
- geopolitical region (253), sim 73.38%
- street (235), sim 59.80%
- location / geopolitical entity (229), sim 76.74%
- location / hospital (225), sim 70.33%
- location / administrative division (225), sim 71.59%
- location / geographic location (224), sim 86.15%
- location / road (222), sim 75.04%
- location / us state (220), sim 80.30%
- location / educational institution (212), sim 76.57%

celestial body

body of water

- location / mountain (209), sim 72.13%
- diocese (204), sim 54.60%
- place (195), sim 61.05%
- geographical region (195), sim 78.91%
- location / body of water (185), sim 73.59%
- location / geopolitical region (184), sim 83.89%
- police station (183), sim 64.05%
- location / religious building (175), sim 77.90%
- location / regency (175), sim 58.22%
- location / sports venue (174), sim 79.39%
- location / street name (173), sim 80.71%
- location / place (172), sim 74.06%
- location / temple (168), sim 71.38%
- location / diocese (167), sim 71.88%
- airport (166), sim 60.18%
- island (165), sim 60.88%
- cultural reference / building (161), sim 69.87%
- hotel (160), sim 59.25%
- planet (160), sim 60.39%
- location / subdistrict (160), sim 56.22%
- location / university (157), sim 76.81%
- location / sports team (157), sim 77.12%
- location / political entity (155), sim 77.84%
- universe (319), sim 54.89%
- location / beach (153), sim 68.15%
- location / mountain range (150), sim 75.61%
- location / hotel (150), sim 73.65%
- location / park (150), sim 72.54%
- location / historical region (145), sim 85.35%
- road (143), sim 60.55%
- location / lake (143), sim 72.29%
- location / school (140), sim 75.55%
- neighborhood (137), sim 64.13%
- location / geographical region (136), sim 86.71%
- mountain (135), sim 56.13%
- location / police station (133), sim 77.41%
- location / state/province (133), sim 86.51%
- location / locality (130), sim 75.60%
- location / government building (125), sim 81.00%
- location / city/town (125), sim 90.16%
- world (122), sim 63.12%

- temple (118), sim 55.64%

- municipality (112), sim 54.74%
- location / court (111), sim 69.21%
- کشور / country (110), sim 79.45%
- location / address (109), sim 62.20%
- restaurant (108), sim 54.53%
- location / ancient city (107), sim 86.36%
- geographic location (107), sim 83.49%
- mountain range (107), sim 61.92%
- bank (105), sim 51.73%
building type
hospital
infrastructure project

## Individual Agent

37 tags, 138551 mentions

### Seed tags

- person (123246), sim 99.96%
- deity (2389), sim 54.70%
- person / football player (1548), sim 70.95%
- person / politician (1536), sim 75.76%
- person / actor (1223), sim 74.60%
- religious figure (967), sim 67.96%

### New tags included

- person / character (757), sim 72.64%
- person / athlete (624), sim 77.00%
- person / musician (602), sim 76.22%
- person / deity (592), sim 72.74%
- person / artist (442), sim 74.68%
- person / author (442), sim 74.62%
- person / fictional character (353), sim 70.26%
- political leader (110), sim 71.09%
- person / political leader (141), sim 75.35%
- person / basketball player (322), sim 71.16%
- person / cricketer (317), sim 67.90%
- person / mythological figure (283), sim 67.80%
- politician (227), sim 59.40%
- person / historical person (220), sim 89.40%
- people (208), sim 70.56%
- person / cricket player (197), sim 70.75%
- person / saint (190), sim 70.09%
- person / singer (188), sim 71.91%
- saint (188), sim 50.90%
- pope (182), sim 51.81%
- person / pope (182), sim 70.66%
- person / actress (172), sim 70.56%
- person / composer (169), sim 68.48%


religious leader

- person / poet (158), sim 69.90%
- actor (150), sim 57.63%
- person / philosopher (148), sim 71.58%
- شخص / person (132), sim 95.42%
- person / police officer (130), sim 72.16%
- cultural reference / person (129), sim 97.10%
- pessoa / person (124), sim 95.94%
- persons / person (107), sim 98.36%
- person / person name (106), sim 92.21%
- deity/divine entity (128), sim 62.81%
person / religious figure
person / political figure
person / film director
person / football manager
person / nickname
person / character name
person / racing driver
government official
football player
person / biblical figure
political figure

fictional character
character
character / fictional character



person / football coach

## Organization / Collective Agent

121 tags, 104380 mentions

### Seed tags

- organization (39535), sim 97.90%
- organization / company (3785), sim 82.76%
- organization / sports club (3655), sim 83.37%
- organization / government organization (3522), sim 95.98%
- organization / political organization (2271), sim 95.18%
- political system (159), sim 70.52%

- organization / football club (2167), sim 81.91%
- political party (2114), sim 68.57%
- government organization (1995), sim 92.31%
- brand (1921), sim 54.37%
- organization / government agency (1694), sim 84.85%
- political organization (1535), sim 90.89%
- organization / educational institution (1528), sim 83.94%
- organization / sports team (1398), sim 83.15%
- educational institution (1293), sim 71.20%
- organization / political party (1242), sim 82.72%
- organization / international organization (1188), sim 93.41%
- organization / university (1184), sim 76.31%
- organization / news agency (1103), sim 83.13%
- news agency (1047), sim 69.69%
- religious order (131), sim 62.20%
brand / company

### New tags included

- government agency (880), sim 72.26%
- company (846), sim 69.62%
- government (839), sim 63.64%
- organization / news organization (804), sim 93.45%

- political entity (790), sim 74.51%
- organization / hospital (699), sim 69.67%
- organization / sports organization (658), sim 94.76%
- organization / financial institution (644), sim 83.44%
- organization / government ministry (628), sim 82.03%
- organization / military organization (569), sim 94.24%
- organization / social media platform (530), sim 80.90%
- organization / law enforcement agency (518), sim 81.45%
- organization / religious organization (517), sim 93.33%
- military organization (517), sim 89.47%
- sports club (487), sim 69.65%
- organization / government (477), sim 79.53%
- organization / bank (438), sim 70.70%
- organization / website (435), sim 80.56%
- organization / court (431), sim 69.96%

- news organization (417), sim 88.29%
- political party / political organization (415), sim 87.81%
- government ministry (411), sim 67.79%
- organization / airline (401), sim 72.61%
- organization / brand (393), sim 73.18%
- political organization / political party (392), sim 76.32%
- organization / hotel (391), sim 71.54%
- organization / media organization (388), sim 93.47%
- organization / terrorist organization (386), sim 93.25%
- religious organization (380), sim 88.16%
- media / news organization (376), sim 85.76%
- international organization (369), sim 88.09%
- organization / television network (348), sim 78.81%
- organization / newspaper (347), sim 76.87%
- organization / governmental organization (341), sim 94.97%
- geopolitical entity (323), sim 64.70%
- media organization (311), sim 88.16%
- location / organization (300), sim 96.72%
- sports team / sports club (289), sim 71.23%
- financial institution (266), sim 70.27%
- organization / basketball team (257), sim 80.10%
- brand / organization (257), sim 97.58%
- football club (255), sim 67.48%
- organization / musical group (243), sim 83.11%
- organization / telecommunications company (242), sim 81.76%
- organization / legislative body (223), sim 76.09%
- organization / police department (209), sim 78.35%
- government department (209), sim 69.34%

- governmental organization (205), sim 90.88%
- organization / school (199), sim 78.11%
- organization type (196), sim 86.08%
- organization / automotive brand (195), sim 74.83%
- religious institution (190), sim 70.59%
- organization / sports league (187), sim 81.84%
- sports organization (184), sim 90.09%
- sports team / football club (181), sim 70.91%
- institution (176), sim 69.02%
- organization / police force (168), sim 75.41%
- organization / restaurant (168), sim 70.52%
- newspaper (163), sim 60.24%
- organization / radio station (161), sim 73.81%
- organization / streaming service (158), sim 72.24%
- organization / military unit (155), sim 79.08%
- organization abbreviation (154), sim 84.02%
- organization / police station (154), sim 75.96%
- organization / research institute (152), sim 79.21%
- organization / pharmaceutical company (147), sim 82.24%
- organization / museum (146), sim 72.28%
- terrorist organization (145), sim 88.77%
- organization / government body (140), sim 82.55%
- organization / tv channel (139), sim 69.30%
- organization / news website (138), sim 82.37%
- organization / labor union (136), sim 74.63%
- organization / organization abbreviation (136), sim 90.45%
- organization / game developer (135), sim 74.61%
- government building (130), sim 70.51%
- organization / religious order (130), sim 76.27%
- organization / government department (127), sim 83.17%
- organization / police unit (127), sim 78.06%
- cultural reference / organization (119), sim 97.60%
- organization / central bank (118), sim 71.68%
- political alliance (118), sim 67.22%
- organization / government organization abbreviation (117), sim 93.39%
- organization / television channel (115), sim 74.63%
- establishment (113), sim 59.24%
- organization / research institution (113), sim 83.85%
- organization / music group (113), sim 85.21%
- police department (107), sim 62.14%
- event / organization (107), sim 97.03%
- organization / racing team (105), sim 79.65%
- organization / publishing house (101), sim 77.31%
- organization / magazine (101), sim 73.49%
sports team
university
law enforcement agency
court
legislative body
military unit
government body
business type
dynasty
political body
academic department
school
event / sports league
sports league
event / football league

## Time Expression

30 tags, 64902 mentions

### Seed tags

- date (31621), sim 93.74%
- time period (8353), sim 79.22%
- date / year (3656), sim 86.60%
- year (3292), sim 73.83%
- time (3278), sim 72.98%
- duration (2895), sim 62.39%
- day of the week (2393), sim 71.33%
- month (1571), sim 69.63%
- time period / duration (1048), sim 72.09%
- temporal expression (182), sim 63.74%


### New tags included

- time period / date (822), sim 98.38%
- time period / month (779), sim 77.92%
- date / day of the week (664), sim 84.84%
- time duration (546), sim 77.76%
- date / month (419), sim 83.52%
- year / date (386), sim 97.54%
- historical period (353), sim 72.73%
- time period / year (319), sim 80.35%
- time period / day of the week (308), sim 78.42%
- day of week (257), sim 71.33%
- time period / time duration (256), sim 79.99%
- date range (247), sim 85.96%
- holiday (214), sim 50.47%
- address (178), sim 46.10%
- email address (174), sim 50.43%
- time period / season (172), sim 68.99%
season


- time period / historical period (162), sim 77.10%
- time period / decade (129), sim 71.80%
- time of day (107), sim 79.62%

## cultural reference

39 tags, 26653 mentions

### Seed tags

- cultural reference (15874), sim 100.00%

### New tags included

- religious text (598), sim 65.26%
- cultural reference / religious text (578), sim 79.29%
- person / historical figure (570), sim 73.78%
- social issue (477), sim 69.65%
- cultural reference / deity (301), sim 64.80%
- cultural reference / song (298), sim 66.89%
- cultural reference / movie (297), sim 69.26%
- cultural reference / religious figure (283), sim 80.99%
- cultural reference / tv show (275), sim 69.83%
- historical figure (274), sim 72.36%
- mythological figure (266), sim 61.83%

hindu god of water
cultural reference / religion


- cultural reference / literary work (205), sim 80.28%
- cultural practice (204), sim 78.97%
- cultural reference / tv series (185), sim 69.99%
- cultural reference / music genre (175), sim 73.38%
- cultural reference / sacred symbol/mantra (172), sim 76.02%
- cultural reference / nickname (148), sim 62.63%
- cultural reference / food (143), sim 68.22%

- cultural reference / festival (127), sim 67.29%
- artifact (126), sim 56.32%
- cultural reference / holiday (124), sim 65.09%

- cultural artifact (119), sim 80.98%
- cultural reference / art form (111), sim 76.77%
- cultural reference / mythological figure (108), sim 77.10%
- cultural reference / film (106), sim 68.98%
- cultural reference / fictional character (102), sim 72.32%

god
deity / hindu god of thunder
deity / ritual drink
hindu god of friendship


## Abstract Concept / Mental-Social Construct

32 tags, 33872 mentions

### Seed tags

- concept (12658), sim 96.60%
- scientific concept (9102), sim 94.85%
- economic concept (1586), sim 91.64%
- legal concept (1560), sim 89.39%
- cultural concept (1184), sim 91.36%
- financial concept (1089), sim 88.75%
- philosophical concept (1016), sim 92.18%
entity
object

feature
category

### New tags included

- political concept (685), sim 90.87%
- religious concept (498), sim 88.99%
- social concept (415), sim 90.83%
- abstract concept (276), sim 87.39%
- philosophical concept/deity / philosophical concept (257), sim 89.49%
- medical concept (209), sim 90.16%
- business concept (182), sim 88.51%
- health concept (180), sim 87.44%
- psychological concept (147), sim 90.49%
political ideology
political group
philosophical school
- biological concept (145), sim 89.89%
- general concept (135), sim 87.09%
- educational concept (134), sim 90.72%
- cultural reference / concept (133), sim 97.60%
- scientific concept / scientific field (130), sim 76.76%
- cultural reference / religious concept (105), sim 88.41%

environmental issue


- natural phenomenon (120), sim 65.20%
- scientific concept / chemical substance (116), sim 72.36%
- biological process (111), sim 68.77%






## LANGUAGE

2 tags, 3333 mentions

### Seed tags

- language (3184), sim 100.00%

### New tags included

- programming language (149), sim 89.31%

## Measurement / Quantity Expression

24 tags, 37702 mentions

### Seed tags

- quantity (20583), sim 97.24%
- measurement (2948), sim 61.53%
- age (2443), sim 50.70%
- percentage (2437), sim 59.13%
- quantity / monetary value (2170), sim 82.83%
- monetary value (1367), sim 68.57%
- measurement / duration (171), sim 66.06%
- age range (132), sim 64.93%

### New tags included

- measurement / area (121), sim 73.08%
- statistic / percentage (887), sim 61.25%
- number (779), sim 64.85%
- price (416), sim 62.90%
- quantity / duration (384), sim 73.24%
- quantity / percentage (376), sim 76.63%
- quantity / money (366), sim 71.47%
- measurement / distance (359), sim 63.15%
- quantity / age (318), sim 71.05%
- measurement / quantity (270), sim 98.19%
- quantity / number (203), sim 79.31%
- ordinal number (185), sim 63.28%
- quantities (184), sim 76.89%
- statistic / quantity (169), sim 96.85%
- quantity / currency amount (165), sim 85.34%
- unit of measurement (159), sim 66.26%
- quantity / price (135), sim 78.14%
- currency/quantity / monetary value (124), sim 85.21%

statistic
statistics


## Event, Process, Action, Undertaking

20 tags, 21570 mentions

### Seed tags

- event (17186), sim 100.00%

### New tags included

- historical event (489), sim 85.34%
- event / sports event (403), sim 91.74%
- event / sports competition (321), sim 73.92%
- event / festival (318), sim 75.24%
- festival (318), sim 58.93%
- event / holiday (313), sim 64.73%
- event / historical event (287), sim 91.56%
- political event (233), sim 84.28%
- event / sports tournament (205), sim 77.28%
- sports event (199), sim 85.65%
- event / sporting event (198), sim 92.08%
- cultural event (150), sim 84.84%
- cultural reference / event (141), sim 97.06%
- event / political event (132), sim 90.93%
- sporting event (131), sim 86.23%
- event / election (123), sim 69.83%
- event / ritual/sacrifice (120), sim 65.39%
- religious event (104), sim 82.18%
election
event / football competition
crime
natural disaster



## Human-Made Artifact / Technology / Product

44 tags, 32237 mentions

### Seed tags

- product (13714), sim 94.12%
- technology (6510), sim 77.53%
- website (1692), sim 58.15%
- social media platform (1366), sim 70.73%
- vehicle (553), sim 59.27%
- vehicle model (166), sim 69.99%
- car model (103), sim 65.46%

### New tags included

- financial product (509), sim 85.30%
- product / food (463), sim 69.58%
- product category (440), sim 83.92%

- product / car model (366), sim 78.62%
- product / vehicle model (326), sim 79.80%
- product / smartphone model (286), sim 79.26%


- product / agricultural product (247), sim 90.90%
- ingredient (245), sim 59.25%
- product / product category (223), sim 89.11%
- product / automobile model (222), sim 77.93%
- software (210), sim 69.36%
- agricultural product (206), sim 86.18%
- product / food product (183), sim 90.24%
- product type (181), sim 85.82%
operating system
program
media / website
website section
- product / drug (173), sim 72.78%
- application (171), sim 59.42%
- food product (170), sim 85.50%
- product / video game (156), sim 76.57%
- product / mobile phone model (152), sim 77.69%
- beverage (142), sim 56.63%
- product / beverage (140), sim 72.82%
- product / product model (140), sim 91.22%
- product / motorcycle model (136), sim 77.07%
- technology / product (135), sim 99.04%
- technology / operating system (133), sim 71.11%
- product / vehicle (126), sim 74.48%
- product / software (126), sim 82.19%
- brand / automotive brand (121), sim 70.56%
- platform (118), sim 58.80%
- product / application (114), sim 75.71%
- product / vaccine (108), sim 70.80%
- food ingredient (108), sim 64.06%
- food (949), sim 57.05%
musical instrument
transportation
weapon
dish
clothing item




## Organic / Bodily / Natural-Material Entity

40 tags, 17832 mentions

### Seed tags

fruit
- disease (2975), sim 92.96%
- medical condition (1908), sim 81.55%
- scientific concept / disease (1333), sim 95.94%
- material (1224), sim 61.90%
- animal (1214), sim 67.69%
- medical condition / disease (1060), sim 97.28%

### New tags included

- medical procedure (654), sim 70.99%
- chemical compound (503), sim 63.36%
- event / disease (384), sim 93.58%

- biological entity (326), sim 70.42%
- plant (320), sim 55.99%
- anatomical structure (311), sim 67.04%
- chemical substance (302), sim 65.14%
- drug (250), sim 59.83%
- virus (205), sim 63.49%
- symptom (204), sim 65.61%
- chemical element (202), sim 64.95%
- scientific concept / medical condition (172), sim 84.25%
- animal species (160), sim 71.92%
- organ (157), sim 47.87%
- species (155), sim 61.31%
- species / animal species (153), sim 70.65%
- medical treatment (148), sim 76.66%
- medical specialty (120), sim 65.18%
- nutrient (114), sim 54.76%
- hormone (113), sim 52.24%
- vaccine (111), sim 58.05%
- plant species (111), sim 66.60%
- scientific concept / virus (110), sim 72.99%
- medical term (103), sim 71.27%
body part
resource
substance



## Classifier / Category / Role / Status / Type

149 tags, 50785 mentions

### Seed tags

- title (3001), sim 74.54%
- profession (2037), sim 75.98%
- occupation (1634), sim 71.35%
- job title (1457), sim 86.39%
- political position (1405), sim 78.54%
person / occupation
person / profession
person / political position
person / job title
military personnel
profession / occupation
position
government position
role
religious title
title/position
position/title
political office
military rank
title/role
title / political position
title / job title
political title

### New tags included
## Creative Work

16 tags, 4344 mentions

### Seed tags

- media (1506), sim 100.00%

### New tags included

- media / newspaper (410), sim 71.29%
- media outlet (277), sim 86.30%
- platform / social media platform (266), sim 72.76%
- technology / social media platform (257), sim 78.44%
- media / news agency (245), sim 75.99%
- media / tv show (193), sim 68.16%
- media type (151), sim 82.66%
- media / media outlet (146), sim 92.12%
- media / magazine (144), sim 64.71%
- media / social media platform (144), sim 88.15%
- media / media organization (142), sim 90.67%
- media format (122), sim 84.72%
- media / news website (121), sim 74.44%
- social media handle (117), sim 78.71%
- news outlet (103), sim 61.36%
publication



work of art ---------------------

work of art
video game
film / movie
literary work
film
game
song
tv show
cultural reference / work of art
cultural reference / book title
film / film title
book title
cultural reference / song title
genre
work of art / book title
tv series
work of art / literary work
movie
film title
work of art / movie
media / publication
book
literary genre
game / video game
game genre
work of literature
music genre
art form



## Money / Financial Asset / Economic Instrument

11 tags, 4236 mentions

### Seed tags

- currency (1647), sim 100.00%

### New tags included

- cryptocurrency (824), sim 53.60%
- currency / monetary value (597), sim 81.23%
- currency amount (290), sim 84.30%
- currency/amount / monetary value (209), sim 79.51%
- currency pair (119), sim 81.21%
- currency amount / monetary value (118), sim 76.07%
- quantity / currency (115), sim 96.77%
- currency / currency amount (110), sim 90.94%
- stock exchange (104), sim 56.17%
- organization / cryptocurrency exchange (103), sim 66.44%

## Group Identity / Non-Institutional Human Collective

26 tags, 12071 mentions

### Seed tags

- nationality (2652), sim 83.10%
- ethnic group (1614), sim 91.51%
- group (1180), sim 83.23%
- demographic group (1016), sim 84.27%
- community (148), sim 62.41%


### New tags included

- persons (339), sim 73.43%
- religion (671), sim 62.62%
- color (648), sim 44.57%
- social group (623), sim 81.49%
- group of people (547), sim 80.23%
- religious group (405), sim 83.23%

- demographic (223), sim 59.66%
- cultural reference / ethnic group (200), sim 91.29%
- person / nationality (178), sim 86.12%
- person / religious leader (154), sim 72.92%
- social class (153), sim 64.94%
- demonym (139), sim 39.75%
- person / ethnic group (139), sim 92.21%
- location / nationality (121), sim 84.88%
- location / ethnic group (118), sim 91.82%
- family relation (111), sim 65.26%
- person / demographic group (105), sim 85.97%
- nationality/ethnic group (102), sim 97.35%
- cultural reference / religious group (102), sim 84.10%





## NO_VECTOR

- เหตุการณ์ (103)

------------
## Law / Government / Policy

* legislation
* legal term
* law
* policy
* legal document / law
* regulation
* legal code
* legislation / law
* legal case
* government program
* program / government program
* legal document
* document

## Economy / Finance

* economic policy
* Economy / Finance
* financial instrument
* financial term
* economic sector
* money
* ranking
* financial metric
* tax
* financial index / stock market index
* economic activity
* economic indicator
* technical indicator
* financial market
* market
* commodity
* industry

## Science / Knowledge / Academic

* statistic
* academic degree
* academic discipline
* scientific field
* scientific concept / field of study
* educational program
* educational level
* field
* field of study / academic discipline
* category
* academic program
* philosophical school
* education level
* topic
* statistics
* degree
* skill

## Identifier / Contact / Reference

* nickname
* phone number
* url
* page number
* contact number / phone number
* family name
* word
* latin word
* pronoun
* hashtag

## Action / Process

* action
* activity
* process
* project
* service
"""

COUNT_RE = re.compile(r"^(?P<tag>.+?)\s*\((?P<count>\d+)\)")
SUMMARY_RE = re.compile(r"^\d+\s+tags,\s+\d+\s+mentions$")


def load_required() -> dict[str, int]:
    required = {}
    with INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["count"])
            if count > 100:
                required[row["original_label"]] = count
    return required


def strip_bullet(line: str) -> tuple[bool, str]:
    stripped = line.strip()
    if stripped.startswith("- "):
        return True, stripped[2:].strip()
    if stripped.startswith("* "):
        return True, stripped[2:].strip()
    return False, stripped


def normalize_candidate(line: str) -> tuple[str, int | None]:
    line = line.strip()
    match = COUNT_RE.match(line)
    if match:
        return match.group("tag").strip(), int(match.group("count"))
    if ", sim " in line:
        line = line.split(", sim ", 1)[0].strip()
    return line.strip(), None


def parse_occurrences(required: dict[str, int]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    occurrences = []
    ignored_candidates = []
    current_bucket = ""
    lines = RAW.splitlines()
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_bucket = line[3:].strip()
            continue
        if line.startswith("#") or line.startswith("### "):
            continue
        if set(line) <= {"-"}:
            continue
        if SUMMARY_RE.match(line):
            continue
        if line.startswith("Seed regions ") or line.startswith("`finerweb_label_inventory"):
            continue
        if line.startswith("Slash labels ") or line.startswith("All labels "):
            continue
        if line.lower() in {"cultural reference", "language"}:
            # These standalone lines are pasted section labels; the actual tag is listed separately.
            current_bucket = line
            continue
        if "----------------" in line:
            continue

        is_bullet, candidate_line = strip_bullet(line)
        tag, pasted_count = normalize_candidate(candidate_line)
        if not tag:
            continue
        if tag.startswith("Input ") or tag.startswith("Seed "):
            continue
        if tag in required:
            occurrences.append(
                {
                    "tag": tag,
                    "bucket": current_bucket,
                    "line": idx,
                    "pasted_count": pasted_count,
                    "required_count": required[tag],
                    "style": "bullet" if is_bullet else "bare",
                }
            )
        else:
            ignored_candidates.append(
                {
                    "text": tag,
                    "bucket": current_bucket,
                    "line": idx,
                    "style": "bullet" if is_bullet else "bare",
                }
            )
    return occurrences, ignored_candidates


def main() -> None:
    required = load_required()
    occurrences, ignored = parse_occurrences(required)
    counts = Counter(str(item["tag"]) for item in occurrences)
    unique_tags = set(counts)
    missing = sorted(set(required) - unique_tags)
    duplicates = sorted(tag for tag, count in counts.items() if count > 1)
    pasted_count_mismatches = [
        item
        for item in occurrences
        if item["pasted_count"] is not None and int(item["pasted_count"]) != int(item["required_count"])
    ]

    by_bucket: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in occurrences:
        by_bucket[str(item["bucket"])].append(item)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["tag", "bucket", "line", "style", "pasted_count", "required_count"])
        for item in occurrences:
            writer.writerow(
                [
                    item["tag"],
                    item["bucket"],
                    item["line"],
                    item["style"],
                    "" if item["pasted_count"] is None else item["pasted_count"],
                    item["required_count"],
                ]
            )

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Audit Of Pasted Revamped >100 Tag Text\n\n")
        handle.write("Parsed the pasted text directly. Bullet lines and bare standalone lines were counted as tags when they matched an original FinerWeb label with count >100.\n\n")
        handle.write(f"- Required inventory tags >100: {len(required)}\n")
        handle.write(f"- Parsed recognized occurrences: {len(occurrences)}\n")
        handle.write(f"- Parsed unique recognized tags: {len(unique_tags)}\n")
        handle.write(f"- Missing required tags: {len(missing)}\n")
        handle.write(f"- Duplicate recognized tags: {len(duplicates)}\n")
        handle.write(f"- Pasted count mismatches: {len(pasted_count_mismatches)}\n\n")

        handle.write("## Duplicate Tags\n\n")
        if duplicates:
            for tag in duplicates:
                where = [item for item in occurrences if item["tag"] == tag]
                handle.write(f"- `{tag}` ({required[tag]})\n")
                for item in where:
                    handle.write(f"  - line {item['line']}, bucket `{item['bucket']}`, {item['style']}\n")
        else:
            handle.write("None.\n")
        handle.write("\n")

        handle.write("## Missing Tags\n\n")
        if missing:
            for tag in missing:
                handle.write(f"- `{tag}` ({required[tag]})\n")
        else:
            handle.write("None.\n")
        handle.write("\n")

        handle.write("## Count Mismatches\n\n")
        if pasted_count_mismatches:
            for item in pasted_count_mismatches:
                handle.write(
                    f"- `{item['tag']}` line {item['line']}: pasted {item['pasted_count']}, inventory {item['required_count']}\n"
                )
        else:
            handle.write("None.\n")
        handle.write("\n")

        handle.write("## Recognized Tags By Bucket\n\n")
        for bucket, items in by_bucket.items():
            unique_in_bucket = len({str(item["tag"]) for item in items})
            handle.write(f"### {bucket}\n\n")
            handle.write(f"{len(items)} occurrences, {unique_in_bucket} unique tags\n\n")

        handle.write("## Ignored Candidate Lines\n\n")
        for item in ignored:
            handle.write(f"- line {item['line']}, bucket `{item['bucket']}`: `{item['text']}`\n")

    print(f"required_gt100\t{len(required)}")
    print(f"recognized_occurrences\t{len(occurrences)}")
    print(f"recognized_unique\t{len(unique_tags)}")
    print(f"missing\t{len(missing)}")
    print(f"duplicates\t{len(duplicates)}")
    print(f"count_mismatches\t{len(pasted_count_mismatches)}")
    print(f"report\t{OUT_MD}")
    print(f"occurrences_tsv\t{OUT_TSV}")
    if duplicates:
        print("\nDUPLICATES")
        for tag in duplicates:
            print(tag)
    if missing:
        print("\nMISSING")
        for tag in missing:
            print(f"{tag}\t{required[tag]}")


if __name__ == "__main__":
    main()
