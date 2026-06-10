from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser, Wishlist
from .permissions import IsOwner
from .serializers import (
    AdminUserSerializer,
    RegisterSerializer,
    LoginSerializer,
    ProfileSerializer,
    WishlistSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    EmailVerificationSerializer,
    ResendVerificationSerializer,
    build_token_pair,
)
from .services import otp_resend_wait_seconds, send_verification_otp, verify_email_otp
from products.utils import merge_guest_cart
from products.models import Product


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save(is_active=False)
        try:
            send_verification_otp(user)
        except Exception:
            user.delete()
            return Response(
                {"detail": "We could not send the verification code. Check the email settings and try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Verification code sent", "email": user.email}, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = CustomUser.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if not user:
            return Response({"detail": "No account was found for this email."}, status=status.HTTP_404_NOT_FOUND)
        try:
            verify_email_otp(user, serializer.validated_data["code"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Email verified. You can now sign in."})


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = CustomUser.objects.filter(email__iexact=serializer.validated_data["email"]).first()
        if not user:
            return Response({"detail": "No account was found for this email."}, status=status.HTTP_404_NOT_FOUND)
        if user.email_verified:
            return Response({"detail": "This email is already verified."}, status=status.HTTP_400_BAD_REQUEST)
        wait_seconds = otp_resend_wait_seconds(user)
        if wait_seconds:
            return Response(
                {"detail": f"Please wait {wait_seconds} seconds before requesting another code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            send_verification_otp(user)
        except Exception:
            return Response(
                {"detail": "We could not send a new code. Check the email settings and try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "A new verification code was sent."})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        merge_guest_cart(request, user)
        tokens = build_token_pair(user)
        return Response(tokens)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logged out"})


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            return Response({"access": str(token.access_token)})
        except Exception:
            return Response({"detail": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = CustomUser.objects.filter(email=email).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
            send_mail(
                "Reset your password",
                f"Click to reset: {reset_url}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        return Response({"detail": "If the email exists, a reset link was sent"})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password reset successful"})


class ProfileView(RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = Wishlist.objects.filter(user=request.user).order_by("-created_at")
        serializer = WishlistSerializer(items, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        product_id = request.data.get("product_id")
        if not product_id:
            return Response({"detail": "product_id required"}, status=status.HTTP_400_BAD_REQUEST)
        if not Product.objects.filter(id=product_id, is_deleted=False).exists():
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        Wishlist.objects.get_or_create(user=request.user, product_id=product_id)
        return Response({"detail": "Added"}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        product_id = request.data.get("product_id") or request.query_params.get("product_id")
        if not product_id:
            return Response({"detail": "product_id required"}, status=status.HTTP_400_BAD_REQUEST)
        Wishlist.objects.filter(user=request.user, product_id=product_id).delete()
        return Response({"detail": "Removed"})


class AdminUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if not self.request.user.is_staff:
            return CustomUser.objects.none()
        return CustomUser.objects.select_related("seller_profile").order_by("-date_joined")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user.is_staff:
            self.permission_denied(request)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.is_deleted = False
        user.save(update_fields=["is_active", "is_deleted"])
        return Response(self.get_serializer(user).data)

    @action(detail=True, methods=["post"])
    def restrict(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(self.get_serializer(user).data)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.is_deleted = True
        instance.save(update_fields=["is_active", "is_deleted"])
