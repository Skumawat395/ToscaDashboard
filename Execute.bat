@echo off
echo ===================================================
echo   Starting Sequential Execution Pipeline
echo ===================================================
 
:: 1. Run the Scheduler and wait for it to dump fresh data to the TXT file
echo [STEP 1/4] Running Tosca Scheduler...
cmd /c ""C:\Tosca\Batch\SchedulerBatchFile.bat" > "C:\Tosca\Batch\Results\RawData.txt""
 
:: 2. Move to the results directory and parse the new data into the HTML file
echo [STEP 2/4] Parsing results with Python...
cd /d "C:\Tosca\Batch\Results"
 
:: UPDATED: Changed the filename to match image_7bcfc1.png exactly
"C:\Python314\python.exe" Tosca_DashBoard.py

:: 3. Execute Python code
echo [STEP 3/4] Parsing results with Python...
cd /d "C:\Tosca\Batch\Results"
 
:: UPDATED: Changed the filename to match image_7bcfc1.png exactly
"C:\Python314\python.exe" ToscaDB.py

:: 4. Automatically launch the freshly updated HTML report in your default browser
echo [STEP 4/4] Launching updated Himalaya Rise Dashboard...
start "" "ToscaExecutionDashboard.html"
 


echo ===================================================
echo   Pipeline Finished Successfully!
echo ===================================================
pause
