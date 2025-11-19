# GitHub Actions Secrets Configuration Guide

To set up your GitHub Actions CI/CD pipeline, you need to configure the following secrets in your GitHub repository:

## How to Add Secrets

1. Go to your repository on GitHub
2. Click on **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret listed below

---

## Required Secrets

### Application Secrets

**SECRET_KEY**
- Description: Django secret key for cryptographic signing
- Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- Example: `django-insecure-xyz123abc456...`

**DELTA_API_KEY**
- Description: Your Delta Exchange API key
- Get from: Delta Exchange dashboard

**DELTA_API_SECRET**
- Description: Your Delta Exchange API secret
- Get from: Delta Exchange dashboard

**DELTA_API_BASE**
- Description: Delta Exchange API base URL
- Value: `https://api.delta.exchange` (or testnet URL)

---

## Deployment Secrets (Required for CD)

### Staging Environment

**STAGING_HOST**
- Description: Staging server IP address or hostname
- Example: `staging.yourdomain.com` or `192.168.1.100`

**STAGING_USERNAME**
- Description: SSH username for staging server
- Example: `ubuntu` or `deploy`

**STAGING_SSH_KEY**
- Description: Private SSH key for staging server access
- Generate with: `ssh-keygen -t ed25519 -C "github-actions"`
- Copy private key content (entire file including BEGIN/END lines)

**STAGING_PORT** (Optional)
- Description: SSH port for staging server
- Default: `22`

### Production Environment

**PRODUCTION_HOST**
- Description: Production server IP address or hostname
- Example: `yourdomain.com` or `192.168.1.200`

**PRODUCTION_USERNAME**
- Description: SSH username for production server
- Example: `ubuntu` or `deploy`

**PRODUCTION_SSH_KEY**
- Description: Private SSH key for production server access
- Generate with: `ssh-keygen -t ed25519 -C "github-actions-prod"`
- Copy private key content (entire file including BEGIN/END lines)

**PRODUCTION_PORT** (Optional)
- Description: SSH port for production server
- Default: `22`

---

## Environment Variables Setup

For each environment (staging/production), create appropriate `.env` files on your servers:

**On Staging Server:**
```bash
cd /opt/deltastrategy
cp .env.example .env.staging
# Edit .env.staging with staging credentials
```

**On Production Server:**
```bash
cd /opt/deltastrategy
cp .env.example .env
# Edit .env with production credentials
```

---

## Server Setup Requirements

### 1. Install Docker & Docker Compose on servers

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. Create deployment directory

```bash
sudo mkdir -p /opt/deltastrategy
sudo chown $USER:$USER /opt/deltastrategy
```

### 3. Add GitHub Actions SSH key to authorized_keys

```bash
# On the server, add the public key corresponding to the private key stored in GitHub secrets
echo "PUBLIC_KEY_HERE" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 4. Clone repository (first time only)

```bash
cd /opt/deltastrategy
git clone https://github.com/ShyamTandel/DeltaStrategy.git .
```

---

## GitHub Environments Setup (Optional but Recommended)

1. Go to **Settings** → **Environments**
2. Create two environments:
   - **staging**: Add protection rules if needed
   - **production**: Add required reviewers for manual approval

---

## Testing the Pipeline

1. Push code to `dev-api` branch to trigger staging deployment
2. Push code to `main` branch to trigger production deployment
3. Monitor the **Actions** tab in GitHub to see pipeline progress

---

## Workflow Triggers

- **Tests & Build**: Run on every push and pull request
- **Staging Deployment**: Automatic on `dev` or `dev-api` branch pushes
- **Production Deployment**: Automatic on `main` branch pushes (add manual approval via GitHub Environments for safety)

---

## Security Best Practices

1. ✅ Never commit `.env` files to git
2. ✅ Rotate secrets regularly
3. ✅ Use separate API keys for staging and production
4. ✅ Enable GitHub environment protection rules for production
5. ✅ Use SSH keys with strong passphrases
6. ✅ Limit SSH key access to specific IP ranges if possible
7. ✅ Enable 2FA on GitHub account
8. ✅ Review deployment logs regularly
