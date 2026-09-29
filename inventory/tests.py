from decimal import Decimal

from django.test import TestCase

from accounts.tests import auth_client, make_user
from inventory.models import Brand, Category, Product, StockTransaction


def make_product(**overrides):
    data = {
        "name": "Cotton Shirt", "sku": "SKU-1", "selling_price": Decimal("100.00"),
        "cost_price": Decimal("60.00"), "stock_quantity": 10, "minimum_stock": 5,
    }
    data.update(overrides)
    return Product.objects.create(**data)


class InventoryPermissionTests(TestCase):
    def test_unauthenticated_gets_401(self):
        from rest_framework.test import APIClient

        self.assertEqual(APIClient().get("/api/inventory/products/").status_code, 401)

    def test_read_allowed_write_forbidden_for_non_managers(self):
        make_product()
        for role in ("CASHIER", "STAFF"):
            client = auth_client(make_user(role, f"u_{role}"))
            self.assertEqual(client.get("/api/inventory/products/").status_code, 200)
            res = client.post(
                "/api/inventory/products/",
                {"name": "X", "sku": "X1", "selling_price": "5.00"},
                format="json",
            )
            self.assertEqual(res.status_code, 403, role)


class CatalogCrudTests(TestCase):
    def setUp(self):
        self.client = auth_client(make_user("MANAGER", "mgr"))

    def test_category_crud(self):
        res = self.client.post("/api/inventory/categories/", {"name": "Shirts"}, format="json")
        self.assertEqual(res.status_code, 201)
        cid = res.data["id"]
        self.assertEqual(
            self.client.patch(f"/api/inventory/categories/{cid}/", {"name": "Tops"}, format="json").status_code,
            200,
        )
        self.assertEqual(self.client.get(f"/api/inventory/categories/{cid}/").data["name"], "Tops")
        self.assertEqual(self.client.delete(f"/api/inventory/categories/{cid}/").status_code, 204)

    def test_brand_crud(self):
        res = self.client.post("/api/inventory/brands/", {"name": "Acme"}, format="json")
        self.assertEqual(res.status_code, 201)
        bid = res.data["id"]
        self.assertEqual(
            self.client.put(f"/api/inventory/brands/{bid}/", {"name": "Acme 2"}, format="json").status_code,
            200,
        )
        self.assertEqual(self.client.delete(f"/api/inventory/brands/{bid}/").status_code, 204)

    def test_product_create_with_opening_stock(self):
        cat = Category.objects.create(name="Shirts")
        res = self.client.post(
            "/api/inventory/products/",
            {"name": "Linen Shirt", "sku": "LS-1", "barcode": "", "category": cat.id,
             "cost_price": "500.00", "selling_price": "899.00", "stock_quantity": 12,
             "minimum_stock": 3, "unit": "PCS", "tax_percentage": "5.00"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIsNone(Product.objects.get(sku="LS-1").barcode)
        txn = StockTransaction.objects.get(product_id=res.data["id"])
        self.assertEqual((txn.previous_quantity, txn.new_quantity), (0, 12))

    def test_validation_errors(self):
        make_product(barcode="123")
        base = {"name": "P", "sku": "NEW", "selling_price": "10.00"}
        self.assertEqual(
            self.client.post("/api/inventory/products/", {**base, "sku": "SKU-1"}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post("/api/inventory/products/", {**base, "barcode": "123"}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post("/api/inventory/products/", {**base, "selling_price": "-1"}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post("/api/inventory/products/", {**base, "stock_quantity": -3}, format="json").status_code, 400)
        self.assertEqual(
            self.client.post("/api/inventory/products/", {**base, "tax_percentage": "150"}, format="json").status_code, 400)

    def test_cannot_change_stock_via_patch(self):
        p = make_product()
        res = self.client.patch(f"/api/inventory/products/{p.id}/", {"stock_quantity": 99}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_delete_product_with_history_returns_409(self):
        p = make_product()
        self.client.post(
            "/api/inventory/stock/adjust/", {"product": p.id, "quantity": 1, "reason": "x"}, format="json"
        )
        res = self.client.delete(f"/api/inventory/products/{p.id}/")
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.data["success"])


class ProductListingTests(TestCase):
    def setUp(self):
        self.client = auth_client(make_user("CASHIER", "cash"))
        self.cat1, self.cat2 = Category.objects.create(name="A"), Category.objects.create(name="B")
        self.brand = Brand.objects.create(name="Br")
        make_product(name="iPhone 15", sku="IP15", selling_price=Decimal("800"), category=self.cat1, brand=self.brand)
        make_product(name="Galaxy", sku="GX", selling_price=Decimal("600"), category=self.cat2, is_active=False)
        make_product(name="Cable", sku="CB", selling_price=Decimal("10"), category=self.cat2)

    def test_search_filter_ordering(self):
        self.assertEqual(self.client.get("/api/inventory/products/?search=iphone").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/inventory/products/?category={self.cat2.id}").data["count"], 2)
        self.assertEqual(self.client.get(f"/api/inventory/products/?brand={self.brand.id}").data["count"], 1)
        self.assertEqual(self.client.get("/api/inventory/products/?is_active=true").data["count"], 2)
        self.assertEqual(self.client.get("/api/inventory/products/?min_price=500&max_price=700").data["count"], 1)
        prices = [p["selling_price"] for p in self.client.get("/api/inventory/products/?ordering=selling_price").data["results"]]
        self.assertEqual(prices, sorted(prices))

    def test_pagination(self):
        res = self.client.get("/api/inventory/products/?page_size=2")
        self.assertEqual(res.data["count"], 3)
        self.assertEqual(len(res.data["results"]), 2)
        self.assertIsNotNone(res.data["next"])
        self.assertEqual(len(self.client.get("/api/inventory/products/?page_size=500").data["results"]), 3)


class StockTests(TestCase):
    def setUp(self):
        self.user = make_user("MANAGER", "mgr")
        self.client = auth_client(self.user)
        self.product = make_product()

    def test_adjust_adds_stock_and_logs(self):
        res = self.client.post(
            "/api/inventory/stock/adjust/",
            {"product": self.product.id, "quantity": 20, "reason": "New stock received"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 30)
        txn = StockTransaction.objects.get()
        self.assertEqual((txn.previous_quantity, txn.new_quantity, txn.created_by), (10, 30, self.user))
        self.assertEqual(txn.transaction_type, "PURCHASE")

    def test_damage_removes_and_cannot_go_negative(self):
        ok = self.client.post(
            "/api/inventory/stock/adjust/",
            {"product": self.product.id, "quantity": 4, "transaction_type": "DAMAGE", "reason": "torn"},
            format="json",
        )
        self.assertEqual(ok.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)
        bad = self.client.post(
            "/api/inventory/stock/adjust/",
            {"product": self.product.id, "quantity": -100, "reason": "oops"},
            format="json",
        )
        self.assertEqual(bad.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)

    def test_zero_and_invalid_product_rejected(self):
        self.assertEqual(self.client.post("/api/inventory/stock/adjust/",
                         {"product": self.product.id, "quantity": 0, "reason": "x"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/inventory/stock/adjust/",
                         {"product": 9999, "quantity": 1, "reason": "x"}, format="json").status_code, 400)

    def test_cashier_cannot_adjust(self):
        res = auth_client(make_user("CASHIER", "cash")).post(
            "/api/inventory/stock/adjust/",
            {"product": self.product.id, "quantity": 1, "reason": "x"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_low_stock(self):
        make_product(name="Plenty", sku="PL", stock_quantity=100, minimum_stock=5)
        make_product(name="Empty", sku="EM", stock_quantity=0, minimum_stock=2)
        res = self.client.get("/api/inventory/low-stock/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)  # "Cotton Shirt" (10 > 5) is fine, only Empty
        self.assertEqual(res.data["results"][0]["sku"], "EM")
