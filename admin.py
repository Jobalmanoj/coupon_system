from django.contrib import admin
from .models import Coupon

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discountType', 'discountValue', 'startDate', 'endDate')
    search_fields = ('code',)
