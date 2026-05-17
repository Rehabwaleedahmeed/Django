from django.db import transaction

from products.models import Cart, Product
from products.utils import DEFAULT_TAX_RATE, apply_discount, money
from users.models import Address

from .models import Order, OrderItem, OrderStatus, OrderStatusHistory, ShippingAddress


def calculate_cart_totals(user, lock: bool = False):
    cart = Cart.objects.select_related("promo_code").filter(user=user).first()
    if not cart:
        raise ValueError("Cart is empty")
    cart_items = list(cart.items.select_related("product").order_by("id"))
    if not cart_items:
        raise ValueError("Cart is empty")

    product_ids = [item.product_id for item in cart_items]
    products_qs = Product.objects.filter(id__in=product_ids, is_deleted=False)
    if lock:
        products_qs = products_qs.select_for_update()
    products = products_qs.in_bulk()

    subtotal = money(0)
    for item in cart_items:
        product = products.get(item.product_id)
        if not product or not product.in_stock:
            raise ValueError(f"Product {item.product_id} is unavailable")
        if item.quantity > product.stock_count:
            raise ValueError(f"Insufficient stock for {product.name}")
        subtotal += money(product.price * item.quantity)

    discount = apply_discount(subtotal, cart.promo_code)
    tax = money((subtotal - discount) * DEFAULT_TAX_RATE)
    total = money(subtotal - discount + tax)
    return {
        "cart": cart,
        "items": cart_items,
        "products": products,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total": total,
    }


@transaction.atomic
def place_order_from_cart(user, shipping_data=None):
    totals = calculate_cart_totals(user, lock=True)
    cart = totals["cart"]
    cart_items = totals["items"]
    products = totals["products"]

    order = Order.objects.create(
        user=user,
        promo_code=cart.promo_code,
        status=OrderStatus.PENDING,
        subtotal=totals["subtotal"],
        discount=totals["discount"],
        tax=totals["tax"],
        total=totals["total"],
    )

    if not shipping_data:
        address = Address.objects.filter(user=user).first()
        if address:
            shipping_data = {
                "line1": address.line1,
                "line2": address.line2,
                "city": address.city,
                "state": address.state,
                "postal_code": address.postal_code,
                "country": address.country,
            }

    if shipping_data:
        ShippingAddress.objects.create(order=order, **shipping_data)

    items_to_create = []
    for item in cart_items:
        product = products[item.product_id]
        unit_price = money(product.price)
        line_total = money(unit_price * item.quantity)
        items_to_create.append(
            OrderItem(
                order=order,
                product=product,
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
    OrderItem.objects.bulk_create(items_to_create)
    OrderStatusHistory.objects.create(order=order, status=OrderStatus.PENDING, note="Order placed")

    cart.items.all().delete()
    cart.promo_code = None
    cart.save(update_fields=["promo_code", "updated_at"])

    return order
