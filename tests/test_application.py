"""HTTP composition without external dictionaries, model weights or API calls."""

import gzip
import json
from pathlib import Path

import pytest
from flask import url_for

from db import db, User
from language_engine.application import create_app
from language_engine.http import dictionary_downloads, startup


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        startup, "init_all", lambda: pytest.fail("Fixture loaded neural resources")
    )
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "fixture-only",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        },
        prepare_database=False,
        load_resources=False,
    )
    with app.app_context():
        db.create_all()
        db.session.add(User(username="fixture", email="fixture@example.invalid"))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_all_original_http_paths_and_methods_are_registered(app):
    expected = json.loads((Path(__file__).parent / "fixtures/routes.json").read_text())
    actual = {rule.rule: rule for rule in app.url_map.iter_rules()}
    for row in expected:
        assert row["rule"] in actual, row
        rule = actual[row["rule"]]
        assert set(row["methods"]) <= rule.methods
        assert rule.endpoint.rsplit(".", 1)[-1] == row["function"]


def test_landing_and_public_metadata_without_model_assets(app):
    client = app.test_client()
    landing = client.get("/")
    assert landing.status_code == 200
    assert "le_vid=" in landing.headers["Set-Cookie"]
    assert client.get("/ping").json["ok"]
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/sitemap.xml").status_code == 200
    assert client.get("/api/lang_config?lang=ja").status_code == 200
    assert client.get("/reader").status_code == 200
    with app.test_request_context():
        assert url_for("pages.account_page") == "/account"


@pytest.mark.parametrize(
    "path",
    [
        "/api/user_dict/add",
        "/api/gemini_entry/update",
        "/api/entry_note/generate",
        "/api/entry_decomp/generate",
        "/api/llm_glosses",
        "/api/orth_breakdowns",
    ],
)
def test_paid_gates_survive_blueprint_namespacing(app, path):
    client = app.test_client()
    assert client.post(path, json={}).status_code == 401
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True
    response = client.post(path, json={})
    assert response.status_code == 403
    assert response.json["upgrade_required"] is True


def test_dictionary_cache_is_lazy_and_preserves_source_bytes(tmp_path, monkeypatch):
    tsv = tmp_path / "tiny.tsv"
    content = "headword\tglosses\n語\tword\n".encode("utf-8")
    tsv.write_bytes(content)
    cache = tmp_path / "cache"
    monkeypatch.setattr(dictionary_downloads, "_DICT_GZIP_CACHE_DIR", cache)
    monkeypatch.setattr(
        dictionary_downloads, "_DICT_GZIP_EVENT_LOG_PATH", cache / "events.jsonl"
    )
    monkeypatch.setattr(
        dictionary_downloads, "_resolve_dict_tsv_path", lambda *args, **kwargs: tsv
    )
    assert not cache.exists()
    first, version = dictionary_downloads._ensure_cached_gzip_tsv("ja")
    assert gzip.decompress(first.read_bytes()) == content
    stamp = first.stat().st_mtime_ns
    second, again = dictionary_downloads._ensure_cached_gzip_tsv("ja")
    assert (second, again) == (first, version)
    assert second.stat().st_mtime_ns == stamp


def test_factory_invokes_only_the_selected_resource_loader():
    calls = []
    first = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
        prepare_database=False,
        resource_loader=lambda app: calls.append(app),
    )
    second = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
        prepare_database=False,
        load_resources=False,
    )
    assert calls == [first]
    assert first is not second


def test_lookup_with_injected_nlp_preserves_surface_and_contract(app):
    calls = []

    def nlp(text, language, **options):
        calls.append((text, language))
        return {
            "text": text,
            "sentences": [
                {
                    "id": 1,
                    "text": text,
                    "tokens": [
                        {
                            "id": 1,
                            "text": "語",
                            "lemma": "語",
                            "upos": "NOUN",
                            "xpos": "NN",
                            "feats": "_",
                            "head": 0,
                            "deprel": "root",
                        }
                    ],
                }
            ],
        }

    app.extensions["language_engine.nlp_runner"] = nlp
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True
    result = client.post("/lookup", json={"q": "語", "lang": "ja"})
    assert result.status_code == 200
    assert result.json.get("ok", True)
    assert "語" in result.json["segments"]
    assert calls == [("語", "ja")]
