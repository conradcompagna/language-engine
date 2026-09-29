"""Dependency-free BIO preflight and provenance for future NER runs."""
from collections import Counter
from hashlib import sha256
from importlib import metadata
from pathlib import Path
import platform
import re


def inspect_bio(path: Path) -> tuple[dict, set[tuple[str, ...]]]:
    data = path.read_bytes()
    sentences = []
    tokens = []
    labels = Counter()
    for number, raw in enumerate(data.decode("utf-8-sig").splitlines() + [""], 1):
        if not raw.strip():
            if tokens:
                sentences.append(tuple(tokens))
                tokens = []
            continue
        columns = raw.split()
        if len(columns) != 2 or not re.fullmatch(r"O|[BIES]-\S+", columns[-1]):
            raise ValueError(f"{path.name}:{number}: expected token and BIO/BIOES label")
        tokens.append(columns[0])
        labels[columns[1]] += 1
    if not sentences:
        raise ValueError(f"{path.name}: empty BIO corpus")
    return {
        "name": path.name, "sha256": sha256(data).hexdigest(), "bytes": len(data),
        "sentences": len(sentences), "tokens": sum(labels.values()), "labels": dict(sorted(labels.items())),
    }, set(sentences)


def inspect_split(train: Path, dev: Path) -> dict:
    train_info, train_sentences = inspect_bio(train)
    dev_info, dev_sentences = inspect_bio(dev)
    overlap = train_sentences & dev_sentences
    if overlap:
        raise ValueError(f"Train/dev leakage: {len(overlap)} identical token sequences across splits")
    return {"train": train_info, "dev": dev_info, "exact_sentence_overlap": 0}


def environment_evidence() -> dict:
    versions = {}
    for package in ("trankit", "torch", "transformers", "numpy"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {"python": platform.python_version(), "packages": versions}


def file_evidence(path: Path) -> dict:
    digest = sha256()
    length = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            length += len(chunk)
            digest.update(chunk)
    return {"name": path.name, "bytes": length, "sha256": digest.hexdigest()}
