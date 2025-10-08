from celery import shared_task
from api.delta_client import DeltaClient
from api.monthly_strategy import start_monthly_cycle_if_needed, check_positions_and_adjust
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
        result = start_monthly_cycle_if_needed()
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
def periodic_adjustment_check(target_profit_dollars=1000.0):
    """
    Periodic task to check position adjustments every 30 seconds
    This is the main monitoring task that runs continuously
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🔄 Starting periodic adjustment check at {timestamp}")
    
    try:
        # Main adjustment logic
        result = check_positions_and_adjust(target_profit_dollars)
        logger.info(f"📊 Adjustment check result: {result}")
        
        return {
            'timestamp': timestamp,
            'adjustment_result': result,
            'target_profit': target_profit_dollars,
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
def periodic_api_check(target_profit=1000.0):
    """
    DEPRECATED: Legacy task - use periodic_adjustment_check instead
    Keeping for backward compatibility
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🔄 Legacy API check at {timestamp} - use periodic_adjustment_check instead")
    
    try:
        # Redirect to new adjustment check
        result = check_positions_and_adjust(target_profit)
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

@shared_task
def manual_target_check(target_profit=1000.0):
    """Manual task to check target and close positions"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"🎯 Manual target check at {timestamp} with target: {target_profit}")
    
    try:
        client = DeltaClient(debug=True)
        result = client.check_target_and_close_positions(target_profit)
        
        logger.info(f"Manual target check result: {result}")
        return {
            'timestamp': timestamp,
            'result': result,
            'status': 'success'
        }
        
    except Exception as e:
        error_msg = f"Error in manual target check: {str(e)}"
        logger.error(error_msg)
        return {
            'timestamp': timestamp,
            'error': str(e),
            'status': 'error'
        }