"""Temporary Tosca dashboard server backed by the existing Excel workbook.

Place this file in the same folder as:
  - DashBoard_Light.html
  - ExecutionResult.xlsx

Install:  pip install flask pandas openpyxl
Run:      python server.py
Open:     http://127.0.0.1:5000

This is a validation bridge only. It reads Excel on each API request so that
changes to the workbook are reflected without restarting the server. It does
not connect to SQL Server yet.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from flask import Flask, jsonify, send_file

BASE_DIR = Path(__file__).resolve().parent
EXCEL_FILE = Path(os.getenv("TOSCA_EXCEL_FILE", BASE_DIR / "ExecutionResult.xlsx"))
DASHBOARD_FILE = Path(os.getenv("TOSCA_DASHBOARD_FILE", BASE_DIR / "DashBoard_Light.html"))
SHEET_NAME = os.getenv("TOSCA_SHEET_NAME", "ExecutionResult")

REQUIRED_COLUMNS = [
    "Environment_Name",
    "Module_Name",
    "TestCase_Name",
    "Result",
    "StartTime",
]
OPTIONAL_COLUMNS = ["EndTime", "CreatedBy", "CreatedAt"]

app = Flask(__name__)


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy/date values into JSON-serializable Python values."""
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def load_execution_results() -> list[dict[str, Any]]:
    if not EXCEL_FILE.exists():
        raise FileNotFoundError(
            f"Excel workbook not found: {EXCEL_FILE}. Place it beside server.py "
            "or set TOSCA_EXCEL_FILE to its full path."
        )

    df = pd.read_excel(EXCEL_FILE, sheet_name=SHEET_NAME, engine="openpyxl")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required Excel columns: {', '.join(missing)}. "
            f"Available columns: {', '.join(map(str, df.columns))}"
        )

    # Normalize dates before deriving the month; do not use a synthetic month.
    df["StartTime"] = pd.to_datetime(df["StartTime"], errors="coerce")
    if "EndTime" in df.columns:
        df["EndTime"] = pd.to_datetime(df["EndTime"], errors="coerce")
    if "CreatedAt" in df.columns:
        df["CreatedAt"] = pd.to_datetime(df["CreatedAt"], errors="coerce")

    # Keep the source column names intact for compatibility with the existing
    # Tosca Python script and dashboard data model. Add Month for grouping.
    if "Month" not in df.columns:
        df["Month"] = df["StartTime"].dt.strftime("%B %Y")

    # Add lowercase aliases as well, to make the API easier to consume from JS.
    aliases = {
        "environment": "Environment_Name",
        "module": "Module_Name",
        "testCase": "TestCase_Name",
        "result": "Result",
        "startTime": "StartTime",
        "endTime": "EndTime",
        "createdBy": "CreatedBy",
        "createdAt": "CreatedAt",
        "month": "Month",
    }

    rows: list[dict[str, Any]] = []
    for record in df.to_dict(orient="records"):
        row = {str(k): json_safe(v) for k, v in record.items()}
        for alias, source in aliases.items():
            if source in row:
                row[alias] = row[source]
        rows.append(row)
    return rows


@app.get("/")
def dashboard():
    if not DASHBOARD_FILE.exists():
        return (
            f"Dashboard HTML not found: {DASHBOARD_FILE}. "
            "Place DashBoard_Light.html beside server.py or set "
            "TOSCA_DASHBOARD_FILE.",
            404,
        )
    return send_file(DASHBOARD_FILE)


@app.get("/api/results")
def api_results():
    """Return all workbook rows as a JSON array for the dashboard."""
    try:
        rows = load_execution_results()
        response = jsonify(rows)
        response.headers["Cache-Control"] = "no-store"
        return response
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        app.logger.exception("Unable to load Tosca execution results")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "mode": "excel-validation",
            "excel_file": str(EXCEL_FILE),
            "dashboard_file": str(DASHBOARD_FILE),
            "sheet": SHEET_NAME,
        }
    )


@app.get("/api/summary")
def summary():
    """Small diagnostic summary to verify workbook data before UI integration."""
    try:
        rows = load_execution_results()
        results: dict[str, int] = {}
        environments: dict[str, int] = {}
        modules: dict[str, int] = {}
        for row in rows:
            result = str(row.get("Result") or "Unknown")
            environment = str(row.get("Environment_Name") or "Unknown")
            module = str(row.get("Module_Name") or "Unknown")
            results[result] = results.get(result, 0) + 1
            environments[environment] = environments.get(environment, 0) + 1
            modules[module] = modules.get(module, 0) + 1
        return jsonify(
            {
                "total_records": len(rows),
                "results": results,
                "environments": environments,
                "modules": modules,
                "first_start_time": min(
                    (r["StartTime"] for r in rows if r.get("StartTime")),
                    default=None,
                ),
                "last_start_time": max(
                    (r["StartTime"] for r in rows if r.get("StartTime")),
                    default=None,
                ),
            }
        )
    except Exception as exc:
        app.logger.exception("Unable to summarize Tosca execution results")
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    print(f"Excel workbook : {EXCEL_FILE}")
    print(f"Dashboard HTML: {DASHBOARD_FILE}")
    print("Open dashboard : http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
