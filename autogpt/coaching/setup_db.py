#!/usr/bin/env python3
"""
Apply the ABN Co-Navigator schema (and pending migrations) to Supabase.

Reads credentials from .env automatically.

Usage:
    # Full schema bootstrap (new project):
    python autogpt/coaching/setup_db.py

    # Migrations only (existing project — safe to re-run):
    python autogpt/coaching/setup_db.py --migrate

Requires SUPABASE_PAT **or** SUPABASE_SERVICE_KEY in .env.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

PAT         = os.environ.get("SUPABASE_PAT", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PROJECT_REF = "aakbytofflrctepuedyh"

if not PAT and not SERVICE_KEY:
    print("ERROR: Set SUPABASE_PAT or SUPABASE_SERVICE_KEY in .env")
    print("  PAT:         https://supabase.com/dashboard/account/tokens")
    print("  Service key: https://supabase.com/dashboard/project/"
          f"{PROJECT_REF}/settings/api")
    sys.exit(1)

# ── Parse schema file ─────────────────────────────────────────────────────────
SCHEMA_FILE = Path(__file__).parent / "supabase_schema.sql"
raw_sql = SCHEMA_FILE.read_text()

MIGRATE_MARKER = "-- MIGRATIONS"
migrate_only = "--migrate" in sys.argv

if migrate_only:
    # Only statements after the MIGRATIONS marker
    idx = raw_sql.find(MIGRATE_MARKER)
    if idx == -1:
        print("No MIGRATIONS section found in schema file.")
        sys.exit(0)
    sql_to_run = raw_sql[idx:]
else:
    sql_to_run = raw_sql


def _parse_statements(sql: str) -> list[str]:
    """Split on semicolons, strip comment-only lines, drop blanks."""
    stmts = []
    for raw in sql.split(";"):
        stmt = "\n".join(
            line for line in raw.splitlines()
            if not line.strip().startswith("--")
        ).strip()
        if stmt:
            stmts.append(stmt)
    return stmts


statements = _parse_statements(sql_to_run)

# ── Supabase Management API ───────────────────────────────────────────────────
MGMT_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"


def run_sql(query: str, token: str) -> dict:
    payload = json.dumps({"query": query + ";"}).encode()
    req = urllib.request.Request(
        MGMT_URL,
        data=payload,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode()}
    except Exception as e:
        return {"status": 0, "error": str(e)}


# ── Auth: try PAT first, fall back to service key ─────────────────────────────
print(f"Connecting to Supabase project: {PROJECT_REF}")
TOKEN = None
probe = run_sql("SELECT current_database()", PAT) if PAT else {"status": 0}
if probe.get("status") in (200, 201):
    TOKEN = PAT
    print("  Auth: personal access token ✅")
elif SERVICE_KEY:
    probe = run_sql("SELECT current_database()", SERVICE_KEY)
    if probe.get("status") in (200, 201):
        TOKEN = SERVICE_KEY
        print("  Auth: service role key ✅")

if not TOKEN:
    print(f"ERROR: Cannot authenticate. Last response: {probe}")
    sys.exit(1)

mode = "MIGRATIONS ONLY" if migrate_only else "FULL SCHEMA"
print(f"  Mode: {mode}  |  {len(statements)} statement(s) to execute")
print("-" * 64)

# ── Execute ───────────────────────────────────────────────────────────────────
errors = []
skipped = 0
applied = 0

for i, stmt in enumerate(statements, 1):
    preview = stmt.replace("\n", " ")[:70]
    result = run_sql(stmt, TOKEN)
    status = result.get("status", 0)

    if status in (200, 201):
        applied += 1
        print(f"  [{i:02d}] ✅  {preview}")
    else:
        err = str(result.get("error", result.get("body", "unknown")))
        if any(x in err for x in ["already exists", "duplicate column",
                                   "duplicate key", "relation already"]):
            skipped += 1
            print(f"  [{i:02d}] ⏭   {preview}  (already exists)")
        else:
            errors.append(i)
            print(f"  [{i:02d}] ❌  {preview}")
            print(f"         {err[:140]}")

print("-" * 64)
print(f"Applied: {applied}  Skipped: {skipped}  Errors: {len(errors)}")

if errors:
    print(f"\n⚠️  {len(errors)} error(s) on statement(s): {errors}")
    sys.exit(1)
else:
    if migrate_only:
        print("\n✅ Migrations applied successfully.")
    else:
        print("\n✅ Schema applied successfully.")
        if not SERVICE_KEY:
            print("\nNext step: add SUPABASE_SERVICE_KEY to .env")
            print("  Get it: https://supabase.com/dashboard/project/"
                  f"{PROJECT_REF}/settings/api")
        else:
            print("SUPABASE_SERVICE_KEY is set. Coaching API is ready.")
            print("  Run: uvicorn autogpt.coaching.api:app --reload")
