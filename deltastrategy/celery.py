"""
Celery configuration for DeltaStrategy project
"""

import os
from celery import Celery
from django.conf import settings

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
        'task': 'api.strategy.monitor_monthly_strategy',
        'schedule': 30.0,  # Every 30 seconds
        'options': {
            'expires': 25.0,  # Expire task if not executed within 25 seconds
        }
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
    task_always_eager=False,  # Set to True for testing
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
    print(f'Request: {self.request!r}')


@app.task(bind=True, name='api.strategy.monitor_monthly_strategy')
def monitor_monthly_strategy_task(self):
    """
    Celery task to monitor monthly strategy every 30 seconds
    
    This task monitors active positions and executes adjustments
    as needed based on the 3 core requirements
    """
    from api.strategy import MonthlyStrategy
    strategy = MonthlyStrategy()
    return strategy.monitor_and_adjust()