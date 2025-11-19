# Delta Strategy - Production Deployment Guide

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose installed
- Git installed
- Port 8000 available

### 1️⃣ Clone and Setup

```bash
git clone https://github.com/ShyamTandel/DeltaStrategy.git
cd DeltaStrategy
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
nano .env  # or use any editor
```

### 2️⃣ Start Production Services

**Linux/Mac:**
```bash
chmod +x start_production.sh
./start_production.sh
```

**Windows:**
```cmd
start_production.bat
```

### 3️⃣ Access Application

- **Web App**: http://localhost:8000
- **Admin Panel**: http://localhost:8000/admin

---

## 📋 Available Scripts

### Windows Scripts

| Script | Description |
|--------|-------------|
| `start_production.bat` | Start all production services |
| `stop_production.bat` | Stop all production services |
| `deploy_production.bat` | Full deployment with migrations |
| `view_logs_production.bat` | View service logs |

### Linux/Mac Scripts

| Script | Description |
|--------|-------------|
| `start_production.sh` | Start all production services |
| `deploy_production.sh` | Full deployment with migrations |

---

## 🏗️ Architecture

The production setup includes:

- **Web Server**: Django with Gunicorn (4 workers)
- **Database**: MySQL 8.0
- **Cache/Queue**: Redis 7
- **Task Workers**: Celery worker (4 concurrent tasks)
- **Task Scheduler**: Celery beat

### Services

```
┌─────────────┐
│   MySQL     │ :3306
└─────────────┘
       ↓
┌─────────────┐
│   Redis     │ :6379
└─────────────┘
       ↓
┌─────────────┐
│  Django Web │ :8000 (Gunicorn)
└─────────────┘
       ↓
┌─────────────────────────────┐
│ Celery Worker & Beat        │
└─────────────────────────────┘
```

---

## 🔧 Configuration

### Environment Variables

See `.env.example` for all available options. Key variables:

```env
# Security
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,yourdomain.com

# Database
DB_NAME=deltadb
DB_USER=deltauser
DB_PASSWORD=strong-password

# API Credentials
DELTA_API_KEY=your-api-key
DELTA_API_SECRET=your-api-secret
```

### Production Security Settings

For HTTPS deployments, enable these in `.env`:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

---

## 📊 Monitoring & Logs

### View All Logs
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

### View Specific Service
```bash
# Web server
docker-compose -f docker-compose.prod.yml logs -f web

# Celery worker
docker-compose -f docker-compose.prod.yml logs -f celery_worker

# Celery beat
docker-compose -f docker-compose.prod.yml logs -f celery_beat
```

### Log Files Location
- Application logs: `./logs/`
- Gunicorn access: `./logs/gunicorn-access.log`
- Gunicorn errors: `./logs/gunicorn-error.log`

---

## 🔄 Updates & Maintenance

### Deploy New Version

**Full deployment with backup:**
```bash
./deploy_production.sh  # Linux/Mac
deploy_production.bat   # Windows
```

This script will:
1. ✅ Backup database
2. ✅ Pull latest images
3. ✅ Build new containers
4. ✅ Run migrations
5. ✅ Collect static files
6. ✅ Restart services

### Manual Migration

```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### Create Superuser

```bash
docker-compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

Or set in `.env`:
```env
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@yourdomain.com
DJANGO_SUPERUSER_PASSWORD=your-password
```

---

## 🗄️ Database Backup & Restore

### Manual Backup

```bash
# Create backup directory
mkdir -p backups

# Backup database
docker-compose -f docker-compose.prod.yml exec mysql mysqldump \
  -u root -p${MYSQL_ROOT_PASSWORD} ${MYSQL_DATABASE} > backups/backup_$(date +%Y%m%d).sql
```

### Restore Backup

```bash
docker-compose -f docker-compose.prod.yml exec -T mysql mysql \
  -u root -p${MYSQL_ROOT_PASSWORD} ${MYSQL_DATABASE} < backups/backup_20231118.sql
```

---

## 🐛 Troubleshooting

### Services Not Starting

```bash
# Check service status
docker-compose -f docker-compose.prod.yml ps

# Check logs for errors
docker-compose -f docker-compose.prod.yml logs
```

### Database Connection Issues

```bash
# Check MySQL is running
docker-compose -f docker-compose.prod.yml exec mysql mysqladmin ping

# Test connection
docker-compose -f docker-compose.prod.yml exec web python manage.py check --database default
```

### Celery Not Processing Tasks

```bash
# Check celery worker status
docker-compose -f docker-compose.prod.yml exec celery_worker celery -A deltastrategy inspect active

# Check celery beat status
docker-compose -f docker-compose.prod.yml exec celery_beat celery -A deltastrategy inspect scheduled
```

### Reset Everything

```bash
# Stop and remove all containers, volumes
docker-compose -f docker-compose.prod.yml down -v

# Start fresh
./start_production.sh  # or .bat on Windows
```

---

## 🔒 Security Checklist

- [ ] Changed default SECRET_KEY
- [ ] Set DEBUG=False
- [ ] Configured ALLOWED_HOSTS
- [ ] Strong database passwords
- [ ] SSL/HTTPS enabled (if public)
- [ ] Firewall configured
- [ ] Regular backups scheduled
- [ ] Monitoring enabled
- [ ] API keys secured

---

## 📈 Performance Tuning

### Gunicorn Workers

Default: 4 workers. Adjust in `Dockerfile.prod`:
```dockerfile
CMD ["gunicorn", ..., "--workers", "8", ...]
```

Rule of thumb: `(2 × CPU cores) + 1`

### Celery Concurrency

Default: 4 concurrent tasks. Adjust in `docker-compose.prod.yml`:
```yaml
command: celery -A deltastrategy worker --concurrency=8 ...
```

### Database Connections

Adjust in `docker-compose.prod.yml`:
```yaml
command: --max-connections=500
```

---

## 📞 Support

- **GitHub Issues**: https://github.com/ShyamTandel/DeltaStrategy/issues
- **Documentation**: See README.md

---

## 📝 License

[Your License Here]
