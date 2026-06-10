from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminSellerViewSet, EarningsView, SellerOrderView, SellerProductsView, SellerProfileView, SellerRegisterView

router = DefaultRouter()
router.register(r"admin/sellers", AdminSellerViewSet, basename="admin-sellers")

urlpatterns = [
    path("register/", SellerRegisterView.as_view(), name="seller-register"),
    path("me/", SellerProfileView.as_view(), name="seller-profile"),
    path("me/products/", SellerProductsView.as_view(), name="seller-products"),
    path("me/products/<int:product_id>/", SellerProductsView.as_view(), name="seller-product-detail"),
    path("me/orders/", SellerOrderView.as_view(), name="seller-orders"),
    path("me/orders/<int:order_id>/status/", SellerOrderView.as_view(), name="seller-order-status"),
    path("me/earnings/", EarningsView.as_view(), name="seller-earnings"),
] + router.urls
