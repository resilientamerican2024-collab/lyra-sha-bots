"""Non-secret production preflight. Does not contact providers or activate anything."""
import os
from pathlib import Path

LIVE_FLAGS = ("STRIPE_CHECKOUT_LIVE", "STRIPE_ACCEPT_LIVE", "STRIPE_DELIVER_TO_CUSTOMER", "STRIPE_AUTO_REFUND_LIVE")


def live_blockers(require_checkout=True):
    flags = LIVE_FLAGS if require_checkout else LIVE_FLAGS[1:]
    blockers = [name + " must be 1" for name in (*flags, "STRIPE_AUTO_REFUND") if os.environ.get(name) != "1"]
    for name in ("STRIPE_CHECKOUT_KEY", "STRIPE_REFUND_KEY"):
        if not os.environ.get(name, "").startswith("rk_live_"):
            blockers.append(name + " requires a restricted live key")
    for name in ("STRIPE_WEBHOOK_SECRET", "ORDER_WEBHOOK_SECRET", "RESEND_API_KEY", "RESEND_FROM"):
        if not os.environ.get(name):
            blockers.append(name + " missing")
    mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "")
    if not mount or not Path(mount).is_dir():
        blockers.append("persistent volume missing")
    if os.environ.get("LEADS_PROVIDER") != "overture":
        blockers.append("Overture provider required")
    if os.environ.get("FULFILLMENT_MAX_LEADS") != "10":
        blockers.append("FULFILLMENT_MAX_LEADS must be 10")
    if os.environ.get("ALLOWED_NICHES", "plumber,roofer,landscaper") != "plumber,roofer,landscaper":
        blockers.append("launch industries changed")
    for name, path in (("CHECKOUT_SUCCESS_URL", "/leads/success"), ("CHECKOUT_CANCEL_URL", "/leads/cancel")):
        if os.environ.get(name, "").split("?", 1)[0] != "https://www.lyrashaai.com" + path:
            blockers.append(name + " must use approved public route")
    return blockers


def validate_startup():
    if any(os.environ.get(name, "").lower() in ("1", "true", "yes") for name in LIVE_FLAGS):
        # Checkout may be off while already-paid orders continue draining.
        blockers = live_blockers(require_checkout=os.environ.get("STRIPE_CHECKOUT_LIVE") == "1")
        if blockers:
            raise RuntimeError("Live launch blocked: " + "; ".join(blockers))
