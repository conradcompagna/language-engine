"""Language policy, payload identity and provider transport without paid calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import gemini_dict
from language_engine.gemini import transport

CASES = json.loads(
    (Path(__file__).parent / "fixtures/gemini_contract.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES, ids=[case["function"] for case in CASES])
def test_pre_extraction_contract(case):
    result = getattr(gemini_dict, case["function"])(*case["args"])
    assert json.loads(json.dumps(result, ensure_ascii=False)) == case["expected"]


def test_provider_payload_and_usage(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 4,
                    "thoughtsTokenCount": 2,
                    "totalTokenCount": 16,
                },
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "pos": "noun",
                                            "glosses": "word",
                                            "romanization": "go",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
            },
        )

    monkeypatch.setattr(transport.requests, "post", post)
    result, usage = transport._call_gemini("語", "語を読む", "ja")
    assert result["headword"] == "語"
    assert result["romanization"] == "go"
    assert usage == {"prompt_tokens": 10, "response_tokens": 6, "total_tokens": 16}
    assert len(calls) == 1
    assert calls[0]["timeout"] == 30
    assert (
        "romanization"
        in calls[0]["json"]["generationConfig"]["responseSchema"]["required"]
    )


def test_generated_tsv_path_remains_at_repository_root():
    assert (
        gemini_dict.get_tsv_path("JA")
        == Path(__file__).resolve().parents[1] / "gemini_generated_tsvs/ja.tsv"
    )
