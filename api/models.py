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
    remote_order_id = models.BigIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'option_position'
        
    def __str__(self):
        return f"{self.symbol} {self.side} delta={self.delta}"
