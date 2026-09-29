import logging

from django.db.models import ProtectedError
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class InsufficientStock(APIException):
    """Raised when an operation would make stock negative (HTTP 409)."""

    status_code = 409
    default_detail = "Insufficient stock."
    default_code = "insufficient_stock"
    user_message = "Insufficient stock"


def success_response(message, data=None, status_code=200):
    return Response(
        {"success": True, "message": message, "data": {} if data is None else data},
        status=status_code,
    )


def error_response(message, errors=None, status_code=400):
    return Response(
        {"success": False, "message": message, "errors": errors or {}},
        status=status_code,
    )


def custom_exception_handler(exc, context):
    """Return every error in the same {success, message, errors} envelope."""
    if isinstance(exc, ProtectedError):
        return error_response(
            "This record cannot be deleted because other records depend on it.",
            status_code=409,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled server error", exc_info=exc)
        return error_response("An internal server error occurred.", status_code=500)

    data = response.data
    message = getattr(exc, "user_message", None)
    if isinstance(data, dict) and "detail" in data:
        message = message or str(data["detail"])
        errors = {k: v for k, v in data.items() if k != "detail"}
    else:
        errors = data if isinstance(data, dict) else {"non_field_errors": data}
        message = message or "Validation failed"

    response.data = {"success": False, "message": message, "errors": errors}
    return response
