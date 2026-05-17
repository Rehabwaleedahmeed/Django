from decimal import Decimal

from rest_framework import serializers

from .models import CartItem, Category, Product, ProductImage, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_primary"]


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "name", "price", "avg_rating", "in_stock", "stock_count", "category"]


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "price",
            "avg_rating",
            "in_stock",
            "stock_count",
            "category",
            "images",
        ]


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "price",
            "in_stock",
            "stock_count",
            "category",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "product", "rating", "comment", "created_at"]
        read_only_fields = ["id", "created_at", "product"]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True, required=False)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "line_total"]
        read_only_fields = ["id", "product", "line_total"]

    def get_line_total(self, obj) -> str:
        if isinstance(obj, dict):
            value = obj.get("line_total")
            if value is not None:
                return str(value)
            quantity = Decimal(obj.get("quantity") or 0)
            product = obj.get("product") or {}
            price = Decimal(str(product.get("price") or 0))
            return str(quantity * price)
        return str(Decimal(obj.quantity) * obj.product.price)


class CartSummarySerializer(serializers.Serializer):
    item_count = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    promo_code = serializers.CharField(allow_null=True, required=False)


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True)
    summary = CartSummarySerializer()
    promo_code = serializers.CharField(allow_null=True, required=False)
