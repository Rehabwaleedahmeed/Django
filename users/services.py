import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def send_verification_otp(user):
    user.email_otp = f"{secrets.randbelow(1_000_000):06d}"
    user.email_otp_sent_at = timezone.now()
    user.email_otp_attempts = 0
    user.save(update_fields=["email_otp", "email_otp_sent_at", "email_otp_attempts"])
    send_mail(
        "Your North & Co. verification code",
        f"Your verification code is {user.email_otp}. It expires in {settings.EMAIL_OTP_EXPIRY_MINUTES} minutes.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def verify_email_otp(user, code):
    if user.email_verified:
        return
    expires_at = user.email_otp_sent_at + timedelta(minutes=settings.EMAIL_OTP_EXPIRY_MINUTES) if user.email_otp_sent_at else None
    if not expires_at or timezone.now() > expires_at:
        raise ValueError("This verification code has expired. Request a new code.")
    if user.email_otp_attempts >= 5:
        raise ValueError("Too many incorrect attempts. Request a new verification code.")
    if not secrets.compare_digest(user.email_otp, code):
        user.email_otp_attempts += 1
        if user.email_otp_attempts >= 5:
            user.email_otp = ""
            user.save(update_fields=["email_otp", "email_otp_attempts"])
            raise ValueError("Too many incorrect attempts. Request a new verification code.")
        user.save(update_fields=["email_otp_attempts"])
        remaining = 5 - user.email_otp_attempts
        raise ValueError(f"That verification code is incorrect. {remaining} attempts remaining.")
    user.is_active = True
    user.email_verified = True
    user.email_otp = ""
    user.email_otp_attempts = 0
    user.save(update_fields=["is_active", "email_verified", "email_otp", "email_otp_attempts"])


def otp_resend_wait_seconds(user):
    if not user.email_otp_sent_at:
        return 0
    elapsed = (timezone.now() - user.email_otp_sent_at).total_seconds()
    return max(0, int(settings.EMAIL_OTP_RESEND_SECONDS - elapsed))
