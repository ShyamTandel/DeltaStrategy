#!/bin/bash
# Quick start script for production environment

set -e

echo "Starting Delta Strategy in Production Mode..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your actual credentials!"
    exit 1
fi

# Start all services
docker-compose -f docker-compose.prod.yml up -d

echo "✅ Services started!"
echo ""
echo "Access the application at: http://localhost:8000"
echo "View logs: docker-compose -f docker-compose.prod.yml logs -f"
