from decimal import Decimal

from rest_framework import serializers

from .models import CartItem, Category, DiscountType, HomepageBanner, Product, ProductImage, PromoCode, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]


class PromoCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = [
            "id",
            "code",
            "discount_type",
            "value",
            "minimum_order_amount",
            "is_active",
            "starts_at",
            "ends_at",
        ]

    def validate_discount_type(self, value):
        if value not in DiscountType.values:
            raise serializers.ValidationError("Invalid discount type")
        return value


class HomepageBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomepageBanner
        fields = [
            "id",
            "title",
            "subtitle",
            "image_url",
            "cta_label",
            "cta_url",
            "sort_order",
            "is_active",
            "starts_at",
            "ends_at",
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image", "is_primary"]

    def get_image(self, obj) -> str:
        if not obj.image:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "price", "avg_rating", "in_stock", "stock_count", "category", "primary_image"]

    def to_representation(self, instance):
        if isinstance(instance, dict):
            return instance
        return super().to_representation(instance)

    def get_primary_image(self, obj) -> str | None:
        images = list(obj.images.all())
        primary = next((image for image in images if image.is_primary), images[0] if images else None)
        if not (primary and primary.image):
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(primary.image.url)
        return primary.image.url


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    user_has_purchased = serializers.SerializerMethodField()
    user_has_reviewed = serializers.SerializerMethodField()

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
            "reviews",
            "seller",
            "user_has_purchased",
            "user_has_reviewed",
        ]

    def get_reviews(self, obj):
        return ReviewSerializer(obj.reviews.select_related("user").order_by("-created_at"), many=True).data

    def get_seller(self, obj):
        profile = getattr(obj.seller, "seller_profile", None)
        return {
            "id": obj.seller_id,
            "name": obj.seller.name,
            "store_name": profile.store_name if profile else "",
        }

    def get_user_has_purchased(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        from orders.models import Order, OrderStatus
        return Order.objects.filter(
            user=request.user,
            items__product=obj
        ).exclude(status=OrderStatus.CANCELLED).exists()

    def get_user_has_reviewed(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        from products.models import Review
        return Review.objects.filter(product=obj, user=request.user).exists()


class ProductWriteSerializer(serializers.ModelSerializer):
    category_detail = CategorySerializer(source="category", read_only=True)

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
            "category_detail",
            "is_deleted",
        ]
        read_only_fields = ["id", "is_deleted", "category_detail"]


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "rating", "comment", "created_at", "user_name"]
        read_only_fields = ["id", "created_at", "product"]


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True, required=False)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "line_total"]
        read_only_fields = ["id", "product", "line_total"]

    def to_representation(self, instance):
        if isinstance(instance, dict):
            return instance
        return super().to_representation(instance)

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
