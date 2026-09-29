from rest_framework import serializers

from sales.models import Sale


def _money():
    return serializers.DecimalField(max_digits=16, decimal_places=2)


class DateRangeSerializer(serializers.Serializer):
    """Validates the optional ?start_date=&end_date= query parameters."""

    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def validate(self, attrs):
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if start and end and start > end:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs


class DashboardSerializer(serializers.Serializer):
    today_sales = _money()
    today_orders = serializers.IntegerField()
    total_products = serializers.IntegerField()
    low_stock_products = serializers.IntegerField()
    total_customers = serializers.IntegerField()
    total_revenue = _money()
    monthly_revenue = _money()


class SalesReportSerializer(serializers.Serializer):
    total_sales = _money()
    total_orders = serializers.IntegerField()
    total_tax = _money()
    total_discounts = _money()
    total_revenue = _money()
    average_order_value = _money()


class DailySalesSerializer(serializers.Serializer):
    date = serializers.DateField()
    orders = serializers.IntegerField()
    revenue = _money()


class MonthlySalesSerializer(serializers.Serializer):
    month = serializers.CharField()
    orders = serializers.IntegerField()
    revenue = _money()


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity_sold = serializers.IntegerField()
    revenue = _money()


class PaymentSummarySerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices)
    transactions = serializers.IntegerField()
    total_amount = _money()
