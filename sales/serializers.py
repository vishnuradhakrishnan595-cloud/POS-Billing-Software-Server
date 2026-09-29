from decimal import Decimal

from rest_framework import serializers

from accounts.models import User
from inventory.models import Product
from sales.models import Customer, Sale, SaleItem
from sales import services


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "email", "phone", "address", "city", "state",
            "postal_code", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and not user.is_superuser and user.role == User.Role.STAFF:
            return {key: data[key] for key in ("id", "name", "city")}  # limited view
        return data


class SaleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id", "product", "product_name", "product_sku", "quantity",
            "unit_price", "discount", "tax", "total", "created_at",
        ]
        read_only_fields = fields


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    cashier_name = serializers.CharField(source="cashier.username", read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "invoice_number", "customer", "customer_name", "cashier", "cashier_name",
            "subtotal", "tax_amount", "discount_amount", "total_amount", "payment_method",
            "payment_status", "sale_status", "notes", "items", "created_at", "updated_at",
        ]
        read_only_fields = fields


class SaleItemInputSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1)
    discount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0")
    )


class SaleCreateSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices)
    payment_status = serializers.ChoiceField(
        choices=Sale.PaymentStatus.choices, default=Sale.PaymentStatus.PAID
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0")
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = SaleItemInputSerializer(many=True, allow_empty=False)

    def validate_payment_status(self, value):
        if value == Sale.PaymentStatus.REFUNDED:
            raise serializers.ValidationError("A new sale cannot be created as refunded.")
        return value

    def validate_items(self, items):
        seen = set()
        for item in items:
            pid = item["product"].pk
            if pid in seen:
                raise serializers.ValidationError(
                    "Each product may appear only once; combine the quantities."
                )
            seen.add(pid)
        return items

    def create(self, validated_data):
        return services.create_sale(
            cashier=self.context["request"].user,
            customer=validated_data.get("customer"),
            payment_method=validated_data["payment_method"],
            payment_status=validated_data["payment_status"],
            discount_amount=validated_data["discount_amount"],
            notes=validated_data["notes"],
            items=validated_data["items"],
        )


class SaleUpdateSerializer(serializers.Serializer):
    sale_status = serializers.ChoiceField(choices=Sale.SaleStatus.choices, required=False)
    payment_status = serializers.ChoiceField(choices=Sale.PaymentStatus.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        return services.update_sale(
            sale=instance, user=self.context["request"].user, **validated_data
        )
