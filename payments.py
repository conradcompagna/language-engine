"""
payments.py — Flask blueprint for Stripe subscription management.

Endpoints:
  POST /payments/create-checkout  — create a Stripe Checkout session (monthly or yearly)
  POST /payments/webhook          — Stripe webhook handler
  GET  /payments/portal           — redirect to Stripe Customer Portal
  GET  /payments/status           — current subscription + quota status
"""

import datetime

from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import current_user, login_required

from db import db, User, Subscription, LookupQuota, ApiUsage

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


def _get_stripe():
    """Lazy import and configure stripe."""
    import stripe
    from config import STRIPE_SECRET_KEY

    stripe.api_key = STRIPE_SECRET_KEY
    return stripe


def _public_url(endpoint):
    from config import APP_BASE_URL

    if APP_BASE_URL:
        return APP_BASE_URL + url_for(endpoint)
    return url_for(endpoint, _external=True)


def _price_id_for_billing(billing):
    from config import STRIPE_MONTHLY_PRICE_ID, STRIPE_YEARLY_PRICE_ID

    if billing == "yearly":
        return STRIPE_YEARLY_PRICE_ID
    if billing == "monthly":
        return STRIPE_MONTHLY_PRICE_ID
    return ""


# ---------------------------------------------------------------------------
# Create Checkout Session
# ---------------------------------------------------------------------------


@payments_bp.route("/create-checkout", methods=["POST"])
@login_required
def create_checkout():
    from config import STRIPE_SECRET_KEY

    if not STRIPE_SECRET_KEY:
        return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not configured."}), 501

    stripe = _get_stripe()

    data = request.get_json(silent=True) or {}
    billing = (data.get("billing") or "monthly").strip().lower()
    if billing not in ("monthly", "yearly"):
        return jsonify({"ok": False, "error": "Invalid billing cycle."}), 400

    price_id = _price_id_for_billing(billing)
    if not price_id:
        return jsonify({"ok": False, "error": f"Stripe {billing} price ID is not configured."}), 501

    try:
        from analytics import record_checkout_attempt

        record_checkout_attempt()
    except Exception:
        pass

    # Create or reuse Stripe customer
    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email,
            metadata={"user_id": str(current_user.id)},
        )
        current_user.stripe_customer_id = customer.id
        db.session.commit()

    checkout_session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        client_reference_id=str(current_user.id),
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        metadata={"user_id": str(current_user.id), "billing": billing},
        subscription_data={"metadata": {"user_id": str(current_user.id), "billing": billing}},
        success_url=_public_url("account_page") + "?payment=success",
        cancel_url=_public_url("account_page") + "?payment=canceled",
    )

    return jsonify({"ok": True, "url": checkout_session.url})


# ---------------------------------------------------------------------------
# Stripe Webhook
# ---------------------------------------------------------------------------


@payments_bp.route("/webhook", methods=["POST"])
def webhook():
    from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        return jsonify({"error": "Stripe webhook is not configured."}), 501

    stripe = _get_stripe()

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    etype = event["type"]
    obj = event["data"]["object"]

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _sync_subscription(obj)

    elif etype == "checkout.session.completed":
        # Ensure customer is linked
        customer_id = obj.get("customer")
        if customer_id:
            user = User.query.filter_by(stripe_customer_id=customer_id).first()
            if not user and obj.get("client_reference_id"):
                try:
                    user = db.session.get(User, int(obj["client_reference_id"]))
                except (TypeError, ValueError):
                    user = None
                if user:
                    user.stripe_customer_id = customer_id
                    db.session.commit()
            if user and obj.get("subscription"):
                sub_obj = stripe.Subscription.retrieve(obj["subscription"])
                _sync_subscription(sub_obj)

    elif etype in ("invoice.payment_failed", "invoice.payment_action_required"):
        subscription_id = obj.get("subscription")
        if subscription_id:
            sub_obj = stripe.Subscription.retrieve(subscription_id)
            _sync_subscription(sub_obj)

    return jsonify({"ok": True})


def _sync_subscription(sub_obj):
    """Upsert a Subscription row from a Stripe subscription object."""
    customer_id = sub_obj.get("customer")
    user = User.query.filter_by(stripe_customer_id=customer_id).first()
    if not user:
        return

    sub = Subscription.query.filter_by(user_id=user.id).first()
    if not sub:
        sub = Subscription(user_id=user.id)
        db.session.add(sub)

    sub.stripe_subscription_id = sub_obj.get("id")
    sub.status = sub_obj.get("status", "inactive")

    sub.tier = "pro"
    sub.cancel_at_period_end = bool(sub_obj.get("cancel_at_period_end"))

    subscription_items = sub_obj.get("items") or {}
    item_rows = subscription_items.get("data") or []
    period_end = item_rows[0].get("current_period_end") if item_rows else None
    if period_end:
        sub.current_period_end = datetime.datetime.utcfromtimestamp(period_end)

    db.session.commit()


