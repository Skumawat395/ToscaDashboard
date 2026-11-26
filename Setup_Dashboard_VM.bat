@echo off
:: ===================================================================
::  One-time setup of the dashboard on the Windows VM.
::  Run as Administrator (right-click > Run as administrator).
::
::    Setup_Dashboard_VM.bat           install / update and start
::    Setup_Dashboard_VM.bat /remove   stop and remove the auto-start
::
::  Afterwards the dashboard starts with Windows (no login needed) and
::  restarts on its own if it stops. Settings come from data\.env.
:: ===================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "TASK=Tosca Dashboard"
set "RULE=Tosca Dashboard"

net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: Run this file as Administrator ^(right-click ^> Run as administrator^).
    goto :fail
)

if /i "%~1"=="/remove" goto :remove

echo ===================================================
echo   Tosca Dashboard - VM setup
echo ===================================================

:: --- 1. Python -------------------------------------------------------
echo [1/5] Checking Python...
set "PYTHON="
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON=%%P"
if not defined PYTHON (
    echo ERROR: Python not found. Install Python 3 "for all users" and tick "Add python.exe to PATH".
    goto :fail
)
echo       %PYTHON%

:: --- 2. Packages -----------------------------------------------------
echo [2/5] Installing Python packages...
"%PYTHON%" -m pip install --disable-pip-version-check -q -r "dashboard\requirements.txt"
if errorlevel 1 (
    echo ERROR: Package installation failed - see the message above.
    goto :fail
)

:: --- 3. Settings -----------------------------------------------------
echo [3/5] Checking data\.env...
if not exist "data\.env" (
    echo ERROR: data\.env not found. Copy dashboard\.env.example to data\.env and fill in the dashboard values.
    goto :fail
)
set "HOST=127.0.0.1"
set "PORT=5000"
set "URL_PREFIX="
set "RESULTS_SOURCE="
set "DASHBOARD_URL="
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("data\.env") do (
    if /i "%%A"=="HOST" if not "%%B"=="" set "HOST=%%B"
    if /i "%%A"=="PORT" if not "%%B"=="" set "PORT=%%B"
    if /i "%%A"=="URL_PREFIX" set "URL_PREFIX=%%B"
    if /i "%%A"=="RESULTS_SOURCE" set "RESULTS_SOURCE=%%B"
    if /i "%%A"=="DASHBOARD_URL" set "DASHBOARD_URL=%%B"
)
if /i not "%RESULTS_SOURCE%"=="supabase" echo       WARNING: RESULTS_SOURCE is "%RESULTS_SOURCE%". On the VM set RESULTS_SOURCE=supabase.
if not defined URL_PREFIX echo       WARNING: URL_PREFIX is empty. For ondemandqa.com/automationreports set URL_PREFIX=/automationreports.
echo       HOST=%HOST%  PORT=%PORT%  URL_PREFIX=%URL_PREFIX%

:: --- 4. Firewall (only when another server's IIS forwards to this VM) --
echo [4/5] Firewall...
netsh advfirewall firewall delete rule name="%RULE%" >nul 2>&1
if "%HOST%"=="127.0.0.1" (
    echo       Not needed: HOST=127.0.0.1, IIS on this VM forwards to the dashboard.
) else (
    netsh advfirewall firewall add rule name="%RULE%" dir=in action=allow protocol=TCP localport=%PORT% profile=domain,private >nul
    if errorlevel 1 ( echo ERROR: Could not add the firewall rule. & goto :fail )
    echo       Opened TCP %PORT% for the domain/private network.
)

:: --- 5. Auto-start task ----------------------------------------------
echo [5/5] Registering auto-start and starting the dashboard...
"%PYTHON%" "dashboard\server.py" --stop
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute '%PYTHON%' -Argument '\"%~dp0dashboard\server.py\"' -WorkingDirectory '%~dp0';" ^
  "$t = New-ScheduledTaskTrigger -AtStartup;" ^
  "$s = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;" ^
  "$p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
  "Register-ScheduledTask -TaskName '%TASK%' -Action $a -Trigger $t -Settings $s -Principal $p -Force | Out-Null;" ^
  "Start-ScheduledTask -TaskName '%TASK%'"
if errorlevel 1 ( echo ERROR: Could not register the scheduled task. & goto :fail )

set "HEALTH=http://127.0.0.1:%PORT%/api/health"
for /l %%i in (1,1,15) do (
    timeout /t 2 /nobreak >nul
    powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing '%HEALTH%' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
    if not errorlevel 1 goto :started
)
echo ERROR: The dashboard did not start. Run "python dashboard\server.py" in this folder to see why.
goto :fail

:started
echo ===================================================
echo   Dashboard is running and starts with Windows.
echo   On this VM : http://127.0.0.1:%PORT%%URL_PREFIX%/
if defined DASHBOARD_URL echo   Team link  : %DASHBOARD_URL%
echo   Restart    : schtasks /end /tn "%TASK%" ^& schtasks /run /tn "%TASK%"
echo   Remove     : Setup_Dashboard_VM.bat /remove
echo ===================================================
pause
exit /b 0

:remove
echo Removing the dashboard auto-start...
schtasks /end /tn "%TASK%" >nul 2>&1
schtasks /delete /tn "%TASK%" /f >nul 2>&1
python "dashboard\server.py" --stop
netsh advfirewall firewall delete rule name="%RULE%" >nul 2>&1
echo Done. The dashboard is stopped and will not start with Windows.
pause
exit /b 0

:fail
echo ===================================================
echo   Setup STOPPED - fix the error above and run it again
echo ===================================================
pause
exit /b 1
