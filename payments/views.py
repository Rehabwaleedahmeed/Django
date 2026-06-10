from decimal import Decimal

from django.http import HttpRequest
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from orders.services import calculate_cart_totals, place_order_from_cart

from .models import Payment, PaymentMethod, PaymentStatus, Wallet
from .serializers import PaymentSerializer, WalletSerializer
from .services import stripe_create_intent, stripe_retrieve_intent, verify_webhook_signature, wallet_deduct


class StripeIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        currency = request.data.get("currency") or "usd"
        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get("idempotency_key")
        try:
            totals = calculate_cart_totals(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        intent = stripe_create_intent(totals["total"], currency, idempotency_key, {"user_id": request.user.id})

        payment, _ = Payment.objects.get_or_create(
            user=request.user,
            intent_id=intent.id,
            defaults={
                "method": PaymentMethod.STRIPE,
                "status": PaymentStatus.PENDING,
                "amount": totals["total"],
                "currency": currency,
                "idempotency_key": idempotency_key or "",
            },
        )

        return Response({"client_secret": intent.client_secret, "payment_id": payment.id})


class StripeConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        intent_id = request.data.get("intent_id")
        if not intent_id:
            return Response({"detail": "intent_id required"}, status=status.HTTP_400_BAD_REQUEST)

        payment = Payment.objects.filter(user=request.user, intent_id=intent_id).first()
        if payment and payment.order:
            return Response({"detail": "Order already created", "order_id": payment.order_id})

        try:
            totals = calculate_cart_totals(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        intent = stripe_retrieve_intent(intent_id)
        if intent.status not in {"succeeded", "requires_capture"}:
            return Response({"detail": "Payment not completed"}, status=status.HTTP_400_BAD_REQUEST)
        if intent.metadata and str(intent.metadata.get("user_id")) != str(request.user.id):
            return Response({"detail": "Payment does not belong to user"}, status=status.HTTP_400_BAD_REQUEST)
        if intent.currency != (request.data.get("currency") or "usd"):
            return Response({"detail": "Payment currency mismatch"}, status=status.HTTP_400_BAD_REQUEST)
        expected_amount = int(totals["total"] * Decimal("100"))
        if intent.amount != expected_amount:
            return Response({"detail": "Payment amount mismatch"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = place_order_from_cart(request.user, request.data.get("shipping_address"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not payment:
            payment = Payment.objects.create(
                user=request.user,
                order=order,
                method=PaymentMethod.STRIPE,
                status=PaymentStatus.SUCCEEDED,
                amount=totals["total"],
                currency=request.data.get("currency") or "usd",
                intent_id=intent_id,
            )
        else:
            payment.order = order
            payment.status = PaymentStatus.SUCCEEDED
            payment.amount = totals["total"]
            payment.save(update_fields=["order", "status", "amount", "updated_at"])

        return Response({"detail": "Payment confirmed", "order_id": order.id})


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: HttpRequest):
        payload = request.body
        sig_header = request.headers.get("Stripe-Signature", "")
        try:
            event = verify_webhook_signature(payload, sig_header)
        except Exception:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event["type"] == "payment_intent.succeeded":
            intent = event["data"]["object"]
            Payment.objects.filter(intent_id=intent.get("id")).update(status=PaymentStatus.SUCCEEDED)
        if event["type"] == "payment_intent.payment_failed":
            intent = event["data"]["object"]
            Payment.objects.filter(intent_id=intent.get("id")).update(status=PaymentStatus.FAILED)

        return Response(status=status.HTTP_200_OK)


class PaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id=None):
        order = get_object_or_404(Order, id=order_id)
        if order.user_id != request.user.id and not request.user.is_staff:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        payment = Payment.objects.filter(order=order).first()
        if not payment:
            return Response({"detail": "Payment not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)


class CODView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            order = place_order_from_cart(request.user, request.data.get("shipping_address"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        Payment.objects.create(
            user=request.user,
            order=order,
            method=PaymentMethod.COD,
            status=PaymentStatus.PENDING,
            amount=order.total,
            currency="usd",
        )
        return Response({"detail": "COD order created", "order_id": order.id}, status=status.HTTP_201_CREATED)


class WalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return Response(WalletSerializer(wallet).data)

    def post(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        amount = Decimal(str(request.data.get("amount") or "100.00"))
        wallet.balance += amount
        wallet.save(update_fields=["balance", "updated_at"])
        return Response(WalletSerializer(wallet).data)


class WalletPayView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            with transaction.atomic():
                totals = calculate_cart_totals(request.user, lock=True)
                wallet = Wallet.objects.select_for_update().filter(user=request.user).first()
                if not wallet or wallet.balance < totals["total"]:
                    raise ValueError("Insufficient wallet balance")
                order = place_order_from_cart(request.user, request.data.get("shipping_address"))
                wallet_deduct(request.user, order.total, order=order, reference=f"order-{order.id}")
                Payment.objects.create(
                    user=request.user,
                    order=order,
                    method=PaymentMethod.WALLET,
                    status=PaymentStatus.SUCCEEDED,
                    amount=order.total,
                    currency="usd",
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Wallet payment completed", "order_id": order.id}, status=status.HTTP_201_CREATED)
