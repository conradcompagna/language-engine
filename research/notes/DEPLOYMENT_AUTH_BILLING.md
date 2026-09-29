# Auth and Billing Go-Live Checklist

Set these environment variables on the production host:

```text
APP_BASE_URL=https://your-domain.com
LE_SECRET_KEY=<random production secret>
GOOGLE_CLIENT_ID=<Google OAuth web client ID>
GOOGLE_CLIENT_SECRET=<Google OAuth web client secret>
STRIPE_SECRET_KEY=<Stripe live secret key>
STRIPE_WEBHOOK_SECRET=<Stripe live webhook signing secret>
STRIPE_MONTHLY_PRICE_ID=<Stripe recurring monthly price ID for $10 Pro>
STRIPE_YEARLY_PRICE_ID=<Stripe recurring yearly price ID for $100 Pro>
GEMINI_API_KEY=<Gemini API key>
```

Google Cloud Console:

```text
Authorized JavaScript origin: https://your-domain.com
Authorized redirect URI: https://your-domain.com/auth/google/callback
```

Stripe Dashboard:

```text
Webhook endpoint: https://your-domain.com/payments/webhook
Events:
checkout.session.completed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
invoice.payment_failed
invoice.payment_action_required
```

Also configure the Stripe Customer Portal in live mode.
