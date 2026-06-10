from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CartItemView,
    CartSummaryView,
    CartView,
    CategoryViewSet,
    HomepageBannerViewSet,
    ProductViewSet,
    PromoCodeAdminViewSet,
    PromoCodeView,
)

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="products")
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"banners", HomepageBannerViewSet, basename="banners")
router.register(r"admin/promo-codes", PromoCodeAdminViewSet, basename="admin-promo-codes")

urlpatterns = [
	path("cart/", CartView.as_view({"get": "get", "delete": "delete"}), name="cart"),
	path("cart/items/", CartItemView.as_view({"post": "post"}), name="cart-items"),
	path("cart/items/<int:item_id>/", CartItemView.as_view({"patch": "patch", "delete": "delete"}), name="cart-item"),
	path("cart/promo/", PromoCodeView.as_view({"post": "post"}), name="cart-promo"),
	path("cart/summary/", CartSummaryView.as_view({"get": "get"}), name="cart-summary"),
] + router.urls
