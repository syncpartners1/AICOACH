"""Migration script: Transfer all data from Supabase to GCP Cloud SQL (PostgreSQL).

Usage:
    python -m autogpt.coaching.migrate_supabase_to_gcp
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List

from supabase import create_client

from autogpt.coaching.config import coaching_config
from autogpt.coaching.db import execute_query, get_db_cursor, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TABLES_IN_ORDER = [
    "user_profiles",
    "objectives",
    "user_key_results",
    "clients",
    "coaching_sessions",
    "weekly_kr_activities",
    "daily_highlights",
    "coaching_learnings",
]


def migrate():
    """Extract all records from Supabase and insert into GCP Cloud SQL."""
    if not coaching_config.supabase_url or not coaching_config.supabase_service_key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set to read source data.")
        sys.exit(1)

    logger.info("Step 1: Initializing GCP Cloud SQL target database schema...")
    init_db()

    logger.info("Step 2: Connecting to Supabase source...")
    sp_client = create_client(coaching_config.supabase_url, coaching_config.supabase_service_key)

    total_migrated = 0

    for table in TABLES_IN_ORDER:
        logger.info(f"Migrating table: {table}...")
        try:
            res = sp_client.table(table).select("*").execute()
            rows: List[Dict[str, Any]] = res.data or []
        except Exception as e:
            logger.warning(f"Could not fetch table {table} from Supabase (may not exist yet): {e}")
            continue

        if not rows:
            logger.info(f"  → 0 rows found in Supabase table '{table}'.")
            continue

        logger.info(f"  → Found {len(rows)} rows in Supabase. Inserting into GCP Cloud SQL...")

        # Build column list and parameterized INSERT ON CONFLICT query
        columns = list(rows[0].keys())
        cols_str = ", ".join(columns)
        placeholders = ", ".join([f"%({c})s" for c in columns])

        # Primary key mapping for ON CONFLICT DO NOTHING
        pk_map = {
            "user_profiles": "user_id",
            "objectives": "objective_id",
            "user_key_results": "kr_id",
            "clients": "id",
            "coaching_sessions": "id",
            "weekly_kr_activities": "activity_id",
            "daily_highlights": "highlight_id",
            "coaching_learnings": "learning_id",
        }
        pk = pk_map.get(table, "id")

        insert_sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) ON CONFLICT ({pk}) DO NOTHING;"

        inserted_count = 0
        with get_db_cursor(commit=True) as cursor:
            for r in rows:
                # Convert complex structures (dict/list) to JSON strings if needed
                formatted_row = {}
                for k, v in r.items():
                    if isinstance(v, (dict, list)):
                        formatted_row[k] = json.dumps(v)
                    else:
                        formatted_row[k] = v

                cursor.execute(insert_sql, formatted_row)
                inserted_count += cursor.rowcount

        logger.info(f"  ✅ Table '{table}': {inserted_count}/{len(rows)} rows inserted into GCP Cloud SQL.")
        total_migrated += inserted_count

    # Verification Step
    logger.info("Step 3: Verification — Comparing table counts...")
    print("\n" + "=" * 60)
    print(f"{'Table Name':<25} | {'Supabase Count':<15} | {'GCP Cloud SQL Count':<15}")
    print("-" * 60)

    for table in TABLES_IN_ORDER:
        try:
            sp_count = len(sp_client.table(table).select("*").execute().data or [])
        except Exception:
            sp_count = 0

        try:
            gcp_res = execute_query(f"SELECT COUNT(*) as cnt FROM {table};", fetch_one=True)
            gcp_count = gcp_res["cnt"] if gcp_res else 0
        except Exception:
            gcp_count = 0

        print(f"{table:<25} | {sp_count:<15} | {gcp_count:<15}")

    print("=" * 60)
    logger.info("Data migration complete!")


if __name__ == "__main__":
    migrate()
