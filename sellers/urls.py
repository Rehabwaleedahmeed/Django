from django.urls import path

from .views import EarningsView, SellerOrderView, SellerProductsView, SellerProfileView, SellerRegisterView

urlpatterns = [
    path("register/", SellerRegisterView.as_view(), name="seller-register"),
    path("me/", SellerProfileView.as_view(), name="seller-profile"),
    path("me/products/", SellerProductsView.as_view(), name="seller-products"),
    path("me/orders/", SellerOrderView.as_view(), name="seller-orders"),
    path("me/orders/<int:order_id>/status/", SellerOrderView.as_view(), name="seller-order-status"),
    path("me/earnings/", EarningsView.as_view(), name="seller-earnings"),
]
