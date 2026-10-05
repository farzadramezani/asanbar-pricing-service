import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class PricingError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def is_pricing_request(request: Request) -> bool:
    return request.url.path == "/api/v1/pricing" or request.url.path.startswith("/api/v1/pricing/")


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    correlation_id = request.headers.get("X-Correlation-Id")
    if correlation_id is None:
        correlation_id = str(uuid4())
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "correlation_id": correlation_id}},
    )


async def pricing_error_handler(request: Request, exc: PricingError) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    if is_pricing_request(request):
        return error_response(request, 422, "VALIDATION_ERROR", "Invalid pricing request.")
    return await request_validation_exception_handler(request, exc)


async def http_error_handler(request: Request, exc: HTTPException):
    if is_pricing_request(request):
        response = error_response(request, exc.status_code, "HTTP_ERROR", str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response
    return await http_exception_handler(request, exc)


async def unexpected_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled request error", exc_info=(type(exc), exc, exc.__traceback__))
    if is_pricing_request(request):
        return error_response(request, 500, "INTERNAL_ERROR", "Unable to process pricing request.")
    return PlainTextResponse("Internal Server Error", status_code=500)
