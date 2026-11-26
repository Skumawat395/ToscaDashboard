# Tricentis Tosca SAP Release Quality Intelligence Dashboard

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
├─ Execute.bat                 ← THE file you run after every Tosca execution (Tosca PC)
├─ Setup_Dashboard_VM.bat      ← one-time setup of the shared dashboard (VM)
├─ README.md
├─ deploy/
│  └─ iis-automationreports-rule.xml  ← IIS rule for ondemandqa.com/automationreports
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
│  ├─ execution_lists.json   ← project / module / environment per execution list
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
| `GetResults.tcs` | Visits each execution list (RISE QM/MM/PM/PP/SD, ROW MM/SD), prints the project folder and execution list names, and calls `scripts\GetIndividualResult.tcs` for every execution entry. |
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
`Execute.bat` installs them automatically if they are missing. To install them yourself:
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
| Automatically after a scheduled execution | `Execute.bat /auto` (e.g. in Task Scheduler) | Same steps, without the pause or opening the browser. Exit code 0 = success, 1 = failed. |
| You only want to view the dashboard | `python dashboard\server.py`, then open http://127.0.0.1:5000 | Starts the server and **stops any earlier instance first**, so only one ever runs. `Execute.bat` restarts it the same way. |
| You want the dashboard switched off | `python dashboard\server.py --stop` (or Ctrl+C in its window) | Stops every running dashboard server. Nothing else is left running. |
| Supabase was down during an import | `python dashboard\sync_supabase.py` | Uploads the runs still waiting. Every import also retries automatically. |
| After changing code | `python -m unittest discover -s dashboard\tests` | Runs the storage tests. |

> `Execute.bat` checks Python, the packages and `data\.env` first, and **stops with a clear message at the first failing step** instead of opening an out-of-date dashboard.

> You don't have to run `Execute.bat` after **every** execution. If several executions happened since the last import, each one becomes its own report. Running it right after each execution keeps the dashboard current.

---

## Project, module and environment

Tosca only gives the folder and execution list names. `dashboard\execution_lists.json` maps each list to what the dashboard shows:

| Execution list (Tosca) | Project | Module | Environment |
|---|---|---|---|
| `QM_RISE_QA_SeparateExeList` | RISE_INDIA | QM | QA |
| `MM_RISE_QA_SeparateExeList` | RISE_INDIA | MM | QA |
| `PM_RISE_QA` (was `PM_Raise_QA`) | RISE_INDIA | PM | QA |
| `PP_RISE_QA` | RISE_INDIA | PP | QA |
| `SD_RISE_QA` | RISE_INDIA | SD | QA |
| `ROW_MM` | ROW | MM | QA |
| `ROW_SD` | ROW | SD | QA |

The database keeps the raw Tosca names, so editing this file never changes stored results; it only changes how they are shown.

---

## 4. How reports and duplicates work

