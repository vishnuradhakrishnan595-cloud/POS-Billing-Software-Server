from django.urls import include, path
from rest_framework.routers import SimpleRouter

from inventory import views

router = SimpleRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("brands", views.BrandViewSet, basename="brand")
router.register("products", views.ProductViewSet, basename="product")
router.register("stock", views.StockTransactionViewSet, basename="stock")

urlpatterns = [
    # Must come before the router so "adjust" is not treated as a stock pk.
    path("stock/adjust/", views.StockAdjustView.as_view(), name="stock-adjust"),
    path("low-stock/", views.LowStockView.as_view(), name="low-stock"),
    path("", include(router.urls)),
]
