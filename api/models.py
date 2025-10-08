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
    
    # New fields for PnL tracking
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0.00, help_text="Realized PnL when position is closed")
    closed_at = models.DateTimeField(null=True, blank=True, help_text="UTC timestamp when position was closed")
    close_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, help_text="Price at which position was closed")
    
    # Strategy cycle tracking
    strategy_cycle_id = models.CharField(max_length=50, null=True, blank=True, help_text="Monthly cycle identifier (YYYY-MM)")
    is_initial_position = models.BooleanField(default=False, help_text="True if this was one of the initial two positions sold")

    class Meta:
        db_table = 'option_position'
        
    def __str__(self):
        return f"{self.symbol} {self.side} delta={self.delta}"


class MonthlyPnLTracker(models.Model):
    """
    Track realized PnL for each monthly strategy cycle
    """
    cycle_id = models.CharField(max_length=50, help_text="Monthly cycle identifier (YYYY-MM)")
    underlying = models.CharField(max_length=10, default="BTC", help_text="Underlying asset")
    closed_position_symbol = models.CharField(max_length=128, help_text="Symbol of closed position")
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, help_text="Realized PnL from closed position")
    close_price = models.DecimalField(max_digits=20, decimal_places=8, help_text="Price at which position was closed")
    entry_price = models.DecimalField(max_digits=20, decimal_places=8, help_text="Original entry price")
    size = models.DecimalField(max_digits=20, decimal_places=8, help_text="Position size")
    closed_at = models.DateTimeField(help_text="UTC timestamp when position was closed")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'monthly_pnl_tracker'
        unique_together = ['cycle_id', 'closed_position_symbol', 'closed_at']  # Prevent duplicates
        
    def __str__(self):
        return f"{self.cycle_id} - {self.closed_position_symbol}: ${self.realized_pnl}"
