from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import (
    IsAdminManagerOrCashier,
    IsAdminOrManager,
    IsAuthenticatedUser,
)
from config.exceptions import success_response
from sales.models import Customer, Sale
from sales.serializers import (
    CustomerSerializer,
    SaleCreateSerializer,
    SaleSerializer,
    SaleUpdateSerializer,
)


def scoped_sales(user):
    """Sales the user may see: everything for admin/manager, own sales for cashiers."""
    qs = Sale.objects.select_related("customer", "cashier").prefetch_related("items__product")
    if user.is_superuser or user.role in (User.Role.ADMIN, User.Role.MANAGER):
        return qs
    if user.role == User.Role.CASHIER:
        return qs.filter(cashier=user)
    return qs.none()


class SaleFilter(filters.FilterSet):
    start_date = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    end_date = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = Sale
        fields = ["payment_method", "payment_status", "sale_status", "cashier", "customer"]


SALE_SEARCH = ["invoice_number", "customer__name", "customer__phone"]
SALE_ORDERING = ["created_at", "total_amount", "invoice_number"]


class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SaleSerializer
    filterset_class = SaleFilter
    search_fields = SALE_SEARCH
    ordering_fields = SALE_ORDERING

    def get_permissions(self):
        if self.action == "partial_update":
            return [IsAdminOrManager()]
        return [IsAdminManagerOrCashier()]

    def get_queryset(self):
        return scoped_sales(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()
        sale = scoped_sales(request.user).get(pk=sale.pk)
        return success_response("Sale created successfully", SaleSerializer(sale).data, 201)

    def partial_update(self, request, *args, **kwargs):
        sale = self.get_object()
        serializer = SaleUpdateSerializer(
            sale, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        sale = scoped_sales(request.user).get(pk=sale.pk)
        return Response(SaleSerializer(sale).data)


class SaleListBase(generics.ListAPIView):
    serializer_class = SaleSerializer
    permission_classes = [IsAdminManagerOrCashier]
    filterset_class = SaleFilter
    search_fields = SALE_SEARCH
    ordering_fields = SALE_ORDERING


class MySalesView(SaleListBase):
    def get_queryset(self):
        return scoped_sales(self.request.user).filter(cashier=self.request.user)


class TodaySalesView(SaleListBase):
    def get_queryset(self):
        return scoped_sales(self.request.user).filter(created_at__date=timezone.localdate())


class RecentSalesView(APIView):
    permission_classes = [IsAdminManagerOrCashier]

    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get("limit", 10)), 1), 50)
        except ValueError:
            limit = 10
        sales = scoped_sales(request.user)[:limit]
        data = SaleSerializer(sales, many=True).data
        return Response({"count": len(data), "results": data})


class InvoiceView(generics.RetrieveAPIView):
    serializer_class = SaleSerializer
    permission_classes = [IsAdminManagerOrCashier]
    lookup_field = "invoice_number"
    lookup_url_kwarg = "invoice_number"

    def get_queryset(self):
        return scoped_sales(self.request.user)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    search_fields = ["name", "email", "phone"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticatedUser()]
        if self.action in ("create", "sales"):
            return [IsAdminManagerOrCashier()]
        return [IsAdminOrManager()]

    @action(detail=True, methods=["get"], url_path="sales")
    def sales(self, request, pk=None):
        customer = self.get_object()
        queryset = scoped_sales(request.user).filter(customer=customer)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(
            SaleSerializer(page, many=True, context={"request": request}).data
        )
