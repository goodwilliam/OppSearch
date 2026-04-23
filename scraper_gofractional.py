import os
import re
import json
from datetime import date

import cloudscraper

BASE_URL = "https://www.gofractional.com"
SOURCE_NAME = "gofractional"

DATA_DIR = "docs/data"
SEEN_FILE = os.path.join(DATA_DIR, "seen.json")
RAW_DIR = os.path.join(DATA_DIR, "raw")
FLAGGED_DIR = os.path.join(DATA_DIR, "flagged")
OPPORTUNITIES_FILE = os.path.join(DATA_DIR, "opportunities.json")
RAW_ALL_FILE = os.path.join(DATA_DIR, "raw_all.json")


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_build_id(scraper):
    resp = scraper.get(BASE_URL, timeout=15)
    resp.raise_for_status()
    match = re.search(r'"buildId":"([^"]+)"', resp.text)
    if not match:
        raise RuntimeError("Could not find Next.js buildId in gofractional homepage")
    return match.group(1)


def scrape_gofractional():
    scraper = cloudscraper.create_scraper()
    build_id = get_build_id(scraper)

    url = f"{BASE_URL}/_next/data/{build_id}/jobs/design.json"
    resp = scraper.get(url, timeout=15)
    resp.raise_for_status()

    raw_jobs = resp.json()["pageProps"]["data"]["publicJobs"]["jobs"]

    jobs = []
    for j in raw_jobs:
        rate = ""
        if j.get("minHourlyRate") and j.get("maxHourlyRate"):
            rate = f"${j['minHourlyRate']}-${j['maxHourlyRate']}/hr"
        elif j.get("minHourlyRate"):
            rate = f"${j['minHourlyRate']}/hr"

        hours = ""
        if j.get("minWeeklyHours") and j.get("maxWeeklyHours"):
            hours = f"{j['minWeeklyHours']}-{j['maxWeeklyHours']} hrs/wk"
        elif j.get("minWeeklyHours"):
            hours = f"{j['minWeeklyHours']} hrs/wk"

        jobs.append({
            "slug": j["slug"],
            "url": f"{BASE_URL}/job/{j['slug']}",
            "title": j["title"],
            "company": j.get("sourceCompanyName") or "",
            "location": j.get("location") or "",
            "rate": rate,
            "hours": hours,
            "posted": (j.get("createdAt") or "")[:10],
            "source": SOURCE_NAME,
        })

    return jobs


def main():
    today = date.today().isoformat()
    seen = set(load_json(SEEN_FILE, []))

    print("Scraping gofractional.com...")
    all_jobs = scrape_gofractional()
    print(f"  Found {len(all_jobs)} total listings")

    new_jobs = [j for j in all_jobs if j["slug"] not in seen]
    print(f"  {len(new_jobs)} new (not seen before)")

    if not new_jobs:
        print("Nothing new today.")
        return

    for job in new_jobs:
        job["date_scraped"] = today
        job["flagged"] = True  # all jobs here are already design roles

    save_json(os.path.join(RAW_DIR, f"{today}-gofractional.json"), new_jobs)
    flagged_today = new_jobs
    save_json(os.path.join(FLAGGED_DIR, f"{today}-gofractional.json"), flagged_today)
    print(f"  {len(flagged_today)} matched keywords:")
    for j in flagged_today:
        print(f"    ✓ {j['title']} @ {j['company']}")

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
