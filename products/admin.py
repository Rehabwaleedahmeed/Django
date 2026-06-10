from django.contrib import admin

from .models import Category, HomepageBanner, Product, ProductImage, PromoCode, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name", "slug"]


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "in_stock", "stock_count", "avg_rating", "is_deleted"]
    list_filter = ["in_stock", "is_deleted", "category"]
    search_fields = ["name", "description"]
    inlines = [ProductImageInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["product", "user", "rating", "created_at"]
    list_filter = ["rating"]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "discount_type", "value", "minimum_order_amount", "is_active"]
    list_filter = ["discount_type", "is_active"]
    search_fields = ["code"]


@admin.register(HomepageBanner)
class HomepageBannerAdmin(admin.ModelAdmin):
    list_display = ["title", "sort_order", "is_active", "starts_at", "ends_at"]
    list_filter = ["is_active"]
    search_fields = ["title", "subtitle"]
