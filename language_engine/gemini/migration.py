"""Gemini migration service."""

from dict_lookup_sqlite import (
    delete_custom_form_index_entry,
    ensure_custom_form_index,
    sync_custom_form_index_entry,
)
import json
import uuid
from .custom_entries import _glosses_to_senses, _json_load_list, _normalize_forms
from .legacy_tsv import _parse_tsv_rows
from .settings import TSV_DIR


def migrate_legacy_custom_entries():
    from db import db, CustomDictEntry

    if CustomDictEntry.query.first():
        ensure_custom_form_index()
        return

    existing_pairs = {
        (str(e.language or "").strip().lower(), str(e.headword or "").strip())
        for e in CustomDictEntry.query.with_entities(
            CustomDictEntry.language, CustomDictEntry.headword
        ).all()
    }

    def import_row(lang_code: str, row: dict, fallback_source: str = "gemini"):
        lang = str(lang_code or "").strip().lower()
        headword = str(row.get("headword", "") or "").strip()
        if not lang or not headword:
            return
        key = (lang, headword)
        if key in existing_pairs:
            return

        glosses_raw = row.get("glosses", "[]")
        glosses = []
        detected_source = (
            str(row.get("source", "") or fallback_source or "gemini").strip().lower()
            or "gemini"
        )
        try:
            parsed = json.loads(glosses_raw)
            if isinstance(parsed, list):
                for sense in parsed:
                    if isinstance(sense, dict) and sense.get("_source"):
                        detected_source = (
                            str(sense.get("_source") or detected_source).strip().lower()
                            or detected_source
                        )
                        continue
                    if isinstance(sense, dict):
                        for gloss in sense.get("glosses") or []:
                            text = str(gloss or "").strip()
                            if text:
                                glosses.append(text)
        except (TypeError, ValueError):
            pass

        forms = _normalize_forms(_json_load_list(row.get("forms", "[]")))
        entry = CustomDictEntry(
            entry_id=uuid.uuid4().hex,
            language=lang,
            headword=headword,
            romanization=str(row.get("romanization", "") or "").strip() or None,
            pos=str(row.get("pos", "") or "").strip() or None,
            glosses_json=json.dumps(
                _glosses_to_senses(glosses, detected_source), ensure_ascii=False
            ),
            forms_json=json.dumps(forms, ensure_ascii=False),
            commentary=str(row.get("commentary", "") or "").strip() or None,
            lemma=str(row.get("lemma", "") or "").strip() or None,
            source=detected_source,
        )
        db.session.add(entry)
        existing_pairs.add(key)

    TSV_DIR.mkdir(exist_ok=True)
    for path in sorted(TSV_DIR.glob("*.tsv")):
        lang = path.stem.strip().lower()
        _header, rows = _parse_tsv_rows(path)
        if not rows:
            continue
        for row in rows:
            import_row(lang, row, fallback_source="gemini")
        db.session.commit()

    db.session.commit()
    ensure_custom_form_index(force_rebuild=True)
