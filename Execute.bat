@echo off
cd /d "%~dp0"
echo ===================================================
echo   Starting Sequential Execution Pipeline
echo ===================================================
 
:: 1. Run the Scheduler and wait for it to dump fresh data to the TXT file
echo [STEP 1/4] Running Tosca Scheduler...
call "SchedulerBatchFile.bat" > "Results\RawData.txt"
 
:: 2. Move to the results directory and parse the new data into the HTML file
echo [STEP 2/4] Parsing results with Python...
cd /d "Results"
 
:: UPDATED: Changed the filename to match image_7bcfc1.png exactly
python Tosca_DashBoard.py

:: 3. Execute Python code
echo [STEP 3/4] Parsing results with Python...
cd /d "Results"
 
:: UPDATED: Changed the filename to match image_7bcfc1.png exactly
python ToscaDB.py

:: 4. Automatically launch the freshly updated HTML report in your default browser
echo [STEP 4/4] Launching updated Himalaya Rise Dashboard...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/api/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 start "Tosca Dashboard Server" /min cmd /c "python server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000/execution"
 


echo ===================================================
echo   Pipeline Finished Successfully!
echo ===================================================
pause
