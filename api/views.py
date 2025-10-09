"""
All API views for Delta Strategy application
Consolidated from celery_views.py, strategy_views.py and original views.py
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.delta_client import DeltaClient
from api.models import OptionPosition


logger = logging.getLogger(__name__)

# Check Celery availability
try:
    from celery import current_app
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


def home_view(request):
    """
    Home page view
    """
    context = {
        'current_time': timezone.now(),
    }
    return render(request, 'home.html', context)

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint
    """
    return Response({
        'status': 'healthy',
        'message': 'DeltaStrategy API is running'
    })
