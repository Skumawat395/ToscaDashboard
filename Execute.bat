@echo off
cd /d "%~dp0"
echo ===================================================
echo   Tosca Results Import Pipeline
echo   Run this after every Tosca execution: it imports the
echo   latest execution as a new report. Earlier reports stay
echo   in the database from earlier runs.
echo ===================================================

:: 1. Read the latest execution log of every execution entry from Tosca
echo [STEP 1/4] Reading latest Tosca execution results...
call "tosca\run_tcshell.bat" > "data\RawData.txt"
if errorlevel 1 (
    echo TCShell failed - see data\RawData.txt. Nothing was imported.
    pause
    exit /b 1
)

:: 2. Parse RawData.txt and store only NEW results (already imported ones are skipped)
echo [STEP 2/4] Storing new results in the database and syncing to Supabase...
python "dashboard\import_results.py"

:: 3. Rebuild the static execution dashboard
echo [STEP 3/4] Rebuilding the execution dashboard snapshot...
python "dashboard\build_snapshot.py"

:: 4. Start the dashboard server if needed and open the dashboard
echo [STEP 4/4] Opening the dashboard...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/api/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 start "Tosca Dashboard Server" /min cmd /c "python dashboard\server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000"

echo ===================================================
echo   Pipeline Finished
echo ===================================================
pause
