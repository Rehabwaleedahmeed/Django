from django.conf import settings
from django.db import models
from cloudinary.models import CloudinaryField


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    SUSPENDED = "suspended", "Suspended"


class SellerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_profile")
    store_name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)
    logo = CloudinaryField("image", blank=True, null=True)
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"SellerProfile {self.user_id}"


class Earnings(models.Model):
    seller = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_earnings")
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Earnings {self.seller_id}"
