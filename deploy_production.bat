@echo off
REM Production Deployment Script for Delta Strategy (Windows)

echo ==========================================
echo Delta Strategy - Production Deployment
echo ==========================================

REM Check if .env file exists
if not exist .env (
    echo Error: .env file not found!
    echo Please copy .env.example to .env and configure it
    exit /b 1
)

REM Create backup directory
if not exist backups mkdir backups

REM Backup database before deployment
echo Creating database backup...
set BACKUP_FILE=backups\deltadb_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%.sql
set BACKUP_FILE=%BACKUP_FILE: =0%
docker-compose -f docker-compose.prod.yml exec -T mysql mysqldump -u root -p%MYSQL_ROOT_PASSWORD% %MYSQL_DATABASE% > %BACKUP_FILE% 2>nul || echo Backup skipped (database might not be running)

REM Pull latest images
echo Pulling latest Docker images...
docker-compose -f docker-compose.prod.yml pull

REM Build new images
echo Building Docker images...
docker-compose -f docker-compose.prod.yml build --no-cache

REM Stop old containers
echo Stopping old containers...
docker-compose -f docker-compose.prod.yml down

REM Start new containers
echo Starting new containers...
docker-compose -f docker-compose.prod.yml up -d

REM Wait for services to be healthy
echo Waiting for services to be healthy...
timeout /t 10 /nobreak

REM Run migrations
echo Running database migrations...
docker-compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput

REM Collect static files
echo Collecting static files...
docker-compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput --clear

REM Check service health
echo Checking service health...
docker-compose -f docker-compose.prod.yml ps

echo.
echo ==========================================
echo Deployment completed successfully!
echo ==========================================
echo.
echo Service Status:
docker-compose -f docker-compose.prod.yml ps
echo.
echo View logs with: docker-compose -f docker-compose.prod.yml logs -f
echo Check specific service: docker-compose -f docker-compose.prod.yml logs -f [web^|celery_worker^|celery_beat]

pause
