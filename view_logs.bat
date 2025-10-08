@echo off
echo ===================================================================
echo Delta Strategy API Monitoring Logs
echo ===================================================================

echo.
echo 📋 Choose how you want to view the logs:
echo.
echo [1] Real-time log monitor (shows API calls as they happen)
echo [2] View log file directly (static view)
echo [3] Check current status
echo [4] View Celery worker logs (if terminal is open)
echo [5] Open monitoring dashboard in browser
echo.

set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" (
    echo.
    echo 🔄 Starting real-time log monitor...
    echo Press Ctrl+C to stop monitoring
    echo.
    venv\Scripts\activate.bat && python monitor_logs.py
) else if "%choice%"=="2" (
    echo.
    echo 📄 Opening log file...
    if exist "logs\deltastrategy.log" (
        type logs\deltastrategy.log | more
    ) else (
        echo ❌ Log file not found: logs\deltastrategy.log
        echo Make sure Django server is running
    )
) else if "%choice%"=="3" (
    echo.
    echo 📊 Checking current status...
    venv\Scripts\activate.bat && python monitor_logs.py --status
) else if "%choice%"=="4" (
    echo.
    echo 💡 To see Celery worker logs:
    echo    1. Look for the "Celery Worker" terminal window
    echo    2. You should see logs like:
    echo       [INFO] Received task: tasks.periodic_api_check
    echo       [INFO] 🔄 Starting periodic API check...
    echo       [INFO] 📊 PnL Summary: ...
    echo       [INFO] 🎯 Target Check Result: ...
    echo.
) else if "%choice%"=="5" (
    echo.
    echo 🌐 Opening monitoring dashboard...
    start http://localhost:8000/monitoring/
) else (
    echo ❌ Invalid choice. Please run the script again.
)

echo.
pause