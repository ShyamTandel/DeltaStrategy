@echo off
echo ===================================================================
echo Starting Delta Strategy Services
echo ===================================================================

cd /d f:\DELTASTRATEGY\DeltaStrategy

echo Step 1: Starting Redis Server...
start "Redis Server" cmd /k "wsl sudo service redis-server start"
timeout /t 3

echo Step 2: Starting Celery Worker...
start "Celery Worker" cmd /k "venv\Scripts\activate.bat && celery -A deltastrategy worker --loglevel=info --pool=solo"
timeout /t 3

echo Step 3: Starting Celery Beat Scheduler...
start "Celery Beat" cmd /k "venv\Scripts\activate.bat && celery -A deltastrategy beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler"
timeout /t 3

echo Step 4: Starting Django Server...
start "Django Server" cmd /k "venv\Scripts\activate.bat && python manage.py runserver"
timeout /t 3

echo.
echo ===================================================================
echo 🚀 All services started!
echo.
echo Open these URLs in your browser:
echo 📊 Monitoring Dashboard: http://localhost:8000/monitoring/
echo 🏠 Main Site: http://localhost:8000/
echo 📋 API Status: http://localhost:8000/api/monitoring/status/
echo ===================================================================

echo.
echo Your APIs will now be checked every 30 seconds automatically!
echo Check the monitoring dashboard to see real-time status.

pause