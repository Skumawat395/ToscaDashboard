"""Tosca dashboard server backed by local SQLite with Supabase sync.

Layout:
  dashboard/web/dashboard.html          dashboard page (served at /)
  data/.env                             settings and secrets
  data/tosca_results.sqlite3            local results database
  data/ToscaExecutionDashboard.html     static snapshot (served at /execution)

Install:  pip install -r dashboard/requirements.txt
Run:      python dashboard/server.py          (replaces any server already running)
Stop:     python dashboard/server.py --stop
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
    get_results_version,
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
# Set SESSION_COOKIE_SECURE=1 when people open the dashboard over https.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}

# URL_PREFIX serves the dashboard under a sub-path, e.g. /automationreports for
# https://ondemandqa.com/automationreports. Empty = served at /.
URL_PREFIX = "/" + os.getenv("URL_PREFIX", "").strip().strip("/") if os.getenv("URL_PREFIX", "").strip("/ ") else ""


class _PrefixMiddleware:
    """Mount the app under URL_PREFIX. The page uses relative URLs, so the
    prefix itself is redirected to prefix + '/' and anything outside is 404."""

    def __init__(self, wsgi_app, prefix: str):
        self.wsgi_app, self.prefix = wsgi_app, prefix

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == "/api/health":
            # Also answered without the prefix, for Execute.bat and monitoring.
            return self.wsgi_app(environ, start_response)
        if path in ("", "/", self.prefix):
            start_response("308 Permanent Redirect", [("Location", self.prefix + "/")])
            return [b""]
        if path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):]
            return self.wsgi_app(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [f"Not found. The dashboard is at {self.prefix}/".encode()]


if URL_PREFIX:
    app.wsgi_app = _PrefixMiddleware(app.wsgi_app, URL_PREFIX)
    app.config["SESSION_COOKIE_PATH"] = URL_PREFIX + "/"


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


@app.get("/api/results-version")
@login_required
def api_results_version():
    """Tiny change signal; the dashboard reloads /api/results only when it changes."""
    try:
        response = jsonify(get_results_version())
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as exc:
        app.logger.exception("Unable to check results version")
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


PORT = int(os.getenv("PORT", "5000"))

# Finds earlier dashboard servers: python processes running dashboard\server.py,
# plus whatever python process listens on PORT with server.py on its command line.
# Our own process and its parent (e.g. the py.exe launcher) are excluded.
_FIND_OLD_SERVERS_PS = r"""
$skip = @({self_pid}, {parent_pid})
$byName = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object {{ $_.CommandLine -match 'dashboard[\\/]+server\.py' }} |
    ForEach-Object {{ $_.ProcessId }}
$byPort = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {{ Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" }} |
    Where-Object {{ $_.CommandLine -match 'server\.py' }} |
    ForEach-Object {{ $_.ProcessId }}
@($byName) + @($byPort) | Where-Object {{ $_ -and ($skip -notcontains $_) }} | Sort-Object -Unique
"""


def stop_previous_instances() -> list[int]:
    """Stop every earlier dashboard server so only one ever runs. Windows only."""
    if os.name != "nt":
        return []
    import subprocess
    import time

    script = _FIND_OLD_SERVERS_PS.format(
        self_pid=os.getpid(), parent_pid=os.getppid(), port=PORT
    )
    found = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=30,
    ).stdout.split()
    pids = [int(p) for p in found if p.isdigit()]
    for pid in pids:
        # /T also ends the child process the old debug reloader started.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)

    # Wait until the port is free so the new server can bind it.
    import socket
    for _ in range(20):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", PORT)) != 0:
                break
        time.sleep(0.25)
    return pids


if __name__ == "__main__":
    import sys

    stopped = stop_previous_instances()
    if stopped:
        print(f"Stopped previous dashboard server(s): PID {', '.join(map(str, stopped))}")
    if "--stop" in sys.argv[1:]:
        if not stopped:
            print("No dashboard server was running.")
        raise SystemExit(0)

    print(f"Local database : {DATABASE_FILE}")
    print(f"Dashboard HTML: {DASHBOARD_FILE}")
    print(f"Cloud sync     : {sync_status()}")
    print(f"Results source : {os.getenv('RESULTS_SOURCE', 'auto')}")
    # HOST=127.0.0.1 (default): this PC only. --share or HOST=0.0.0.0: anyone on the network.
    host = "0.0.0.0" if "--share" in sys.argv[1:] else os.getenv("HOST", "127.0.0.1")
    print(f"Open dashboard : http://127.0.0.1:{PORT}{URL_PREFIX}/")
    if os.getenv("DASHBOARD_URL"):
        print(f"Team link      : {os.getenv('DASHBOARD_URL')}")
    elif host != "127.0.0.1":
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("10.255.255.255", 1))  # no packet is sent; picks the LAN address
                lan_ip = probe.getsockname()[0]
        except OSError:
            lan_ip = socket.gethostbyname(socket.gethostname())
        print(f"Share this link: http://{lan_ip}:{PORT}{URL_PREFIX}/   (others on your network)")
        print(f"            or : http://{socket.gethostname()}:{PORT}{URL_PREFIX}/")
    print("Stop it with   : Ctrl+C here, or python dashboard\\server.py --stop")
    try:
        # Production web server (Windows-friendly). Falls back to Flask's own
        # server if waitress is not installed.
        from waitress import serve
    except ImportError:
        print("Web server     : Flask development server (pip install waitress for production)")
        # debug=False: no reloader child process and no interactive debugger.
        app.run(host=host, port=PORT, debug=False)
    else:
        print("Web server     : waitress")
        serve(app, host=host, port=PORT, threads=8, ident=None)
