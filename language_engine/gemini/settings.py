"""Gemini settings service."""

from config import GEMINI_API_KEY
from pathlib import Path
import logging

log = logging.getLogger(__name__)


GEMINI_DICT_ENABLED = True


GEMINI_DICT_MODEL = "gemini-3.1-flash-lite"


TSV_DIR = Path(__file__).resolve().parents[2] / "gemini_generated_tsvs"


TSV_HEADER = "headword\tromanization\tpos\tglosses\tforms\tcommentary\tlemma"


LEGACY_TSV_HEADER = "headword\tromanization\tpos\tglosses\tlabel\tlemma\tforms"


def is_enabled() -> bool:
    return bool(GEMINI_DICT_ENABLED and GEMINI_API_KEY)
