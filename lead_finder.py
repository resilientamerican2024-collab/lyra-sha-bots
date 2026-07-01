#!/usr/bin/env python3
"""
lead_finder.py — Clean, ToS-safe business lead finder.

Uses the official Google Places API (New) Text Search. No scraping.
Same data as a Maps scraper (name, address, phone, website, rating)
without the blocking / Terms-of-Service risk.

SETUP (one time):
    python3 lead_finder.py --save-key AIza...your_key...

USAGE:
    python3 lead_finder.py --type "Plumber" --city "Miami"
    python3 lead_finder.py --type "Digital Marketing Agency" --city "Austin, TX" --max 100
    python3 lead_finder.py --type "Restaurant" --city "New York" --out nyc_restaurants.csv

Output: a CSV of leads saved to /Users/cnp/Downloads/leads/ by default.
"""

import argparse
import csv
import json
import os
import sys
import time

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "places_config.json")
DEFAULT_OUT_DIR = "/Users/cnp/Downloads/leads"
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Fields we pull back. Keep this tight — you are billed per field group.
FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.googleMapsUri",
    "places.businessStatus",
    "nextPageToken",
])

CSV_COLUMNS = [
    "name", "address", "phone", "website",
    "rating", "review_count", "status", "google_maps_url",
]


def load_key():
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("api_key")
    except (json.JSONDecodeError, OSError):
        return None


def save_key(key):
    with open(CONFIG_PATH, "w") as f:
        json.dump({"api_key": key}, f)
    os.chmod(CONFIG_PATH, 0o600)
    print(f"✅ API key saved to {CONFIG_PATH}")


def search(api_key, query, max_results):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    results = []
    page_token = None

    while len(results) < max_results:
        body = {"textQuery": query, "pageSize": 20}
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(SEARCH_URL, headers=headers, json=body, timeout=30)

        if resp.status_code != 200:
            detail = resp.text
            if resp.status_code == 403:
                detail += "\n→ Key may lack Places API (New) access or billing isn't enabled."
            elif resp.status_code == 400 and "API key not valid" in resp.text:
                detail += "\n→ The API key is not valid. Re-run with --save-key."
            raise RuntimeError(f"Places API error {resp.status_code}: {detail}")

        data = resp.json()
        places = data.get("places", [])
        results.extend(places)

        page_token = data.get("nextPageToken")
        if not page_token or not places:
            break
        time.sleep(2)  # nextPageToken needs a brief delay before it's valid

    return results[:max_results]


def to_row(place):
    return {
        "name": place.get("displayName", {}).get("text", ""),
        "address": place.get("formattedAddress", ""),
        "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber", ""),
        "website": place.get("websiteUri", ""),
        "rating": place.get("rating", ""),
        "review_count": place.get("userRatingCount", ""),
        "status": place.get("businessStatus", ""),
        "google_maps_url": place.get("googleMapsUri", ""),
    }


def write_csv(rows, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="ToS-safe business lead finder (Google Places API).")
    parser.add_argument("--save-key", metavar="KEY", help="Save your Google Places API key and exit.")
    parser.add_argument("--type", help='Business type, e.g. "Plumber".')
    parser.add_argument("--city", help='City, e.g. "Miami" or "Austin, TX".')
    parser.add_argument("--max", type=int, default=60, help="Max leads to fetch (default 60).")
    parser.add_argument("--out", help="Output CSV path or filename.")
    args = parser.parse_args()

    if args.save_key:
        save_key(args.save_key.strip())
        return

    api_key = load_key()
    if not api_key:
        sys.exit("❌ No API key found. Run: python3 lead_finder.py --save-key YOUR_KEY")

    if not args.type or not args.city:
        sys.exit("❌ Need both --type and --city. Example: --type \"Plumber\" --city \"Miami\"")

    query = f"{args.type} in {args.city}"
    print(f"🔎 Searching: {query}  (up to {args.max} leads)")

    try:
        places = search(api_key, query, args.max)
    except RuntimeError as e:
        sys.exit(f"❌ {e}")

    if not places:
        print("No results. Try a broader business type or a larger city.")
        return

    rows = [to_row(p) for p in places]

    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(DEFAULT_OUT_DIR, args.out)
    else:
        safe = f"{args.type}_{args.city}".lower().replace(" ", "_").replace(",", "")
        out_path = os.path.join(DEFAULT_OUT_DIR, f"leads_{safe}.csv")

    write_csv(rows, out_path)
    with_phone = sum(1 for r in rows if r["phone"])
    with_site = sum(1 for r in rows if r["website"])
    print(f"✅ {len(rows)} leads saved → {out_path}")
    print(f"   {with_phone} have phone numbers · {with_site} have websites")


if __name__ == "__main__":
    main()
