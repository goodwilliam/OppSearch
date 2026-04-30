import os
import json
import re
import html as html_module
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

DATA_DIR = "docs/data"
HN_JOBS_FILE = os.path.join(DATA_DIR, "hn_jobs.json")
HN_SEEN_FILE = os.path.join(DATA_DIR, "hn_seen.json")

REMOTE_KEYWORDS = ["remote", "anywhere", "distributed", "wfh", "work from home"]

# Match in first line only — covers "UX Designer", "Brand Designers", "Creative Director" etc.
DESIGN_PATTERN = re.compile(
    r"\bdesigners?\b|creative[\s\-]?director|art[\s\-]?director"
    r"|head[\s\-]of[\s\-]design|design[\s\-]lead|design[\s\-]director"
    r"|design[\s\-]manager|\bux[\s/\-]?designer|\bui[\s/\-]?designer"
    r"|\bproduct[\s\-]designer|\bbrand[\s\-]designer",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(
    "|".join(re.escape(k) for k in REMOTE_KEYWORDS),
    re.IGNORECASE,
)


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def find_wih_thread():
    now = datetime.utcnow()
    month = now.strftime("%B")
    year = now.year
    r = requests.get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "query": f"Ask HN Who is hiring {month} {year}",
            "tags": "story",
            "hitsPerPage": 5,
        },
        timeout=10,
    )
    for hit in r.json().get("hits", []):
        title = hit.get("title", "").lower()
        if "who is hiring" in title and str(year) in title:
            return hit["objectID"], hit.get("title", "")
    return None, None


def get_comment_ids(thread_id):
    r = requests.get(
        f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json",
        timeout=10,
    )
    return r.json().get("kids", [])


def fetch_comment(comment_id):
    try:
        r = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json",
            timeout=10,
        )
        return r.json()
    except Exception:
        return None


def parse_comment(comment, thread_title):
    if not comment or comment.get("dead") or comment.get("deleted"):
        return None

    raw_html = comment.get("text", "")
    if not raw_html:
        return None

    # Strip HTML to plain text
    plain = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)

    # Search full text — many companies list roles in the body, not just the header line
    if not DESIGN_PATTERN.search(plain):
        return None
    if not REMOTE_PATTERN.search(plain):
        return None

    first_line = plain.split("\n")[0][:200].strip()

    # Parse timestamp
    ts = comment.get("time", 0)
    posted = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""

    return {
        "id": f"hn:{comment['id']}",
        "comment_id": comment["id"],
        "thread_title": thread_title,
        "first_line": first_line,
        "url": f"https://news.ycombinator.com/item?id={comment['id']}",
        "posted": posted,
        "remote": True,
        "source": "hackernews",
    }


def main():
    today = date.today().isoformat()
    seen = set(load_json(HN_SEEN_FILE, []))
    existing = load_json(HN_JOBS_FILE, [])

    print("Finding current Who's Hiring thread...")
    thread_id, thread_title = find_wih_thread()
    if not thread_id:
        print("  Could not find thread — skipping.")
        return
    print(f"  Found: {thread_title} (id={thread_id})")

    all_ids = get_comment_ids(thread_id)
    print(f"  {len(all_ids)} top-level comments")

    new_ids = [i for i in all_ids if f"hn:{i}" not in seen]
    print(f"  {len(new_ids)} new (not seen before)")

    if not new_ids:
        print("  Nothing new.")
        return

    # Fetch new comments in parallel
    new_jobs = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_comment, i): i for i in new_ids}
        for future in as_completed(futures):
            comment = future.result()
            parsed = parse_comment(comment, thread_title)
            if parsed:
                parsed["date_scraped"] = today
                new_jobs.append(parsed)

    print(f"  {len(new_jobs)} matched design + remote keywords")
    for j in new_jobs:
        print(f"    {j['first_line'][:80]}")

    if not new_jobs:
        # Still mark all as seen so we don't re-fetch next time
        seen.update(f"hn:{i}" for i in new_ids)
        save_json(HN_SEEN_FILE, sorted(seen))
        print("  No matches but updated seen.json")
        return

    updated = new_jobs + existing
    save_json(HN_JOBS_FILE, updated)

    seen.update(f"hn:{i}" for i in new_ids)
    save_json(HN_SEEN_FILE, sorted(seen))
    print(f"  hn_jobs.json updated — {len(updated)} total")


if __name__ == "__main__":
    main()
