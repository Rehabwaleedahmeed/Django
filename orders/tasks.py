from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import Order


@shared_task
def send_order_status_email(order_id: int, status: str) -> None:
    order = Order.objects.select_related("user").filter(id=order_id).first()
    if not order:
        return
    send_mail(
        "Order status update",
        f"Your order {order.id} is now {status}.",
        settings.DEFAULT_FROM_EMAIL,
        [order.user.email],
        fail_silently=False,
    )
