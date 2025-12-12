from celery import shared_task
from django.utils import timezone
from api.delta_client import DeltaClient
from api.strategy import MonthlyStrategy, TestStrangel
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@shared_task
def monthly_strategy_start_task():
    """
    Task to start monthly strategy on first day of month
    Should be called daily to check if new cycle needs to start
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🔄 Checking if monthly cycle should start at {timestamp}")
    
    try:
        strategy = MonthlyStrategy()
        result = strategy.start_monthly_cycle()
        logger.info(f"📊 Monthly cycle start result: {result}")
        
        return {
            'timestamp': timestamp,
            'monthly_start_result': result,
            'status': 'success'
        }
        
    except Exception as e:
        error_msg = f"❌ Error in monthly cycle start: {str(e)}"
        logger.error(error_msg)
        return {
            'timestamp': timestamp,
            'error': str(e),
            'status': 'error'
        }

@shared_task
def periodic_adjustment_check(target_profit_percentage=80.0):
    """
    Periodic task to check position adjustments every 30 seconds
    This is the main monitoring task that runs continuously
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🔄 Starting periodic adjustment check at {timestamp}")
    
    try:
        # Main adjustment logic
        strategy = MonthlyStrategy()
        result = strategy.monitor_and_adjust(target_profit_percentage)
        logger.info(f"📊 Adjustment check result: {result}")
        # strategy = TestStrangel()
        # result = strategy.stradel()
        # logger.info(f"📊 Adjustment check result: {result}")

        return {
            'timestamp': timestamp,
            'adjustment_result': result,
            'target_profit': target_profit_percentage,
            'status': 'success'
        }
        
    except Exception as e:
        error_msg = f"❌ Error in periodic adjustment check: {str(e)}"
        logger.error(error_msg)
        return {
            'timestamp': timestamp,
            'error': str(e),
            'status': 'error'
        }

@shared_task
def periodic_api_check(cycle_id=None, target_profit_percentage=80.0):
    """
    DEPRECATED: Legacy task - use periodic_adjustment_check instead
    Keeping for backward compatibility
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🔄 Legacy API check at {timestamp} - use periodic_adjustment_check instead")
    
    try:
        current_date = timezone.now()
        cycle_id = f"{current_date.year}-{current_date.month:02d}"
        # Redirect to new adjustment check
        strategy = MonthlyStrategy()
        result = strategy._check_target(cycle_id=cycle_id, target_profit_percentage=target_profit_percentage)
        logger.info(f"📊 Legacy check result: {result}")
        
        return {
            'timestamp': timestamp,
            'legacy_redirect': True,
            'adjustment_result': result,
            'status': 'success'
        }
        
    except Exception as e:
        error_msg = f"❌ Error in legacy API check: {str(e)}"
        logger.error(error_msg)
        return {
            'timestamp': timestamp,
            'error': str(e),
            'status': 'error'
        }

@shared_task
def test_connection_task():
    """Simple task to test connection"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"✅ Connection test at {timestamp}")
    
    try:
        client = DeltaClient(debug=False)
        auth_result = client.test_auth()
        
        return {
            'timestamp': timestamp,
            'auth_test': auth_result,
            'status': 'success'
        }
    except Exception as e:
        return {
            'timestamp': timestamp,
            'error': str(e),
            'status': 'error'
        }