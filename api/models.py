from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class Strategy(models.Model):
    """
    Model to represent a trading strategy
    """
    name = models.CharField(max_length=200)
    description = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = "Strategies"
    
    def __str__(self):
        return self.name

class Trade(models.Model):
    """
    Model to represent individual trades
    """
    TRADE_TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
    ]
    
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='trades')
    symbol = models.CharField(max_length=10)
    trade_type = models.CharField(max_length=4, choices=TRADE_TYPES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.trade_type} {self.quantity} {self.symbol} @ {self.price}"

class Portfolio(models.Model):
    """
    Model to represent user portfolio
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    total_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cash_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Portfolio"
