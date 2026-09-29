from django.contrib import admin

from sales.models import Customer, Sale, SaleItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "city", "created_at")
    list_filter = ("city", "state")
    search_fields = ("name", "email", "phone")
    ordering = ("name",)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price", "discount", "tax", "total")
    can_delete = False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number", "customer", "cashier", "total_amount",
        "payment_method", "payment_status", "sale_status", "created_at",
    )
    list_filter = ("payment_method", "payment_status", "sale_status", "created_at")
    search_fields = ("invoice_number", "customer__name", "customer__phone", "cashier__username")
    ordering = ("-created_at",)
    inlines = [SaleItemInline]


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ("sale", "product", "quantity", "unit_price", "discount", "tax", "total")
    list_filter = ("created_at",)
    search_fields = ("sale__invoice_number", "product__name", "product__sku")
    ordering = ("-created_at",)
