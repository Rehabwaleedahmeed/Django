from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminUserViewSet, ProfileView, WishlistView

router = DefaultRouter()
router.register(r"admin/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("me/", ProfileView.as_view(), name="profile"),
    path("me/wishlist/", WishlistView.as_view(), name="wishlist"),
] + router.urls
