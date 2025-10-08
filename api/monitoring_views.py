from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from tasks import periodic_api_check, test_connection_task, manual_target_check
from django_celery_beat.models import PeriodicTask
from celery.result import AsyncResult
import json
from datetime import datetime

def api_status(request):
    """API status endpoint to check if monitoring is running"""
    try:
        # Get periodic task status
        periodic_tasks = PeriodicTask.objects.filter(
            name__in=['Periodic API Check Every 30 Seconds', 'Connection Test Every 5 Minutes']
        )
        
        task_status = []
        for task in periodic_tasks:
            task_status.append({
                'name': task.name,
                'enabled': task.enabled,
                'last_run_at': task.last_run_at.isoformat() if task.last_run_at else None,
                'total_run_count': task.total_run_count,
                'task': task.task,
                'args': task.args,
            })
        
        return JsonResponse({
            'status': 'running',
            'periodic_tasks': task_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@csrf_exempt
def trigger_manual_check(request):
    """Manually trigger API check"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.body else {}
            target_profit = float(data.get('target_profit', 1000.0))
        except (json.JSONDecodeError, ValueError):
            target_profit = 1000.0
    else:
        target_profit = float(request.GET.get('target_profit', 1000.0))
    
    # Trigger the task
    result = manual_target_check.delay(target_profit)
    
    return JsonResponse({
        'task_id': result.id,
        'status': 'Task triggered',
        'target_profit': target_profit,
        'timestamp': datetime.now().isoformat()
    })

def get_task_result(request, task_id):
    """Get the result of a specific task"""
    try:
        result = AsyncResult(task_id)
        
        return JsonResponse({
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({
            'task_id': task_id,
            'status': 'error',
            'error': str(e)
        }, status=500)

def monitoring_dashboard(request):
    """Simple HTML dashboard for monitoring"""
    return render(request, 'monitoring_dashboard.html')

@csrf_exempt
def control_monitoring(request):
    """Enable or disable monitoring"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action', 'enable')  # enable or disable
            
            tasks = PeriodicTask.objects.filter(
                name__in=['Periodic API Check Every 30 Seconds', 'Connection Test Every 5 Minutes']
            )
            
            if action == 'enable':
                tasks.update(enabled=True)
                message = 'Monitoring enabled'
            elif action == 'disable':
                tasks.update(enabled=False)
                message = 'Monitoring disabled'
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
            
            return JsonResponse({
                'status': 'success',
                'message': message,
                'affected_tasks': tasks.count(),
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Only POST method allowed'}, status=405)