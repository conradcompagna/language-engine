"""
config.py — Application configuration for Language Engine.

Reads secrets from environment variables or a .env file.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_local_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()

# Trankit backend switch.
# 1 = compressed ONNX CPU pipeline, 0 = stock Trankit pipeline.
NEWPIPELINE = int(os.environ.get("NEWPIPELINE", "1"))

ENV_NAME = (os.environ.get("LE_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
IS_PRODUCTION = ENV_NAME in {"production", "prod"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Flask
SECRET_KEY = os.environ.get("LE_SECRET_KEY", "").strip()
if IS_PRODUCTION and not SECRET_KEY:
    raise RuntimeError("LE_SECRET_KEY must be set when LE_ENV=production or FLASK_ENV=production.")
if not SECRET_KEY:
    SECRET_KEY = "change-me-in-production-please"

# SQLite database (lives next to router.py)
DATABASE_URL = os.environ.get("LE_DATABASE_URL", f"sqlite:///{BASE_DIR / 'language_engine.db'}")

# Public production origin, for OAuth callbacks and Stripe return URLs.
# Example: https://languageengine.app
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

# Stripe
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_MONTHLY_PRICE_ID = os.environ.get("STRIPE_MONTHLY_PRICE_ID", "")  # Pro monthly ($10)
STRIPE_YEARLY_PRICE_ID = os.environ.get("STRIPE_YEARLY_PRICE_ID", "")  # Pro yearly ($100)

# Google OAuth (optional)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Google Translate API
GOOGLE_TRANSLATE_API_KEY = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
LE_GEMINI_COMMS_LOG = _env_bool("LE_GEMINI_COMMS_LOG", default=False)

# Production runtime switches
ENABLE_LEGACY_DOCUMENT_ROUTES = _env_bool(
    "LE_ENABLE_LEGACY_DOCUMENT_ROUTES", default=not IS_PRODUCTION
)
TRUST_PROXY_HEADERS = _env_bool("LE_TRUST_PROXY_HEADERS", default=IS_PRODUCTION)
ANALYTICS_ENABLED = _env_bool("LE_ANALYTICS_ENABLED", default=True)

# Contact/support email
CONTACT_TO_EMAIL = os.environ.get("CONTACT_TO_EMAIL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USERNAME or CONTACT_TO_EMAIL)
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# Free tier
FREE_LOOKUP_TOKENS_PER_DAY = int(os.environ.get("LE_FREE_LOOKUP_TOKENS", "1000"))
FREE_LOOKUPS_PER_DAY = FREE_LOOKUP_TOKENS_PER_DAY

# ---------------------------------------------------------------------------
# Subscription tiers & API budget caps (hard monthly caps)
# ---------------------------------------------------------------------------
# Tier names: "free", "pro"
# Monthly budget = 25% of subscription price; caps derived from Google API rates.
#
# Google Translate: $20/million chars  => $0.00002/char
# Gemini budget is tracked in USD using actual input/output token rates.
#
# Pro ($10/mo or $100/yr → $2.50/mo budget):
#   $0.50 translate + $2.00 Gemini
#   translate chars: 25000   gemini budget usd: 2.00

GEMINI_MODEL_PRICING_USD_PER_1M = {
    # Gemini Developer API pricing checked 2026-08-08.
    "gemini-3.1-flash-lite": {
        "input_tokens": 0.25,
        "output_tokens": 1.50,
    },
}

TIER_CAPS = {
    "free": {
        "mt_chars_per_month": 0,
        "llm_budget_usd_per_month": 0.0,
        "gemini_model": None,
    },
    "pro": {
        "mt_chars_per_month": 25_000,
        "llm_budget_usd_per_month": 2.00,
        "gemini_model": "gemini-3.1-flash-lite",
    },
}

# Hard output cap on Gemini responses (tokens)
GEMINI_MAX_OUTPUT_TOKENS = 2000
# Hard input cap on user query text (characters)
GEMINI_MAX_USER_QUERY_CHARS = 5000  # ~1000 words

# Subscription prices (display only — actual charge is set via Stripe Price ID)
MONTHLY_PRICE_PRO_USD = "10"
YEARLY_PRICE_PRO_USD = "100"
