from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from accounts.models import phone_validator
from inventory.models import Product, money_field


class Customer(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=12, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["phone"], name="customer_phone_idx"),
            models.Index(fields=["email"], name="customer_email_idx"),
            models.Index(fields=["name"], name="customer_name_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"


class Sale(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        UPI = "UPI", "UPI"
        BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
        OTHER = "OTHER", "Other"

    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        PENDING = "PENDING", "Pending"
        PARTIAL = "PARTIAL", "Partial"
        REFUNDED = "REFUNDED", "Refunded"

    class SaleStatus(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        REFUNDED = "REFUNDED", "Refunded"

    invoice_number = models.CharField(max_length=32, unique=True)
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="sales"
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales"
    )
    subtotal = money_field(default=Decimal("0.00"))
    tax_amount = money_field(default=Decimal("0.00"))
    discount_amount = money_field(default=Decimal("0.00"))
    total_amount = money_field(default=Decimal("0.00"))
    payment_method = models.CharField(
        max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    payment_status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PAID
    )
    sale_status = models.CharField(
        max_length=10, choices=SaleStatus.choices, default=SaleStatus.COMPLETED
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_at"], name="sale_created_idx"),
            models.Index(fields=["sale_status", "created_at"], name="sale_status_created_idx"),
            models.Index(fields=["payment_method"], name="sale_payment_method_idx"),
        ]

    def __str__(self):
        return self.invoice_number


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = money_field()
    discount = money_field(default=Decimal("0.00"))
    tax = money_field(default=Decimal("0.00"))
    total = money_field()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="saleitem_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_id} ({self.sale_id})"
