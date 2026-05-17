from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.permissions import IsSellerOrAdmin
from .models import Order, OrderStatus, OrderStatusHistory
from .serializers import OrderCreateSerializer, OrderDetailSerializer, OrderStatusHistorySerializer
from .services import place_order_from_cart
from .tasks import send_order_status_email


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderDetailSerializer(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id, user=request.user)
        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)

    def create(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order = place_order_from_cart(request.user, serializer.validated_data.get("shipping_address"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)

    def cancel(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.status != OrderStatus.PENDING:
            return Response({"detail": "Only pending orders can be cancelled"}, status=status.HTTP_400_BAD_REQUEST)
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        OrderStatusHistory.objects.create(order=order, status=OrderStatus.CANCELLED, note="Cancelled by user")
        send_order_status_email.delay(order.id, order.status)
        return Response(OrderDetailSerializer(order).data)


class OrderStatusView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "patch":
            return [IsSellerOrAdmin()]
        return [permission() for permission in self.permission_classes]

    def get(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id)
        user = request.user
        if not (user.is_staff or user.role in {"seller", "admin"} or order.user_id == user.id):
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        history = order.status_history.order_by("created_at")
        serializer = OrderStatusHistorySerializer(history, many=True)
        return Response(serializer.data)

    def patch(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id)
        new_status = request.data.get("status")
        if new_status not in OrderStatus.values:
            return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        allowed_transitions = {
            OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
            OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
            OrderStatus.PROCESSING: {OrderStatus.SHIPPED},
            OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
            OrderStatus.DELIVERED: set(),
            OrderStatus.CANCELLED: set(),
        }

        if new_status not in allowed_transitions.get(order.status, set()):
            return Response({"detail": "Invalid status transition"}, status=status.HTTP_400_BAD_REQUEST)

        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        OrderStatusHistory.objects.create(order=order, status=new_status, note="Status updated")
        send_order_status_email.delay(order.id, new_status)
        return Response(OrderDetailSerializer(order).data)
