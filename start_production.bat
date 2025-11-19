@echo off
REM Quick start script for production environment (Windows)

echo Starting Delta Strategy in Production Mode...

REM Check if .env exists
if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env
    echo Warning: Please edit .env file with your actual credentials!
    pause
    exit /b 1
)

REM Start all services
docker-compose -f docker-compose.prod.yml up -d

echo Services started!
echo.
echo Access the application at: http://localhost:8000
echo View logs: docker-compose -f docker-compose.prod.yml logs -f

pause
