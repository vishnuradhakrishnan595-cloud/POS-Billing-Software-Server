from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminOrManager
from inventory.models import Product
from reports.serializers import (
    DailySalesSerializer,
    DashboardSerializer,
    DateRangeSerializer,
    MonthlySalesSerializer,
    PaymentSummarySerializer,
    SalesReportSerializer,
    TopProductSerializer,
)
from sales.models import Customer, Sale, SaleItem

ZERO = Decimal("0.00")


def total_of(field):
    return Coalesce(
        Sum(field),
        Value(ZERO),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def completed_sales():
    return Sale.objects.filter(sale_status=Sale.SaleStatus.COMPLETED)


def apply_dates(queryset, request, field="created_at"):
    serializer = DateRangeSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    start = serializer.validated_data.get("start_date")
    end = serializer.validated_data.get("end_date")
    if start:
        queryset = queryset.filter(**{f"{field}__date__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__date__lte": end})
    return queryset


class ReportView(APIView):
    """Base class: reports are restricted to ADMIN and MANAGER."""

    permission_classes = [IsAdminOrManager]


class DashboardView(ReportView):
    def get(self, request):
        today = timezone.localdate()
        sales = completed_sales()
        today_stats = sales.filter(created_at__date=today).aggregate(
            revenue=total_of("total_amount"), orders=Count("id")
        )
        monthly = sales.filter(
            created_at__date__year=today.year, created_at__date__month=today.month
        ).aggregate(revenue=total_of("total_amount"))
        data = {
            "today_sales": today_stats["revenue"],
            "today_orders": today_stats["orders"],
            "total_products": Product.objects.filter(is_active=True).count(),
            "low_stock_products": Product.objects.filter(
                stock_quantity__lte=F("minimum_stock")
            ).count(),
            "total_customers": Customer.objects.count(),
            "total_revenue": sales.aggregate(revenue=total_of("total_amount"))["revenue"],
            "monthly_revenue": monthly["revenue"],
        }
        return Response(DashboardSerializer(data).data)


class SalesReportView(ReportView):
    def get(self, request):
        sales = apply_dates(completed_sales(), request)
        agg = sales.aggregate(
            orders=Count("id"),
            subtotal=total_of("subtotal"),
            tax=total_of("tax_amount"),
            discounts=total_of("discount_amount"),
            revenue=total_of("total_amount"),
        )
        orders = agg["orders"]
        average = (agg["revenue"] / orders).quantize(Decimal("0.01")) if orders else ZERO
        data = {
            "total_sales": agg["subtotal"],
            "total_orders": orders,
            "total_tax": agg["tax"],
            "total_discounts": agg["discounts"],
            "total_revenue": agg["revenue"],
            "average_order_value": average,
        }
        return Response(SalesReportSerializer(data).data)


class DailySalesView(ReportView):
    def get(self, request):
        rows = (
            apply_dates(completed_sales(), request)
            .annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(orders=Count("id"), revenue=total_of("total_amount"))
            .order_by("date")
        )
        return Response(DailySalesSerializer(list(rows), many=True).data)


class MonthlySalesView(ReportView):
    def get(self, request):
        rows = (
            apply_dates(completed_sales(), request)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(orders=Count("id"), revenue=total_of("total_amount"))
            .order_by("month")
        )
        data = [
            {"month": r["month"].strftime("%Y-%m"), "orders": r["orders"], "revenue": r["revenue"]}
            for r in rows
        ]
        return Response(MonthlySalesSerializer(data, many=True).data)


class TopProductsView(ReportView):
    def get(self, request):
        items = SaleItem.objects.filter(sale__sale_status=Sale.SaleStatus.COMPLETED)
        items = apply_dates(items, request, field="sale__created_at")
        try:
            limit = min(max(int(request.query_params.get("limit", 10)), 1), 100)
        except ValueError:
            limit = 10
        rows = (
            items.values("product_id", "product__name")
            .annotate(quantity_sold=Sum("quantity"), revenue=total_of("total"))
            .order_by("-quantity_sold", "product_id")[:limit]
        )
        data = [
            {
                "product_id": r["product_id"],
                "product_name": r["product__name"],
                "quantity_sold": r["quantity_sold"],
                "revenue": r["revenue"],
            }
            for r in rows
        ]
        return Response(TopProductSerializer(data, many=True).data)


class PaymentSummaryView(ReportView):
    def get(self, request):
        rows = (
            apply_dates(completed_sales(), request)
            .values("payment_method")
            .annotate(transactions=Count("id"), total_amount=total_of("total_amount"))
        )
        by_method = {r["payment_method"]: r for r in rows}
        data = [
            {
                "payment_method": method,
                "transactions": by_method.get(method, {}).get("transactions", 0),
                "total_amount": by_method.get(method, {}).get("total_amount", ZERO),
            }
            for method, _label in Sale.PaymentMethod.choices
        ]
        return Response(PaymentSummarySerializer(data, many=True).data)
