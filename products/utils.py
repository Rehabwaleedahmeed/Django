from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import Cart, CartItem, DiscountType, Product, PromoCode

SESSION_CART_KEY = "guest_cart"
MONEY_QUANTIZE = Decimal("0.01")
DEFAULT_TAX_RATE = Decimal("0.10")


def money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def get_guest_cart(session) -> dict:
    cart = session.get(SESSION_CART_KEY)
    if not isinstance(cart, dict):
        cart = {}
    items = cart.get("items")
    if not isinstance(items, list):
        items = []
    promo_code = cart.get("promo_code")
    return {"items": items, "promo_code": promo_code}


def set_guest_cart(session, cart_data: dict) -> None:
    session[SESSION_CART_KEY] = {
        "items": cart_data.get("items", []),
        "promo_code": cart_data.get("promo_code"),
    }
    session.modified = True


def clear_guest_cart(session) -> None:
    if SESSION_CART_KEY in session:
        del session[SESSION_CART_KEY]
        session.modified = True


def get_cart_subtotal(items) -> Decimal:
    subtotal = Decimal("0")
    for item in items:
        subtotal += money(item["quantity"]) * money(item["price"])
    return money(subtotal)


def apply_discount(subtotal: Decimal, promo_code: PromoCode | None) -> Decimal:
    if not promo_code:
        return money(0)
    if promo_code.discount_type == DiscountType.FLAT:
        return money(min(promo_code.value, subtotal))
    discount = subtotal * (promo_code.value / Decimal("100"))
    return money(min(discount, subtotal))


def validate_promo_code(promo_code: PromoCode, subtotal: Decimal) -> None:
    now = timezone.now()
    if not promo_code.is_active:
        raise ValueError("Promo code is inactive")
    if promo_code.starts_at and promo_code.starts_at > now:
        raise ValueError("Promo code is not active yet")
    if promo_code.ends_at and promo_code.ends_at < now:
        raise ValueError("Promo code has expired")
    if subtotal < promo_code.minimum_order_amount:
        raise ValueError("Cart does not meet the minimum order amount")


@transaction.atomic
def merge_guest_cart(request, user):
    guest_cart = get_guest_cart(request.session)
    if not guest_cart["items"]:
        return Cart.objects.get_or_create(user=user)[0]

    cart, _ = Cart.objects.get_or_create(user=user)
    product_ids = [item.get("product_id") for item in guest_cart["items"] if item.get("product_id")]
    products = Product.objects.filter(id__in=product_ids, is_deleted=False).in_bulk()

    for item in guest_cart["items"]:
        product_id = item.get("product_id")
        quantity = int(item.get("quantity") or 0)
        if not product_id or quantity <= 0:
            continue
        product = products.get(product_id)
        if not product or not product.in_stock or product.stock_count <= 0:
            continue

        available_quantity = min(quantity, product.stock_count)
        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": available_quantity})
        if not created:
            cart_item.quantity = min(cart_item.quantity + available_quantity, product.stock_count)
            cart_item.save(update_fields=["quantity", "updated_at"])

    promo_code_value = guest_cart.get("promo_code")
    if promo_code_value:
        promo_code = PromoCode.objects.filter(code__iexact=promo_code_value).first()
        if promo_code:
            subtotal = get_cart_subtotal(
                [
                    {"quantity": item.quantity, "price": item.product.price}
                    for item in cart.items.select_related("product")
                ]
            )
            try:
                validate_promo_code(promo_code, subtotal)
            except ValueError:
                pass
            else:
                cart.promo_code = promo_code
                cart.save(update_fields=["promo_code", "updated_at"])

    clear_guest_cart(request.session)
    return cart
