from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.errors import (
    PricingError,
    http_error_handler,
    pricing_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.api.health import router
from app.api.pricing import router as pricing_router

app = FastAPI(title="Asanbar Pricing Service")
app.include_router(router)
app.include_router(pricing_router)
app.add_exception_handler(PricingError, pricing_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
