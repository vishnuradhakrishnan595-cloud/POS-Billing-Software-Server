from django.db.models import F
from django_filters import rest_framework as filters
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import (
    IsAdminOrManager,
    IsAuthenticatedUser,
    ReadOnlyOrAdminManager,
)
from config.exceptions import success_response
from inventory.models import Brand, Category, Product, StockTransaction
from inventory.serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductSerializer,
    StockAdjustmentSerializer,
    StockTransactionSerializer,
)
from inventory.services import adjust_stock


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [ReadOnlyOrAdminManager]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [ReadOnlyOrAdminManager]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class ProductFilter(filters.FilterSet):
    min_price = filters.NumberFilter(field_name="selling_price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="selling_price", lookup_expr="lte")
    min_stock = filters.NumberFilter(field_name="stock_quantity", lookup_expr="gte")
    max_stock = filters.NumberFilter(field_name="stock_quantity", lookup_expr="lte")

    class Meta:
        model = Product
        fields = ["category", "brand", "is_active", "stock_quantity"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category", "brand")
    serializer_class = ProductSerializer
    permission_classes = [ReadOnlyOrAdminManager]
    filterset_class = ProductFilter
    search_fields = ["name", "sku", "barcode", "description"]
    ordering_fields = ["name", "selling_price", "cost_price", "stock_quantity", "created_at"]


class StockTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockTransaction.objects.select_related("product", "created_by")
    serializer_class = StockTransactionSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ["product", "transaction_type", "created_by"]
    search_fields = ["product__name", "product__sku", "reason"]
    ordering_fields = ["created_at", "quantity"]


class StockAdjustView(APIView):
    permission_classes = [IsAdminOrManager]

    def post(self, request):
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        txn = adjust_stock(
            product_id=data["product"].pk,
            quantity=data["quantity"],
            transaction_type=data["transaction_type"],
            reason=data["reason"],
            user=request.user,
        )
        return success_response(
            "Stock adjusted successfully", StockTransactionSerializer(txn).data, 201
        )


class LowStockView(APIView):
    permission_classes = [IsAuthenticatedUser]

    def get(self, request):
        products = Product.objects.select_related("category", "brand").filter(
            stock_quantity__lte=F("minimum_stock")
        )
        data = ProductSerializer(products, many=True, context={"request": request}).data
        return Response({"count": len(data), "results": data})
