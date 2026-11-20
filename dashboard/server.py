"""Tosca dashboard server backed by local SQLite with Supabase sync.

Layout:
  dashboard/web/dashboard.html          dashboard page (served at /)
  data/.env                             settings and secrets
  data/tosca_results.sqlite3            local results database
  data/ToscaExecutionDashboard.html     static snapshot (served at /execution)

Install:  pip install -r dashboard/requirements.txt
Run:      python dashboard/server.py
Open:     http://127.0.0.1:5000

Dashboard rows are read from Supabase by default (RESULTS_SOURCE=auto), falling
back to local SQLite when the cloud is unavailable. Set RESULTS_SOURCE=local or
RESULTS_SOURCE=supabase to force one source.
"""

from __future__ import annotations

import os
import hmac
import secrets
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, session, url_for
from typing import Any

from result_store import (
    DATA_DIR,
    DATABASE_FILE,
    get_dashboard_results,
    sync_pending_runs,
    sync_status,
)

BASE_DIR = Path(__file__).resolve().parent

DASHBOARD_FILE = Path(os.getenv("TOSCA_DASHBOARD_FILE") or BASE_DIR / "web" / "dashboard.html")
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_bytes(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return jsonify({"error": "Authentication required."}), 401
        return view(*args, **kwargs)

    return wrapped


def load_execution_results() -> list[dict[str, Any]]:
    rows, _source = get_dashboard_results()
    return rows


@app.get("/")
def dashboard():
    if not DASHBOARD_FILE.exists():
        return (
            f"Dashboard HTML not found: {DASHBOARD_FILE}. "
            "Place dashboard.html in dashboard/web/ or set "
            "TOSCA_DASHBOARD_FILE.",
            404,
        )
    return send_file(DASHBOARD_FILE)


ASSET_FILES = {"tf-logo.png", "tf-logo.svg"}


@app.get("/assets/<name>")
def asset(name: str):
    """Static brand assets (the TF logo) that sit next to dashboard.html."""
    path = DASHBOARD_FILE.parent / name
    if name not in ASSET_FILES or not path.exists():
        return "Not found", 404
    return send_file(path)


@app.get("/execution")
def execution_dashboard():
    if not session.get("dashboard_authenticated"):
        return redirect(url_for("dashboard", next="/execution"))

    execution_file = DATA_DIR / "ToscaExecutionDashboard.html"
    if not execution_file.exists():
        return "Execution dashboard not found. Run build_snapshot.py first.", 404

    response = send_file(execution_file)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/login")
def api_login():
    if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD:
        return jsonify({"error": "Dashboard credentials are not configured."}), 503

    credentials = request.get_json(silent=True) or {}
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Invalid username or password."}), 401

    if hmac.compare_digest(username.strip(), DASHBOARD_USERNAME) and hmac.compare_digest(
        password, DASHBOARD_PASSWORD
    ):
        session["dashboard_authenticated"] = True
        return jsonify({"authenticated": True})

    return jsonify({"error": "Invalid username or password."}), 401


@app.get("/api/auth-status")
def api_auth_status():
    return jsonify({"authenticated": bool(session.get("dashboard_authenticated"))})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"authenticated": False})


@app.get("/api/results")
@login_required
def api_results():
    """Return testcase rows from Supabase (or local SQLite per RESULTS_SOURCE)."""
    try:
        rows, source = get_dashboard_results()
        response = jsonify({"rows": rows, "source": source})
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
            "mode": "local-sqlite-with-supabase-sync",
            "results_source": os.getenv("RESULTS_SOURCE", "auto"),
            "database_file": str(DATABASE_FILE),
            "dashboard_file": str(DASHBOARD_FILE),
            **sync_status(),
        }
    )


@app.post("/api/sync")
@login_required
def api_sync():
    """Retry cloud upload for locally saved runs waiting to sync."""
    return jsonify({**sync_pending_runs(), **sync_status()})


@app.get("/api/summary")
@login_required
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
    print(f"Local database : {DATABASE_FILE}")
    print(f"Dashboard HTML: {DASHBOARD_FILE}")
    print(f"Cloud sync     : {sync_status()}")
    print(f"Results source : {os.getenv('RESULTS_SOURCE', 'auto')}")
    print("Open dashboard : http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
