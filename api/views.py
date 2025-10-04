from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

# Create your views here.

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

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def sample_api(request):
    """
    Sample API endpoint that handles both GET and POST requests
    """
    if request.method == 'GET':
        return Response({
            'message': 'This is a GET request',
            'data': {
                'example': 'data',
                'timestamp': '2024-01-01'
            }
        })
    
    elif request.method == 'POST':
        # Get data from request
        data = request.data
        return Response({
            'message': 'Data received successfully',
            'received_data': data,
            'status': 'success'
        }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([AllowAny])
def delta_strategy_info(request):
    """
    API endpoint to get information about Delta Strategy
    """
    return Response({
        'project': 'DeltaStrategy',
        'description': 'Django API for Delta Strategy application',
        'version': '1.0.0',
        'endpoints': {
            'health': '/api/health/',
            'sample': '/api/sample/',
            'info': '/api/info/'
        }
    })

# Example of a class-based view using Django REST Framework
from rest_framework.views import APIView
from rest_framework import generics
from .models import Strategy, Trade, Portfolio
from .serializers import StrategySerializer, TradeSerializer, PortfolioSerializer

class DataAPIView(APIView):
    """
    Class-based API view example
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """Handle GET requests"""
        return Response({
            'message': 'Class-based view GET response',
            'data': []
        })
    
    def post(self, request):
        """Handle POST requests"""
        return Response({
            'message': 'Class-based view POST response',
            'received': request.data
        }, status=status.HTTP_201_CREATED)
    
    def put(self, request):
        """Handle PUT requests"""
        return Response({
            'message': 'Class-based view PUT response',
            'updated': request.data
        })
    
    def delete(self, request):
        """Handle DELETE requests"""
        return Response({
            'message': 'Class-based view DELETE response'
        }, status=status.HTTP_204_NO_CONTENT)

# Strategy API Views
class StrategyListCreateView(generics.ListCreateAPIView):
    """
    API view to list all strategies or create a new strategy
    """
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer
    permission_classes = [AllowAny]  # Change this for production
    
    def perform_create(self, serializer):
        # For now, we'll set created_by to the first user or None
        # In production, use serializer.save(created_by=self.request.user)
        from django.contrib.auth.models import User
        user = User.objects.first()
        serializer.save(created_by=user)

class StrategyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update or delete a strategy
    """
    queryset = Strategy.objects.all()
    serializer_class = StrategySerializer
    permission_classes = [AllowAny]  # Change this for production

# Trade API Views
class TradeListCreateView(generics.ListCreateAPIView):
    """
    API view to list all trades or create a new trade
    """
    queryset = Trade.objects.all()
    serializer_class = TradeSerializer
    permission_classes = [AllowAny]  # Change this for production

class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update or delete a trade
    """
    queryset = Trade.objects.all()
    serializer_class = TradeSerializer
    permission_classes = [AllowAny]  # Change this for production

# Portfolio API Views
class PortfolioListView(generics.ListAPIView):
    """
    API view to list all portfolios
    """
    queryset = Portfolio.objects.all()
    serializer_class = PortfolioSerializer
    permission_classes = [AllowAny]  # Change this for production
