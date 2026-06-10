from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem, OrderStatus, OrderStatusHistory
from orders.tasks import send_order_status_email
from orders.services import restore_order_stock
from products.models import Product
from products.permissions import IsAdminOnly
from products.serializers import ProductListSerializer, ProductWriteSerializer

from .models import ApprovalStatus, Earnings, SellerProfile
from .permissions import IsApprovedSeller
from .serializers import (
    AdminSellerProfileSerializer,
    SellerRegisterSerializer,
    SellerProfileSerializer,
    SellerOrderSerializer,
    EarningsSerializer,
    SellerReviewSerializer,
)


class SellerRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SellerRegisterSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        return Response(SellerProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class SellerProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_object_or_404(SellerProfile, user=request.user)
        return Response(SellerProfileSerializer(profile, context={"request": request}).data)

    def put(self, request):
        profile = get_object_or_404(SellerProfile, user=request.user)
        serializer = SellerProfileSerializer(profile, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SellerProductsView(APIView):
    permission_classes = [IsAuthenticated, IsApprovedSeller]

    def get(self, request):
        products = Product.objects.filter(seller=request.user, is_deleted=False).order_by("-created_at")
        serializer = ProductListSerializer(products, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save(seller=request.user)
        
        image_file = request.FILES.get("image")
        if image_file:
            from products.models import ProductImage
            ProductImage.objects.create(product=product, image=image_file, is_primary=True)
            
        return Response(ProductWriteSerializer(product).data, status=status.HTTP_201_CREATED)

    def patch(self, request, product_id=None):
        product = get_object_or_404(Product, id=product_id, seller=request.user, is_deleted=False)
        serializer = ProductWriteSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        image_file = request.FILES.get("image")
        if image_file:
            from products.models import ProductImage
            ProductImage.objects.filter(product=product).update(is_primary=False)
            ProductImage.objects.create(product=product, image=image_file, is_primary=True)
            
        return Response(serializer.data)

    def delete(self, request, product_id=None):
        product = get_object_or_404(Product, id=product_id, seller=request.user, is_deleted=False)
        product.is_deleted = True
        product.save(update_fields=["is_deleted"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SellerOrderView(APIView):
    permission_classes = [IsAuthenticated, IsApprovedSeller]

    def get(self, request):
        orders = (
            Order.objects.filter(items__product__seller=request.user)
            .distinct()
            .select_related("user")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )
        serializer = SellerOrderSerializer(orders, many=True, context={"seller": request.user, "request": request})
        return Response(serializer.data)

    def patch(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id)
        if not order.items.filter(product__seller=request.user).exists():
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
        OrderStatusHistory.objects.create(order=order, status=new_status, note="Status updated by seller")
        send_order_status_email.delay(order.id, new_status)
        return Response(SellerOrderSerializer(order, context={"seller": request.user, "request": request}).data)


class EarningsView(APIView):
    permission_classes = [IsAuthenticated, IsApprovedSeller]

    def get(self, request):
        valid_statuses = {
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        }
        totals = (
            OrderItem.objects.filter(product__seller=request.user, order__status__in=valid_statuses)
            .aggregate(total_sales=Sum("line_total"), total_orders=Count("order", distinct=True))
        )
        earnings, _ = Earnings.objects.get_or_create(seller=request.user)
        earnings.total_sales = totals.get("total_sales") or 0
        earnings.total_orders = totals.get("total_orders") or 0
        earnings.save(update_fields=["total_sales", "total_orders", "updated_at"])
        return Response(EarningsSerializer(earnings).data)


class SellerReviewsView(APIView):
    permission_classes = [IsAuthenticated, IsApprovedSeller]

    def get(self, request):
        from products.models import Review
        reviews = Review.objects.filter(product__seller=request.user).select_related("product", "user").order_by("-created_at")
        serializer = SellerReviewSerializer(reviews, many=True)
        return Response(serializer.data)


class AdminSellerViewSet(viewsets.ModelViewSet):
    serializer_class = AdminSellerProfileSerializer
    permission_classes = [IsAdminOnly]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return SellerProfile.objects.select_related("user").order_by("-created_at")

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.APPROVED
        profile.save(update_fields=["status", "updated_at"])
        user = profile.user
        user.role = "seller"
        user.is_active = True
        user.save(update_fields=["role", "is_active"])
        Earnings.objects.get_or_create(seller=user)
        return Response(self.get_serializer(profile).data)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        profile = self.get_object()
        profile.status = ApprovalStatus.SUSPENDED
        profile.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(profile).data)
