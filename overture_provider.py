"""Overture Maps lead provider (open data, no API, no cost). Used when LEADS_PROVIDER=overture.
Reads a monthly snapshot (overture_wy_places.csv, release recorded per row) extracted from the Overture
places theme (CDLA-Permissive-2.0 / Apache-2.0). Category matching is a strict allow-list per niche (config, not code per niche).
Safeguards here: state match, city match (validated again downstream), category allow-list, confidence floor,
open status required, phone or website required (downstream), national-brand listings flagged, dedupe (downstream)."""
import csv, os, re, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = os.environ.get("OVERTURE_SNAPSHOT", str(HERE / "overture_wy_places.csv"))

# niche -> allowed Overture taxonomy.primary values
CATEGORIES = {
    "plumber": {"plumbing"},
    "roofer": {"roofing"},
    "hvac": {"hvac_service"},
    "landscaper": {"landscaping", "lawn_service", "gardener", "irrigation_service"},
    "window installer": {"windows_installation", "window_supplier"},
    "insulation contractor": {"insulation_installation"},
    "well driller": {"well_drilling"},
}
NATIONAL_DOMAINS = ("rotorooter.com", "homedepot.com", "lowes.com", "benjaminfranklinplumbing.com", "mrrooter.com")

# Required credit lines (docs.overturemaps.org/attribution), per dataset present in delivered rows.
CREDIT = {
    "meta": "Data from Meta. Available under CDLA Permissive 2.0.",
    "Microsoft": "Data from Microsoft. Available under CDLA Permissive 2.0.",
    "BrightQuery": "Data from BrightQuery. Available under CDLA Permissive 2.0.",
    "Foursquare": "Data from Foursquare. Copyright 2024 Foursquare Labs, Inc. All rights reserved. Available under Apache 2.0. Foursquare data was transformed to the Overture schema.",
}
_cache = {"rows": None}
_lock = threading.Lock()


def _rows():
    with _lock:
        if _cache["rows"] is None:
            with open(SNAPSHOT, newline="", encoding="utf-8") as f:
                _cache["rows"] = list(csv.DictReader(f))
        return _cache["rows"]


def attribution(datasets, release=""):
    lines = ["Contains data (c) Overture Maps Foundation (https://overturemaps.org), places theme" + (f", release {release}." if release else ".")]
    for d in sorted(datasets):
        if d in CREDIT:
            lines.append(CREDIT[d])
    lines.append("Publicly available business information; may be out of date. Not verified email addresses or consumer leads.")
    return " ".join(lines)


def datasets_of(src):
    return {s.strip() for s in (src or "").split("+") if s.strip() and not s.strip().startswith("Overture")}


def source_overture(btype, city, state, limit, niche_key):
    cats = CATEGORIES.get(niche_key)
    if not cats:
        return []  # unsupported/custom niche: nothing we can honestly supply -> shortfall/refund
    floor = float(os.environ.get("OVERTURE_MIN_CONFIDENCE", "0.6"))
    need_open = os.environ.get("OVERTURE_REQUIRE_OPEN", "1") != "0"
    out = []
    for r in _rows():
        if (r["state"] or "").upper() != (state or "").upper() or (r["city"] or "").strip().lower() != (city or "").strip().lower():
            continue
        if r["cat"] not in cats:
            continue
        try:
            conf = float(r["confidence"] or 0)
        except ValueError:
            conf = 0
        if conf < floor:
            continue
        status = (r["status"] or "").lower()
        closed = status != "open" if need_open else status in ("permanently_closed", "temporarily_closed")
        addr = ", ".join(x for x in [r["street"], r["city"], f"{r['state']} {r['zip']}".strip()] if x)
        dom = re.sub(r"^https?://(www\.)?|[/?].*$", "", r["website"] or "").lower()
        ds = datasets_of(r["src"])
        out.append({"name": r["name"], "address": addr, "phone": r["phone"], "website": r["website"],
                    "rating": "", "review_count": "", "source": "Overture Maps (" + ", ".join(sorted(ds) or ["Overture"]) + ")",
                    "source_url": f"https://overturemaps.org/ id={r['id']}", "_city": r["city"], "_closed": closed,
                    "_category": r["cat"], "confidence": f"{conf:.2f}", "source_release": r["release"],
                    "_national": any(dom.endswith(n) for n in NATIONAL_DOMAINS), "_datasets": ds})
    out.sort(key=lambda x: -float(x["confidence"]))
    return out
