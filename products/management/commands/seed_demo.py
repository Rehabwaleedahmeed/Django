from decimal import Decimal

from django.core.management.base import BaseCommand

from products.models import Category, Product
from sellers.models import ApprovalStatus, SellerProfile
from users.models import CustomUser


PRODUCTS = [
    ("Ceramic Pour-Over Set", "Kitchen", "Hand-finished stoneware for a slower morning ritual.", "68.00", 18),
    ("Linen Table Runner", "Home", "Washed European linen with a relaxed, natural drape.", "42.00", 24),
    ("Oak Bedside Lamp", "Lighting", "Warm ambient light in solid oak and opal glass.", "129.00", 9),
    ("Woven Market Tote", "Accessories", "A structured everyday carry woven from natural fibers.", "54.00", 31),
    ("Low Lounge Chair", "Furniture", "A generous, grounded chair designed for long reads.", "480.00", 5),
    ("Brass Desk Tray", "Workspace", "A quietly useful catch-all with a brushed finish.", "36.00", 40),
    ("Cotton Throw", "Home", "Soft, weighty cotton with a subtle woven texture.", "74.00", 16),
    ("Stoneware Vase", "Home", "An organic silhouette for stems or an empty shelf.", "58.00", 12),
]


class Command(BaseCommand):
    help = "Create a small repeatable catalog for local frontend development."

    def handle(self, *args, **options):
        seller, _ = CustomUser.objects.get_or_create(
            email="studio@example.com",
            defaults={"name": "North Studio", "role": CustomUser.Role.SELLER, "is_active": True, "email_verified": True},
        )
        SellerProfile.objects.update_or_create(
            user=seller,
            defaults={"store_name": "North Studio", "bio": "Useful objects for considered spaces.", "status": ApprovalStatus.APPROVED},
        )

        for name, category_name, description, price, stock in PRODUCTS:
            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"slug": category_name.lower().replace(" ", "-")},
            )
            Product.objects.update_or_create(
                seller=seller,
                name=name,
                defaults={
                    "category": category,
                    "description": description,
                    "price": Decimal(price),
                    "stock_count": stock,
                    "in_stock": stock > 0,
                },
            )
        self.stdout.write(self.style.SUCCESS("Demo catalog is ready."))
