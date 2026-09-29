"""Reconstruct published research artifacts from ordered, hash-checked manifests.

Usage: python research/artifacts.py PATH/manifest.json --output /tmp/original
Omit --output to verify without writing. No model or private data is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _part(root: Path, entry: dict) -> bytes:
    path = (root / entry['path']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Artifact part escapes manifest directory')
    data = path.read_bytes()
    if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise ValueError(f'Artifact part checksum mismatch: {entry["path"]}')
    return data


def reconstruct(manifest_path: Path) -> bytes:
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema') != 1:
        raise ValueError('Unsupported artifact manifest schema')
    root = manifest_path.parent
    kind = manifest['kind']
    if kind == 'text-concat':
        result = b''.join(_part(root, entry) for entry in manifest['entries'])
    else:
        data = {}
        if kind == 'json-families':
            for entry in manifest['entries']:
                parts = [json.loads(_part(root, part)) for part in entry['parts']]
                if entry['combine'] == 'single' and len(parts) == 1:
                    value = parts[0]
                elif entry['combine'] == 'list' and all(isinstance(part, list) for part in parts):
                    value = [item for part in parts for item in part]
                else:
                    raise ValueError('Invalid family combination')
                if entry['key'] in data:
                    raise ValueError('Duplicate family key')
                data[entry['key']] = value
        elif kind == 'json-records':
            for entry in manifest['entries']:
                part = json.loads(_part(root, entry))
                if data.keys() & part.keys():
                    raise ValueError('Duplicate record key')
                data.update(part)
        else:
            raise ValueError(f'Unsupported artifact kind: {kind}')
        result = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    if len(result) != manifest['original_bytes'] or hashlib.sha256(result).hexdigest() != manifest['original_sha256']:
        raise ValueError('Reconstructed artifact differs from original')
    return result


def load_json(manifest_path: Path):
    return json.loads(reconstruct(manifest_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = reconstruct(args.manifest)
    if args.output:
        args.output.write_bytes(data)
    print(f'Verified {len(data)} bytes; SHA-256 {hashlib.sha256(data).hexdigest()}')


if __name__ == '__main__':
    main()
