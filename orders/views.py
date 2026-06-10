from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from products.permissions import IsSellerOrAdmin
from products.permissions import IsAdminOnly
from .models import Order, OrderStatus, OrderStatusHistory
from .serializers import OrderCreateSerializer, OrderDetailSerializer, OrderStatusHistorySerializer
from .services import place_guest_order_from_cart, place_order_from_cart, restore_order_stock
from .tasks import send_order_status_email


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    def list(self, request):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        orders = Order.objects.filter(user=request.user).order_by("-created_at")
        serializer = OrderDetailSerializer(orders, many=True)
        return Response(serializer.data)

    def retrieve(self, request, order_id=None):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        order = get_object_or_404(Order, id=order_id, user=request.user)
        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)

    def create(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            if request.user.is_authenticated:
                order = place_order_from_cart(request.user, serializer.validated_data.get("shipping_address"))
            else:
                if not serializer.validated_data.get("guest_email"):
                    return Response({"guest_email": ["This field is required for guest checkout."]}, status=status.HTTP_400_BAD_REQUEST)
                order = place_guest_order_from_cart(request.session, serializer.validated_data, serializer.validated_data.get("shipping_address"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderDetailSerializer(order).data, status=status.HTTP_201_CREATED)

    def cancel(self, request, order_id=None):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.status != OrderStatus.PENDING:
            return Response({"detail": "Only pending orders can be cancelled"}, status=status.HTTP_400_BAD_REQUEST)
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        restore_order_stock(order)
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
        if not request.user.is_staff and not order.items.filter(product__seller=request.user).exists():
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
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
        if new_status == OrderStatus.CANCELLED:
            restore_order_stock(order)
        OrderStatusHistory.objects.create(order=order, status=new_status, note="Status updated")
        send_order_status_email.delay(order.id, new_status)
        return Response(OrderDetailSerializer(order).data)


class AdminOrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderDetailSerializer
    permission_classes = [IsAdminOnly]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return (
            Order.objects.select_related("user", "promo_code", "shipping_address")
            .prefetch_related("items__product__category", "status_history")
            .order_by("-created_at")
        )

    def partial_update(self, request, *args, **kwargs):
        order = self.get_object()
        new_status = request.data.get("status")
        if new_status:
            if new_status not in OrderStatus.values:
                return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)
            if order.status != new_status:
                order.status = new_status
                order.save(update_fields=["status", "updated_at"])
                if new_status == OrderStatus.CANCELLED:
                    restore_order_stock(order)
                OrderStatusHistory.objects.create(order=order, status=new_status, note="Status updated by admin")
                send_order_status_email.delay(order.id, new_status)
        shipping_data = request.data.get("shipping_address")
        if shipping_data:
            from .models import ShippingAddress

            ShippingAddress.objects.update_or_create(order=order, defaults=shipping_data)
        return Response(self.get_serializer(order).data)
