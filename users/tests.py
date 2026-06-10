from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import CustomUser


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthenticationFlowTests(APITestCase):
    def test_register_sends_otp_then_verify_and_login(self):
        register = self.client.post(
            reverse("register"),
            {"email": "customer@example.com", "name": "Customer", "password": "strong-pass-123"},
            format="json",
        )
        self.assertEqual(register.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)

        user = CustomUser.objects.get(email="customer@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(len(user.email_otp), 6)
        self.assertIn(user.email_otp, mail.outbox[0].body)

        verify = self.client.post(
            reverse("verify_email"),
            {"email": user.email, "code": user.email_otp},
            format="json",
        )
        self.assertEqual(verify.status_code, 200)

        login = self.client.post(
            reverse("login"),
            {"email": user.email, "password": "strong-pass-123"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)
        self.assertIn("refresh", login.data)

    def test_inactive_login_requests_verification(self):
        user = CustomUser.objects.create_user(email="inactive@example.com", password="strong-pass-123")
        response = self.client.post(
            reverse("login"),
            {"email": user.email, "password": "strong-pass-123"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.data["verification_required"])
        self.assertEqual(response.data["email"], user.email)

    def test_resend_is_rate_limited(self):
        user = CustomUser.objects.create_user(email="inactive@example.com", password="strong-pass-123")
        first = self.client.post(reverse("resend_verification"), {"email": user.email}, format="json")
        second = self.client.post(reverse("resend_verification"), {"email": user.email}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_otp_attempts_are_limited(self):
        user = CustomUser.objects.create_user(email="inactive@example.com", password="strong-pass-123")
        self.client.post(reverse("resend_verification"), {"email": user.email}, format="json")
        for _ in range(5):
            response = self.client.post(
                reverse("verify_email"),
                {"email": user.email, "code": "000000"},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Too many incorrect attempts", response.data["detail"])
