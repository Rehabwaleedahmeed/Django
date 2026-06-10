from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .filters import ProductFilter
from .models import Cart, CartItem, Category, HomepageBanner, Product, PromoCode, Review
from .permissions import IsSellerOrAdmin, IsAdminOnly
from .serializers import (
    CartItemSerializer,
    CartSerializer,
    CartSummarySerializer,
    CategorySerializer,
    HomepageBannerSerializer,
    PromoCodeSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ReviewSerializer,
)
from .utils import DEFAULT_TAX_RATE, apply_discount, clear_guest_cart, get_cart_subtotal, get_guest_cart, money, set_guest_cart, validate_promo_code


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAdminOnly()]
        return [AllowAny()]


class PromoCodeAdminViewSet(viewsets.ModelViewSet):
    serializer_class = PromoCodeSerializer
    permission_classes = [IsAdminOnly]

    def get_queryset(self):
        return PromoCode.objects.all().order_by("code")


class HomepageBannerViewSet(viewsets.ModelViewSet):
    serializer_class = HomepageBannerSerializer
    ordering = ["sort_order", "-created_at"]

    def get_queryset(self):
        queryset = HomepageBanner.objects.all()
        if not self.request.user.is_authenticated or not self.request.user.is_staff:
            now = timezone.now()
            queryset = queryset.filter(is_active=True).filter(
                Q(starts_at__isnull=True) | Q(starts_at__lte=now),
                Q(ends_at__isnull=True) | Q(ends_at__gte=now),
            )
        return queryset.order_by("sort_order", "-created_at")

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsAdminOnly()]
        return [AllowAny()]


class ProductViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["price", "avg_rating"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Product.objects.filter(is_deleted=False)
            .select_related("category", "seller", "seller__seller_profile")
            .prefetch_related("images")
        )

    def get_serializer_class(self):
        if self.action in {"list"}:
            return ProductListSerializer
        if self.action in {"retrieve"}:
            return ProductDetailSerializer
        return ProductWriteSerializer

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSellerOrAdmin()]
        if self.action == "reviews":
            return [IsAuthenticated()]
        return [AllowAny()]

    def perform_create(self, serializer):
        product = serializer.save(seller=self.request.user)
        image_file = self.request.FILES.get("image")
        if image_file:
            from .models import ProductImage
            ProductImage.objects.create(product=product, image=image_file, is_primary=True)

    def perform_update(self, serializer):
        product = serializer.save()
        image_file = self.request.FILES.get("image")
        if image_file:
            from .models import ProductImage
            ProductImage.objects.filter(product=product).update(is_primary=False)
            ProductImage.objects.create(product=product, image=image_file, is_primary=True)

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])

    @action(detail=True, methods=["post", "delete"], permission_classes=[IsAuthenticated], url_path="reviews")
    def reviews(self, request, pk=None):
        product = self.get_object()
        if request.method.lower() == "delete":
            review = Review.objects.filter(product=product, user=request.user).first()
            if not review:
                return Response({"detail": "Review not found"}, status=status.HTTP_404_NOT_FOUND)
            review.delete()
            return Response({"detail": "Review deleted"})

        if request.user.role == "seller":
            return Response({"detail": "Sellers cannot submit reviews."}, status=status.HTTP_400_BAD_REQUEST)

        from orders.models import Order, OrderStatus
        has_purchased = Order.objects.filter(
            user=request.user,
            items__product=product
        ).exclude(status=OrderStatus.CANCELLED).exists()

        if not has_purchased:
            return Response(
                {"detail": "You can only review products you have purchased."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if Review.objects.filter(product=product, user=request.user).exists():
            return Response({"detail": "You have already reviewed this product."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        Review.objects.create(
            product=product,
            user=request.user,
            rating=serializer.validated_data["rating"],
            comment=serializer.validated_data.get("comment", ""),
        )
        return Response({"detail": "Review submitted"}, status=status.HTTP_201_CREATED)


class CartMixin:
    tax_rate = DEFAULT_TAX_RATE

    def get_user_cart(self):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        return cart

    def get_guest_items(self):
        guest_cart = get_guest_cart(self.request.session)
        product_ids = [item.get("product_id") for item in guest_cart["items"] if item.get("product_id")]
        products = Product.objects.filter(id__in=product_ids, is_deleted=False).select_related("category", "seller")
        product_map = {product.id: product for product in products}
        items = []
        for item in guest_cart["items"]:
            product_id = item.get("product_id")
            quantity = int(item.get("quantity") or 0)
            product = product_map.get(product_id)
            if not product or quantity <= 0:
                continue
            items.append(
                {
                    "id": product.id,
                    "product": ProductListSerializer(product, context={"request": self.request}).data,
                    "quantity": quantity,
                    "line_total": str(money(product.price * quantity)),
                    "price": product.price,
                }
            )
        return items, guest_cart.get("promo_code")

    def get_cart_data(self):
        if self.request.user.is_authenticated:
            cart = self.get_user_cart()
            items = cart.items.select_related("product", "product__category", "product__seller").order_by("id")
            items_data = CartItemSerializer(items, many=True, context={"request": self.request}).data
            promo_code = cart.promo_code.code if cart.promo_code else None
            subtotal = get_cart_subtotal(
                [{"quantity": item.quantity, "price": item.product.price} for item in items]
            )
            promo = cart.promo_code
        else:
            items_data, promo_code = self.get_guest_items()
            subtotal = get_cart_subtotal(items_data)
            promo = PromoCode.objects.filter(code__iexact=promo_code).first() if promo_code else None

        discount = apply_discount(subtotal, promo)
        tax = money((subtotal - discount) * self.tax_rate)
        total = money(subtotal - discount + tax)
        summary = {
            "item_count": sum(int(item["quantity"]) for item in items_data),
            "subtotal": subtotal,
            "discount": discount,
            "tax": tax,
            "total": total,
            "promo_code": promo.code if promo else None,
        }
        return {"items": items_data, "summary": summary, "promo_code": summary["promo_code"]}

    def build_response(self):
        payload = self.get_cart_data()
        serializer = CartSerializer(payload, context={"request": self.request})
        return Response(serializer.data)

    def get_product_and_quantity(self, request):
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity") or 1)
        if not product_id:
            raise ValueError("product_id required")
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        product = get_object_or_404(Product, id=product_id, is_deleted=False)
        if not product.in_stock or product.stock_count <= 0:
            raise ValueError("Product is out of stock")
        return product, quantity

    def serialize_guest_item(self, product, quantity):
        return {
            "id": product.id,
            "product": ProductListSerializer(product, context={"request": self.request}).data,
            "quantity": quantity,
            "line_total": str(money(product.price * quantity)),
            "price": product.price,
        }


class CartView(CartMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]

    def get(self, request):
        return self.build_response()

    def delete(self, request):
        if request.user.is_authenticated:
            cart = self.get_user_cart()
            cart.items.all().delete()
            cart.promo_code = None
            cart.save(update_fields=["promo_code", "updated_at"])
        else:
            clear_guest_cart(request.session)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemView(CartMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            product, quantity = self.get_product_and_quantity(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_authenticated:
            cart = self.get_user_cart()
            item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
            if not created:
                new_quantity = item.quantity + quantity
                if new_quantity > product.stock_count:
                    return Response({"detail": "Requested quantity exceeds stock"}, status=status.HTTP_400_BAD_REQUEST)
                item.quantity = new_quantity
                item.save(update_fields=["quantity", "updated_at"])
            else:
                item.refresh_from_db()
            serializer = CartItemSerializer(item, context={"request": self.request})
            return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        guest_cart = get_guest_cart(request.session)
        existing_item = next((item for item in guest_cart["items"] if item.get("product_id") == product.id), None)
        new_quantity = quantity if existing_item is None else int(existing_item["quantity"]) + quantity
        if new_quantity > product.stock_count:
            return Response({"detail": "Requested quantity exceeds stock"}, status=status.HTTP_400_BAD_REQUEST)
        if existing_item is None:
            guest_cart["items"].append({"product_id": product.id, "quantity": quantity})
        else:
            existing_item["quantity"] = new_quantity
        set_guest_cart(request.session, guest_cart)
        return Response(self.serialize_guest_item(product, new_quantity), status=status.HTTP_201_CREATED if existing_item is None else status.HTTP_200_OK)

    def patch(self, request, item_id=None):
        quantity = request.data.get("quantity")
        if quantity is None:
            return Response({"detail": "quantity required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 1:
            return Response({"detail": "quantity must be at least 1"}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_authenticated:
            cart = self.get_user_cart()
            item = get_object_or_404(CartItem, id=item_id, cart=cart)
            if quantity > item.product.stock_count:
                return Response({"detail": "Requested quantity exceeds stock"}, status=status.HTTP_400_BAD_REQUEST)
            item.quantity = quantity
            item.save(update_fields=["quantity", "updated_at"])
            return Response(CartItemSerializer(item, context={"request": self.request}).data)

        guest_cart = get_guest_cart(request.session)
        item = next((entry for entry in guest_cart["items"] if entry.get("product_id") == item_id), None)
        if not item:
            return Response({"detail": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
        product = get_object_or_404(Product, id=item_id, is_deleted=False)
        if quantity > product.stock_count:
            return Response({"detail": "Requested quantity exceeds stock"}, status=status.HTTP_400_BAD_REQUEST)
        item["quantity"] = quantity
        set_guest_cart(request.session, guest_cart)
        return Response(self.serialize_guest_item(product, quantity))

    def delete(self, request, item_id=None):
        if request.user.is_authenticated:
            cart = self.get_user_cart()
            item = get_object_or_404(CartItem, id=item_id, cart=cart)
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        guest_cart = get_guest_cart(request.session)
        new_items = [entry for entry in guest_cart["items"] if entry.get("product_id") != item_id]
        if len(new_items) == len(guest_cart["items"]):
            return Response({"detail": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
        guest_cart["items"] = new_items
        set_guest_cart(request.session, guest_cart)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromoCodeView(CartMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code") or request.data.get("promo_code")
        if not code:
            return Response({"detail": "code required"}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.is_authenticated:
            cart = self.get_user_cart()
            subtotal = get_cart_subtotal(
                [{"quantity": item.quantity, "price": item.product.price} for item in cart.items.select_related("product")]
            )
            promo_code = get_object_or_404(PromoCode, code__iexact=code)
            try:
                validate_promo_code(promo_code, subtotal)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            cart.promo_code = promo_code
            cart.save(update_fields=["promo_code", "updated_at"])
            return Response({"detail": "Promo code applied", "promo_code": promo_code.code})

        guest_cart = get_guest_cart(request.session)
        items, _ = self.get_guest_items()
        subtotal = get_cart_subtotal(items)
        promo_code = get_object_or_404(PromoCode, code__iexact=code)
        try:
            validate_promo_code(promo_code, subtotal)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        guest_cart["promo_code"] = promo_code.code
        set_guest_cart(request.session, guest_cart)
        return Response({"detail": "Promo code applied", "promo_code": promo_code.code})


class CartSummaryView(CartMixin, viewsets.ViewSet):
    permission_classes = [AllowAny]

    def get(self, request):
        payload = self.get_cart_data()
        serializer = CartSummarySerializer(payload["summary"])
        return Response(serializer.data)


