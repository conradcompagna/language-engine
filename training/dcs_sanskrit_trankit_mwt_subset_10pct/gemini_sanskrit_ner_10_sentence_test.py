from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import GEMINI_API_KEY, GEMINI_MODEL_PRICING_USD_PER_1M


INPUT_FILE = (
    ROOT
    / "training"
    / "dcs_sanskrit_trankit_mwt_subset_10pct"
    / "train_10k_parent_tokens_unannotated_bio_chunks"
    / "unannotatedchild"
    / "unannotatedchild_chunk_001_source_01_sent_0001_0100.bio"
)
OUT_DIR = (
    ROOT / "training" / "dcs_sanskrit_trankit_mwt_subset_10pct" / "gemini_ner_test_10_sentences"
)
MODEL = "gemini-2.5-flash-lite"

ALLOWED_LABELS = {
    "O",
    "PERSON",
    "PLACE",
    "DEITY",
    "GROUP",
    "TEXT",
    "RITUAL",
    "ASTRO",
    "BODY",
    "DISEASE",
    "MEDICINE",
    "PLANT",
    "ANIMAL",
    "FOOD",
    "SUBSTANCE",
    "TOOL",
    "MEASURE",
    "PROCEDURE",
    "CONCEPT",
}


def read_first_sentences(path: Path, limit: int) -> list[list[str]]:
    sentences: list[list[str]] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                sentences.append(current)
                current = []
                if len(sentences) == limit:
                    break
            continue
        current.append(stripped.rsplit(maxsplit=1)[0])
    if current and len(sentences) < limit:
        sentences.append(current)
    return sentences


def build_prompts(sentences: list[list[str]]) -> tuple[str, str]:
    labels = ", ".join(sorted(ALLOWED_LABELS))
    system_prompt = f"""You annotate Sanskrit token streams for NER.

Hard output rules:
- Return exactly one non-empty output row for each input token row.
- Each output row must be exactly: token LABEL
- The token string must be copied exactly from the input: same characters, same diacritics, same order.
- Do not add, remove, split, merge, normalize, translate, or correct tokens.
- Use exactly one ASCII space between the token and the label.
- Use only these labels: {labels}
- Do not use BIO prefixes. Do not output B- or I-.
- Do not output sentence numbers, indexes, markdown, JSON, comments, explanations, or extra blank lines.

Annotation guide:
- PERSON: named human beings, sages, kings, authors, mythic humans.
- PLACE: named places, regions, rivers, mountains, cities, hermitages.
- DEITY: named gods, divine beings, semi-divine figures.
- GROUP: social, ethnic, caste, dynastic, or institutional groups.
- TEXT: named scriptures, books, chapters, treatises.
- RITUAL: named rites, sacrifices, vows, ceremonies.
- ASTRO: named planets, constellations, lunar mansions, zodiac items.
- BODY: body parts, tissues, organs, bodily substances.
- DISEASE: diseases, symptoms, pathological states.
- MEDICINE: named medicines, formulas, treatments.
- PLANT: plants, herbs, trees, botanical items.
- ANIMAL: animals and animal species.
- FOOD: foods, drinks, edible preparations.
- SUBSTANCE: materials, minerals, metals, fluids, non-food substances.
- TOOL: instruments, weapons, utensils, built objects used as tools.
- MEASURE: numbers, quantities, units, measures, calendrical quantities.
- PROCEDURE: medical, ritual, technical, or instructional actions/processes.
- CONCEPT: abstract doctrinal, philosophical, grammatical, or technical concepts.
- O: anything that does not fit a label confidently.

Example sentence 1 input:
rāmaḥ
ayodhyāyām
sītayā
saha
avasat
.

Example sentence 1 correct output:
rāmaḥ PERSON
ayodhyāyām PLACE
sītayā PERSON
saha O
avasat O
. O

Example sentence 2 input:
bhagavān
dhanvantariḥ
jvarasya
cikitsām
uvāca
.

Example sentence 2 correct output:
bhagavān O
dhanvantariḥ DEITY
jvarasya DISEASE
cikitsām PROCEDURE
uvāca O
. O

Example sentence 3 input:
agnau
ghṛtena
darbhaiḥ
homaḥ
kriyate
.

Example sentence 3 correct output:
agnau RITUAL
ghṛtena SUBSTANCE
darbhaiḥ PLANT
homaḥ RITUAL
kriyate O
. O

Example sentence 4 input:
aśvinī
nakṣatre
brāhmaṇaḥ
vratam
ārabheta
.

Example sentence 4 correct output:
aśvinī ASTRO
nakṣatre ASTRO
brāhmaṇaḥ GROUP
vratam RITUAL
ārabheta O
. O
"""
    lines: list[str] = []
    for index, sentence in enumerate(sentences, start=1):
        lines.append(f"[sentence {index}]")
        lines.extend(sentence)
        lines.append("")
    user_prompt = "Annotate these input tokens. Sentence marker lines are context only and are not tokens:\n\n"
    user_prompt += "\n".join(lines).strip()
    return system_prompt, user_prompt


