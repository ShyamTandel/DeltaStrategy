#!/bin/bash

# Entrypoint script for Delta Strategy Docker container

echo "🚀 Starting Delta Strategy Docker Container..."

# Wait a moment for any system initialization
sleep 2

# Check if we're running as root (needed for supervisor)
if [ "$(id -u)" != "0" ]; then
    echo "❌ This container needs to run as root to manage all services"
    exit 1
fi

# Switch to app user for Django operations
echo "📋 Running Django setup as appuser..."

# Change to app directory
cd /app

# Wait for database to be available (retry mechanism)
echo "🔍 Waiting for database connection..."
for i in {1..30}; do
    if su appuser -c "python manage.py check --database default" > /dev/null 2>&1; then
        echo "✅ Database is accessible"
        break
    else
        echo "⏳ Waiting for database... (attempt $i/30)"
        sleep 2
    fi
    if [ $i -eq 30 ]; then
        echo "⚠️  Database not accessible, continuing without migrations"
        echo "💡 Make sure your database is running and accessible"
        export SKIP_DB_OPERATIONS=1
    fi
done

# Only run database operations if database is accessible
if [ -z "$SKIP_DB_OPERATIONS" ]; then
    echo "🔄 Running Django migrations..."
    su appuser -c "python manage.py makemigrations --noinput" || echo "⚠️  makemigrations failed"
    su appuser -c "python manage.py migrate --noinput" || echo "⚠️  migrate failed"
else
    echo "⏭️  Skipping database operations"
fi

# Collect static files if needed (skip if no STATIC_ROOT configured)
echo "📦 Collecting static files..."
su appuser -c "python manage.py collectstatic --noinput" 2>/dev/null || echo "⚠️  Static files collection skipped (not configured)"

# Create superuser if DJANGO_SUPERUSER_* environment variables are set
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "👤 Creating Django superuser..."
    su appuser -c "python manage.py shell -c \"
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD');
    print('Superuser created successfully')
else:
    print('Superuser already exists')
\""
fi

# Test Redis connectivity
echo "🔍 Testing Redis connectivity..."
redis-cli ping > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Redis is accessible"
else
    echo "⚠️  Redis test failed - will start with supervisor"
fi

# Create log directory if it doesn't exist
mkdir -p /app/logs
chown -R appuser:appuser /app/logs

echo "🎯 Starting all services with supervisor..."

# Execute the command passed to docker run
exec "$@"