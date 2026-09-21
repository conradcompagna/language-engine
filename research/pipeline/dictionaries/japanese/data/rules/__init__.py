"""Load the ordered Japanese morphology rule families without external assets."""
import hashlib
import json
from pathlib import Path


def load_bundle(directory: Path):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('kind') != 'json-families':
        raise ValueError('Unsupported morphology manifest')
    bundle = {}
    for entry in manifest['entries']:
        values = []
        for part in entry['parts']:
            path = (directory / part['path']).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError('Rule path escapes data directory')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != part['sha256']:
                raise ValueError(f'Rule checksum mismatch: {part["path"]}')
            values.append(json.loads(data))
        bundle[entry['key']] = values[0] if entry['combine'] == 'single' else [row for value in values for row in value]
    return bundle
