from django.db import transaction

from config.exceptions import InsufficientStock
from inventory.models import Product, StockTransaction

TT = StockTransaction.TransactionType


def change_stock(*, product, delta, transaction_type, reason, user):
    """Apply a signed ``delta`` to an already-locked ``product`` and record it.

    Callers must hold a ``select_for_update`` lock on the product inside a
    ``transaction.atomic()`` block. Raises ``InsufficientStock`` if stock would
    become negative.
    """
    previous = product.stock_quantity
    new = previous + delta
    if new < 0:
        raise InsufficientStock(
            {"product": [f"Only {previous} units of '{product.name}' are available."]}
        )
    product.stock_quantity = new
    product.save(update_fields=["stock_quantity", "updated_at"])
    return StockTransaction.objects.create(
        product=product,
        transaction_type=transaction_type,
        quantity=delta,
        previous_quantity=previous,
        new_quantity=new,
        reason=reason or "",
        created_by=user if getattr(user, "pk", None) else None,
    )


@transaction.atomic
def adjust_stock(*, product_id, quantity, transaction_type, reason, user):
    """Manual stock movement.

    PURCHASE / RETURN always add, DAMAGE always removes, ADJUSTMENT uses the sign given.
    """
    product = Product.objects.select_for_update().get(pk=product_id)
    if transaction_type in (TT.PURCHASE, TT.RETURN):
        delta = abs(quantity)
    elif transaction_type == TT.DAMAGE:
        delta = -abs(quantity)
    else:
        delta = quantity
    return change_stock(
        product=product,
        delta=delta,
        transaction_type=transaction_type,
        reason=reason,
        user=user,
    )
