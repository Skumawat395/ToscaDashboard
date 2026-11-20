# Tosca Execution Dashboard

Collects Tosca execution results after each run, stores them in a local SQLite database, copies them to Supabase, and shows them in a web dashboard with login.

```
 Tosca execution finished
          │
          ▼
 Execute.bat ──► tosca\run_tcshell.bat ──► TCShell runs tosca\GetResults.tcs
          │                                  (every log of every execution entry)  
          │                                         │
          │                                         ▼
          │                                data\RawData.txt
          ▼
 dashboard\import_results.py ──► stores only NEW results, one report per execution ──► data\tosca_results.sqlite3 ──► Supabase
          │
          ▼
 dashboard\build_snapshot.py ──► data\ToscaExecutionDashboard.html (static snapshot)
          │
          ▼
 dashboard\server.py ──► http://127.0.0.1:5000 (login → latest report)
```

---

## 1. Folder layout

```
ToscaDashboard/
├─ Execute.bat                 ← THE file you run after every Tosca execution
├─ README.md
├─ tosca/                      ← everything TCShell / Tosca
│  ├─ run_tcshell.bat
│  ├─ GetResults.tcs
│  └─ scripts/*.tcs
├─ dashboard/                  ← Python app (code only, committed to git)
│  ├─ server.py
│  ├─ import_results.py
│  ├─ build_snapshot.py
│  ├─ result_store.py
│  ├─ sync_supabase.py
│  ├─ web/dashboard.html
│  ├─ supabase_schema.sql
│  ├─ requirements.txt
│  ├─ .env.example
│  └─ tests/
└─ data/                       ← runtime data & secrets (ignored by git, never commit)
   ├─ .env
   ├─ tosca_results.sqlite3
   ├─ RawData.txt
   ├─ ExecutionResult.xlsx
   └─ ToscaExecutionDashboard.html
```

### `tosca\`: TCShell side

| File | Purpose |
|---|---|
| `run_tcshell.bat` | Reads `TOSCA_TCSHELL`, `TOSCA_WORKSPACE` and `TOSCA_AUTH` from `data\.env` and runs `GetResults.tcs` with TCShell. Command echo is off, so the auth value never reaches the log. |
| `GetResults.tcs` | Visits each execution list (RISE QM/MM/PM/PP/SD, ROW MM/SD), prints the environment and module names, and calls `scripts\GetIndividualResult.tcs` for every execution entry. |
| `scripts\GetIndividualResult.tcs` | Gets **every** test case log of one execution entry, newest first. Logs already imported are skipped by `import_results.py`. |
| `scripts\GetTestCaseLog.tcs` | Prints `Result`, `StartTime` and `EndTime`, then calls `GetTestCaseName.tcs`. |
| `scripts\GetTestCaseName.tcs` | Prints the test case `Name`, `CreatedBy` and `CreatedAt`. |
| `scripts\GenerateTestCaseReport.tcs` | Optional: prints Tosca PDF reports per list. Disabled in `GetResults.tcs`. |
| `scripts\Execute_TestCases.tcs` | Optional: runs an execution list from TCShell. Not part of the import pipeline. |

### `dashboard\`: Python app

