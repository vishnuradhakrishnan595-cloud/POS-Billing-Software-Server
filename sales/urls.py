from django.urls import include, path
from rest_framework.routers import SimpleRouter

from sales import views

router = SimpleRouter()
router.register("customers", views.CustomerViewSet, basename="customer")

urlpatterns = [
    path("", include(router.urls)),  # /customers/...
    path("invoice/<str:invoice_number>/", views.InvoiceView.as_view(), name="sale-invoice"),
    path("my-sales/", views.MySalesView.as_view(), name="my-sales"),
    path("today/", views.TodaySalesView.as_view(), name="today-sales"),
    path("recent/", views.RecentSalesView.as_view(), name="recent-sales"),
    path("", views.SaleViewSet.as_view({"get": "list", "post": "create"}), name="sale-list"),
    path(
        "<int:pk>/",
        views.SaleViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="sale-detail",
    ),
]
