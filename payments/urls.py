from django.urls import path

from .views import CODView, PaymentStatusView, StripeConfirmView, StripeIntentView, StripeWebhookView, WalletPayView, WalletView

urlpatterns = [
    path("payments/intent/", StripeIntentView.as_view(), name="stripe-intent"),
    path("payments/confirm/", StripeConfirmView.as_view(), name="stripe-confirm"),
    path("payments/webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
    path("payments/<int:order_id>/", PaymentStatusView.as_view(), name="payment-status"),
    path("payments/cod/", CODView.as_view(), name="payment-cod"),
    path("wallet/", WalletView.as_view(), name="wallet"),
    path("wallet/pay/", WalletPayView.as_view(), name="wallet-pay"),
]
