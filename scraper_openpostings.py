"""
Extract design jobs from the OpenPostings jobs.db after sync completes.
Writes new matches to docs/data/jobs.json.
"""
import os
import json
import re
import sqlite3
from datetime import date

DB_PATH = "/tmp/openpostings/jobs.db"
JOBS_FILE = "docs/data/jobs.json"
SEEN_FILE = "docs/data/jobs_seen.json"

DESIGN_PATTERN = re.compile(
    r"\bdesigners?\b|creative[\s\-]?director|art[\s\-]?director"
    r"|head[\s\-]of[\s\-]design|design[\s\-]lead|design[\s\-]director"
    r"|design[\s\-]manager|\bux[\s/\-]?designer|\bui[\s/\-]?designer"
    r"|\bproduct[\s\-]designer|\bbrand[\s\-]designer|\bvisual[\s\-]designer"
    r"|\bgraphic[\s\-]designer|\bmotion[\s\-]designer",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(
    r"remote|anywhere|distributed|wfh|work[\s\-]from[\s\-]home",
    re.IGNORECASE,
)

ATS_URL_MAP = [
    ("jobs.lever.co",             "lever"),
    ("boards.greenhouse.io",      "greenhouse"),
    ("job-boards.greenhouse.io",  "greenhouse"),
    ("jobs.ashbyhq.com",          "ashby"),
    ("app.bamboohr.com",          "bamboohr"),
    ("breezy.hr",                 "breezy"),
    ("careers.icims.com",         "icims"),
    ("jobs.zoho.com",             "zoho"),
    ("join.com",                  "join"),
    ("app.rippling.com",          "rippling"),
    ("jobs.teamtailor.com",       "teamtailor"),
    ("freshteam.com",             "freshteam"),
    ("workday.com",               "workday"),
    ("app.gem.com",               "gem"),
    ("app.hibob.com",             "hibob"),
    ("app.loxo.co",               "loxo"),
    ("getro.com",                 "getro"),
    ("app.recruitee.com",         "recruitee"),
    ("jobs.smartrecruiters.com",  "smartrecruiters"),
    ("jobs.jobvite.com",          "jobvite"),
    ("app.pinpointhq.com",        "pinpointhq"),
    ("app.manatal.com",           "manatal"),
    ("app.talentlyft.com",        "talentlyft"),
]


def platform_from_url(url):
    url_lower = url.lower()
    for fragment, name in ATS_URL_MAP:
        if fragment in url_lower:
            return name
    return "other"


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    if not os.path.exists(DB_PATH):
        print("OpenPostings DB not found — skipping.")
        return

    today = date.today().isoformat()
    seen = set(load_json(SEEN_FILE, []))
    existing = load_json(JOBS_FILE, [])

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT company_name, position_name, job_posting_url, posting_date "
        "FROM Postings WHERE hidden = 0"
    ).fetchall()
    conn.close()

    print(f"  {len(rows)} total postings in DB")

    new_jobs = []
    for row in rows:
        title   = (row["position_name"] or "").strip()
        company = (row["company_name"]  or "").strip()
        url     = (row["job_posting_url"] or "").strip()

        if not url or not title:
            continue

        uid = f"op:{url}"
        if uid in seen:
            continue

        if not DESIGN_PATTERN.search(title):
            continue

        platform = platform_from_url(url)
        remote   = bool(REMOTE_PATTERN.search(title))

        new_jobs.append({
            "id":              uid,
            "title":           title,
            "company":         company,
            "url":             url,
            "date_scraped":    row["posting_date"] or today,
            "employment_type": "unknown",
            "location":        "",
            "remote":          remote,
            "platform":        platform,
            "source":          "openpostings",
        })
        seen.add(uid)

    print(f"  {len(new_jobs)} new design jobs from OpenPostings")
    for j in new_jobs[:20]:
        print(f"    [{j['platform']}] {j['company']} — {j['title']}")

    if new_jobs:
        updated = new_jobs + existing
        save_json(JOBS_FILE, updated)
        save_json(SEEN_FILE, sorted(seen))
        print(f"  jobs.json updated — {len(updated)} total")
    else:
        print("  Nothing new.")


if __name__ == "__main__":
    main()
