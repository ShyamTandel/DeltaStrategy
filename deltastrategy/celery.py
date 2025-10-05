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
    'monitor-strategy-positions': {
        'task': 'api.strategy.monitor_strategy_positions_task',
        'schedule': 30.0,  # Every 30 seconds
        'options': {
            'expires': 25.0,  # Expire task if not executed within 25 seconds
            'retry': True,
            'retry_policy': {
                'max_retries': 3,
                'interval_start': 1,
                'interval_step': 1,
            }
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


@app.task(bind=True, name='api.strategy.monitor_strategy_positions_task')
def monitor_strategy_positions_task(self):
    """
    Celery task to monitor active strategy positions every 30 seconds
    
    This task:
    - Checks current prices of active positions
    - Monitors for price doubling conditions  
    - Checks profit targets
    - Executes automatic position management
    """
    from api.strategy import monitor_positions
    return monitor_positions()

@app.task(bind=True, name='api.strategy.execute_strategy_background_task')  
def execute_strategy_background_task(self, underlying="BTC", reference_date=None, profit_target=50.0, position_size=2):
    """
    Execute delta strategy in background
    
    Args:
        underlying: Asset symbol (e.g., "BTC")
        reference_date: Optional date in YYYY-MM-DD format
        profit_target: Profit target percentage (default 50%)
        position_size: Position size (default 2)
    """
    from api.strategy import execute_strategy_background
    return execute_strategy_background(underlying, reference_date, profit_target, position_size)

@app.task(bind=True, name='api.strategy.emergency_close_all_task')
def emergency_close_all_task(self):
    """
    Emergency close all active positions
    
    This task will immediately close all open positions
    in case of emergency or system shutdown
    """
    from api.strategy import emergency_close_all
    return emergency_close_all()