from django.db import models

class Coupon(models.Model):
    CODE_MAX = 64

    code = models.CharField(max_length=CODE_MAX, unique=True)
    description = models.CharField(max_length=255, blank=True)
    discountType = models.CharField(max_length=10)  # 'FLAT' or 'PERCENT'
    discountValue = models.FloatField()
    maxDiscountAmount = models.FloatField(null=True, blank=True)
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    usageLimitPerUser = models.IntegerField(null=True, blank=True)
    eligibility = models.JSONField(default=dict, blank=True)  # follows assignment schema

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code
from django.conf import settings

class CouponUsage(models.Model):
    coupon = models.ForeignKey("Coupon", on_delete=models.CASCADE, related_name="usages")
    user_id = models.CharField(max_length=128, db_index=True)  # stores the userId string from API payload
    used_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} used {self.coupon.code} at {self.used_at}"

