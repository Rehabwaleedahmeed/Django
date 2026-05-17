from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order
from products.models import Product


@receiver(post_save, sender=Order)
def handle_order_created(sender, instance, created, **kwargs) -> None:
    if not created:
        return
    items = instance.items.select_related("product")
    for item in items:
        Product.objects.filter(id=item.product_id).update(stock_count=F("stock_count") - item.quantity)
        Product.objects.filter(id=item.product_id, stock_count__lte=0).update(in_stock=False)

    send_mail(
        "Order confirmation",
        f"Your order {instance.id} has been placed.",
        settings.DEFAULT_FROM_EMAIL,
        [instance.user.email],
        fail_silently=False,
    )
