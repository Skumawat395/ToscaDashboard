@echo off
:: ===================================================================
::  Tosca Results Import Pipeline - the ONLY file to run after Tosca
::  executions. It checks the setup, reads the results from Tosca,
::  stores the new ones (local DB + Supabase), rebuilds the snapshot
::  and opens the dashboard.
::
::  Usage:
::    Execute.bat          double-click: shows progress, opens browser, waits at end
::    Execute.bat /auto    for Task Scheduler: no pause, no browser
:: ===================================================================
setlocal
cd /d "%~dp0"

set "AUTO="
if /i "%~1"=="/auto" set "AUTO=1"

echo ===================================================
echo   Tosca Results Import Pipeline   %DATE% %TIME:~0,8%
echo ===================================================

:: ---------------------------------------------------------------
:: 0. Pre-flight checks: Python, packages, data\.env
:: ---------------------------------------------------------------
echo [STEP 0/4] Checking setup...

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH. Install Python 3 and tick "Add python.exe to PATH".
    goto :fail
)

if not exist "data\.env" (
    echo ERROR: data\.env not found. Copy dashboard\.env.example to data\.env and fill in every value.
    goto :fail
)

python -c "import flask, openpyxl, dotenv, supabase" >nul 2>&1
if errorlevel 1 (
    echo Python packages are missing - installing them now...
    python -m pip install -r "dashboard\requirements.txt"
    if errorlevel 1 (
        echo ERROR: Could not install the packages in dashboard\requirements.txt.
        goto :fail
    )
)
echo           OK

:: ---------------------------------------------------------------
:: 1. Read every execution log of every execution entry from Tosca
:: ---------------------------------------------------------------
echo [STEP 1/4] Reading Tosca execution results (this can take a few minutes)...
call "tosca\run_tcshell.bat" > "data\RawData.txt"
if errorlevel 1 (
    echo ERROR: TCShell failed - see the end of data\RawData.txt. Nothing was imported.
    goto :fail
)

:: ---------------------------------------------------------------
:: 2. Store only NEW results, then sync to Supabase
::    (runs that failed to sync earlier are retried here too)
:: ---------------------------------------------------------------
echo [STEP 2/4] Storing new results and syncing to Supabase...
python "dashboard\import_results.py"
if errorlevel 1 (
    echo ERROR: Import failed - see the message above. The dashboard was not updated.
    goto :fail
)

:: ---------------------------------------------------------------
:: 3. Rebuild the static snapshot (data\ToscaExecutionDashboard.html)
:: ---------------------------------------------------------------
echo [STEP 3/4] Rebuilding the dashboard snapshot...
python "dashboard\build_snapshot.py"
if errorlevel 1 (
    echo ERROR: Snapshot build failed - see the message above. Results ARE stored; only the snapshot is stale.
    goto :fail
)

:: ---------------------------------------------------------------
:: 4. Start the server if it isn't running, then open the dashboard
:: ---------------------------------------------------------------
echo [STEP 4/4] Restarting the dashboard server...
:: Stop any earlier server first so exactly one runs, with the latest code and .env.
python "dashboard\server.py" --stop
start "Tosca Dashboard Server" /min cmd /c "python dashboard\server.py"
call :wait_for_server
if errorlevel 1 (
    echo ERROR: The dashboard server did not start. Run "python dashboard\server.py" to see why.
    goto :fail
)
if not defined AUTO start "" "http://127.0.0.1:5000"

echo ===================================================
echo   Pipeline finished successfully
echo   Dashboard: http://127.0.0.1:5000
echo ===================================================
if not defined AUTO pause
exit /b 0

:fail
echo ===================================================
echo   Pipeline STOPPED - fix the error above and run Execute.bat again
echo ===================================================
if not defined AUTO pause
exit /b 1

:: --- helpers --------------------------------------------------------
:health
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/api/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:wait_for_server
:: Up to ~20 seconds for the server to come up.
for /l %%i in (1,1,10) do (
    timeout /t 2 /nobreak >nul
    call :health
    if not errorlevel 1 exit /b 0
)
exit /b 1
