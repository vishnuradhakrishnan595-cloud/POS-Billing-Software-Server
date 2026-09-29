"""Business logic for sales. All stock-changing work runs inside one DB transaction."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from config.exceptions import InsufficientStock
from inventory.models import Product, StockTransaction
from inventory.services import change_stock
from sales.models import Sale, SaleItem

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _invoice_number(offset=0):
    today = timezone.localdate()
    prefix = f"INV-{today:%Y%m%d}-"
    count = Sale.objects.filter(invoice_number__startswith=prefix).count()
    return f"{prefix}{count + 1 + offset:04d}"


def _create_sale_row(**fields):
    """Insert the Sale, retrying with the next number if a concurrent sale took ours."""
    for attempt in range(10):
        try:
            with transaction.atomic():  # savepoint so an IntegrityError doesn't poison the outer txn
                return Sale.objects.create(invoice_number=_invoice_number(attempt), **fields)
        except IntegrityError:
            continue
    raise ValidationError({"invoice_number": ["Could not generate a unique invoice number."]})


@transaction.atomic
def create_sale(*, cashier, customer, payment_method, payment_status, discount_amount, notes, items):
    """Create a sale, its items and stock movements atomically.

    ``items`` is a list of dicts: {"product": Product, "quantity": int, "discount": Decimal}.
    """
    # Lock every product row (in id order, to avoid deadlocks) for the whole transaction.
    ids = sorted({item["product"].pk for item in items})
    products = {
        p.pk: p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by("pk")
    }

    lines, errors = [], []
    subtotal = tax_total = ZERO
    for item in items:
        product = products[item["product"].pk]
        quantity = item["quantity"]
        line_discount = money(item.get("discount") or ZERO)

        if not product.is_active:
            errors.append(f"'{product.name}' is inactive and cannot be sold.")
            continue
        if product.stock_quantity < quantity:
            raise InsufficientStock(
                {"product": [f"Only {product.stock_quantity} units of '{product.name}' are available."]}
            )

        gross = money(product.selling_price * quantity)
        if line_discount > gross:
            errors.append(f"Discount for '{product.name}' exceeds the line amount.")
            continue
        taxable = gross - line_discount
        tax = money(taxable * product.tax_percentage / HUNDRED)
        lines.append(
            {
                "product": product, "quantity": quantity, "unit_price": product.selling_price,
                "discount": line_discount, "tax": tax, "total": taxable + tax,
            }
        )
        subtotal += taxable
        tax_total += tax

    if errors:
        raise ValidationError({"items": errors})

    discount_amount = money(discount_amount or ZERO)
    if discount_amount > subtotal + tax_total:
        raise ValidationError({"discount_amount": ["Discount cannot exceed the sale total."]})

    sale = _create_sale_row(
        customer=customer,
        cashier=cashier,
        subtotal=subtotal,
        tax_amount=tax_total,
        discount_amount=discount_amount,
        total_amount=subtotal + tax_total - discount_amount,
        payment_method=payment_method,
        payment_status=payment_status,
        sale_status=Sale.SaleStatus.COMPLETED,
        notes=notes or "",
    )
    for line in lines:
        SaleItem.objects.create(
            sale=sale, product=line["product"], quantity=line["quantity"],
            unit_price=line["unit_price"], discount=line["discount"],
            tax=line["tax"], total=line["total"],
        )
        change_stock(
            product=line["product"],
            delta=-line["quantity"],
            transaction_type=StockTransaction.TransactionType.SALE,
            reason=f"Sale {sale.invoice_number}",
            user=cashier,
        )
    return sale


@transaction.atomic
def update_sale(*, sale, user, sale_status=None, payment_status=None, notes=None):
    """Update a sale. Cancelling/refunding a completed sale returns its stock."""
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    if sale_status and sale_status != sale.sale_status:
        if sale.sale_status != Sale.SaleStatus.COMPLETED:
            raise ValidationError(
                {"sale_status": [f"A {sale.sale_status.lower()} sale cannot change status."]}
            )
        if sale_status == Sale.SaleStatus.COMPLETED:
            raise ValidationError({"sale_status": ["A sale cannot be re-completed."]})

        items = list(sale.items.select_related("product").order_by("product_id"))
        locked = {
            p.pk: p
            for p in Product.objects.select_for_update()
            .filter(pk__in=[i.product_id for i in items])
            .order_by("pk")
        }
        for item in items:
            change_stock(
                product=locked[item.product_id],
                delta=item.quantity,
                transaction_type=StockTransaction.TransactionType.RETURN,
                reason=f"{sale_status.title()} sale {sale.invoice_number}",
                user=user,
            )
        sale.sale_status = sale_status
        if sale_status == Sale.SaleStatus.REFUNDED:
            sale.payment_status = Sale.PaymentStatus.REFUNDED

    if payment_status:
        sale.payment_status = payment_status
    if notes is not None:
        sale.notes = notes
    sale.save()
    return sale
