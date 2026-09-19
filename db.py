"""
db.py — SQLAlchemy models for Language Engine user accounts & subscriptions.

Tables:
  - User: email/password auth, email verification, optional Google OAuth ID
  - Subscription: Stripe subscription state (with tier)
  - AccountActionToken: expiring tokens for password reset, email verification, and email change
  - LookupQuota: daily lookup counter per user
  - ApiUsage: monthly API budget tracking (MT chars + Gemini tokens)
  - SyntheticEntry: cached Google Translate glosses for unknown tokens
  - CustomDictEntry: unified SQLite-backed custom entries
  - EntryNote: shared notes on dictionary entries
  - EntryDecomp: shared morpheme decompositions
"""
import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # null for Google-only users
    password_length = db.Column(db.Integer, nullable=True)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)

    # Stripe
    stripe_customer_id = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    subscription = db.relationship("Subscription", backref="user", uselist=False, lazy=True)
    quota = db.relationship("LookupQuota", backref="user", uselist=False, lazy=True)
    api_usage = db.relationship("ApiUsage", backref="user", uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        self.password_length = len(password or "")

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # Emails that always get premium access (admin/owner accounts)
    PREMIUM_EMAILS = set()

    @property
    def is_subscribed(self):
        if self.email and self.email.lower() in self.PREMIUM_EMAILS:
            return True
        return (
            self.subscription is not None
            and self.subscription.status in ("active", "trialing")
        )

    @property
    def tier(self):
        """Return 'free' or 'pro'."""
        if self.email and self.email.lower() in self.PREMIUM_EMAILS:
            return "pro"
        if self.subscription and self.subscription.status in ("active", "trialing"):
            return "pro"
        return "free"


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=True)
    status = db.Column(db.String(50), default="inactive")  # active, canceled, past_due, inactive
    tier = db.Column(db.String(20), default="pro")
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AccountActionToken(db.Model):
    __tablename__ = "account_action_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    purpose = db.Column(db.String(40), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class LookupQuota(db.Model):
    __tablename__ = "lookup_quotas"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    count = db.Column(db.Integer, default=0)  # Daily Trankit token count for free lookup gating.
    date = db.Column(db.Date, default=datetime.date.today)

    def reset_if_new_day(self):
        today = datetime.date.today()
        if self.date != today:
            self.count = 0
            self.date = today

    def increment(self, amount=1):
        self.reset_if_new_day()
        try:
            amount = int(amount or 0)
        except (TypeError, ValueError):
            amount = 0
        self.count += max(0, amount)

    @property
    def remaining(self):
        from config import FREE_LOOKUP_TOKENS_PER_DAY
        self.reset_if_new_day()
        return max(0, FREE_LOOKUP_TOKENS_PER_DAY - self.count)


# ---------------------------------------------------------------------------
# Analytics — local aggregate counters for production operations
# ---------------------------------------------------------------------------

class AnalyticsDaily(db.Model):
    __tablename__ = "analytics_daily"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True, index=True)

    landing_visits = db.Column(db.Integer, default=0)
    landing_unique_visitors = db.Column(db.Integer, default=0)
    checkout_attempts = db.Column(db.Integer, default=0)

    lookup_requests = db.Column(db.Integer, default=0)
    lookup_tokens = db.Column(db.Integer, default=0)
    lookup_dp_only_requests = db.Column(db.Integer, default=0)

    trankit_run_count = db.Column(db.Integer, default=0)
    trankit_run_ms_total = db.Column(db.Integer, default=0)
    trankit_wait_count = db.Column(db.Integer, default=0)
    trankit_wait_ms_total = db.Column(db.Integer, default=0)
    trankit_wait_ms_max = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )


class AnalyticsLanguageDaily(db.Model):
    __tablename__ = "analytics_language_daily"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    language = db.Column(db.String(20), nullable=False, index=True)

    lookup_requests = db.Column(db.Integer, default=0)
    lookup_tokens = db.Column(db.Integer, default=0)
    lookup_dp_only_requests = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("date", "language", name="uq_analytics_language_daily"),
    )


class AnalyticsVisitorDay(db.Model):
    __tablename__ = "analytics_visitor_days"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    visitor_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("date", "visitor_hash", name="uq_analytics_visitor_day"),
    )


# ---------------------------------------------------------------------------
# API Usage — hard monthly budget caps (resets on billing period)
# ---------------------------------------------------------------------------