def call_gemini(system_prompt: str, user_prompt: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "candidateCount": 1,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def response_text(data: dict) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini response had no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts)


def validate_output(text: str, tokens: list[str]) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != len(tokens):
        raise ValueError(f"row count mismatch: expected {len(tokens)}, got {len(lines)}")
    parsed: list[tuple[str, str]] = []
    for index, (line, expected_token) in enumerate(zip(lines, tokens), start=1):
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            raise ValueError(f"line {index} is not 'token LABEL': {line!r}")
        token, label = parts
        if token != expected_token:
            raise ValueError(
                f"line {index} token mismatch: expected {expected_token!r}, got {token!r}"
            )
        if label not in ALLOWED_LABELS:
            raise ValueError(f"line {index} invalid label {label!r}")
        parsed.append((token, label))
    return parsed


def to_bio(sentences: list[list[str]], flat_labels: list[tuple[str, str]]) -> str:
    rows: list[str] = []
    cursor = 0
    for sentence in sentences:
        previous_label = "O"
        for token in sentence:
            out_token, label = flat_labels[cursor]
            if out_token != token:
                raise ValueError(f"internal BIO conversion token mismatch at {cursor}")
            if label == "O":
                tag = "O"
            else:
                prefix = "I" if label == previous_label else "B"
                tag = f"{prefix}-{label}"
            rows.append(f"{token} {tag}")
            previous_label = label
            cursor += 1
        rows.append("")
    return "\n".join(rows).rstrip() + "\n"


def write_usage(data: dict) -> None:
    usage = data.get("usageMetadata") or {}
    pricing = GEMINI_MODEL_PRICING_USD_PER_1M.get(MODEL, {})
    input_tokens = int(usage.get("promptTokenCount") or 0)
    output_tokens = int(usage.get("candidatesTokenCount") or 0)
    input_cost = input_tokens * float(pricing.get("input_tokens", 0.0)) / 1_000_000
    output_cost = output_tokens * float(pricing.get("output_tokens", 0.0)) / 1_000_000
    usage_out = {
        "model": MODEL,
        "prompt_token_count": input_tokens,
        "candidate_token_count": output_tokens,
        "total_token_count": int(usage.get("totalTokenCount") or 0),
        "estimated_input_cost_usd": input_cost,
        "estimated_output_cost_usd": output_cost,
        "estimated_total_cost_usd": input_cost + output_cost,
        "raw_usage": usage,
    }
    (OUT_DIR / "usage.json").write_text(
        json.dumps(usage_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sentences = read_first_sentences(INPUT_FILE, 10)
    tokens = [token for sentence in sentences for token in sentence]
    system_prompt, user_prompt = build_prompts(sentences)

    (OUT_DIR / "input_10_sentences.bio").write_text(
        "\n\n".join("\n".join(f"{token} O" for token in sentence) for sentence in sentences) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")
    (OUT_DIR / "user_prompt.txt").write_text(user_prompt, encoding="utf-8")

    data = call_gemini(system_prompt, user_prompt)
    (OUT_DIR / "response.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = response_text(data)
    (OUT_DIR / "raw_atomic_output.txt").write_text(text, encoding="utf-8")
    write_usage(data)

    parsed = validate_output(text, tokens)
    (OUT_DIR / "validated_atomic_output.txt").write_text(
        "\n".join(f"{token} {label}" for token, label in parsed) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "validated_bio_output.bio").write_text(to_bio(sentences, parsed), encoding="utf-8")
    summary = {
        "input_file": str(INPUT_FILE),
        "sentence_count": len(sentences),
        "token_count": len(tokens),
        "validation": "passed",
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
