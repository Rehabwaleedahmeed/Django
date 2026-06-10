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
    guest_email = serializers.EmailField(required=False, allow_blank=True)
    guest_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    guest_phone = serializers.CharField(required=False, allow_blank=True, max_length=40)


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shipping_address = ShippingAddressSerializer(read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    promo_code = serializers.SerializerMethodField()
    buyer = serializers.SerializerMethodField()

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
            "buyer",
            "created_at",
            "items",
            "shipping_address",
            "status_history",
        ]

    def get_promo_code(self, obj):
        return obj.promo_code.code if obj.promo_code else None

    def get_buyer(self, obj):
        if obj.user_id:
            return {"id": obj.user_id, "email": obj.user.email, "name": obj.user.name, "guest": False}
        return {"id": None, "email": obj.guest_email, "name": obj.guest_name, "phone": obj.guest_phone, "guest": True}
