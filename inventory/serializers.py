from django.db import transaction
from rest_framework import serializers

from inventory.models import Brand, Category, Product, StockTransaction


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    brand_name = serializers.CharField(source="brand.name", read_only=True, default=None)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "barcode", "category", "category_name", "brand",
            "brand_name", "description", "cost_price", "selling_price", "stock_quantity",
            "minimum_stock", "unit", "tax_percentage", "is_active", "is_low_stock",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sku(self, value):
        return value.strip()

    def validate_barcode(self, value):
        value = (value or "").strip()
        return value or None

    def validate(self, attrs):
        if (
            self.instance is not None
            and "stock_quantity" in attrs
            and attrs["stock_quantity"] != self.instance.stock_quantity
        ):
            raise serializers.ValidationError(
                {"stock_quantity": "Use POST /api/inventory/stock/adjust/ to change stock."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        product = super().create(validated_data)
        if product.stock_quantity > 0:
            StockTransaction.objects.create(
                product=product,
                transaction_type=StockTransaction.TransactionType.PURCHASE,
                quantity=product.stock_quantity,
                previous_quantity=0,
                new_quantity=product.stock_quantity,
                reason="Opening stock",
                created_by=self.context["request"].user,
            )
        return product


class StockTransactionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )

    class Meta:
        model = StockTransaction
        fields = [
            "id", "product", "product_name", "transaction_type", "quantity",
            "previous_quantity", "new_quantity", "reason", "created_by",
            "created_by_name", "created_at",
        ]
        read_only_fields = fields


class StockAdjustmentSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField()
    transaction_type = serializers.ChoiceField(
        choices=[
            StockTransaction.TransactionType.PURCHASE,
            StockTransaction.TransactionType.RETURN,
            StockTransaction.TransactionType.ADJUSTMENT,
            StockTransaction.TransactionType.DAMAGE,
        ],
        required=False,
    )
    reason = serializers.CharField(max_length=255)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Quantity cannot be zero.")
        return value

    def validate(self, attrs):
        if "transaction_type" not in attrs:
            attrs["transaction_type"] = (
                StockTransaction.TransactionType.PURCHASE
                if attrs["quantity"] > 0
                else StockTransaction.TransactionType.ADJUSTMENT
            )
        return attrs
