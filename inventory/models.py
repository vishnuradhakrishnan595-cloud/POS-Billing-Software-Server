from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


def money_field(**kwargs):
    return models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        **kwargs,
    )


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        PIECE = "PCS", "Piece"
        METER = "MTR", "Meter"
        KILOGRAM = "KG", "Kilogram"
        LITER = "LTR", "Liter"
        BOX = "BOX", "Box"
        PACK = "PACK", "Pack"

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, unique=True)
    barcode = models.CharField(max_length=64, unique=True, null=True, blank=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    description = models.TextField(blank=True)
    cost_price = money_field(default=Decimal("0.00"))
    selling_price = money_field()
    stock_quantity = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=5, choices=Unit.choices, default=Unit.PIECE)
    tax_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="product_name_idx"),
            models.Index(fields=["is_active", "category"], name="product_active_cat_idx"),
            models.Index(fields=["created_at"], name="product_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(selling_price__gte=0) & Q(cost_price__gte=0),
                name="product_prices_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.minimum_stock


class StockTransaction(models.Model):
    class TransactionType(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        SALE = "SALE", "Sale"
        RETURN = "RETURN", "Return"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        DAMAGE = "DAMAGE", "Damage"

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="stock_transactions"
    )
    transaction_type = models.CharField(max_length=12, choices=TransactionType.choices)
    quantity = models.IntegerField(help_text="Signed change applied to stock.")
    previous_quantity = models.PositiveIntegerField()
    new_quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="stock_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"], name="stocktx_created_idx"),
            models.Index(fields=["product", "created_at"], name="stocktx_product_idx"),
        ]

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} x {self.product_id}"
