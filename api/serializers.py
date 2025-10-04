from rest_framework import serializers
from .models import Strategy, Trade, Portfolio
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class StrategySerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    
    class Meta:
        model = Strategy
        fields = ['id', 'name', 'description', 'created_by', 'created_at', 'updated_at', 'is_active']
        read_only_fields = ['created_at', 'updated_at']

class TradeSerializer(serializers.ModelSerializer):
    strategy = StrategySerializer(read_only=True)
    strategy_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = Trade
        fields = ['id', 'strategy', 'strategy_id', 'symbol', 'trade_type', 'quantity', 'price', 'timestamp']
        read_only_fields = ['timestamp']

class PortfolioSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Portfolio
        fields = ['id', 'user', 'total_value', 'cash_balance', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']