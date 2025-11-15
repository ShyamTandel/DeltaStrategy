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
from django.urls import path
from api import views
from api.strategy import CloseAllPositionsView, StartStrategyView, MonitorStrategyView, StatusView, TestStrangel

urlpatterns = [
    path('', views.home_view, name='home'),
    path('admin/', admin.site.urls),
    
    # Clean Strategy APIs - Only 3 endpoints needed
    path('api/start/', StartStrategyView.as_view(), name='start-strategy'),
    path('api/monitor/', MonitorStrategyView.as_view(), name='monitor-strategy'),
    path('api/status/', StatusView.as_view(), name='strategy-status'),
    path('api/test-strangel/', TestStrangel.as_view(), name='test-strangel'),
    path('api/close-all/', CloseAllPositionsView.as_view(), name='close-all-positions'),
]
