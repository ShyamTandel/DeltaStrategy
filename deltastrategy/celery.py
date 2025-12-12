"""
Celery configuration for DeltaStrategy project
"""

import os
from celery import Celery
from django.conf import settings
import logging
logger = logging.getLogger(__name__)
# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deltastrategy.settings')

app = Celery('deltastrategy')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat Schedule for automatic background execution
app.conf.beat_schedule = {
    # Monitor active positions every 30 seconds automatically
    'monitor-monthly-strategy': {
        'task': 'api.tasks.periodic_adjustment_check',
        'schedule': 30.0,  # Every 30 seconds
        'options': {
            'expires': 25.0,  # Expire if not executed in 25 seconds
        },
    },
}

# Celery configuration
app.conf.update(
    timezone='UTC',
    enable_utc=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_backend='django-db',
    task_always_eager=False,  # True for testing only
    task_eager_propagates=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_compression='gzip',
    result_compression='gzip',
)


@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery setup"""
    logger.info(f'Request: {self.request!r}')
