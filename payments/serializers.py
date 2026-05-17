from rest_framework import serializers

from .models import Payment, Wallet


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "method", "status", "amount", "currency", "intent_id", "created_at"]
        read_only_fields = ["id", "created_at", "intent_id"]


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ["balance", "updated_at"]
        read_only_fields = ["balance", "updated_at"]