| File | Purpose | Run it yourself? |
|---|---|---|
| `server.py` | Web server: login, API and dashboard page. | Yes, if it isn't already running |
| `import_results.py` | Parses `data\RawData.txt`, saves **only new** results (one report per execution), then syncs to Supabase. | No, `Execute.bat` runs it |
| `build_snapshot.py` | Builds `data\ToscaExecutionDashboard.html`, a self-contained snapshot. | No, `Execute.bat` runs it |
| `result_store.py` | Shared database code: save, skip duplicates, read, Supabase sync, loading `data\.env`. | No |
| `sync_supabase.py` | Retries uploading runs that failed to reach Supabase. | Only if a sync failed |
| `web\dashboard.html` | The dashboard page served at `/`. It is also the template for the snapshot. | No |
| `supabase_schema.sql` | Creates the Supabase tables. | Once, in Supabase |
| `requirements.txt` | Python packages. | Once |
| `.env.example` | Template for `data\.env`. | Copy once |
| `tests\` | Unit tests for the storage logic. | After code changes |

### `data\`: runtime files (never commit)

| File | What it is |
|---|---|
| `.env` | Secrets and settings. See section 2.2. |
| `tosca_results.sqlite3` | **The main store of every result. Never delete it.** |
| `RawData.txt` | TCShell output from the last run. Overwritten each time. |
| `ExecutionResult.xlsx` | Old history. Imported once, automatically, only if the database is empty. |
| `ToscaExecutionDashboard.html` | Generated snapshot served at `/execution`. Overwritten each run. |

---

## 2. One-time setup

Do this once on the machine that has Tosca installed.

### 2.1 Install Python packages
```powershell
cd D:\TFW\Automation\ToscaDashboard
pip install -r dashboard\requirements.txt
```

### 2.2 Create `data\.env`
Copy `dashboard\.env.example` to `data\.env` and fill in every value:

| Key | What to put |
|---|---|
| `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` | The dashboard login for the team. |
| `FLASK_SECRET_KEY` | Any long random text. Keeps people logged in across server restarts. |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_KEY` | The **secret / service_role** key (`sb_secret_...`). A publishable or anon key won't work. |
| `RESULTS_SOURCE` | Where the dashboard reads from: `auto` (Supabase, falling back to local), `supabase`, or `local`. |
| `RUN_GAP_MINUTES` | Optional, default `60`. Minutes with no test case running that separate two executions into two reports. |
| `TOSCA_TCSHELL` | Full path to `TCShell.exe`. |
| `TOSCA_WORKSPACE` | Full path to the `.tws` workspace file. |
| `TOSCA_AUTH` | Base64 client credentials for TCShell `-auth`. |
| `TOSCA_SQLITE_FILE` | Optional. Leave empty to use `data\tosca_results.sqlite3`. |

### 2.3 Create the Supabase tables
In Supabase, open **SQL Editor**, paste the contents of `dashboard\supabase_schema.sql`, and run it.

### 2.4 First import
Run `Execute.bat` once.

---

## 3. Day-to-day: which file to run, and when

All commands are run from the project folder (`D:\TFW\Automation\ToscaDashboard`).

| When | Run | What happens |
|---|---|---|
| **After Tosca executions** | Double-click **`Execute.bat`** | Reads all execution logs, adds the new ones (one report per execution), syncs to Supabase, rebuilds the snapshot, and opens the dashboard. |
| You only want to view the dashboard | `python dashboard\server.py`, then open http://127.0.0.1:5000 | Starts the server. `Execute.bat` also starts it if it isn't running. |
| Supabase was down during an import | `python dashboard\sync_supabase.py` | Uploads the runs still waiting. Every import also retries automatically. |
| After changing code | `python -m unittest discover -s dashboard\tests` | Runs the storage tests. |

> You don't have to run `Execute.bat` after **every** execution. If several executions happened since the last import, each one becomes its own report. Running it right after each execution keeps the dashboard current.

---

## 4. How reports and duplicates work

- **One execution = one report.** TCShell returns **every** log of every execution entry, old ones included.
- **Duplicates are skipped.** A result is identified by **environment + module + test case + start time**. Logs already in the database are skipped, so:
  - logs from executions since the last import → stored;
  - logs imported earlier → skipped, because they are already stored;
  - nothing executed since the last import → no report is created, and the script prints *"nothing was added"*.
- **Splitting into reports:** the new logs are sorted by start time. A gap of more than `RUN_GAP_MINUTES` (default 60) with nothing running starts a new report. Two executions at 09:00 and 14:00 therefore become two reports, even when `Execute.bat` ran only once. Lists executed at very different times also become separate reports.
- **Several executions in a month** each appear as a separate report, newest first:
  ```
  November 2026
    25 Nov 2026, 14:00 (Latest) — 12 TCs · 91.7% pass
    20 Nov 2026, 09:04          — 214 TCs · 70.1% pass
  ```
