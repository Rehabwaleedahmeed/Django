from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction

from .models import Wallet, WalletTransaction, WalletTransactionType


def stripe_create_intent(amount: Decimal, currency: str, idempotency_key: str | None, metadata: dict | None = None):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    params = {
        "amount": int(amount * Decimal("100")),
        "currency": currency,
        "metadata": metadata or {},
    }
    return stripe.PaymentIntent.create(**params, idempotency_key=idempotency_key)


def stripe_retrieve_intent(intent_id: str):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.PaymentIntent.retrieve(intent_id)


def verify_webhook_signature(payload: bytes, sig_header: str):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)


@transaction.atomic
def wallet_deduct(user, amount: Decimal, order=None, reference: str = ""):
    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
    if wallet.balance < amount:
        raise ValueError("Insufficient wallet balance")
    wallet.balance = wallet.balance - amount
    wallet.save(update_fields=["balance", "updated_at"])
    WalletTransaction.objects.create(
        wallet=wallet,
        order=order,
        amount=amount,
        transaction_type=WalletTransactionType.DEBIT,
        reference=reference,
    )
    return wallet
