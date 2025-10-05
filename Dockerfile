# Use Python 3.10.11 slim image
FROM python:3.10.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
        gcc \
        python3-dev \
        redis-server \
        supervisor \
        curl \
        procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create directories for logs and supervisor
RUN mkdir -p /app/logs /var/log/supervisor /etc/supervisor/conf.d

# Copy supervisor configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy entrypoint and startup scripts
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create a non-root user for security but keep some permissions
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /var/log/supervisor

# Expose ports
EXPOSE 8000 6379

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command to run supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]