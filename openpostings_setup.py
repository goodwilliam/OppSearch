"""
Configure the OpenPostings jobs.db before running the sync server.
- Enables only tech/design-relevant ATS platforms
- Skips government, education, hourly-worker platforms
"""
import sqlite3
import json
import sys

DB_PATH = "/tmp/openpostings/jobs.db"

# Tech and creative company ATS platforms only
ENABLED_ATS = [
    "ashby",           # Tech startups — great for design roles
    "greenhouse",      # Tech companies
    "lever",           # Tech companies
    "bamboohr",        # SMBs and startups
    "breezy",          # SMBs
    "icims",           # Enterprise tech
    "zoho",            # Various
    "join",            # European tech companies
    "rippling",        # Tech-forward companies
    "teamtailor",      # Design-forward companies
    "freshteam",       # Startups
    "workday",         # Large companies with design teams
    "gem",             # Tech companies
    "hibob",           # Tech companies
    "loxo",            # Agencies and companies
    "getro",           # VC portfolio companies (high signal)
    "recruitee",       # Various companies
    "smartrecruiters", # Various tech companies
    "jobvite",         # Tech companies
    "pinpointhq",      # UK tech companies
    "manatal",         # Various
    "talentlyft",      # Various
    "careerspage",     # Various
]

conn = sqlite3.connect(DB_PATH)
conn.execute("""
    INSERT OR REPLACE INTO SyncServiceSettings (id, ats_request_queue_concurrency, sync_enabled_ats)
    VALUES (1, 2, ?)
""", [json.dumps(ENABLED_ATS)])
conn.commit()

count = conn.execute(
    "SELECT COUNT(*) FROM companies WHERE ATS_name IN ({})".format(
        ",".join("?" * len(ENABLED_ATS))
    ),
    ENABLED_ATS,
).fetchone()[0]

conn.close()
print(f"Configured {len(ENABLED_ATS)} ATS platforms ({count} companies to sync)")
