"""
URL configuration for deltastrategy project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from api import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('admin/', admin.site.urls),
    path('api/health/', views.health_check, name='health_check'),
    path('api/test-credentials/', views.test_delta_credentials, name='test_credentials'),
    
    # Original API (backward compatibility)
    path('api/start-cycle/', views.StartMonthCycleAPIView.as_view(), name='start-cycle'),
    
    # Main Strategy APIs (all consolidated in views.py)
    path('api/strategy/', views.StrategyExecuteAPIView.as_view(), name='strategy-execute'),
    path('api/strategy/status/', views.StrategyStatusAPIView.as_view(), name='strategy-status'),
    path('api/strategy/close-all/', views.StrategyCloseAllAPIView.as_view(), name='strategy-close-all'),
    path('api/strategy/execute-full-local/', views.FullLocalStrategyAPIView.as_view(), name='strategy-full-local'),
    
    # Background/Celery APIs (work even if Celery not available)
    path('api/strategy/execute-background/', views.BackgroundStrategyExecuteAPIView.as_view(), name='strategy-background'),
    path('api/strategy/monitoring/status/', views.MonitoringStatusAPIView.as_view(), name='monitoring-status'),
    path('api/strategy/force-monitor/', views.ForceMonitorAPIView.as_view(), name='force-monitor'),
    
    # Monitoring Dashboard APIs
    path('api/monitoring/status/', views.api_status, name='api-status'),
    path('api/monitoring/trigger/', views.trigger_manual_check, name='trigger-manual-check'),
    path('api/monitoring/result/<str:task_id>/', views.get_task_result, name='get-task-result'),
    path('api/monitoring/control/', views.control_monitoring, name='control-monitoring'),
    path('monitoring/', views.monitoring_dashboard, name='monitoring-dashboard'),
    
    # Monthly Strategy APIs
    path('api/monthly-strategy/start/', views.MonthlyStrategyStartAPIView.as_view(), name='monthly-strategy-start'),
    path('api/monthly-strategy/status/', views.MonthlyStrategyStatusAPIView.as_view(), name='monthly-strategy-status'),
    path('api/monthly-strategy/adjust/', views.MonthlyStrategyAdjustAPIView.as_view(), name='monthly-strategy-adjust'),
    path('api/monthly-strategy/close-all/', views.MonthlyStrategyCloseAllAPIView.as_view(), name='monthly-strategy-close-all'),
]
