"""Local-first storage and retryable Supabase synchronization for Tosca runs."""

from __future__ import annotations

import os
import sqlite3
import uuid
import base64
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATABASE_FILE = Path(os.getenv("TOSCA_SQLITE_FILE", BASE_DIR / "tosca_results.sqlite3"))

DATE_FORMATS = (
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@contextmanager
def _connection(db_path: Path | str):
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _timestamp(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).isoformat()
        except ValueError:
            continue
    return None


def initialize_database(db_path: Path | str = DATABASE_FILE) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS execution_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                sync_error TEXT
            );
            CREATE TABLE IF NOT EXISTS test_case_results (
                run_id TEXT NOT NULL REFERENCES execution_runs(run_id) ON DELETE CASCADE,
                case_index INTEGER NOT NULL,
                environment_name TEXT NOT NULL,
                module_name TEXT NOT NULL,
                testcase_name TEXT NOT NULL,
                result TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                created_by TEXT,
                created_at TEXT,
                PRIMARY KEY (run_id, case_index)
            );
            CREATE INDEX IF NOT EXISTS test_case_results_start_time_idx
                ON test_case_results (start_time);
            """
        )


def save_execution_run(
    records: list[dict[str, Any]], db_path: Path | str = DATABASE_FILE
) -> str:
    """Commit a complete run locally before attempting any cloud operation."""
    if not records:
        raise ValueError("Cannot store an execution run with no testcase records.")

    initialize_database(db_path)
    run_id = str(uuid.uuid4())
    started_at = min(
        (_timestamp(record.get("StartTime")) for record in records if record.get("StartTime")),
        default=None,
    ) or datetime.now().astimezone().isoformat()
    completed_at = datetime.now().astimezone().isoformat()

    with _connection(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO execution_runs (run_id, started_at, completed_at) VALUES (?, ?, ?)",
            (run_id, started_at, completed_at),
        )
        connection.executemany(
            """
            INSERT INTO test_case_results (
                run_id, case_index, environment_name, module_name,
                testcase_name, result, start_time, end_time, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    index,
                    str(record.get("Environment_Name") or ""),
                    str(record.get("Module_Name") or ""),
                    str(record.get("TestCase_Name") or ""),
                    str(record.get("Result") or "Unknown"),
                    _timestamp(record.get("StartTime")),
                    _timestamp(record.get("EndTime")),
                    str(record.get("CreatedBy") or ""),
                    _timestamp(record.get("CreatedAt")),
                )
                for index, record in enumerate(records)
            ],
        )
    return run_id


