from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Address, CustomUser, Wishlist
from products.models import Product
from products.serializers import ProductListSerializer


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["line1", "line2", "city", "state", "postal_code", "country"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(
        choices=[(CustomUser.Role.CUSTOMER, "Customer"), (CustomUser.Role.SELLER, "Seller")],
        default=CustomUser.Role.CUSTOMER
    )

    class Meta:
        model = CustomUser
        fields = ["email", "password", "name", "role"]

    def create(self, validated_data):
        role = validated_data.pop("role", CustomUser.Role.CUSTOMER)
        user = CustomUser.objects.create_user(role=role, **validated_data)
        return user

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_email(self, value):
        existing = CustomUser.objects.filter(email__iexact=value).first()
        if existing and not existing.email_verified:
            raise serializers.ValidationError("This account is waiting for verification. Sign in to request a new code.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = CustomUser.objects.normalize_email(attrs.get("email"))
        user = CustomUser.objects.filter(email__iexact=email).first()
        if not user or not user.check_password(attrs.get("password")):
            raise serializers.ValidationError("Invalid email or password")
        if user.is_deleted:
            raise AuthenticationFailed({"detail": "This account has been removed."})
        if not user.is_active:
            raise AuthenticationFailed(
                {"detail": "Verify your email before signing in.", "verification_required": True, "email": user.email}
            )
        attrs["user"] = user
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    address = AddressSerializer(required=False)

    class Meta:
        model = CustomUser
        fields = ["id", "email", "name", "avatar", "role", "is_staff", "address"]
        read_only_fields = ["id", "email", "role", "is_staff"]

    def update(self, instance, validated_data):
        address_data = validated_data.pop("address", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()

        if address_data is not None:
            Address.objects.update_or_create(user=instance, defaults=address_data)
        return instance


class AdminUserSerializer(serializers.ModelSerializer):
    seller_status = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "name",
            "role",
            "is_active",
            "is_deleted",
            "is_staff",
            "email_verified",
            "date_joined",
            "seller_status",
        ]
        read_only_fields = ["id", "email", "date_joined", "seller_status"]

    def get_seller_status(self, obj):
        profile = getattr(obj, "seller_profile", None)
        return profile.status if profile else None


class WishlistSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = Wishlist
        fields = ["id", "product_id", "product", "created_at"]

    def get_product(self, obj):
        product = (
            Product.objects.filter(id=obj.product_id, is_deleted=False)
            .select_related("category")
            .prefetch_related("images")
            .first()
        )
        return ProductListSerializer(product).data if product else None


class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        try:
            uid = urlsafe_base64_decode(attrs["uid"]).decode()
            user = CustomUser.objects.get(pk=uid)
        except (CustomUser.DoesNotExist, ValueError, TypeError):
            raise serializers.ValidationError("Invalid reset link")
        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid reset link")
        validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs


class EmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the six-digit verification code."})


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


def build_token_pair(user: CustomUser) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
