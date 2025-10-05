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
    
    # Original API (backward compatibility)
    path('api/start-cycle/', views.StartMonthCycleAPIView.as_view(), name='start-cycle'),
    
    # Main Strategy APIs (all consolidated in views.py)
    path('api/strategy/', views.StrategyExecuteAPIView.as_view(), name='strategy-execute'),
    path('api/strategy/status/', views.StrategyStatusAPIView.as_view(), name='strategy-status'),
    path('api/strategy/close-all/', views.StrategyCloseAllAPIView.as_view(), name='strategy-close-all'),
    
    # Background/Celery APIs (work even if Celery not available)
    path('api/strategy/execute-background/', views.BackgroundStrategyExecuteAPIView.as_view(), name='strategy-background'),
    path('api/strategy/monitoring/status/', views.MonitoringStatusAPIView.as_view(), name='monitoring-status'),
    path('api/strategy/force-monitor/', views.ForceMonitorAPIView.as_view(), name='force-monitor'),
]
