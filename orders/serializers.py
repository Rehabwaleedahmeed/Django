from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusHistory, ShippingAddress
from products.serializers import ProductListSerializer


class ShippingAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingAddress
        fields = ["line1", "line2", "city", "state", "postal_code", "country"]


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "unit_price", "line_total"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["status", "note", "created_at"]


class OrderCreateSerializer(serializers.Serializer):
    shipping_address = ShippingAddressSerializer(required=False)


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = ShippingAddressSerializer(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    promo_code = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "status",
            "subtotal",
            "discount",
            "tax",
            "total",
            "promo_code",
            "created_at",
            "items",
            "shipping_address",
            "status_history",
        ]

    def get_promo_code(self, obj):
        return obj.promo_code.code if obj.promo_code else None
