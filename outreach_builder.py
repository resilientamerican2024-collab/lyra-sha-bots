#!/usr/bin/env python3
"""
outreach_builder.py — Turns raw business leads into ready-to-send review-management pitches.

Front end of the Review Bot sales funnel:
  1. Find businesses (Google Places API) for a type + city
  2. Pull their recent reviews
  3. Qualify the ones worth pitching (have contact info, enough reviews, room to improve)
  4. Write a FREE personalized sample review response with Claude (Template A — highest converting)
  5. Output a ready-to-send outreach pack: CSV + a plain-text file of DMs you can copy/paste

USAGE:
    python3 outreach_builder.py --type "Beauty Salon" --city "Newark, NJ"
    python3 outreach_builder.py --type "Restaurant" --city "Miami" --max 40 --limit-samples 25
    python3 outreach_builder.py --type "Bodega" --city "Bronx, NY" --lang es   # Spanish pitch

Reuses the Places key from places_config.json and the Claude key from review_bot_config.json.
Output → /Users/cnp/Downloads/leads/
"""

import argparse
import csv
import json
import os
import sys
import time

import requests

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PLACES_CONFIG = os.path.join(TOOLS_DIR, "places_config.json")
BOT_CONFIG = os.path.join(TOOLS_DIR, "review_bot_config.json")
OUT_DIR = "/Users/cnp/Downloads/leads"
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.googleMapsUri",
    "places.reviews",
    "nextPageToken",
])

PITCH_PRICE = "$97/month"

# Template A (English) and C (Spanish), from review_bot_outreach.md
PITCH_EN = """Hey {name} 👋

I noticed some of your Google reviews don't have responses — that actually hurts your ranking on Maps and quietly costs you customers.

I wrote a response to one of your recent reviews, free, so you can see what I mean:

---
{sample}
---

I run an AI service that does this automatically for local businesses — every new review gets a warm, human-sounding response within minutes, 24/7. You never have to think about it.

{price}, fully done for you. Want me to set it up? First 30 days free."""

PITCH_ES = """Hola {name} 👋

Noté que algunas de tus reseñas de Google no tienen respuesta — eso baja tu posición en Maps y te cuesta clientes sin que te des cuenta.

Escribí una respuesta a una de tus reseñas recientes, gratis, para que veas a qué me refiero:

---
{sample}
---

Tengo un servicio de IA que hace esto automáticamente para negocios locales — cada reseña nueva recibe una respuesta cálida y humana en minutos, 24/7. Tú no tienes que hacer nada.

{price}, yo me encargo de todo. ¿Te lo configuro? Los primeros 30 días son gratis."""


def load_json(path, label):
    if not os.path.exists(path):
        sys.exit(f"❌ {label} not found: {path}")
    with open(path) as f:
        return json.load(f)


def search_with_reviews(api_key, query, max_results):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    results, page_token = [], None
    while len(results) < max_results:
        body = {"textQuery": query, "pageSize": 20}
        if page_token:
            body["pageToken"] = page_token
        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Places API error {resp.status_code}: {resp.text}")
        data = resp.json()
        places = data.get("places", [])
        results.extend(places)
        page_token = data.get("nextPageToken")
        if not page_token or not places:
            break
        time.sleep(2)
    return results[:max_results]


def qualify(place, min_reviews, max_rating):
    """Return True if this business is worth pitching."""
    if place.get("businessStatus") != "OPERATIONAL":
        return False
    if not (place.get("nationalPhoneNumber") or place.get("websiteUri")):
        return False
    if place.get("userRatingCount", 0) < min_reviews:
        return False
    if place.get("rating", 5.0) > max_rating:
        return False
    return True


def pick_review(place):
    """Prefer the most pointed review to respond to — lowest-rated one with text."""
    reviews = [r for r in place.get("reviews", []) if r.get("text", {}).get("text")]
    if not reviews:
        return None
    reviews.sort(key=lambda r: r.get("rating", 5))
    return reviews[0]


