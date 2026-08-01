@echo off
REM autocomputer Dashboard one-click launcher
REM Starts the API server and opens the browser automatically
setlocal
cd /d "%~dp0.."

echo [autocomputer] Starting Dashboard server...
echo [autocomputer] Browser will open http://127.0.0.1:8765

start "" cmd /c "cd /d %~dp0.. && set PYTHONPATH=python && python -c "import threading,webbrowser; from autocomputer.server import run_server; threading.Timer(2.0, lambda: webbrowser.open('http://127.0.0.1:8765')).start(); run_server()""

timeout /t 4 >nul
echo [autocomputer] If the browser did not open, visit http://127.0.0.1:8765 manually
endlocal
