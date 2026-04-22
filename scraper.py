import os
import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fractionaljobs.io"
SOURCE_NAME = "fractionaljobs"

DATA_DIR = "docs/data"
SEEN_FILE = os.path.join(DATA_DIR, "seen.json")
RAW_DIR = os.path.join(DATA_DIR, "raw")
FLAGGED_DIR = os.path.join(DATA_DIR, "flagged")
OPPORTUNITIES_FILE = os.path.join(DATA_DIR, "opportunities.json")
RAW_ALL_FILE = os.path.join(DATA_DIR, "raw_all.json")

# Matched as whole words to avoid substrings (e.g. "ui" inside "recruiter")
TITLE_KEYWORDS = ["design", "designer", "ux", "ui", "creative director", "brand"]
KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in TITLE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def is_relevant(title):
    return bool(KEYWORD_PATTERN.search(title))


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def scrape_fractionaljobs():
    resp = requests.get(BASE_URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    jobs = []
    for card in soup.find_all("div", class_="job-item"):
        job_id_el = card.find("div", class_="job-id")
        if not job_id_el:
            continue
        slug = job_id_el.get_text(strip=True)
        if not slug:
            continue

        h3s = card.find_all("h3", class_="text-size-regular")
        company = h3s[0].get_text(strip=True) if len(h3s) > 0 else ""
        title = h3s[2].get_text(strip=True) if len(h3s) > 2 else (h3s[1].get_text(strip=True) if len(h3s) > 1 else "")

        hide_el = card.find("div", class_="hide")
        category = ""
        if hide_el:
            cat_el = hide_el.find("div", class_=False)
            if cat_el:
                category = cat_el.get_text(strip=True)

        date_el = card.find("div", class_="date")
        posted = date_el.get_text(strip=True) if date_el else ""

        more_info = card.find("div", class_="job-item_more-info")
        info_parts = []
        if more_info:
            for div in more_info.find_all("div", class_="text-inline", recursive=False):
                t = div.get_text(strip=True)
                if t and t != "|":
                    info_parts.append(t)
        hours = info_parts[0] if len(info_parts) > 0 else ""
        rate = info_parts[1] if len(info_parts) > 1 else ""
        location = info_parts[2] if len(info_parts) > 2 else ""

        jobs.append({
            "slug": slug,
            "url": f"{BASE_URL}/jobs/{slug}",
            "title": title,
            "company": company,
            "category": category,
            "hours": hours,
            "rate": rate,
            "location": location,
            "posted": posted,
            "source": SOURCE_NAME,
        })

    return jobs


def main():
    today = date.today().isoformat()
    seen = set(load_json(SEEN_FILE, []))

    print("Scraping fractionaljobs.io...")
    all_jobs = scrape_fractionaljobs()
    print(f"  Found {len(all_jobs)} total listings")

    new_jobs = [j for j in all_jobs if j["slug"] not in seen]
    print(f"  {len(new_jobs)} new (not seen before)")

    if not new_jobs:
        print("Nothing new today.")
        return

    # Tag each job with when we found it
    for job in new_jobs:
        job["date_scraped"] = today
        job["flagged"] = is_relevant(job["title"])

    # Daily snapshot files
    save_json(os.path.join(RAW_DIR, f"{today}.json"), new_jobs)
    flagged_today = [j for j in new_jobs if j["flagged"]]
    save_json(os.path.join(FLAGGED_DIR, f"{today}.json"), flagged_today)
    print(f"  {len(flagged_today)} matched keywords:")
    for j in flagged_today:
        print(f"    ✓ {j['title']} @ {j['company']}")

    # Prepend new items to aggregate files (newest first)
    opportunities = load_json(OPPORTUNITIES_FILE, [])
    opportunities = flagged_today + opportunities
    save_json(OPPORTUNITIES_FILE, opportunities)

    raw_all = load_json(RAW_ALL_FILE, [])
    raw_all = new_jobs + raw_all
    save_json(RAW_ALL_FILE, raw_all)

    seen.update(j["slug"] for j in new_jobs)
    save_json(SEEN_FILE, sorted(seen))
    print(f"  seen.json updated ({len(seen)} total slugs tracked)")


if __name__ == "__main__":
    main()
