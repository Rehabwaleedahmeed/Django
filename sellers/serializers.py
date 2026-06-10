from django.db import transaction
from rest_framework import serializers

from orders.models import Order, OrderItem
from products.serializers import ProductListSerializer

from .models import ApprovalStatus, Earnings, SellerProfile


class SellerRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = ["store_name", "bio", "logo"]

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        if SellerProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError("Seller profile already exists")
        profile = SellerProfile.objects.create(user=user, status=ApprovalStatus.PENDING, **validated_data)
        if user.role != "seller":
            user.role = "seller"
            user.save(update_fields=["role"])
        return profile


class SellerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = SellerProfile
        fields = ["id", "email", "name", "store_name", "bio", "logo", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "email", "name", "status", "created_at", "updated_at"]


class AdminSellerProfileSerializer(SellerProfileSerializer):
    class Meta(SellerProfileSerializer.Meta):
        read_only_fields = ["id", "email", "name", "created_at", "updated_at"]


class SellerOrderItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "unit_price", "line_total"]


class SellerOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    buyer = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "status", "total", "created_at", "buyer", "items"]

    def get_items(self, obj):
        seller = self.context.get("seller")
        items = obj.items.filter(product__seller=seller)
        return SellerOrderItemSerializer(items, many=True).data

    def get_buyer(self, obj):
        if obj.user_id:
            return {"id": obj.user_id, "email": obj.user.email}
        return {"id": None, "email": obj.guest_email, "guest": True}


class EarningsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Earnings
        fields = ["total_sales", "total_orders", "updated_at"]
        read_only_fields = ["total_sales", "total_orders", "updated_at"]
