from decimal import Decimal
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.tests import auth_client, make_user
from inventory.models import Product, StockTransaction
from sales import services
from sales.models import Customer, Sale, SaleItem


def make_product(sku="P1", price="100.00", tax="10.00", stock=10, **extra):
    return Product.objects.create(
        name=f"Product {sku}", sku=sku, selling_price=Decimal(price),
        tax_percentage=Decimal(tax), stock_quantity=stock, minimum_stock=1, **extra,
    )


class CustomerTests(TestCase):
    def setUp(self):
        self.cashier = make_user("CASHIER", "cash")
        self.client = auth_client(self.cashier)

    def test_crud_and_permissions(self):
        res = self.client.post(
            "/api/sales/customers/", {"name": "Asha", "phone": "9876543210", "city": "Kochi"}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        cid = res.data["id"]
        # cashiers can view and create but not edit/delete
        self.assertEqual(self.client.patch(f"/api/sales/customers/{cid}/", {"city": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/sales/customers/{cid}/").status_code, 403)
        manager = auth_client(make_user("MANAGER", "mgr"))
        self.assertEqual(manager.patch(f"/api/sales/customers/{cid}/", {"city": "Tvm"}, format="json").status_code, 200)
        self.assertEqual(manager.delete(f"/api/sales/customers/{cid}/").status_code, 204)

    def test_invalid_phone_rejected(self):
        res = self.client.post("/api/sales/customers/", {"name": "A", "phone": "abc"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_search_and_staff_limited_view(self):
        Customer.objects.create(name="Ravi Kumar", phone="9000000001", email="ravi@example.com", city="Kochi")
        Customer.objects.create(name="Meena", phone="9000000002")
        self.assertEqual(self.client.get("/api/sales/customers/?search=ravi").data["count"], 1)
        self.assertEqual(self.client.get("/api/sales/customers/?search=9000000002").data["count"], 1)
        staff = auth_client(make_user("STAFF", "stf"))
        row = staff.get("/api/sales/customers/?search=ravi").data["results"][0]
        self.assertEqual(set(row), {"id", "name", "city"})
        self.assertEqual(staff.post("/api/sales/customers/", {"name": "N", "phone": "9000000009"}, format="json").status_code, 403)


class SaleCreationTests(TestCase):
    def setUp(self):
        self.cashier = make_user("CASHIER", "cash")
        self.client = auth_client(self.cashier)
        self.customer = Customer.objects.create(name="Asha", phone="9876543210")
        self.p1 = make_product("P1", "100.00", "10.00", 10)
        self.p2 = make_product("P2", "50.00", "0.00", 5)

    def _sale(self, items=None, **extra):
        payload = {
            "customer": self.customer.id, "payment_method": "CASH", "discount_amount": 50,
            "items": items or [{"product": self.p1.id, "quantity": 2}, {"product": self.p2.id, "quantity": 1}],
        }
        payload.update(extra)
        return self.client.post("/api/sales/", payload, format="json")

    def test_unauthenticated_401_and_staff_403(self):
        self.assertEqual(APIClient().post("/api/sales/", {}, format="json").status_code, 401)
        staff = auth_client(make_user("STAFF", "stf"))
        self.assertEqual(staff.post("/api/sales/", {}, format="json").status_code, 403)

    def test_sale_calculates_totals_and_reduces_stock(self):
        res = self._sale()
        self.assertEqual(res.status_code, 201, res.data)
        data = res.data["data"]
        # subtotal 250 (200 + 50), tax 20 (10% of 200), discount 50 -> 220
        self.assertEqual(Decimal(str(data["subtotal"])), Decimal("250.00"))
        self.assertEqual(Decimal(str(data["tax_amount"])), Decimal("20.00"))
        self.assertEqual(Decimal(str(data["total_amount"])), Decimal("220.00"))
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["cashier"], self.cashier.id)
        self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertEqual((self.p1.stock_quantity, self.p2.stock_quantity), (8, 4))
        txns = StockTransaction.objects.filter(transaction_type="SALE")
        self.assertEqual(txns.count(), 2)
        self.assertEqual(txns.get(product=self.p1).quantity, -2)

    def test_invoice_number_generated_unique_and_fetchable(self):
        a = self._sale().data["data"]["invoice_number"]
        b = self._sale().data["data"]["invoice_number"]
        self.assertRegex(a, r"^INV-\d{8}-\d{4}$")
        self.assertNotEqual(a, b)
        res = self.client.get(f"/api/sales/invoice/{a}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["invoice_number"], a)

    def test_insufficient_stock_returns_409_and_changes_nothing(self):
        res = self._sale(items=[{"product": self.p1.id, "quantity": 1}, {"product": self.p2.id, "quantity": 6}])
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.data["success"])
        self.assertEqual(res.data["message"], "Insufficient stock")
        self.assertIn("product", res.data["errors"])
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock_quantity, 10)
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(StockTransaction.objects.count(), 0)

    def test_inactive_product_rejected(self):
        self.p1.is_active = False
        self.p1.save()
        res = self._sale(items=[{"product": self.p1.id, "quantity": 1}])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_validation_errors(self):
        self.assertEqual(self._sale(items=[]).status_code, 400)
        self.assertEqual(self._sale(items=[{"product": self.p1.id, "quantity": 0}]).status_code, 400)
        self.assertEqual(self._sale(payment_method="BITCOIN").status_code, 400)
        self.assertEqual(self._sale(customer=9999).status_code, 400)
        self.assertEqual(self._sale(discount_amount=-1).status_code, 400)
        self.assertEqual(self._sale(discount_amount=100000).status_code, 400)  # exceeds total
        dup = [{"product": self.p1.id, "quantity": 1}, {"product": self.p1.id, "quantity": 1}]
        self.assertEqual(self._sale(items=dup).status_code, 400)
        self.assertEqual(Sale.objects.count(), 0)

    def test_failure_midway_rolls_back_everything(self):
        original = services.change_stock
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return original(**kwargs)

        with mock.patch("sales.services.change_stock", side_effect=flaky):
            with self.assertRaises(RuntimeError):
                services.create_sale(
                    cashier=self.cashier, customer=self.customer, payment_method="CASH",
                    payment_status="PAID", discount_amount=Decimal("0"), notes="",
                    items=[{"product": self.p1, "quantity": 1}, {"product": self.p2, "quantity": 1}],
                )
        self.p1.refresh_from_db(); self.p2.refresh_from_db()
        self.assertEqual((self.p1.stock_quantity, self.p2.stock_quantity), (10, 5))
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleItem.objects.count(), 0)
        self.assertEqual(StockTransaction.objects.count(), 0)


class SaleHistoryTests(TestCase):
    def setUp(self):
        self.c1, self.c2 = make_user("CASHIER", "c1"), make_user("CASHIER", "c2")
        self.mgr = make_user("MANAGER", "mgr")
        self.product = make_product("P1", "100.00", "0.00", 100)
        self.customer = Customer.objects.create(name="Asha", phone="9876543210")
        self.s1 = self._make(self.c1, "CASH", self.customer)
        self.s2 = self._make(self.c2, "CARD")

    def _make(self, cashier, method, customer=None):
        return services.create_sale(
            cashier=cashier, customer=customer, payment_method=method, payment_status="PAID",
            discount_amount=Decimal("0"), notes="", items=[{"product": self.product, "quantity": 1}],
        )

    def test_cashier_sees_only_own_sales(self):
        client = auth_client(self.c1)
        self.assertEqual(client.get("/api/sales/").data["count"], 1)
        self.assertEqual(client.get(f"/api/sales/{self.s2.id}/").status_code, 404)
        self.assertEqual(client.get(f"/api/sales/invoice/{self.s2.invoice_number}/").status_code, 404)
        self.assertEqual(client.get("/api/sales/my-sales/").data["count"], 1)

    def test_staff_forbidden(self):
        self.assertEqual(auth_client(make_user("STAFF", "stf")).get("/api/sales/").status_code, 403)

    def test_manager_lists_filters_orders(self):
        client = auth_client(self.mgr)
        self.assertEqual(client.get("/api/sales/").data["count"], 2)
        self.assertEqual(client.get("/api/sales/?payment_method=CASH").data["count"], 1)
        self.assertEqual(client.get("/api/sales/?sale_status=COMPLETED").data["count"], 2)
        self.assertEqual(client.get(f"/api/sales/?search={self.s1.invoice_number}").data["count"], 1)
        self.assertEqual(client.get("/api/sales/?start_date=2000-01-01&end_date=2100-01-01").data["count"], 2)
        self.assertEqual(client.get("/api/sales/?start_date=not-a-date").status_code, 400)
        ids = [s["id"] for s in client.get("/api/sales/?ordering=-created_at").data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(client.get("/api/sales/today/").data["count"], 2)
        self.assertEqual(client.get("/api/sales/recent/").data["count"], 2)

    def test_customer_sales_history(self):
        res = auth_client(self.mgr).get(f"/api/sales/customers/{self.customer.id}/sales/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)

    def test_cancel_restores_stock_once(self):
        client = auth_client(self.mgr)
        res = client.patch(f"/api/sales/{self.s1.id}/", {"sale_status": "CANCELLED"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 99)  # 100 - 2 sales + 1 returned
        again = client.patch(f"/api/sales/{self.s1.id}/", {"sale_status": "REFUNDED"}, format="json")
        self.assertEqual(again.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 99)

    def test_refund_sets_payment_status_and_cashier_cannot_patch(self):
        res = auth_client(self.mgr).patch(f"/api/sales/{self.s2.id}/", {"sale_status": "REFUNDED"}, format="json")
        self.assertEqual(res.data["payment_status"], "REFUNDED")
        self.assertEqual(
            auth_client(self.c2).patch(f"/api/sales/{self.s2.id}/", {"notes": "x"}, format="json").status_code, 403
        )
