# Lyra Sha AI — production activation and rollback

Prepared 2026-10-19. PREPARATION ONLY. No authorization to execute this document.

## Binding scope

Ten Local Business Contacts, $29 USD once, Cheyenne WY; plumber, roofer, landscaper.
Complete list or full refund. Preserve the current Overture source, attribution,
CSV/email system, and unrelated bots. Macaly owns the website. Founder owns Publish.

## Confirmed checkpoint

Repository resilientamerican2024-collab/lyra-sha-bots.
Source and running test commit f70eb05dc93b002c332c549585b4d542616f3395.
Project practical-caring (a44fedcb-63ad-460d-8dc2-58eeab667eff).
Existing isolated service truthful-perfection (e1ada17e-1e48-4b8f-ac4f-b281e6389f3f).
Deployment a9087d5c-0b9a-42c5-8154-2367f9ecd927, single instance,
python order_service.py, persistent volume 681445d1-e957-4153-935c-11f0ded2c7b1 at /data.
Test endpoint https://truthful-perfection-production-4b54.up.railway.app.
The Railway environment name "production" does NOT authorize commercial use.
Permanent production service has not been confirmed. Do not infer it from this file.

## Work required before requesting final activation approval

1. Unlock the Mac and regain authenticated Macaly/Stripe access. Finish Macaly's
   existing phone-width and Spanish checkout/success/cancel checks. Do not touch
   /myportal. No new website. Preview currently gives HTTP403 outside authenticated access.
2. Inspect the actual Macaly source/route: use a same-origin server-side proxy to
   POST /checkout/session with product, business_type, city, state, quantity=10,
   optional email and locale=en/es. Validate created=true and a Stripe Checkout URL
   before redirect. Never put private keys in browser code. If the existing proxy
   already works, preserve it. Direct browser-to-Railway CORS is not verified.
3. Confirm authorized Stripe live account and charges capability in its authenticated
   dashboard. Browser inventory shows a TEST account page; this does not establish
   live readiness. Stage separate restricted keys for Checkout and refunds using
   the secure provider/Railway channel, never this file or chat. Minimum permissions
   to evaluate are Checkout Sessions write and Refunds write respectively; verify
   inline price_data dependencies and exact dashboard scope before issuance.
   No account-wide secret key fallback. No key creation was performed here.
4. Prepare live endpoint /stripe/webhook in the confirmed target, subscribe only to
   checkout.session.completed, checkout.session.async_payment_succeeded,
   charge.refunded, charge.dispute.created. Preserve the signing secret only in
   the authorized configuration channel. Do not activate payments yet.
5. Confirm production service, persistent storage, one process/replica, and expected
   operating cost within existing authority. No new paid services/subscriptions.
6. Confirm Resend sending domain/from identity and customer delivery route. Current
   test configuration has a key and sender; historical email IDs prove acceptance,
   not customer inbox delivery or current live-domain verification.
7. Review the prepared patch and actual Macaly connection together. Collect one
   consolidated Founder decision naming exact code revision, Railway service,
   live charge/refund/customer email flags, and any capped real-money test.

## Activation after that exact approval only

Snapshot current deployment metadata and securely back up /data/orders database and
CSV files with the process quiesced or SQLite online backup. Do not print customer
rows or copy credentials into receipts. Preserve test evidence and schema.

Deploy the approved revision to the approved service using order_service.py and
health /health. Stage all settings with live flags OFF. After confirming live keys,
live webhook, delivery identity and the public Macaly route, apply all four live
flags together. launch_config.validate_startup fails closed on partial activation.
The patch fixes price at 2900 cents and permits locale en/es/es-419/auto.

Founder personally publishes Macaly. Verify public page and checkout; use only the
specifically approved real-money test and recipient. Confirm signed paid event,
one order, exact ten-row CSV plus attribution, provider email acceptance AND inbox
arrival, correct amount, and no duplicate fulfillment. Verify refunds only within
the explicitly approved real-money scope. Test success is not proof of LIVE.

## Rollback

Stop new Checkout Session creation first (STRIPE_CHECKOUT_LIVE=0 with the live
checkout key retained causes live checkout rejection). Keep the paid-order webhook,
customer delivery and refund handling running while reconciling paid and pending
sessions. Do not turn off receipt of paid events and acknowledge them as ignored.
Expire unpaid open sessions only within activation authority. Reconcile existing
paid orders/refunds before reverting code or disabling the remaining live flags.

Restore the recorded prior image/commit only after draining/reconciling paid work.
Preserve /data and the current SQLite database; never restore an old database over
new paid orders. No destructive schema migration is introduced by this patch.
Recheck health and confirm new checkout is disabled. Resume only under the remaining
or renewed explicit Founder authority. Rollback is documented, not rehearsed live.

## Operating limits

The worker is SQLite + in-process locks and daemon threads, with startup recovery.
Run one instance/process. Do not introduce multi-worker Gunicorn or replicas here.
Resend acceptance is not inbox delivery. Existing Resend idempotency is time-limited;
reconcile provider state before manually retrying a delivery after a prolonged outage.
Pending refunds stay refund_due; operator reconciliation is required. ALERT_FAILED
is persisted and logged if the founder alert is not accepted. No independent Vera
review was invoked or inferred from these tests.

Sources checked: https://docs.stripe.com/api/checkout/sessions/create
https://docs.stripe.com/api/refunds/create and https://docs.stripe.com/webhooks .