- A report contains only the test cases that were actually executed in that run.
- The **original history import** was saved as a single run spanning many months. It appears as one *"Imported history"* report per month.
- **Supabase** receives each new run once. Re-sending the same run overwrites the same rows instead of adding copies.

---

## 5. Using the dashboard

Open **http://127.0.0.1:5000** and log in with `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD`.

- **The latest report opens by default.** Use the **Report** dropdown at the top to open any earlier report; they are grouped by month.
- **New results appear automatically:** the page refreshes every 60 seconds. If you haven't picked a report yourself, it moves to the newest one.
- **Status in the top bar:** *"Updated 15:32 · Supabase"* (green) means data loaded. *"Offline · retrying"* (red) means the server could not be reached.
- **Sections, top to bottom:**
  1. **Pass rate tile:** the overall pass rate with a Healthy (≥ 80%), Needs attention (50–79%) or Critical (< 50%) label, and the passed / failed / other split.
  2. **Count tiles:** Total, Passed, Failed and Other / Error.
  3. **Pass rate by module:** a chart sorted from highest to lowest. Hover a bar for its counts.
  4. **Environments:** one card per environment with a module table. **Click a module** to filter the test case table to it.
  5. **Test case detail:** search, filters for environment, module and result, and *Clear filters*. Failures are listed first. Shows the execution time and duration, plus a **View report** link per test case.
- **Dark mode** follows your Windows or browser setting.
- `http://127.0.0.1:5000/execution` shows the static snapshot from `data\ToscaExecutionDashboard.html`.

### Server endpoints (for troubleshooting)

| URL | Shows |
|---|---|
| `/api/health` | Server status, results source, total runs and runs pending sync. No login needed. |
| `/api/results` | All result rows and the source used (`supabase` or `local`). Needs login. |
| `/api/summary` | Counts by result, environment and module. Needs login. |
| `/api/sync` (POST) | Retries the Supabase upload. Needs login. |

---

## 6. Common changes

**Add a new execution list:** in `tosca\GetResults.tcs`, copy one of the existing blocks and change both `JumpToNode` paths. Adjust the number of `cn ..` lines so the first `get Name` lands on the **environment** folder, because the environment folder sits at a different depth in different lists. Script paths inside `.tcs` files are relative to `tosca\`, for example `"scripts\\GetIndividualResult.tcs"`.

**Read only from the local database:** set `RESULTS_SOURCE=local` in `data\.env`, then restart `server.py`.

**Rotate the Tosca or Supabase secret:** update `TOSCA_AUTH` or `SUPABASE_KEY` in `data\.env`, then restart `server.py`.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard says **"No reports available"** | Open `/api/health`. If `total_runs` is 0, run `Execute.bat`. Make sure only **one** server is running (`Get-NetTCPConnection -LocalPort 5000`), then restart it with `python dashboard\server.py`. |
| `ERROR: ...\data\.env not found` | Copy `dashboard\.env.example` to `data\.env` and fill it in. |
| `ERROR: TOSCA_AUTH is not set` | Add the `TOSCA_` lines to `data\.env`. |
| `TCShell failed - see data\RawData.txt` | Read the end of `data\RawData.txt`. Usually it's a licence, auth or workspace path problem. |
| *"All results were already imported; nothing was added."* | Normal when nothing was executed since the last import. |
| `/api/health` shows `pending_runs` > 0 | Supabase was unreachable. Run `python dashboard\sync_supabase.py`. |
| Login says credentials are not configured | Set `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` in `data\.env`, then restart the server. |
| Changes to `data\.env` are not picked up | Restart `server.py`. |

---

## 8. Security

- **Everything in `data\` is ignored by git.** That covers `.env` (Tosca client secret, Supabase secret key, dashboard password), the database, and `RawData.txt`.
- `tosca\run_tcshell.bat` runs with command echo off, so the Tosca auth value is never written to `RawData.txt`.
- Earlier commits contain the old Tosca client secret (in `SchedulerBatchFile.bat` and `Results/RawData.txt`). **Rotate it in Tosca** and put the new value in `TOSCA_AUTH`.
- The server listens on `127.0.0.1` only, so it can be reached from this machine and nowhere else.
