import re
import csv
import io
import json
import requests

CSV_URL = "https://storage.stapply.ai/jobs.csv"
OUT_FILE = "docs/data/companies.json"


def collect():
    print("Downloading CSV...")
    resp = requests.get(CSV_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    print(f"  {len(rows)} rows")

    companies = {"lever": set(), "ashby": set(), "greenhouse": set()}

    for row in rows:
        u = row.get("url", "")
        m = re.match(r"https://jobs\.lever\.co/([^/]+)/", u)
        if m:
            companies["lever"].add(m.group(1))
            continue
        m = re.match(r"https://jobs\.ashbyhq\.com/([^/]+)/", u)
        if m:
            companies["ashby"].add(m.group(1))
            continue
        m = re.match(r"https://(?:boards|job-boards)\.greenhouse\.io/([^/]+)/", u)
        if m:
            companies["greenhouse"].add(m.group(1))

    result = {p: sorted(slugs) for p, slugs in companies.items()}

    for p, slugs in result.items():
        print(f"  {p}: {len(slugs)} companies")

    with open(OUT_FILE, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Saved → {OUT_FILE}")


if __name__ == "__main__":
    collect()
