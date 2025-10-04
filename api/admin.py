from django.contrib import admin
from .models import Strategy, Trade, Portfolio

# Register your models here.

@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'trade_type', 'quantity', 'price', 'timestamp']
    list_filter = ['trade_type', 'timestamp']
    search_fields = ['symbol']

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_value', 'cash_balance', 'updated_at']
    search_fields = ['user__username']
