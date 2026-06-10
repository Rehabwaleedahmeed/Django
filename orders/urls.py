from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AdminOrderViewSet, OrderStatusView, OrderViewSet

router = DefaultRouter()
router.register(r"admin/orders", AdminOrderViewSet, basename="admin-orders")

urlpatterns = [
    path("orders/", OrderViewSet.as_view({"get": "list", "post": "create"}), name="orders"),
    path("orders/<int:order_id>/", OrderViewSet.as_view({"get": "retrieve"}), name="order-detail"),
    path("orders/<int:order_id>/cancel/", OrderViewSet.as_view({"patch": "cancel"}), name="order-cancel"),
    path("orders/<int:order_id>/tracking/", OrderStatusView.as_view({"get": "get"}), name="order-tracking"),
    path("orders/<int:order_id>/status/", OrderStatusView.as_view({"patch": "patch"}), name="order-status"),
] + router.urls
