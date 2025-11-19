@echo off
REM View logs for production services

echo ==========================================
echo Delta Strategy - Production Logs
echo ==========================================
echo.
echo Choose a service to view logs:
echo 1. All services
echo 2. Web (Django)
echo 3. Celery Worker
echo 4. Celery Beat
echo 5. MySQL
echo 6. Redis
echo.

set /p choice="Enter your choice (1-6): "

if "%choice%"=="1" (
    docker-compose -f docker-compose.prod.yml logs -f
) else if "%choice%"=="2" (
    docker-compose -f docker-compose.prod.yml logs -f web
) else if "%choice%"=="3" (
    docker-compose -f docker-compose.prod.yml logs -f celery_worker
) else if "%choice%"=="4" (
    docker-compose -f docker-compose.prod.yml logs -f celery_beat
) else if "%choice%"=="5" (
    docker-compose -f docker-compose.prod.yml logs -f mysql
) else if "%choice%"=="6" (
    docker-compose -f docker-compose.prod.yml logs -f redis
) else (
    echo Invalid choice!
    pause
)
