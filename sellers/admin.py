from django.contrib import admin

from .models import Earnings, SellerProfile


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "store_name", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["store_name", "user__email"]


@admin.register(Earnings)
class EarningsAdmin(admin.ModelAdmin):
    list_display = ["seller", "total_sales", "total_orders", "updated_at"]
