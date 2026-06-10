from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order


@receiver(post_save, sender=Order)
def handle_order_created(sender, instance, created, **kwargs) -> None:
    if not created:
        return
    send_mail(
        "Order confirmation",
        f"Your order {instance.id} has been placed.",
        settings.DEFAULT_FROM_EMAIL,
        [instance.user.email],
        fail_silently=False,
    )
