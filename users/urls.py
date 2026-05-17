from django.urls import path

from .views import ProfileView, WishlistView

urlpatterns = [
    path("me/", ProfileView.as_view(), name="profile"),
    path("me/wishlist/", WishlistView.as_view(), name="wishlist"),
]