def generate_sample(claude, business_name, review, lang):
    rating = review.get("rating", 5)
    text = review.get("text", {}).get("text", "").strip()
    reviewer = review.get("authorAttribution", {}).get("displayName", "this customer")
    tone = "Spanish" if lang == "es" else "English"

    user_prompt = f"""Business: {business_name}
Reviewer: {reviewer}
Rating: {rating}/5
Review: "{text}"

Write the owner's response to this review in {tone}."""

    msg = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        system=[{
            "type": "text",
            "text": (
                "You write Google review responses as the business owner. "
                "Rules: 4-5 stars — thank them by first name, reference something specific. "
                "1-3 stars — sincerely acknowledge, apologize without excuses, invite them to reach out. "
                "Under 120 words. Sound like a real human owner who cares, never a template. "
                "Do NOT start with 'Thank you for your review'. Output ONLY the response text."
            ),
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_prompt}],
    )
    return msg.content[0].text.strip()


def main():
    ap = argparse.ArgumentParser(description="Build ready-to-send review-management outreach from leads.")
    ap.add_argument("--type", required=True, help='Business type, e.g. "Beauty Salon".')
    ap.add_argument("--city", required=True, help='City, e.g. "Newark, NJ".')
    ap.add_argument("--max", type=int, default=40, help="Max businesses to scan (default 40).")
    ap.add_argument("--min-reviews", type=int, default=8, help="Skip businesses with fewer reviews (default 8).")
    ap.add_argument("--max-rating", type=float, default=4.7, help="Skip businesses rated above this (default 4.7).")
    ap.add_argument("--limit-samples", type=int, default=25, help="Max free samples to generate with Claude (default 25).")
    ap.add_argument("--lang", choices=["en", "es"], default="en", help="Pitch language (default en).")
    args = ap.parse_args()

    api_key = load_json(PLACES_CONFIG, "Places config").get("api_key")
    if not api_key:
        sys.exit("❌ No Places API key. Run: python3 lead_finder.py --save-key YOUR_KEY")
    claude_key = load_json(BOT_CONFIG, "Review bot config").get("claude_api_key")
    if not claude_key:
        sys.exit("❌ No claude_api_key in review_bot_config.json")

    import anthropic
    claude = anthropic.Anthropic(api_key=claude_key)

    query = f"{args.type} in {args.city}"
    print(f"🔎 Scanning: {query}  (up to {args.max})")
    try:
        places = search_with_reviews(api_key, query, args.max)
    except RuntimeError as e:
        sys.exit(f"❌ {e}")

    qualified = [p for p in places if qualify(p, args.min_reviews, args.max_rating)]
    print(f"   {len(places)} found · {len(qualified)} qualified to pitch")
    if not qualified:
        print("No qualified targets. Try a different type/city or raise --max-rating.")
        return

    template = PITCH_ES if args.lang == "es" else PITCH_EN
    rows, dms, samples_made = [], [], 0

    for p in qualified:
        name = p.get("displayName", {}).get("text", "")
        phone = p.get("nationalPhoneNumber", "")
        website = p.get("websiteUri", "")
        rating = p.get("rating", "")
        count = p.get("userRatingCount", "")

        sample = ""
        review = pick_review(p)
        if review and samples_made < args.limit_samples:
            try:
                sample = generate_sample(claude, name, review, args.lang)
                samples_made += 1
            except Exception as e:
                print(f"   ⚠️ sample failed for {name}: {e}")

        pitch = template.format(name=name, sample=sample or "(I can write you one on the spot — just ask.)",
                                price=PITCH_PRICE) if sample else ""

        rows.append({
            "business": name, "phone": phone, "website": website,
            "rating": rating, "review_count": count,
            "has_sample": "yes" if sample else "no",
            "google_maps_url": p.get("googleMapsUri", ""),
        })
        if pitch:
            dms.append(f"=== {name}  ({rating}★, {count} reviews) ===\n"
                       f"Phone: {phone}  |  Web: {website}\n\n{pitch}\n")

    os.makedirs(OUT_DIR, exist_ok=True)
    safe = f"{args.type}_{args.city}".lower().replace(" ", "_").replace(",", "")
    csv_path = os.path.join(OUT_DIR, f"outreach_{safe}.csv")
    dm_path = os.path.join(OUT_DIR, f"outreach_{safe}_DMs.txt")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(dm_path, "w", encoding="utf-8") as f:
        f.write("\n".join(dms))

    print(f"✅ {len(rows)} prospects → {csv_path}")
    print(f"✅ {samples_made} ready-to-send DMs (with free samples) → {dm_path}")
    print(f"\n💰 Next: copy a DM, find the owner's Instagram/Facebook from their listing, send it.")
    print(f"   Close 3 at {PITCH_PRICE} = ~$291/mo recurring.")


if __name__ == "__main__":
    main()
