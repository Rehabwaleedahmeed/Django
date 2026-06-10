from django.db import transaction
from django.db.models import F

from products.models import Cart, Product, PromoCode
from products.utils import DEFAULT_TAX_RATE, apply_discount, clear_guest_cart, get_guest_cart, money, validate_promo_code
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


def calculate_guest_cart_totals(session, lock: bool = False):
    guest_cart = get_guest_cart(session)
    raw_items = guest_cart.get("items", [])
    if not raw_items:
        raise ValueError("Cart is empty")

    product_ids = [item.get("product_id") for item in raw_items if item.get("product_id")]
    products_qs = Product.objects.filter(id__in=product_ids, is_deleted=False)
    if lock:
        products_qs = products_qs.select_for_update()
    products = products_qs.in_bulk()

    items = []
    subtotal = money(0)
    for item in raw_items:
        product_id = item.get("product_id")
        quantity = int(item.get("quantity") or 0)
        product = products.get(product_id)
        if not product or not product.in_stock:
            raise ValueError(f"Product {product_id} is unavailable")
        if quantity < 1:
            continue
        if quantity > product.stock_count:
            raise ValueError(f"Insufficient stock for {product.name}")
        subtotal += money(product.price * quantity)
        items.append({"product": product, "quantity": quantity})

    if not items:
        raise ValueError("Cart is empty")

    promo = PromoCode.objects.filter(code__iexact=guest_cart.get("promo_code")).first() if guest_cart.get("promo_code") else None
    if promo:
        validate_promo_code(promo, subtotal)
    discount = apply_discount(subtotal, promo)
    tax = money((subtotal - discount) * DEFAULT_TAX_RATE)
    total = money(subtotal - discount + tax)
    return {
        "items": items,
        "promo_code": promo,
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
    for item in cart_items:
        Product.objects.filter(id=item.product_id).update(stock_count=F("stock_count") - item.quantity)
        Product.objects.filter(id=item.product_id, stock_count__lte=0).update(in_stock=False)
    OrderStatusHistory.objects.create(order=order, status=OrderStatus.PENDING, note="Order placed")

    cart.items.all().delete()
    cart.promo_code = None
    cart.save(update_fields=["promo_code", "updated_at"])

    return order


@transaction.atomic
def place_guest_order_from_cart(session, guest_data, shipping_data=None):
    totals = calculate_guest_cart_totals(session, lock=True)
    order = Order.objects.create(
        user=None,
        guest_email=guest_data.get("guest_email", ""),
        guest_name=guest_data.get("guest_name", ""),
        guest_phone=guest_data.get("guest_phone", ""),
        promo_code=totals["promo_code"],
        status=OrderStatus.PENDING,
        subtotal=totals["subtotal"],
        discount=totals["discount"],
        tax=totals["tax"],
        total=totals["total"],
    )

    if shipping_data:
        ShippingAddress.objects.create(order=order, **shipping_data)

    items_to_create = []
    for item in totals["items"]:
        product = item["product"]
        quantity = item["quantity"]
        unit_price = money(product.price)
        line_total = money(unit_price * quantity)
        items_to_create.append(
            OrderItem(order=order, product=product, quantity=quantity, unit_price=unit_price, line_total=line_total)
        )
    OrderItem.objects.bulk_create(items_to_create)
    for item in totals["items"]:
        Product.objects.filter(id=item["product"].id).update(stock_count=F("stock_count") - item["quantity"])
        Product.objects.filter(id=item["product"].id, stock_count__lte=0).update(in_stock=False)
    OrderStatusHistory.objects.create(order=order, status=OrderStatus.PENDING, note="Guest order placed")
    clear_guest_cart(session)
    return order


@transaction.atomic
def restore_order_stock(order):
    items = order.items.select_related("product").select_for_update()
    for item in items:
        Product.objects.filter(id=item.product_id).update(
            stock_count=F("stock_count") + item.quantity,
            in_stock=True,
        )