def get_execution_results(db_path: Path | str = DATABASE_FILE) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with _connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT run_id, case_index, environment_name, module_name,
                   testcase_name, result, start_time, end_time, created_by, created_at
            FROM test_case_results
            ORDER BY start_time DESC, run_id, case_index
            """
        ).fetchall()

    return [_to_dashboard_row(dict(row)) for row in rows]


def _to_dashboard_row(item: dict[str, Any]) -> dict[str, Any]:
    """Add the field aliases used by the dashboard HTML and the reporting scripts."""
    month = item["start_time"][:7] if item.get("start_time") else None
    item.update(
        {
            "Environment_Name": item["environment_name"],
            "Module_Name": item["module_name"],
            "TestCase_Name": item["testcase_name"],
            # Field names read by DashBoard_Light.html
            "Environment": item["environment_name"],
            "Module": item["module_name"],
            "TestCaseName": item["testcase_name"],
            "Result": item["result"],
            "StartTime": item["start_time"],
            "EndTime": item["end_time"],
            "CreatedBy": item["created_by"],
            "CreatedAt": item["created_at"],
            "Month": month,
            "environment": item["environment_name"],
            "module": item["module_name"],
            "testCase": item["testcase_name"],
            "result": item["result"],
            "startTime": item["start_time"],
            "endTime": item["end_time"],
            "createdBy": item["created_by"],
            "createdAt": item["created_at"],
            "month": month,
        }
    )
    return item


_RESULT_COLUMNS = (
    "run_id,case_index,environment_name,module_name,testcase_name,"
    "result,start_time,end_time,created_by,created_at"
)


def get_cloud_execution_results(page_size: int = 1000) -> list[dict[str, Any]]:
    """Read every testcase row from Supabase, paging past the API row limit."""
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set to read from Supabase.")

    from supabase import create_client

    client = create_client(url, key)
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            client.table("test_case_results")
            .select(_RESULT_COLUMNS)
            .order("start_time", desc=True, nullsfirst=False)
            .order("run_id")
            .order("case_index")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return [_to_dashboard_row(dict(row)) for row in rows]


def get_dashboard_results(source: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """Return (rows, source_used) based on RESULTS_SOURCE: supabase, local or auto.

    'auto' (default) reads Supabase and falls back to local SQLite if the cloud
    is unreachable or not configured.
    """
    source = (source or os.getenv("RESULTS_SOURCE", "auto")).strip().lower()
    if source == "local":
        return get_execution_results(), "local"
    if source == "supabase":
        return get_cloud_execution_results(), "supabase"
    try:
        return get_cloud_execution_results(), "supabase"
    except Exception:
        return get_execution_results(), "local"


def sync_pending_runs(db_path: Path | str = DATABASE_FILE) -> dict[str, int | str]:
    """Upsert unsynced local runs; any failure leaves them queued for retry."""
    initialize_database(db_path)
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return {"status": "not_configured", "synced_runs": 0}
    if key.startswith("sb_publishable_"):
        return {"status": "server_secret_required", "synced_runs": 0}
    if key.count(".") == 2:
        try:
            payload = key.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            role = json.loads(base64.urlsafe_b64decode(payload)).get("role")
        except (ValueError, json.JSONDecodeError):
            role = None
        if role != "service_role":
            return {"status": "server_secret_required", "synced_runs": 0}

    try:
        from supabase import create_client

        client = create_client(url, key)
        with _connection(db_path) as connection:
            connection.row_factory = sqlite3.Row
            pending = connection.execute(
                "SELECT run_id, started_at, completed_at FROM execution_runs "
                "WHERE sync_status != 'synced' ORDER BY started_at, run_id"
            ).fetchall()

        synced_count = 0
        for run in pending:
            run_id = run["run_id"]
            client.table("execution_runs").upsert(
                {
                    "id": run_id,
                    "started_at": run["started_at"],
                    "completed_at": run["completed_at"],
                },
                on_conflict="id",
            ).execute()

            with _connection(db_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT case_index, environment_name, module_name, testcase_name,
                           result, start_time, end_time, created_by, created_at
                    FROM test_case_results WHERE run_id = ? ORDER BY case_index
                    """,
                    (run_id,),
                ).fetchall()

            cloud_rows = [
                {
                    "run_id": run_id,
                    "case_index": row["case_index"],
                    "environment_name": row["environment_name"],
                    "module_name": row["module_name"],
                    "testcase_name": row["testcase_name"],
                    "result": row["result"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            for offset in range(0, len(cloud_rows), 500):
                client.table("test_case_results").upsert(
                    cloud_rows[offset : offset + 500],
                    on_conflict="run_id,case_index",
                ).execute()

            with _connection(db_path) as connection:
                connection.execute(
                    "UPDATE execution_runs SET sync_status = 'synced', sync_error = NULL "
                    "WHERE run_id = ?",
                    (run_id,),
                )
            synced_count += 1

        return {"status": "ok", "synced_runs": synced_count}
    except Exception:
        with _connection(db_path) as connection:
            connection.execute(
                "UPDATE execution_runs SET sync_status = 'pending', "
                "sync_error = 'Cloud sync failed; will retry on next run.' "
                "WHERE sync_status != 'synced'"
            )
        return {"status": "pending", "synced_runs": 0}


def sync_status(db_path: Path | str = DATABASE_FILE) -> dict[str, int]:
    initialize_database(db_path)
    with _connection(db_path) as connection:
        total, pending = connection.execute(
            "SELECT count(*), sum(CASE WHEN sync_status != 'synced' THEN 1 ELSE 0 END) "
            "FROM execution_runs"
        ).fetchone()
    return {"total_runs": total or 0, "pending_runs": pending or 0}