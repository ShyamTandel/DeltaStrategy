from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Function-based views
    path('health/', views.health_check, name='health_check'),
    path('sample/', views.sample_api, name='sample_api'),
    path('info/', views.delta_strategy_info, name='delta_strategy_info'),
    
    # Class-based views
    path('data/', views.DataAPIView.as_view(), name='data_api'),
    
    # Strategy endpoints
    path('strategies/', views.StrategyListCreateView.as_view(), name='strategy_list_create'),
    path('strategies/<int:pk>/', views.StrategyDetailView.as_view(), name='strategy_detail'),
    
    # Trade endpoints
    path('trades/', views.TradeListCreateView.as_view(), name='trade_list_create'),
    path('trades/<int:pk>/', views.TradeDetailView.as_view(), name='trade_detail'),
    
    # Portfolio endpoints
    path('portfolios/', views.PortfolioListView.as_view(), name='portfolio_list'),
]