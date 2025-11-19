# Delta Strategy Production Setup

A Django application with Celery and Redis for automated trading strategies.

## Project Structure

```
deltastrategy/
├── .github/workflows/
│   └── deploy-production.yml    # GitHub Actions deployment workflow
├── api/                          # Django app
├── deltastrategy/               # Django project settings
├── templates/                   # HTML templates
├── docker-compose.yml           # Local development
├── docker-compose.prod.yml      # Production deployment
├── Dockerfile                   # Development image
├── Dockerfile.prod             # Production image
├── requirements.txt            # Python dependencies
└── manage.py                   # Django management script
```

## Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd DeltaStrategy
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Run migrations**
   ```bash
   docker-compose exec web python manage.py migrate
   ```

5. **Create superuser**
   ```bash
   docker-compose exec web python manage.py createsuperuser
   ```

## Production Deployment

### Prerequisites

- Docker and Docker Compose installed on the server
- GitHub repository secrets configured:
  - `DOCKER_HUB_USERNAME` - Your Docker Hub username
  - `DOCKER_HUB_TOKEN` - Your Docker Hub access token
  - `PROD_HOST` - Production server hostname/IP
  - `PROD_USERNAME` - SSH username
  - `PROD_SSH_KEY` - SSH private key for authentication

### Setup Instructions

1. **Update GitHub Actions workflow**
   
   Edit `.github/workflows/deploy-production.yml`:
   - Replace `your-dockerhub-username/deltastrategy` with your Docker Hub image name
   - Update the deployment path in the SSH script section

2. **Configure server**
   
   On your production server:
   ```bash
   # Create app directory
   mkdir -p /path/to/your/app
   cd /path/to/your/app
   
   # Copy docker-compose.prod.yml and .env files
   # Set up your .env file with production values
   ```

3. **Deploy**
   
   - Go to GitHub Actions in your repository
   - Select "Deploy to Production" workflow
   - Click "Run workflow"

### Manual Deployment

```bash
# SSH into your server
ssh user@your-server

# Navigate to app directory
cd /path/to/your/app

# Pull latest image
docker pull your-dockerhub-username/deltastrategy:latest

# Set environment variable
export IMAGE_NAME=your-dockerhub-username/deltastrategy

# Deploy
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

## Services

- **web** - Django application (port 8000)
- **celery** - Celery worker for background tasks
- **redis** - Redis cache and message broker

## Environment Variables

Key environment variables in `.env`:

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com

# Database
DB_HOST=your-database-host
DB_NAME=deltastrategy
DB_USER=your-db-user
DB_PASSWORD=your-db-password

# Celery
CELERY_BROKER_URL=redis://redis:6379/0

# Delta API
DELTA_API_KEY=your-delta-api-key
DELTA_API_SECRET=your-delta-api-secret
```

## Monitoring

View logs:
```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f celery
```

Check service status:
```bash
docker-compose -f docker-compose.prod.yml ps
```

## Troubleshooting

**Services not starting:**
```bash
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

**Clear Redis cache:**
```bash
docker-compose -f docker-compose.prod.yml exec redis redis-cli FLUSHALL
```

**Run Django management commands:**
```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py <command>
```

## License

Proprietary
