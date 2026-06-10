from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsSellerOrAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        profile = getattr(user, "seller_profile", None)
        return bool(user.role == "seller" and profile and profile.status == "approved")

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_staff or getattr(obj, "seller_id", None) == request.user.id)


class IsAdminOnly(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_staff)


class IsReviewOwner(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        return obj.user == request.user