- **One execution = one report.** TCShell returns **every** log of every execution entry, old ones included.
- **Duplicates are skipped.** A result is identified by **project folder + execution list + test case + start time**. A renamed list (`renamed_from` in `execution_lists.json`) counts as the same list. Logs already in the database are skipped, so:
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
- **New results appear automatically:** the page checks for new results **once an hour** (only while the tab is open in front, and only if you're logged in). **Click the status text** at the top (*"Last updated …"*) to check right away, for example just after `Execute.bat` finished. If you haven't picked a report yourself, it moves to the newest one. To change the interval, edit `REFRESH_MINUTES` in `dashboard\web\dashboard.html`.
- **Status in the top bar:** *"Updated 15:32 · Supabase"* (green) means data loaded. *"Offline · click to retry"* (red) means the server could not be reached; it also retries on the next hourly check.
- **Sections, top to bottom:**
  1. **Pass rate tile:** the overall pass rate with a Healthy (≥ 80%), Needs attention (50–79%) or Critical (< 50%) label, and the passed / failed / other split.
  2. **Count tiles:** Total, Passed, Failed and Other / Error.
  3. **Pass rate by module:** a chart sorted from highest to lowest. Hover a bar for its counts.
  4. **Projects:** one card per project (RISE_INDIA, ROW) with a module table. **Click a module** to filter the test case table to it.
  5. **Test case detail:** search, filters for project, environment (QA / SIT / PROD), module and result, and *Clear filters*. Failures are listed first. Shows the execution time and duration, plus a **View report** link per test case.
- **Dark mode** follows your Windows or browser setting.
- `http://127.0.0.1:5000/execution` shows the static snapshot from `data\ToscaExecutionDashboard.html`.

### Server endpoints (for troubleshooting)

| URL | Shows |
|---|---|
| `/api/health` | Server status, results source, total runs and runs pending sync. No login needed. |
| `/api/results` | All result rows and the source used (`supabase` or `local`). Needs login. |
| `/api/summary` | Counts by result, project folder and execution list. Needs login. |
| `/api/sync` (POST) | Retries the Supabase upload. Needs login. |

---

## 6. Common changes

**Add a new execution list:**
1. In `tosca\GetResults.tcs`, copy one of the existing blocks and change both `JumpToNode` paths. Adjust the number of `cn ..` lines so the first `get Name` lands on the **project** folder (RISE_INDIA, ROW), because it sits at a different depth in different lists. Script paths inside `.tcs` files are relative to `tosca\`, for example `"scripts\\GetIndividualResult.tcs"`.
2. In `dashboard\execution_lists.json`, add the list with its `project`, `module` and `environment`. A list missing from this file still appears, but under its full list name and the `default_environment`.

**Rename an execution list in Tosca:** update its `JumpToNode` paths in `tosca\GetResults.tcs`, rename its key in `execution_lists.json`, and add the old name to `renamed_from`. Its history stays together and old logs are not imported again.

**Change a list's environment (QA / SIT / PROD):** edit `environment` for that list in `execution_lists.json`, then restart the server. Results already stored are shown with the new value.

**Read only from the local database:** set `RESULTS_SOURCE=local` in `data\.env`, then restart `server.py`.

**Rotate the Tosca or Supabase secret:** update `TOSCA_AUTH` or `SUPABASE_KEY` in `data\.env`, then restart `server.py`.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard says **"No reports available"** | Open `/api/health`. If `total_runs` is 0, run `Execute.bat`. Restart the server with `python dashboard\server.py`. It replaces any server already running. |
| `ERROR: ...\data\.env not found` | Copy `dashboard\.env.example` to `data\.env` and fill it in. |
| `ERROR: TOSCA_AUTH is not set` | Add the `TOSCA_` lines to `data\.env`. |
| `TCShell not found at ...` | TCShell isn't installed on this PC (the Tosca Commander **SAP** edition doesn't include it). Run `Execute.bat` on the PC that has TCShell, or set `TOSCA_TCSHELL` in `data\.env` to its path. |
| `TCShell failed` | Read `data\RawData.new.txt`. Usually it's a licence, auth or workspace path problem. The last good `RawData.txt` is kept. |
| `ondemandqa.com/automationreports` shows an IIS error (502 / 404) | On the VM open `http://127.0.0.1:5000/api/health`. If that fails, the dashboard isn't running: run `Setup_Dashboard_VM.bat` again. If it works, check the IIS rule (section 9) and that ARR proxy is enabled. |
| Dashboard page loads but stays on the login screen / data never loads | `URL_PREFIX` in the VM's `data\.env` must be `/automationreports` (same as the link), then restart the task. |
| *"All results were already imported; nothing was added."* | Normal when nothing was executed since the last import. |
| `/api/health` shows `pending_runs` > 0 | Supabase was unreachable. Run `python dashboard\sync_supabase.py`. |
| Login says credentials are not configured | Set `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` in `data\.env`, then restart the server. |
| Changes to `data\.env` are not picked up | Restart `server.py`. |

---

## 8. Security

- **Everything in `data\` is ignored by git.** That covers `.env` (Tosca client secret, Supabase secret key, dashboard password), the database, and `RawData.txt`.
- `tosca\run_tcshell.bat` runs with command echo off, so the Tosca auth value is never written to `RawData.txt`.
- Earlier commits contain the old Tosca client secret (in `SchedulerBatchFile.bat` and `Results/RawData.txt`). **Rotate it in Tosca** and put the new value in `TOSCA_AUTH`.
- By default the server listens on `127.0.0.1` only, so it can be reached from this machine and nowhere else. `HOST=0.0.0.0` (or `--share`) opens it to the network; only do that on the VM, behind IIS.
- On the VM, use **https** for the team link (the login password is otherwise sent unencrypted) and set `SESSION_COOKIE_SECURE=1`.
- The VM's `data\.env` holds the Supabase secret key: only admins should be able to log on to the VM.

---

## 9. Shared dashboard on the VM (ondemandqa.com/automationreports)

```
 Tosca PC (TCShell)                 Supabase                 Dashboard VM (Windows)
 Execute.bat ── import ──────────►  results  ◄────────────── server.py (auto-start, waitress)
 START_LOCAL_DASHBOARD=no                                     ▲
                                                              │  IIS rule /automationreports
                          https://ondemandqa.com/automationreports/  ← team link (company network / VPN)
```

The VM only **shows** results; it doesn't need Tosca, TCShell or the local database.

### 9.1 On the VM (once)
1. Install **Python 3 for all users** (tick *Add python.exe to PATH*).
2. Copy this project folder to the VM, e.g. `D:\ToscaDashboard`.
3. Create `data\.env` from `dashboard\.env.example` with:
   ```
   DASHBOARD_USERNAME=...            DASHBOARD_PASSWORD=...
   FLASK_SECRET_KEY=<long random text>
   SUPABASE_URL=...                  SUPABASE_KEY=<secret key>
   RESULTS_SOURCE=supabase
   URL_PREFIX=/automationreports
   DASHBOARD_URL=https://ondemandqa.com/automationreports/
   SESSION_COOKIE_SECURE=1           (only if the link is https)
   HOST=127.0.0.1                    (IIS on this VM)  or  0.0.0.0  (IIS on another server)
   PORT=5000
   ```
4. Right-click **`Setup_Dashboard_VM.bat` > Run as administrator.** It installs the packages, opens the firewall port when `HOST=0.0.0.0`, registers the **"Tosca Dashboard"** scheduled task (starts with Windows, restarts if it stops), starts it and checks it answers.

### 9.2 On the IIS server for ondemandqa.com (once, IIS admin)
Install **URL Rewrite** and **Application Request Routing**, enable the ARR proxy, and add the rule from `deploy\iis-automationreports-rule.xml` to the ondemandqa.com site. The file explains each step and what to put for `DASHBOARD-HOST`.

### 9.3 On the Tosca PC (once)
In its `data\.env` set `START_LOCAL_DASHBOARD=no` and `DASHBOARD_URL=https://ondemandqa.com/automationreports/`. `Execute.bat` then imports and syncs to Supabase, skips the local server, and opens the team link.

### 9.4 Day to day on the VM
| To… | Run (as administrator) |
|---|---|
| Restart (after code or `.env` changes) | `schtasks /end /tn "Tosca Dashboard"` then `schtasks /run /tn "Tosca Dashboard"` |
| Check it's running | open `http://127.0.0.1:5000/api/health` on the VM |
| Update the code | copy the new files, then restart |
| Remove | `Setup_Dashboard_VM.bat /remove` |
