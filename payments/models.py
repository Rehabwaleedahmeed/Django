from django.conf import settings
from django.db import models

from orders.models import Order


class PaymentMethod(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    COD = "cod", "Cash on delivery"
    WALLET = "wallet", "Wallet"
    PAYPAL = "paypal", "PayPal"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REQUIRES_ACTION = "requires_action", "Requires action"


class Payment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    order = models.OneToOneField(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment")
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")
    intent_id = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["intent_id"], name="unique_payment_intent", condition=~models.Q(intent_id="")),
            models.UniqueConstraint(fields=["idempotency_key"], name="unique_payment_idempotency", condition=~models.Q(idempotency_key="")),
        ]

    def __str__(self) -> str:
        return f"Payment {self.id} {self.method}"


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Wallet {self.user_id}"


class WalletTransactionType(models.TextChoices):
    DEBIT = "debit", "Debit"
    CREDIT = "credit", "Credit"


class WalletTransaction(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="wallet_transactions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=WalletTransactionType.choices)
    reference = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"WalletTx {self.id} {self.transaction_type}"
