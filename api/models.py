from django.db import models

class OptionPosition(models.Model):
    # stores a tracked option position created by our bot
    product_id = models.IntegerField(db_column='PRODUCT_ID')
    symbol = models.CharField(max_length=128, db_column='SYMBOL')  # e.g. C-BTC-90000-310125
    side = models.CharField(max_length=10, db_column='SIDE')  # 'sell' (we sell options as per FDD)
    size = models.IntegerField(db_column='SIZE')
    limit_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, db_column='LIMIT_PRICE')
    mark_price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True, db_column='MARK_PRICE')
    strike_price = models.DecimalField(max_digits=20, decimal_places=2, db_column='STRIKE_PRICE')
    delta = models.FloatField(db_column='DELTA')
    expiry_date = models.DateField(db_column='EXPIRY_DATE')
    created_at = models.DateTimeField(auto_now_add=True, db_column='CREATED_AT')
    updated_at = models.DateTimeField(auto_now=True, db_column='UPDATED_AT')
    remote_order_id = models.BigIntegerField(null=True, blank=True, db_column='REMOTE_ORDER_ID')
    active = models.BooleanField(default=True, db_column='ACTIVE')
    closed_at = models.DateTimeField(null=True, blank=True, db_column='CLOSED_AT', help_text="UTC timestamp when position was closed")
    
    # Strategy cycle tracking
    strategy_cycle_id = models.CharField(max_length=50, null=True, blank=True, db_column='STRATEGY_CYCLE_ID', help_text="Monthly cycle identifier (YYYY-MM)")
    is_initial_position = models.BooleanField(default=False, db_column='IS_INITIAL_POSITION', help_text="True if this was one of the initial two positions sold")

    class Meta:
        db_table = 'option_position'
        
    def __str__(self):
        return f"{self.symbol} {self.side} delta={self.delta}"



class InitialBalanceTracker(models.Model):
    """
    Track initial USD balance for each strategy cycle
    """
    cycle_id = models.CharField(max_length=50, unique=True, db_column='CYCLE_ID', help_text="Monthly cycle identifier (YYYY-MM)")
    initial_balance_usd = models.DecimalField(max_digits=20, decimal_places=8, db_column='INITIAL_BALANCE_USD', help_text="Initial USD balance when cycle started")
    initial_balance_inr = models.DecimalField(max_digits=20, decimal_places=2, db_column='INITIAL_BALANCE_INR', help_text="Initial INR equivalent balance")
    created_at = models.DateTimeField(auto_now_add=True, db_column='CREATED_AT')
    updated_at = models.DateTimeField(auto_now=True, db_column='UPDATED_AT')
    
    class Meta:
        db_table = 'initial_balance_tracker'
        
    def __str__(self):
        return f"{self.cycle_id}: Initial USD ${self.initial_balance_usd} (₹{self.initial_balance_inr})"
