"""Captured pre-extraction display payloads, including form identity and Unicode."""
import copy
import json
from pathlib import Path

import pytest

from language_engine.http.serializers import (
    _build_hydrated_display_payload,
    _build_shared_base_payload,
    _hydrated_ref_key,
)

ROWS = json.loads((Path(__file__).parent / "fixtures/hydration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", ROWS)
def test_original_hydration_display_and_identity(row):
    before = copy.deepcopy(row["entry"])
    assert _build_hydrated_display_payload(row["entry"]) == row["display"]
    assert _hydrated_ref_key(row["entry"]) == row["ref"]
    assert row["entry"] == before


def test_shared_entry_does_not_inherit_a_matched_form():
    entry = ROWS[3]["entry"]
    result = _build_shared_base_payload(entry, "went", "en")
    assert result["headword"] == "go"
    assert result["ref_key"] == "sqlite|en|4"
    assert result["match_kind"] == "headword"
    assert "_storage_form_row_id" not in result
    assert entry["_storage_form_row_id"] == 7
