"""Gemini prompts service."""

from .morphology import _POS_ENUM


def _build_response_schema(requires_roman: bool, inflects: bool) -> dict:
    """Per-call schema. Only includes fields the model is allowed/required to emit."""
    props: dict = {}
    ordering: list[str] = []
    required: list[str] = []

    if requires_roman:
        props["romanization"] = {
            "type": "string",
            "description": "MANDATORY romanization of the target word (non-Latin script language).",
        }
        ordering.append("romanization")
        required.append("romanization")

    props["pos"] = {
        "type": "string",
        "enum": _POS_ENUM,
        "description": "Choose the best matching part of speech.",
    }
    ordering.append("pos")
    required.append("pos")

    props["glosses"] = {
        "type": "string",
        "description": "1-5 short English glosses explaining the meaning of the target word separated by semicolons.",
    }
    ordering.append("glosses")
    required.append("glosses")

    if inflects:
        props["lemma"] = {
            "type": "string",
            "description": (
                "MANDATORY: lemmatize the word, reducing it to its uninflected base form."
            ),
        }
        props["morphological properties"] = {
            "type": "string",
            "description": (
                "MANDATORY: brief labels tagging the surface form's morphological "
                "properties using full unabbreviated Universal Dependencies category names "
                "(e.g. case, number, gender, animacy, noun class, person, tense, aspect, "
                "mood, voice, verb form, definiteness, degree, pronoun type, polarity, "
                "politeness, clusivity, evidentiality)."
            ),
        }
        ordering.extend(["lemma", "morphological properties"])
        required.extend(["lemma", "morphological properties"])

    return {
        "type": "object",
        "propertyOrdering": ordering,
        "properties": props,
        "required": required,
    }


def _build_system_prompt(requires_roman: bool, inflects: bool) -> str:
    parts = [
        "You are a dictionary entry generator for a commercial reader app.",
        "You are to analyze the surface form of the word provided to you.",
        "Choose the best part of speech from the selection provided, and provide 1-5 concise English"
        " glosses explaining the meaning of the target word.",
    ]
    if requires_roman:
        parts.append(
            "The target is written in a non-Latin script: you MUST provide an accurate romanization."
        )
    if inflects:
        parts.append(
            "If the word is inflected, you MUST lemmatize it, reducing it to its uninflected base form,"
            " and provide brief labels tagging its morphological properties using full unabbreviated"
            " Universal Dependencies category names (e.g. case, number, gender, animacy, person,"
            " tense, aspect, mood, voice, degree, verb form, definiteness, pronoun type, polarity,"
            " politeness, clusivity)."
        )
        parts.append(
            "Examples:\n"
            "  Latin — portārum (noun): lemma=porta, morphological properties=genitive plural feminine\n"
            "  Russian — писала (verb): lemma=писать, morphological properties=past tense, feminine, singular\n"
            "  German — schönsten (adj): lemma=schön, morphological properties=superlative degree, dative plural\n"
            "  Ancient Greek — ἔλυσαν (verb): lemma=λύω, morphological properties=aorist tense, active voice, third person plural\n"
            "  Sanskrit — rājñaḥ (noun): lemma=rājan, morphological properties=genitive singular masculine"
        )
    else:
        parts.append(
            "This word does not inflect: DO NOT output `lemma` or `morphological properties` fields."
        )
        parts.append(
            "Examples:\n"
            "  French — vite (adv): glosses=quickly; fast\n"
            "  Turkish — ev (noun): glosses=house; home\n"
            "  Indonesian — pergi (verb): glosses=go; leave; depart\n"
            "  Swahili — haraka (adv): glosses=quickly; hastily\n"
            "  Vietnamese — đẹp (adj): glosses=beautiful; pretty; attractive"
        )
    return " ".join(parts)
