"""Suppression list + unsubscribe + send-gate for Lyra Sha AI outreach. Does NOT send by itself.
Config items: POSTAL_ADDRESS (UNRESOLVED until Founder provides), UNSUB_BASE_URL (needs a deployed endpoint)."""
import hashlib, hmac, os, re, sqlite3, time
DB = os.environ.get("SUPPRESSION_DB", "suppression.db")
SECRET = os.environ.get("UNSUB_SECRET", "")
POSTAL = os.environ.get("POSTAL_ADDRESS", "Ingrid K Santana Ramirez DBA Lyra Sha AI, 30 N Gould St Ste R, Sheridan, WY 82801, United States")
FROM = "Lyra Sha AI <ingrid@lyrashaai.com>"; REPLY_TO = "ingrid@lyrashaai.com"

def _db():
    c = sqlite3.connect(DB); c.execute("CREATE TABLE IF NOT EXISTS suppressed(email TEXT PRIMARY KEY, reason TEXT, at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS sent(email TEXT, campaign TEXT, resend_id TEXT, at TEXT)"); return c
def norm(e): return e.strip().lower()
def suppress(email, reason="unsubscribe"):
    with _db() as c: c.execute("INSERT OR IGNORE INTO suppressed VALUES(?,?,datetime('now'))", (norm(email), reason))
def is_suppressed(email):
    e = norm(email); dom = e.split("@")[-1]
    with _db() as c:
        return bool(c.execute("SELECT 1 FROM suppressed WHERE email=? OR email=?", (e, "@" + dom)).fetchone())
def token(email): return hmac.new(SECRET.encode(), norm(email).encode(), hashlib.sha256).hexdigest()[:32]
def unsub_url(email, base=None):
    base = base or os.environ.get("UNSUB_BASE_URL", "")
    return f"{base}/unsubscribe?e={norm(email)}&t={token(email)}" if base and SECRET else ""
def handle_unsubscribe(email, tok):
    """Endpoint logic: valid token -> suppress. Returns True if processed."""
    if SECRET and hmac.compare_digest(tok or "", token(email)): suppress(email, "unsubscribe link"); return True
    return False
def preflight(email, body):
    """Returns list of blockers; empty list = OK to send."""
    b = []
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): b.append("invalid email")
    if is_suppressed(email): b.append("suppressed")
    if not POSTAL or "REQUIRED" in body: b.append("postal address not configured")
    if not unsub_url(email): b.append("unsubscribe URL not configured")
    return b
def headers(email):
    u = unsub_url(email)
    return {"List-Unsubscribe": f"<{u}>, <mailto:ingrid@lyrashaai.com?subject=unsubscribe>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"} if u else {}
