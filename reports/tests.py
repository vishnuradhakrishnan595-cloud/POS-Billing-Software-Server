from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.tests import auth_client, make_user
from inventory.models import Product
from sales import services
from sales.models import Customer


class ReportTests(TestCase):
    def setUp(self):
        self.mgr = make_user("MANAGER", "mgr")
        self.client = auth_client(self.mgr)
        self.cashier = make_user("CASHIER", "cash")
        self.a = Product.objects.create(
            name="Shirt", sku="A", selling_price=Decimal("100.00"),
            tax_percentage=Decimal("10.00"), stock_quantity=100, minimum_stock=5,
        )
        self.b = Product.objects.create(
            name="Trousers", sku="B", selling_price=Decimal("200.00"),
            tax_percentage=Decimal("0.00"), stock_quantity=2, minimum_stock=5,  # low stock
        )
        Customer.objects.create(name="Asha", phone="9876543210")
        # Sale 1: 2 x A -> subtotal 200, tax 20, total 220 (CASH)
        self.s1 = self._sale("CASH", [{"product": self.a, "quantity": 2}])
        # Sale 2: 1 x A + 1 x B, discount 30 -> subtotal 300, tax 10, total 280 (UPI)
        self.s2 = self._sale("UPI", [{"product": self.a, "quantity": 1}, {"product": self.b, "quantity": 1}], "30")
        # Sale 3 cancelled: must be excluded from every report
        s3 = self._sale("CARD", [{"product": self.a, "quantity": 5}])
        services.update_sale(sale=s3, user=self.mgr, sale_status="CANCELLED")

    def _sale(self, method, items, discount="0"):
        return services.create_sale(
            cashier=self.cashier, customer=None, payment_method=method, payment_status="PAID",
            discount_amount=Decimal(discount), notes="", items=items,
        )

    def test_reports_forbidden_for_non_managers(self):
        for role in ("CASHIER", "STAFF"):
            client = auth_client(make_user(role, f"u_{role}"))
            for path in ("dashboard", "sales", "daily-sales", "monthly-sales", "top-products", "payment-summary"):
                self.assertEqual(client.get(f"/api/reports/{path}/").status_code, 403, (role, path))

    def test_dashboard(self):
        data = self.client.get("/api/reports/dashboard/").data
        self.assertEqual(data["today_orders"], 2)
        self.assertEqual(Decimal(str(data["today_sales"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(data["total_revenue"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(data["monthly_revenue"])), Decimal("500.00"))
        self.assertEqual(data["total_products"], 2)
        self.assertEqual(data["low_stock_products"], 1)
        self.assertEqual(data["total_customers"], 1)

    def test_sales_report(self):
        today = timezone.localdate().isoformat()
        data = self.client.get(f"/api/reports/sales/?start_date={today}&end_date={today}").data
        self.assertEqual(data["total_orders"], 2)
        self.assertEqual(Decimal(str(data["total_sales"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(data["total_tax"])), Decimal("30.00"))
        self.assertEqual(Decimal(str(data["total_discounts"])), Decimal("30.00"))
        self.assertEqual(Decimal(str(data["total_revenue"])), Decimal("500.00"))
        self.assertEqual(Decimal(str(data["average_order_value"])), Decimal("250.00"))

    def test_sales_report_empty_range_and_invalid_dates(self):
        data = self.client.get("/api/reports/sales/?start_date=2000-01-01&end_date=2000-01-31").data
        self.assertEqual(data["total_orders"], 0)
        self.assertEqual(Decimal(str(data["average_order_value"])), Decimal("0"))
        self.assertEqual(self.client.get("/api/reports/sales/?start_date=2026-02-01&end_date=2026-01-01").status_code, 400)
        self.assertEqual(self.client.get("/api/reports/sales/?start_date=garbage").status_code, 400)

    def test_daily_and_monthly(self):
        daily = self.client.get("/api/reports/daily-sales/").data
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0]["date"], timezone.localdate().isoformat())
        self.assertEqual(daily[0]["orders"], 2)
        self.assertEqual(Decimal(str(daily[0]["revenue"])), Decimal("500.00"))
        monthly = self.client.get("/api/reports/monthly-sales/").data
        self.assertEqual(monthly[0]["month"], timezone.localdate().strftime("%Y-%m"))
        self.assertEqual(monthly[0]["orders"], 2)

    def test_top_products(self):
        data = self.client.get("/api/reports/top-products/").data
        self.assertEqual(data[0]["product_name"], "Shirt")
        self.assertEqual(data[0]["quantity_sold"], 3)
        self.assertEqual(Decimal(str(data[0]["revenue"])), Decimal("330.00"))
        self.assertEqual(data[1]["quantity_sold"], 1)
        self.assertEqual(len(self.client.get("/api/reports/top-products/?limit=1").data), 1)

    def test_payment_summary(self):
        data = {r["payment_method"]: r for r in self.client.get("/api/reports/payment-summary/").data}
        self.assertEqual(set(data), {"CASH", "CARD", "UPI", "BANK_TRANSFER", "OTHER"})
        self.assertEqual(data["CASH"]["transactions"], 1)
        self.assertEqual(Decimal(str(data["CASH"]["total_amount"])), Decimal("220.00"))
        self.assertEqual(Decimal(str(data["UPI"]["total_amount"])), Decimal("280.00"))
        self.assertEqual(data["CARD"]["transactions"], 0)  # cancelled sale excluded
