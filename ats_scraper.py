import os
import json
import re
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

DATA_DIR = "docs/data"
COMPANIES_FILE = os.path.join(DATA_DIR, "companies.json")
JOBS_SEEN_FILE = os.path.join(DATA_DIR, "jobs_seen.json")
JOBS_FILE = os.path.join(DATA_DIR, "jobs.json")

# Single words matched at word boundaries
SINGLE_KEYWORDS = ["designer", "ux", "ui", "fractional"]

# Full phrases matched at word boundaries
PHRASE_KEYWORDS = [
    "creative director", "art director",
    "head of design", "vp of design",
    "design director", "design lead", "design manager",
    "visual design", "motion design", "interaction design",
    "design systems", "product design", "brand design",
    "user experience", "user interface",
]

KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in SINGLE_KEYWORDS + PHRASE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def is_relevant(title):
    return bool(KEYWORD_PATTERN.search(title))


def normalize_type(raw):
    if not raw:
        return "unknown"
    r = raw.lower()

    if any(w in r for w in ("fractional",)):
        return "fractional"
    if any(w in r for w in ("part-time", "part time", "parttime")):
        return "part-time"
    if any(w in r for w in ("contract", "contractor", "freelance", "temp", "temporary")):
        return "contract"
    if any(w in r for w in ("intern", "apprentice", "working student", "trainee")):
        return "internship"
    if any(w in r for w in (
        "full-time", "full time", "fulltime", "permanent", "regular",
        "employee", "cdi", "salary", "salaried", "on-roll",
    )):
        return "full-time"

    return "unknown"


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_lever(company):
    try:
        r = requests.get(
            f"https://api.lever.co/v0/postings/{company}?mode=json",
            timeout=12,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for j in r.json():
            title = j.get("text", "")
            if not is_relevant(title):
                continue
            jobs.append({
                "id": f"lever:{company}:{j['id']}",
                "title": title,
                "company": j.get("company") or company,
                "location": j.get("categories", {}).get("location", ""),
                "employment_type": normalize_type(j.get("categories", {}).get("commitment", "")),
                "url": j.get("hostedUrl") or f"https://jobs.lever.co/{company}/{j['id']}",
                "platform": "lever",
            })
        return jobs
    except Exception:
        return []


def fetch_greenhouse(company):
    try:
        r = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs",
            timeout=12,
        )
        if r.status_code != 200:
            return []
        jobs = []
        for j in r.json().get("jobs", []):
            title = j.get("title", "")
            if not is_relevant(title):
                continue
            jobs.append({
                "id": f"greenhouse:{company}:{j['id']}",
                "title": title,
                "company": company,
                "location": j.get("location", {}).get("name", ""),
                "employment_type": "unknown",
                "url": j.get("absolute_url", ""),
                "platform": "greenhouse",
            })
        return jobs
    except Exception:
        return []


ASHBY_QUERY = """
query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
    jobBoard: jobBoardWithTeams(
        organizationHostedJobsPageName: $organizationHostedJobsPageName
    ) {
        jobPostings {
            id
            title
            employmentType
            locationName
            externalLink
        }
    }
}
"""


def fetch_ashby(company):
    try:
        r = requests.post(
            "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams",
            json={
                "operationName": "ApiJobBoardWithTeams",
                "variables": {"organizationHostedJobsPageName": company},
                "query": ASHBY_QUERY,
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Referer": f"https://jobs.ashbyhq.com/{company}",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return []
        postings = (
            r.json().get("data", {}).get("jobBoard", {}) or {}
        ).get("jobPostings") or []
        jobs = []
        for j in postings:
            title = j.get("title", "")
            if not is_relevant(title):
                continue
            jobs.append({
                "id": f"ashby:{company}:{j['id']}",
                "title": title,
                "company": company,
                "location": j.get("locationName", ""),
                "employment_type": normalize_type(j.get("employmentType", "")),
                "url": j.get("externalLink") or f"https://jobs.ashbyhq.com/{company}/{j['id']}",
                "platform": "ashby",
            })
        return jobs
    except Exception:
        return []


def main():
    today = date.today().isoformat()
    companies = load_json(COMPANIES_FILE, {})
    seen = set(load_json(JOBS_SEEN_FILE, []))
    existing_jobs = load_json(JOBS_FILE, [])

    tasks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for company in companies.get("lever", []):
            tasks.append(executor.submit(fetch_lever, company))
        for company in companies.get("greenhouse", []):
            tasks.append(executor.submit(fetch_greenhouse, company))
        for company in companies.get("ashby", []):
            tasks.append(executor.submit(fetch_ashby, company))

        all_found = []
        for future in as_completed(tasks):
            all_found.extend(future.result())

    print(f"Design jobs found across all companies: {len(all_found)}")

    new_jobs = [j for j in all_found if j["id"] not in seen]
    print(f"New (not seen before): {len(new_jobs)}")

    if not new_jobs:
        print("Nothing new today.")
        return

    for j in new_jobs:
        j["date_scraped"] = today

    updated = new_jobs + existing_jobs
    save_json(JOBS_FILE, updated)

    seen.update(j["id"] for j in new_jobs)
    save_json(JOBS_SEEN_FILE, sorted(seen))

    print(f"jobs.json updated — {len(updated)} total, {len(new_jobs)} new today")

    by_type = {}
    for j in new_jobs:
        t = j["employment_type"]
        by_type[t] = by_type.get(t, 0) + 1
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")


if __name__ == "__main__":
    main()
