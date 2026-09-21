"""Size collisions must never be promoted to verified model provenance."""
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / 'research/tools/check_provenance.py'


def test_size_candidates_require_matching_digest(tmp_path):
    deployed = tmp_path / 'deployed/language'
    deployed.mkdir(parents=True)
    (deployed / 'model.mdl').write_bytes(b'correct')
    runs = tmp_path / 'runs'
    for name, content in [('identical', b'correct'), ('collision', b'incorrc'), ('different', b'x')]:
        run = runs / ('trankit_save_' + name)
        run.mkdir(parents=True)
        (run / 'output.mdl').write_bytes(content)
    (runs / 'trankit_save_empty').mkdir()
    command = [sys.executable, str(SCRIPT), '--runs', str(runs), '--deployed', str(deployed.parent)]
    candidates = subprocess.check_output(command, text=True)
    assert 'trankit_save_collision | Candidate (size only)' in candidates
    assert 'Verified SHA-256 match' not in candidates
    verified = subprocess.check_output(command + ['--hash'], text=True)
    assert 'trankit_save_identical | Verified SHA-256 match' in verified
    assert 'trankit_save_collision | No match found' in verified
    assert 'trankit_save_empty | No model outputs found' in verified
    assert 'Abandoned' not in verified
