from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .filters import ProductFilter
from .models import Category, Product, Review
from .permissions import IsSellerOrAdmin, IsAdminOnly
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ReviewSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer

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
        return Product.objects.filter(is_deleted=False).select_related("category", "seller").prefetch_related("images")

    def get_serializer_class(self):
        if self.action in {"list"}:
            return ProductListSerializer
        if self.action in {"retrieve"}:
            return ProductDetailSerializer
        return ProductWriteSerializer

    def get_permissions(self):
        if self.action in {"create", "update", "partial_update", "destroy"}:
            return [IsSellerOrAdmin()]
        return [AllowAny()]

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user)

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

        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        Review.objects.create(
            product=product,
            user=request.user,
            rating=serializer.validated_data["rating"],
            comment=serializer.validated_data.get("comment", ""),
        )
        return Response({"detail": "Review submitted"}, status=status.HTTP_201_CREATED)