# ---------------------------------------------------------------------------
# Customer Portal (change payment method, cancel)
# ---------------------------------------------------------------------------


@payments_bp.route("/portal")
@login_required
def portal():
    from config import STRIPE_SECRET_KEY

    if not STRIPE_SECRET_KEY:
        return jsonify({"ok": False, "error": "STRIPE_SECRET_KEY is not configured."}), 501

    stripe = _get_stripe()

    if not current_user.stripe_customer_id:
        return redirect(url_for("account_page"))

    portal_session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=_public_url("account_page"),
    )
    return redirect(portal_session.url)


@payments_bp.route("/invoices")
@login_required
def invoices():
    from config import STRIPE_SECRET_KEY

    if not STRIPE_SECRET_KEY or not current_user.stripe_customer_id:
        return jsonify({"ok": True, "invoices": []})

    stripe = _get_stripe()
    try:
        rows = stripe.Invoice.list(customer=current_user.stripe_customer_id, limit=10).get(
            "data", []
        )
    except Exception as exc:
        return jsonify(
            {"ok": False, "error": f"Could not load invoices: {type(exc).__name__}"}
        ), 502

    invoices_out = []
    for inv in rows:
        amount = inv.get("amount_paid")
        if amount is None:
            amount = inv.get("amount_due", 0)
        invoices_out.append(
            {
                "id": inv.get("id", ""),
                "created": inv.get("created"),
                "status": inv.get("status", ""),
                "amount": amount or 0,
                "currency": (inv.get("currency") or "usd").upper(),
                "url": inv.get("hosted_invoice_url") or inv.get("invoice_pdf") or "",
            }
        )
    return jsonify({"ok": True, "invoices": invoices_out})


# ---------------------------------------------------------------------------
# Status: quota + subscription
# ---------------------------------------------------------------------------


@payments_bp.route("/status")
@login_required
def status():
    from config import FREE_LOOKUP_TOKENS_PER_DAY, TIER_CAPS

    quota = LookupQuota.query.filter_by(user_id=current_user.id).first()
    if not quota:
        quota = LookupQuota(user_id=current_user.id)
        db.session.add(quota)
        db.session.commit()

    quota.reset_if_new_day()

    # API usage
    usage = ApiUsage.query.filter_by(user_id=current_user.id).first()
    if usage:
        usage._maybe_reset(current_user)
    db.session.commit()

    tier = current_user.tier
    caps = TIER_CAPS.get(tier, {})
    sub = current_user.subscription
    period_end = sub.current_period_end if sub and sub.current_period_end else None

    return jsonify(
        {
            "ok": True,
            "is_subscribed": current_user.is_subscribed,
            "tier": tier,
            "lookups_used": quota.count,
            "lookups_remaining": quota.remaining if not current_user.is_subscribed else None,
            "lookups_limit": FREE_LOOKUP_TOKENS_PER_DAY,
            "lookup_tokens_used": quota.count,
            "lookup_tokens_remaining": quota.remaining if not current_user.is_subscribed else None,
            "lookup_tokens_limit": FREE_LOOKUP_TOKENS_PER_DAY,
            "subscription_status": sub.status if sub else "none",
            "subscription_current_period_end": period_end.isoformat() + "Z" if period_end else None,
            "subscription_cancel_at_period_end": bool(sub.cancel_at_period_end) if sub else False,
            "mt_chars_used": usage.mt_chars_used if usage else 0,
            "mt_chars_cap": caps.get("mt_chars_per_month", 0),
            "llm_prompt_tokens_used": usage.llm_prompt_tokens_used if usage else 0,
            "llm_output_tokens_used": usage.llm_output_tokens_used if usage else 0,
            "llm_tokens_used": usage.llm_tokens_used if usage else 0,
            "llm_budget_usd": usage.llm_budget_usd(current_user)
            if usage
            else float(caps.get("llm_budget_usd_per_month", 0.0) or 0.0),
            "llm_cost_usd": usage.llm_cost_usd(current_user) if usage else 0.0,
            "llm_usage_pct": usage.llm_usage_percent(current_user) if usage else 0.0,
        }
    )
