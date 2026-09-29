from django.urls import path

from reports import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="report-dashboard"),
    path("sales/", views.SalesReportView.as_view(), name="report-sales"),
    path("daily-sales/", views.DailySalesView.as_view(), name="report-daily-sales"),
    path("monthly-sales/", views.MonthlySalesView.as_view(), name="report-monthly-sales"),
    path("top-products/", views.TopProductsView.as_view(), name="report-top-products"),
    path("payment-summary/", views.PaymentSummaryView.as_view(), name="report-payment-summary"),
]
