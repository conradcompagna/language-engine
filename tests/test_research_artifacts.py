"""Published shards reconstruct their historical artifacts exactly."""
import json
from pathlib import Path
import shutil

import pytest

from research.artifacts import reconstruct
from research.pipeline.dictionaries.japanese.data.rules import load_bundle
from research.pipeline.dictionaries.japanese.data.analyzer import JpInflectionAnalyzer

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / 'research/pipeline/dictionaries/japanese/data/rules'
MANIFESTS = [RULES / 'manifest.json',
    ROOT / 'research/evaluation/reports/grc_lsj_vs_wiktionary_samples/manifest.json',
    ROOT / 'research/experiments/sanskrit-vedic-v1/run_logs/tokenize/manifest.json']


@pytest.mark.parametrize('manifest', MANIFESTS)
def test_historical_artifact_reconstruction(manifest):
    assert reconstruct(manifest)


def test_analyzer_loads_complete_rule_families():
    original = json.loads(reconstruct(RULES / 'manifest.json'))
    assert load_bundle(RULES) == original
    analyzer = JpInflectionAnalyzer()
    assert analyzer.token_rules == original['token_morph_rules']
    assert analyzer.validation_rows == original['validation_examples']
    assert len(analyzer.token_rules) == 124


def test_corrupt_shard_is_rejected(tmp_path):
    shutil.copytree(RULES, tmp_path / 'rules')
    (tmp_path / 'rules/metadata.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        reconstruct(tmp_path / 'rules/manifest.json')
