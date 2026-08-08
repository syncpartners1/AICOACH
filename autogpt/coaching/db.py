"""PostgreSQL database management module for ABN Co-Navigator (GCP Cloud SQL / PostgreSQL)."""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from autogpt.coaching.config import coaching_config

logger = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None


def get_db_url() -> str:
    """Get the active PostgreSQL connection URL."""
    url = (coaching_config.database_url or os.getenv("DATABASE_URL", "")).strip()
    if not url and coaching_config.supabase_url:
        # Construct direct postgres URL from Supabase URL if database_url not set
        parsed = urlparse(coaching_config.supabase_url)
        project_ref = parsed.netloc.split('.')[0]
        password = coaching_config.supabase_service_key
        url = f"postgresql://postgres:{password}@db.{project_ref}.supabase.co:5432/postgres"
    return url.strip()


def get_pool() -> ThreadedConnectionPool:
    """Initialize or get the global ThreadedConnectionPool."""
    global _pool
    if _pool is None or _pool.closed:
        db_url = get_db_url()
        if not db_url:
            raise ValueError("No DATABASE_URL configured.")
        logger.info("Initializing PostgreSQL connection pool...")
        _pool = ThreadedConnectionPool(minconn=1, maxconn=20, dsn=db_url)
    return _pool


@contextmanager
def get_db_cursor(commit: bool = False):
    """Context manager providing a dictionary cursor from the connection pool."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
            if commit:
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute_query(
    sql: str,
    params: Optional[tuple | dict] = None,
    fetch_one: bool = False,
    fetch_all: bool = False,
    commit: bool = False,
) -> Any:
    """Execute a parameterized SQL query against the database."""
    with get_db_cursor(commit=commit) as cursor:
        cursor.execute(sql, params or ())
        if fetch_one:
            res = cursor.fetchone()
            return dict(res) if res else None
        if fetch_all:
            res = cursor.fetchall()
            return [dict(r) for r in res]
        return cursor.rowcount


def init_db(schema_path: Optional[str] = None) -> None:
    """Initialize database schema from SQL file if not present."""
    if not schema_path:
        schema_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    if not os.path.exists(schema_path):
        logger.warning(f"Schema file not found at {schema_path}")
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    logger.info("Applying database schema...")
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql_script)
            conn.commit()
        logger.info("Database schema applied successfully.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error applying database schema: {e}")
        raise
    finally:
        pool.putconn(conn)


# ── Postgrest-Compatible SQL Query Wrapper for GCP Cloud SQL ──────────────────

class PGResponse:
    def __init__(self, data: Any):
        self.data = data


class PGTableQuery:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.op = "SELECT"
        self.select_cols = "*"
        self.where_clauses: List[str] = []
        self.params: Dict[str, Any] = {}
        self.insert_data: Any = None
        self.update_data: Any = None
        self.order_clause: Optional[str] = None
        self.limit_val: Optional[int] = None
        self._param_idx = 0

    def _next_param(self, prefix="p") -> str:
        self._param_idx += 1
        return f"{prefix}_{self._param_idx}"

    def select(self, cols="*") -> PGTableQuery:
        self.op = "SELECT"
        self.select_cols = cols
        return self

    def insert(self, data) -> PGTableQuery:
        self.op = "INSERT"
        self.insert_data = data
        return self

    def upsert(self, data) -> PGTableQuery:
        self.op = "UPSERT"
        self.insert_data = data
        return self

    def update(self, data) -> PGTableQuery:
        self.op = "UPDATE"
        self.update_data = data
        return self

    def delete(self) -> PGTableQuery:
        self.op = "DELETE"
        return self

    def eq(self, col: str, val: Any) -> PGTableQuery:
        if val is None:
            self.where_clauses.append(f"{col} IS NULL")
        else:
            p_name = self._next_param(col)
            self.where_clauses.append(f"{col} = %({p_name})s")
            self.params[p_name] = val
        return self

    def neq(self, col: str, val: Any) -> PGTableQuery:
        if val is None:
            self.where_clauses.append(f"{col} IS NOT NULL")
        else:
            p_name = self._next_param(col)
            self.where_clauses.append(f"{col} != %({p_name})s")
            self.params[p_name] = val
        return self

    def is_(self, col: str, val: Any) -> PGTableQuery:
        if val is None or str(val).lower() in ("null", "none"):
            self.where_clauses.append(f"{col} IS NULL")
        else:
            self.eq(col, val)
        return self

    def gte(self, col: str, val: Any) -> PGTableQuery:
        p_name = self._next_param(col)
        self.where_clauses.append(f"{col} >= %({p_name})s")
        self.params[p_name] = val
        return self

    def lte(self, col: str, val: Any) -> PGTableQuery:
        p_name = self._next_param(col)
        self.where_clauses.append(f"{col} <= %({p_name})s")
        self.params[p_name] = val
        return self

    def gt(self, col: str, val: Any) -> PGTableQuery:
        p_name = self._next_param(col)
        self.where_clauses.append(f"{col} > %({p_name})s")
        self.params[p_name] = val
        return self

    def lt(self, col: str, val: Any) -> PGTableQuery:
        p_name = self._next_param(col)
        self.where_clauses.append(f"{col} < %({p_name})s")
        self.params[p_name] = val
        return self

    def order(self, col: str, desc: bool = False) -> PGTableQuery:
        direction = "DESC" if desc else "ASC"
        self.order_clause = f"ORDER BY {col} {direction}"
        return self

    def limit(self, count: int) -> PGTableQuery:
        self.limit_val = count
        return self

    def execute(self) -> PGResponse:
        where_str = (" WHERE " + " AND ".join(self.where_clauses)) if self.where_clauses else ""

        if self.op == "SELECT":
            sql = f"SELECT {self.select_cols} FROM {self.table_name}{where_str}"
            if self.order_clause:
                sql += f" {self.order_clause}"
            if self.limit_val is not None:
                sql += f" LIMIT {self.limit_val}"
            res = execute_query(sql, self.params, fetch_all=True)
            return PGResponse(data=res or [])

        elif self.op in ("INSERT", "UPSERT"):
            rows = self.insert_data if isinstance(self.insert_data, list) else [self.insert_data]
            all_res = []
            for item in rows:
                cols = list(item.keys())
                cols_str = ", ".join(cols)
                item_params = {}
                placeholders = []
                for c in cols:
                    p_name = self._next_param(c)
                    val = item[c]
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)
                    item_params[p_name] = val
                    placeholders.append(f"%({p_name})s")
                ph_str = ", ".join(placeholders)

                conflict_str = ""
                if self.op == "UPSERT":
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
                    pk = pk_map.get(self.table_name, "id")
                    update_assigns = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != pk])
                    conflict_str = f" ON CONFLICT ({pk}) DO UPDATE SET {update_assigns}" if update_assigns else f" ON CONFLICT ({pk}) DO NOTHING"

                sql = f"INSERT INTO {self.table_name} ({cols_str}) VALUES ({ph_str}){conflict_str} RETURNING *;"
                res = execute_query(sql, item_params, fetch_one=True, commit=True)
                if res:
                    all_res.append(res)
            return PGResponse(data=all_res if isinstance(self.insert_data, list) else (all_res[0] if all_res else {}))

        elif self.op == "UPDATE":
            item = self.update_data or {}
            cols = list(item.keys())
            set_clauses = []
            upd_params = dict(self.params)
            for c in cols:
                p_name = self._next_param(c)
                val = item[c]
                if isinstance(val, (dict, list)):
                    val = json.dumps(val)
                upd_params[p_name] = val
                set_clauses.append(f"{c} = %({p_name})s")
            set_str = ", ".join(set_clauses)
            sql = f"UPDATE {self.table_name} SET {set_str}{where_str} RETURNING *;"
            res = execute_query(sql, upd_params, fetch_all=True, commit=True)
            return PGResponse(data=res or [])

        elif self.op == "DELETE":
            sql = f"DELETE FROM {self.table_name}{where_str} RETURNING *;"
            res = execute_query(sql, self.params, fetch_all=True, commit=True)
            return PGResponse(data=res or [])

        return PGResponse(data=[])


class PGClient:
    """PostgreSQL client presenting Supabase table interface."""

    def table(self, name: str) -> PGTableQuery:
        return PGTableQuery(name)
