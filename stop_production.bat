@echo off
REM Stop all production services

echo Stopping Delta Strategy Production Services...

docker-compose -f docker-compose.prod.yml down

echo.
echo Services stopped!

pause
