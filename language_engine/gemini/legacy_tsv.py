"""Gemini legacy tsv service."""

from pathlib import Path
import json
from .settings import LEGACY_TSV_HEADER, TSV_DIR, TSV_HEADER


def get_tsv_path(lang_code: str) -> Path:
    return TSV_DIR / f"{lang_code.lower()}.tsv"


def _parse_tsv_rows(path: Path) -> tuple[str, list[dict]]:
    """Read a TSV file and return (header_line, list_of_row_dicts).

    Each row dict has keys matching the header columns.
    """
    if not path.exists() or path.stat().st_size == 0:
        return "", []

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return "", []

    header = lines[0].strip()
    cols = header.split("\t")
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        fields = line.split("\t")
        row = {}
        for i, col in enumerate(cols):
            row[col] = fields[i] if i < len(fields) else ""
        rows.append(row)
    return header, rows


def _write_tsv_file(path: Path, header: str, rows: list[dict]):
    """Rewrite the entire TSV file from header + row dicts.
    Automatically upgrades old headers to include commentary and lemma columns."""
    # Upgrade old 5-column header to new 7-column header
    if header == "headword\tromanization\tpos\tglosses\tforms":
        header = TSV_HEADER
    cols = header.split("\t")
    lines = [header]
    for row in rows:
        fields = [str(row.get(c, "")) for c in cols]
        lines.append("\t".join(fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _write_entry(lang_code: str, entry: dict):
    """Write an entry to the TSV as a singleton row.

    The surface form is always the headword.  The canonical/lemma form
    (if different) and Gemini's commentary tags are stored in their own
    columns so the edit UI can display them.
    """
    TSV_DIR.mkdir(exist_ok=True)
    path = get_tsv_path(lang_code)

    # Parse glosses to senses format
    glosses_raw = entry.get("glosses") or ""
    if isinstance(glosses_raw, str):
        gloss_list = [g.strip() for g in glosses_raw.split(";") if g.strip()]
    else:
        gloss_list = glosses_raw
    senses = [{"glosses": [g]} for g in gloss_list]

    entry["forms"] = entry.get("forms") or []
    _append_tsv_row(path, entry, senses)


def _append_tsv_row(path: Path, entry: dict, senses: list[dict]):
    """Append a single new row to the TSV file."""
    forms = entry.get("forms") or []
    commentary = _tsv_escape(entry.get("commentary", ""))
    lemma = _tsv_escape(entry.get("canonical_form", "") or entry.get("lemma", ""))

    existing_header = ""
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing_header = (f.readline() or "").strip()
        except Exception:
            existing_header = ""

    OLD_COMPACT_HEADER = "headword\tromanization\tpos\tglosses\tforms"

    if existing_header == LEGACY_TSV_HEADER:
        row = "\t".join(
            [
                _tsv_escape(entry.get("headword", "")),
                _tsv_escape(entry.get("romanization", "")),
                _tsv_escape(entry.get("pos", "")),
                json.dumps(senses, ensure_ascii=False),
                "",
                "[]",
                json.dumps(forms, ensure_ascii=False),
            ]
        )
    else:
        # Migrate old 5-column header to new 7-column header on first new append
        if existing_header == OLD_COMPACT_HEADER:
            _migrate_tsv_header(path, OLD_COMPACT_HEADER, TSV_HEADER)

        row = "\t".join(
            [
                _tsv_escape(entry.get("headword", "")),
                _tsv_escape(entry.get("romanization", "")),
                _tsv_escape(entry.get("pos", "")),
                json.dumps(senses, ensure_ascii=False),
                json.dumps(forms, ensure_ascii=False),
                commentary,
                lemma,
            ]
        )

    needs_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        if needs_header:
            f.write(TSV_HEADER + "\n")
        f.write(row + "\n")


def _migrate_tsv_header(path: Path, old_header: str, new_header: str):
    """Replace the first line of a TSV file to upgrade the header.
    Existing rows keep their original columns; new columns will be empty."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith(old_header):
            content = new_header + content[len(old_header) :]
            path.write_text(content, encoding="utf-8", newline="")
    except Exception:
        pass


def _tsv_escape(s: str) -> str:
    """Escape tabs and newlines for TSV safety."""
    return str(s).replace("\t", " ").replace("\n", " ").replace("\r", "")
