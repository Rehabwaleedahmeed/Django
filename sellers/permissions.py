from rest_framework.permissions import BasePermission

from .models import ApprovalStatus, SellerProfile


class IsApprovedSeller(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        profile = SellerProfile.objects.filter(user=user).first()
        return bool(profile and profile.status == ApprovalStatus.APPROVED)
