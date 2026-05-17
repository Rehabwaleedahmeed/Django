from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.models import Cart, Product
from products.permissions import IsSellerOrAdmin
from products.utils import DEFAULT_TAX_RATE, apply_discount, money
from users.models import Address

from .models import Order, OrderItem, OrderStatus, OrderStatusHistory, ShippingAddress
from .serializers import OrderCreateSerializer, OrderDetailSerializer, OrderStatusHistorySerializer
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

    @transaction.atomic
    def create(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = Cart.objects.select_related("promo_code").filter(user=request.user).first()
        if not cart:
            return Response({"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
        cart_items = list(cart.items.select_related("product").order_by("id"))
        if not cart_items:
            return Response({"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        product_ids = [item.product_id for item in cart_items]
        products = Product.objects.select_for_update().filter(id__in=product_ids, is_deleted=False).in_bulk()

        subtotal = money(0)
        for item in cart_items:
            product = products.get(item.product_id)
            if not product or not product.in_stock:
                return Response({"detail": f"Product {item.product_id} is unavailable"}, status=status.HTTP_400_BAD_REQUEST)
            if item.quantity > product.stock_count:
                return Response({"detail": f"Insufficient stock for {product.name}"}, status=status.HTTP_400_BAD_REQUEST)
            subtotal += money(product.price * item.quantity)

        discount = apply_discount(subtotal, cart.promo_code)
        tax = money((subtotal - discount) * DEFAULT_TAX_RATE)
        total = money(subtotal - discount + tax)

        order = Order.objects.create(
            user=request.user,
            promo_code=cart.promo_code,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            total=total,
        )

        shipping_data = serializer.validated_data.get("shipping_address")
        if not shipping_data:
            address = Address.objects.filter(user=request.user).first()
            if address:
                shipping_data = {
                    "line1": address.line1,
                    "line2": address.line2,
                    "city": address.city,
                    "state": address.state,
                    "postal_code": address.postal_code,
                    "country": address.country,
                }

        if shipping_data:
            ShippingAddress.objects.create(order=order, **shipping_data)

        items_to_create = []
        for item in cart_items:
            product = products[item.product_id]
            unit_price = money(product.price)
            line_total = money(unit_price * item.quantity)
            items_to_create.append(
                OrderItem(
                    order=order,
                    product=product,
                    quantity=item.quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )
        OrderItem.objects.bulk_create(items_to_create)
        OrderStatusHistory.objects.create(order=order, status=OrderStatus.PENDING, note="Order placed")

        cart.items.all().delete()
        cart.promo_code = None
        cart.save(update_fields=["promo_code", "updated_at"])

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
