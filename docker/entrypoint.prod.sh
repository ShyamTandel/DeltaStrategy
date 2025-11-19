#!/bin/bash
set -e

echo "🚀 Starting Delta Strategy Production Container..."

# Wait for database to be ready
echo "🔍 Waiting for database..."
while ! nc -z $DB_HOST $DB_PORT; do
    echo "⏳ Waiting for database at $DB_HOST:$DB_PORT..."
    sleep 2
done
echo "✅ Database is ready!"

# Wait for Redis to be ready
REDIS_HOST=$(echo $CELERY_BROKER_URL | sed -n 's/.*redis:\/\/\([^:]*\).*/\1/p')
REDIS_PORT=$(echo $CELERY_BROKER_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}

echo "🔍 Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
while ! nc -z $REDIS_HOST $REDIS_PORT; do
    echo "⏳ Waiting for Redis..."
    sleep 2
done
echo "✅ Redis is ready!"

# Run migrations
echo "🔄 Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "📦 Collecting static files..."
python manage.py collectstatic --noinput --clear

# Create superuser if variables are set and user doesn't exist
if [ "$DJANGO_SUPERUSER_USERNAME" ] && [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "👤 Checking for superuser..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD');
    print('✅ Superuser created successfully')
else:
    print('ℹ️  Superuser already exists')
" || echo "⚠️  Could not check/create superuser"
fi

echo "🎯 Starting application..."
exec "$@"
