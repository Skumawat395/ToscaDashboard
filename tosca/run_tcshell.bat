@echo off
:: Runs GetResults.tcs through TCShell.
:: TCShell path, workspace and auth come from data\.env (never commit that file):
::   TOSCA_TCSHELL=C:\Program Files (x86)\TRICENTIS\Tosca Testsuite\ToscaCommander\TCShell.exe
::   TOSCA_WORKSPACE=C:\path\to\workspace.tws
::   TOSCA_AUTH=<base64 client credentials>
:: echo is off so the auth value is never written into data\RawData.txt.
:: Runs from tosca\ so the "scripts\..." paths inside the .tcs files resolve.
setlocal
pushd "%~dp0"

set "ENV_FILE=%~dp0..\data\.env"
if not exist "%ENV_FILE%" (
    echo ERROR: %ENV_FILE% not found. Copy dashboard\.env.example to data\.env and fill in the TOSCA_ values. 1>&2
    popd
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if /i "%%A"=="TOSCA_TCSHELL" set "TOSCA_TCSHELL=%%B"
    if /i "%%A"=="TOSCA_WORKSPACE" set "TOSCA_WORKSPACE=%%B"
    if /i "%%A"=="TOSCA_AUTH" set "TOSCA_AUTH=%%B"
)

if not defined TOSCA_TCSHELL set "TOSCA_TCSHELL=C:\Program Files (x86)\TRICENTIS\Tosca Testsuite\ToscaCommander\TCShell.exe"
if not defined TOSCA_WORKSPACE (
    echo ERROR: TOSCA_WORKSPACE is not set in %ENV_FILE% 1>&2
    popd
    exit /b 1
)
if not defined TOSCA_AUTH (
    echo ERROR: TOSCA_AUTH is not set in %ENV_FILE% 1>&2
    popd
    exit /b 1
)

"%TOSCA_TCSHELL%" -workspace "%TOSCA_WORKSPACE%" -auth "%TOSCA_AUTH%" "GetResults.tcs"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