class ApiUsage(db.Model):
    __tablename__ = "api_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)

    # Google Translate character counter
    mt_chars_used = db.Column(db.Integer, default=0)

    # Legacy Gemini query counter (no longer incremented)
    llm_queries_used = db.Column(db.Integer, default=0)
    # Gemini token counters
    llm_prompt_tokens_used = db.Column(db.Integer, default=0)
    llm_output_tokens_used = db.Column(db.Integer, default=0)
    llm_tokens_used = db.Column(db.Integer, default=0)

    # Billing period start — resets counters when a new period begins
    period_start = db.Column(db.Date, default=datetime.date.today)

    def _maybe_reset(self, user):
        """Reset counters if the billing period has rolled over."""
        today = datetime.date.today()
        if not self.period_start:
            self.period_start = today
        reset_date = self.period_start
        if user.subscription and user.subscription.current_period_end:
            # If past the period end, new period started
            if today >= user.subscription.current_period_end.date():
                reset_date = today
        # Fallback: reset every 30 days from period_start
        if (today - self.period_start).days >= 30:
            reset_date = today
        if reset_date != self.period_start:
            self.mt_chars_used = 0
            self.llm_queries_used = 0
            self.llm_prompt_tokens_used = 0
            self.llm_output_tokens_used = 0
            self.llm_tokens_used = 0
            self.period_start = reset_date

    def can_use_mt(self, chars, user):
        from config import TIER_CAPS
        self._maybe_reset(user)
        cap = TIER_CAPS.get(user.tier, {}).get("mt_chars_per_month", 0)
        return self.mt_chars_used + chars <= cap

    def record_mt(self, chars):
        self.mt_chars_used += chars

    def can_use_llm(self, user):
        self._maybe_reset(user)
        return self.llm_cost_usd(user) < self.llm_budget_usd(user)

    def record_llm(self, prompt_tokens=0, output_tokens=0):
        prompt_tokens = max(0, int(prompt_tokens or 0))
        output_tokens = max(0, int(output_tokens or 0))
        self.llm_prompt_tokens_used = int(self.llm_prompt_tokens_used or 0) + prompt_tokens
        self.llm_output_tokens_used = int(self.llm_output_tokens_used or 0) + output_tokens
        self.llm_tokens_used = int(self.llm_tokens_used or 0) + prompt_tokens + output_tokens

    def llm_budget_usd(self, user):
        from config import TIER_CAPS
        self._maybe_reset(user)
        return float(TIER_CAPS.get(user.tier, {}).get("llm_budget_usd_per_month", 0.0) or 0.0)

    def llm_cost_usd(self, user):
        from config import TIER_CAPS, GEMINI_MODEL_PRICING_USD_PER_1M
        self._maybe_reset(user)
        model = str(TIER_CAPS.get(user.tier, {}).get("gemini_model") or "").strip()
        pricing = GEMINI_MODEL_PRICING_USD_PER_1M.get(model, {})
        input_rate = float(pricing.get("input_tokens", 0.0) or 0.0)
        output_rate = float(pricing.get("output_tokens", 0.0) or 0.0)
        return (
            (float(self.llm_prompt_tokens_used or 0) / 1_000_000.0) * input_rate
            + (float(self.llm_output_tokens_used or 0) / 1_000_000.0) * output_rate
        )

    def llm_usage_percent(self, user):
        budget = self.llm_budget_usd(user)
        if budget <= 0:
            return 0.0
        return (self.llm_cost_usd(user) / budget) * 100.0


# ---------------------------------------------------------------------------
# Synthetic entries — cached MT glosses from Google Translate
# ---------------------------------------------------------------------------

class SyntheticEntry(db.Model):
    __tablename__ = "synthetic_entries"

    id = db.Column(db.Integer, primary_key=True)
    headword = db.Column(db.String(500), nullable=False)
    language = db.Column(db.String(20), nullable=False)
    mt_gloss = db.Column(db.Text, nullable=False)        # frozen original MT translation
    source = db.Column(db.String(50), default="google_translate")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Unique per headword+language
    __table_args__ = (
        db.UniqueConstraint("headword", "language", name="uq_synthetic_headword_lang"),
    )

# ---------------------------------------------------------------------------
# Custom dictionary entries
# ---------------------------------------------------------------------------

class CustomDictEntry(db.Model):
    __tablename__ = "custom_dict_entries"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    language = db.Column(db.String(20), nullable=False, index=True)
    headword = db.Column(db.String(500), nullable=False)
    romanization = db.Column(db.String(500), nullable=True)
    pos = db.Column(db.String(100), nullable=True)
    glosses_json = db.Column(db.Text, nullable=False, default="[]")
    forms_json = db.Column(db.Text, nullable=False, default="[]")
    commentary = db.Column(db.Text, nullable=True)
    lemma = db.Column(db.String(500), nullable=True)
    source = db.Column(db.String(50), nullable=False, default="gemini")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("language", "headword", name="uq_custom_dict_entry_lang_head"),
    )


# ---------------------------------------------------------------------------
# Entry notes — community wiki-style notes on dictionary entries
# ---------------------------------------------------------------------------

class EntryNote(db.Model):
    __tablename__ = "entry_notes"

    id = db.Column(db.Integer, primary_key=True)
    language = db.Column(db.String(20), nullable=False)
    db_alias = db.Column(db.String(100), nullable=False)
    entry_row_id = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("language", "db_alias", "entry_row_id", name="uq_entry_note_lang_alias_row"),
    )


# ---------------------------------------------------------------------------
# Entry morpheme decompositions — Leipzig-style breakdowns
# ---------------------------------------------------------------------------

class EntryDecomp(db.Model):
    __tablename__ = "entry_decomps"

    id = db.Column(db.Integer, primary_key=True)
    language = db.Column(db.String(20), nullable=False)
    # Decomps are keyed solely by the actual surface form the user saw. Each
    # spelling of a word — headword, forms-row variant, lemma-override OOV —
    # gets its own row so inflected decomps never leak to the stem or siblings.
    surface_form = db.Column(db.String(500), nullable=False)
    decomp = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("language", "surface_form", name="uq_entry_decomp_lang_surface"),
    )
