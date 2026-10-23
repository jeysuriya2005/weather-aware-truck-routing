"""
One JSON error shape for every failure:

    {"error": {"code": "...", "message": "...", "fields": {...}?}}

Provider errors are mapped to safe, user-facing messages. Unexpected
exceptions are logged server-side and returned as a generic 500.
"""

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .providers import errors

logger = logging.getLogger(__name__)

PROVIDER_ERROR_STATUS = {
    errors.ProviderNotConfigured: status.HTTP_503_SERVICE_UNAVAILABLE,
    errors.ProviderAuthFailed: status.HTTP_502_BAD_GATEWAY,
    errors.ProviderRateLimited: status.HTTP_503_SERVICE_UNAVAILABLE,
    errors.ProviderTimeout: status.HTTP_504_GATEWAY_TIMEOUT,
    errors.ProviderUnavailable: status.HTTP_502_BAD_GATEWAY,
    errors.ProviderBadResponse: status.HTTP_502_BAD_GATEWAY,
    errors.NoRouteFound: status.HTTP_422_UNPROCESSABLE_ENTITY,
    errors.ProviderRejectedRequest: status.HTTP_422_UNPROCESSABLE_ENTITY,
}

RETRY_AFTER_SECONDS = {errors.ProviderRateLimited: 60}


def _error(code: str, message: str, http_status: int, fields=None, headers=None) -> Response:
    body = {"code": code, "message": message}
    if fields is not None:
        body["fields"] = fields
    return Response({"error": body}, status=http_status, headers=headers)


def api_exception_handler(exc, context):
    if isinstance(exc, errors.ProviderError):
        retry_after = RETRY_AFTER_SECONDS.get(type(exc))
        return _error(
            exc.code,
            exc.message,
            PROVIDER_ERROR_STATUS.get(type(exc), status.HTTP_502_BAD_GATEWAY),
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )

    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error")
        return _error("internal_error", "An unexpected server error occurred.", 500)

    if isinstance(exc, ValidationError):
        response.data = {
            "error": {"code": "invalid_request", "message": "Some fields are invalid.", "fields": response.data}
        }
        return response

    codes = exc.get_codes() if isinstance(exc, APIException) else None
    detail = response.data.get("detail", "") if isinstance(response.data, dict) else ""
    response.data = {"error": {"code": codes if isinstance(codes, str) else "error", "message": str(detail)}}
    return response
