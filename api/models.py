from django.db import models

class OptionPosition(models.Model):
    # stores a tracked option position created by our bot
    product_id = models.IntegerField()
    symbol = models.CharField(max_length=128)  # e.g. C-BTC-90000-310125
    side = models.CharField(max_length=10)  # 'sell' (we sell options as per FDD)
    size = models.IntegerField()
    limit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    mark_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    strike_price = models.DecimalField(max_digits=20, decimal_places=2)
    delta = models.FloatField()
    expiry_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    remote_order_id = models.BigIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    closed_at = models.DateTimeField(null=True, blank=True, help_text="UTC timestamp when position was closed")
    
    # Strategy cycle tracking
    strategy_cycle_id = models.CharField(max_length=50, null=True, blank=True, help_text="Monthly cycle identifier (YYYY-MM)")
    is_initial_position = models.BooleanField(default=False, help_text="True if this was one of the initial two positions sold")

    class Meta:
        db_table = 'option_position'
        
    def __str__(self):
        return f"{self.symbol} {self.side} delta={self.delta}"



class InitialBalanceTracker(models.Model):
    """
    Track initial USD balance for each strategy cycle
    """
    cycle_id = models.CharField(max_length=50, unique=True, help_text="Monthly cycle identifier (YYYY-MM)")
    initial_balance_usd = models.DecimalField(max_digits=20, decimal_places=8, help_text="Initial USD balance when cycle started")
    initial_balance_inr = models.DecimalField(max_digits=20, decimal_places=2, help_text="Initial INR equivalent balance")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'initial_balance_tracker'
        
    def __str__(self):
        return f"{self.cycle_id}: Initial USD ${self.initial_balance_usd} (₹{self.initial_balance_inr})"
