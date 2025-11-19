#!/bin/bash
# Production Deployment Script for Delta Strategy

set -e

echo "=========================================="
echo "Delta Strategy - Production Deployment"
echo "=========================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "📝 Please copy .env.example to .env and configure it"
    exit 1
fi

# Load environment variables
source .env

# Backup database before deployment
echo "📦 Creating database backup..."
BACKUP_DIR="backups"
BACKUP_FILE="$BACKUP_DIR/deltadb_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p $BACKUP_DIR

docker-compose -f docker-compose.prod.yml exec -T mysql mysqldump \
    -u root -p${MYSQL_ROOT_PASSWORD} ${MYSQL_DATABASE} > $BACKUP_FILE 2>/dev/null || \
    echo "⚠️  Backup skipped (database might not be running)"

# Pull latest images
echo "🔄 Pulling latest Docker images..."
docker-compose -f docker-compose.prod.yml pull

# Build new images
echo "🏗️  Building Docker images..."
docker-compose -f docker-compose.prod.yml build --no-cache

# Stop old containers
echo "🛑 Stopping old containers..."
docker-compose -f docker-compose.prod.yml down

# Start new containers
echo "🚀 Starting new containers..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Run migrations
echo "🔄 Running database migrations..."
docker-compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput

# Collect static files
echo "📦 Collecting static files..."
docker-compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput --clear

# Check service health
echo "🏥 Checking service health..."
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo "✅ Deployment completed successfully!"
echo "=========================================="
echo ""
echo "📊 Service Status:"
docker-compose -f docker-compose.prod.yml ps
echo ""
echo "📝 View logs with: docker-compose -f docker-compose.prod.yml logs -f"
echo "🔍 Check specific service: docker-compose -f docker-compose.prod.yml logs -f [web|celery_worker|celery_beat]"
