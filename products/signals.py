from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.db.models import Avg

from .models import Review, Product
from .utils import merge_guest_cart


def update_product_rating(product_id: int) -> None:
    avg = Review.objects.filter(product_id=product_id).aggregate(avg=Avg("rating"))["avg"] or 0.0
    Product.objects.filter(id=product_id).update(avg_rating=avg)


@receiver(post_save, sender=Review)
def update_rating_on_save(sender, instance, **kwargs) -> None:
    update_product_rating(instance.product_id)


@receiver(post_delete, sender=Review)
def update_rating_on_delete(sender, instance, **kwargs) -> None:
    update_product_rating(instance.product_id)


@receiver(user_logged_in)
def merge_cart_on_login(sender, request, user, **kwargs) -> None:
    merge_guest_cart(request, user)
