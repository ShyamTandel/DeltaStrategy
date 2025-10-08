@echo off
echo ===================================================================
echo Delta Strategy Monitoring Setup
echo ===================================================================

echo.
echo Step 1: Activate virtual environment
call venv\Scripts\activate.bat

echo.
echo Step 2: Install required packages
pip install redis celery django-celery-beat django-celery-results

echo.
echo Step 3: Run migrations
python manage.py makemigrations
python manage.py migrate

echo.
echo Step 4: Set up periodic monitoring (every 30 seconds)
python manage.py setup_monitoring --target-profit 1000.0

echo.
echo ===================================================================
echo Setup complete! Now you can start the services:
echo.
echo 1. Start Redis (in separate terminal):
echo    wsl
echo    sudo service redis-server start
echo.
echo 2. Start Celery Worker (in separate terminal):
echo    cd f:\DELTASTRATEGY\DeltaStrategy
echo    venv\Scripts\activate.bat
echo    celery -A deltastrategy worker --loglevel=info --pool=solo
echo.
echo 3. Start Celery Beat (in separate terminal):
echo    cd f:\DELTASTRATEGY\DeltaStrategy  
echo    venv\Scripts\activate.bat
echo    celery -A deltastrategy beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
echo.
echo 4. Start Django server (in separate terminal):
echo    cd f:\DELTASTRATEGY\DeltaStrategy
echo    venv\Scripts\activate.bat
echo    python manage.py runserver
echo.
echo 5. Open monitoring dashboard:
echo    http://localhost:8000/monitoring/
echo ===================================================================

pause