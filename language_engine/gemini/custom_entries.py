"""Gemini custom entries service."""

from dict_lookup_sqlite import (
    delete_custom_form_index_entry,
    ensure_custom_form_index,
    sync_custom_form_index_entry,
)
import json
import uuid
from .legacy_tsv import _tsv_escape

CUSTOM_TSV_HEADER = (
    "entry_id\theadword\tromanization\tpos\tglosses\tforms\tcommentary\tlemma\tsource"
)


def _json_load_list(raw, default=None):
    if default is None:
        default = []
    if raw is None:
        return list(default)
    if isinstance(raw, list):
        return list(raw)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (TypeError, ValueError):
        pass
    return list(default)


def _normalize_glosses(glosses) -> list[str]:
    if isinstance(glosses, str):
        glosses = [g.strip() for g in glosses.split(";") if g.strip()]
    out = []
    seen = set()
    for gloss in glosses or []:
        text = str(gloss or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    if len(out) >= 3 and all(len(g) == 1 for g in out):
        merged = "".join(out).strip()
        if merged:
            return [merged]
    return out


def _normalize_forms(forms) -> list[list[str]]:
    out = []
    for form in forms or []:
        if not isinstance(form, (list, tuple)):
            continue
        word = str(form[0] if len(form) > 0 else "").strip()
        tags = str(form[1] if len(form) > 1 else "").strip()
        roman = str(form[2] if len(form) > 2 else "").strip()
        if not word:
            continue
        out.append([word, tags, roman])
    return out


def _glosses_to_senses(glosses: list[str], source: str = "") -> list[dict]:
    senses = [{"glosses": [g]} for g in _normalize_glosses(glosses)]
    src = str(source or "").strip().lower()
    if src == "user_created":
        senses.append({"_source": "user_created"})
    return senses


def _entry_model_to_frontend(entry) -> dict:
    glosses = []
    for sense in _json_load_list(entry.glosses_json):
        if isinstance(sense, dict):
            for gloss in sense.get("glosses") or []:
                text = str(gloss or "").strip()
                if text:
                    glosses.append(text)
    return {
        "entry_id": entry.entry_id,
        "entry_row_id": entry.id,
        "db_alias": "customdb",
        "headword": entry.headword or "",
        "pos": entry.pos or "",
        "romanization": entry.romanization or "",
        "glosses": _normalize_glosses(glosses),
        "forms": _normalize_forms(_json_load_list(entry.forms_json)),
        "commentary": entry.commentary or "",
        "lemma": entry.lemma or "",
        "source": entry.source or "gemini",
    }


def _entry_to_frontend(entry) -> dict:
    if hasattr(entry, "entry_id") and hasattr(entry, "glosses_json"):
        return _entry_model_to_frontend(entry)
    glosses = entry.get("glosses") or []
    if isinstance(glosses, str):
        glosses = [g.strip() for g in glosses.split(";") if g.strip()]
    result = {
        "entry_id": entry.get("entry_id", ""),
        "headword": entry.get("headword", ""),
        "pos": entry.get("pos", ""),
        "romanization": entry.get("romanization", ""),
        "glosses": _normalize_glosses(glosses),
        "forms": _normalize_forms(entry.get("forms") or []),
        "commentary": entry.get("commentary", ""),
        "lemma": entry.get("canonical_form", "") or entry.get("lemma", ""),
        "source": entry.get("source", "gemini"),
    }
    row_id = entry.get("entry_row_id") or entry.get("id")
    if row_id:
        result["entry_row_id"] = int(row_id)
        result["db_alias"] = str(entry.get("db_alias") or "customdb")
    return result


def _store_generated_entry_db(lang_code: str, entry: dict):
    source = str(entry.get("source") or "gemini").strip().lower() or "gemini"
    return upsert_custom_entry(
        lang_code=lang_code,
        headword=str(entry.get("headword", "")).strip(),
        romanization=str(entry.get("romanization", "") or "").strip(),
        pos=str(entry.get("pos", "") or "").strip(),
        glosses=entry.get("glosses") or [],
        forms=entry.get("forms") or [],
        commentary=str(entry.get("commentary", "") or "").strip(),
        lemma=str(
            entry.get("canonical_form", "") or entry.get("lemma", "") or ""
        ).strip(),
        source=source,
    )


def _query_custom_entry(lang_code: str, headword: str = "", entry_id: str = ""):
    from db import CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    eid = str(entry_id or "").strip()
    hw = str(headword or "").strip()
    q = CustomDictEntry.query
    if eid:
        return q.filter_by(entry_id=eid).first()
    if not lang or not hw:
        return None
    return q.filter_by(language=lang, headword=hw).first()


def upsert_custom_entry(
    lang_code: str,
    headword: str,
    romanization: str = "",
    pos: str = "",
    glosses=None,
    forms=None,
    commentary: str = "",
    lemma: str = "",
    source: str = "gemini",
    entry_id: str = "",
):
    from db import db, CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    hw = str(headword or "").strip()
    if not lang or not hw:
        return None

    src = str(source or "gemini").strip().lower() or "gemini"
    entry = _query_custom_entry(lang, headword=hw, entry_id=entry_id)
    if not entry:
        entry = CustomDictEntry(
            entry_id=str(entry_id or uuid.uuid4().hex),
            language=lang,
            headword=hw,
        )
        db.session.add(entry)

    entry.romanization = str(romanization or "").strip() or None
    entry.pos = str(pos or "").strip() or None
    entry.glosses_json = json.dumps(
        _glosses_to_senses(glosses, src), ensure_ascii=False
    )
    entry.forms_json = json.dumps(_normalize_forms(forms), ensure_ascii=False)
    entry.commentary = str(commentary or "").strip() or None
    entry.lemma = str(lemma or "").strip() or None
    entry.source = src
    db.session.commit()
    sync_custom_form_index_entry(entry.id, entry.language, entry.forms_json)
    return entry


def iter_custom_entry_tsv_lines(lang_code: str, batch_size: int = 500):
    from db import CustomDictEntry

    lang = str(lang_code or "").strip().lower()
    yield CUSTOM_TSV_HEADER + "\n"
    if not lang:
        return

    q = (
        CustomDictEntry.query.filter_by(language=lang)
        .filter(
            (CustomDictEntry.source == "gemini") | (CustomDictEntry.source.is_(None))
        )
        .order_by(CustomDictEntry.id.asc())
        .yield_per(batch_size)
    )
    for entry in q:
        normalized_glosses = _entry_model_to_frontend(entry)["glosses"]
        row = [
            _tsv_escape(entry.entry_id or ""),
            _tsv_escape(entry.headword or ""),
            _tsv_escape(entry.romanization or ""),
            _tsv_escape(entry.pos or ""),
            json.dumps(
                _glosses_to_senses(normalized_glosses, entry.source or "gemini"),
                ensure_ascii=False,
            ),
            json.dumps(
                _normalize_forms(_json_load_list(entry.forms_json)), ensure_ascii=False
            ),
            _tsv_escape(entry.commentary or ""),
            _tsv_escape(entry.lemma or ""),
            _tsv_escape(entry.source or "gemini"),
        ]
        yield "\t".join(row) + "\n"


def get_tsv_text(lang_code: str) -> str:
    return "".join(iter_custom_entry_tsv_lines(lang_code))


def headword_exists(lang_code: str, headword: str) -> bool:
    return _query_custom_entry(lang_code, headword=headword) is not None


def append_user_entry(
    lang_code: str,
    headword: str,
    romanization: str,
    pos: str,
    glosses: list[str],
    forms: list | None = None,
):
    return upsert_custom_entry(
        lang_code=lang_code,
        headword=headword,
        romanization=romanization or "",
        pos=pos or "",
        glosses=glosses or [],
        forms=forms or [],
        commentary="",
        lemma="",
        source="user_created",
    )


def update_tsv_entry(
    lang_code: str,
    headword: str,
    new_romanization: str | None = None,
    new_pos: str | None = None,
    new_glosses: list[str] | None = None,
    new_forms: list | None = None,
    new_commentary: str | None = None,
    new_lemma: str | None = None,
    entry_id: str = "",
):
    entry = _query_custom_entry(lang_code, headword=headword, entry_id=entry_id)
    if not entry:
        return None

    glosses = None
    if new_glosses is not None:
        glosses = new_glosses
    else:
        existing_glosses = []
        for sense in _json_load_list(entry.glosses_json):
            if isinstance(sense, dict):
                existing_glosses.extend(
                    [
                        str(g or "").strip()
                        for g in (sense.get("glosses") or [])
                        if str(g or "").strip()
                    ]
                )

    forms = _normalize_forms(
        new_forms if new_forms is not None else _json_load_list(entry.forms_json)
    )
    updated = upsert_custom_entry(
        lang_code=entry.language,
        headword=entry.headword,
        romanization=(
            new_romanization
            if new_romanization is not None
            else (entry.romanization or "")
        ),
        pos=(new_pos if new_pos is not None else (entry.pos or "")),
        glosses=(glosses if glosses is not None else existing_glosses),
        forms=forms,
        commentary=(
            new_commentary if new_commentary is not None else (entry.commentary or "")
        ),
        lemma=(new_lemma if new_lemma is not None else (entry.lemma or "")),
        source=entry.source or "gemini",
        entry_id=entry.entry_id,
    )
    return updated


def remove_tsv_entry(lang_code: str, headword: str, entry_id: str = "") -> bool:
    from db import db

    entry = _query_custom_entry(lang_code, headword=headword, entry_id=entry_id)
    if not entry:
        return False
    entry_pk = int(entry.id or 0)
    db.session.delete(entry)
    db.session.commit()
    delete_custom_form_index_entry(entry_pk)
    return True
