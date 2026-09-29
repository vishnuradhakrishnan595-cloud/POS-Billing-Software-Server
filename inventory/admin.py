from django.contrib import admin

from inventory.models import Brand, Category, Product, StockTransaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "sku", "barcode", "category", "brand", "selling_price",
        "stock_quantity", "minimum_stock", "is_active",
    )
    list_filter = ("is_active", "category", "brand", "unit")
    search_fields = ("name", "sku", "barcode")
    ordering = ("name",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "product", "transaction_type", "quantity",
        "previous_quantity", "new_quantity", "created_by",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = ("product__name", "product__sku", "reason")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
