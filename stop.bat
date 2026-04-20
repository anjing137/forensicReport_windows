@echo off
echo Stopping Forensic Report System...
taskkill /f /im uvicorn.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Forensic Report System" >nul 2>&1

:: Kill by port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo Server stopped.
pause
