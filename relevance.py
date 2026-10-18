"""Targeted business-relevance filter (config in this file, not per-niche code paths).
Rejects: suppliers/distributors, paint brands, wrong business type (general contractors/excavation etc. with no sign of the
requested trade in name or website), out-of-area phone numbers, and known mismatched websites.
Does NOT reject a local franchise or office just because it belongs to a national brand (those are kept and flagged REVIEW)."""
import re

AREA_CODES = {"WY": {"307"}}  # phone area codes accepted per launch state
SUPPLIER_TOKENS = ("building products", "supply", "supplies", "supplier", "distribut", "wholesale", "hardware", "lumber yard")
BRAND_DENY = ("scotch boy", "sherwin", "benjamin moore", "behr", "valspar", "glidden", "kilz", "beacon building")
PAINT_TOKEN = "paint"  # painters are not roofers/plumbers/landscapers unless the trade word is also present
GC_TOKENS = ("construction", "contractors", "builders", "excavation", "remodel", "general contractor", "homes")
DOMAIN_DENY = {"titanlawncareofnwfl": "website belongs to a different region"}  # data-driven mismatches
NICHE_WORDS = {
    "plumber": ("plumb", "drain", "sewer", "rooter", "pipe"),
    "roofer": ("roof", "shingle", "exterior"),
    "landscaper": ("landscap", "lawn", "yard", "garden", "mow", "turf", "sprinkler", "irrigat", "scaping", "tree", "arbor", "sod", "grass"),
    "hvac": ("heat", "hvac", "cool", "furnace", "air"),
    "window installer": ("window", "glass"),
    "insulation contractor": ("insul", "foam"),
    "well driller": ("well", "drill", "pump"),
}


def _host(site):
    return re.sub(r"^https?://(www\.)?|[/?#].*$", "", (site or "").strip().lower())


def reject_reason(lead, niche_key, state, phone_digits10=""):
    """Return (bucket, detail) when a lead should be rejected, else None."""
    name = (lead.get("name") or "").lower()
    host = _host(lead.get("website"))
    words = NICHE_WORDS.get(niche_key, ())
    has_trade = any(w in name or w in host for w in words)
    for b in BRAND_DENY:
        if b in name or b in host:
            return "supplier_or_brand", b
    for t in SUPPLIER_TOKENS:
        if t in name:
            return "supplier_or_brand", t
    for d, why in DOMAIN_DENY.items():
        if d in host:
            return "out_of_area", why
    if PAINT_TOKEN in name and not has_trade:
        return "wrong_category", "painter"
    if words and not has_trade and any(t in name for t in GC_TOKENS):
        return "wrong_category", "general contractor / unrelated trade"
    codes = AREA_CODES.get((state or "").upper())
    if codes and phone_digits10 and phone_digits10[:3] not in codes:
        return "out_of_area", f"area code {phone_digits10[:3]}"
    return None
