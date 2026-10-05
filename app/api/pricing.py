from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import PricingError
from app.api.pricing_schemas import QuoteBreakdown, QuoteRequest, QuoteResponse
from app.db.models import PricingQuote
from app.db.session import get_session
from app.quotes import create_quote, latest_quote, quote_inputs

router = APIRouter(prefix="/api/v1/pricing")
DatabaseSession = Annotated[Session, Depends(get_session)]


def validate_shipment_id(shipment_id: str) -> None:
    # PostgreSQL text cannot store a NUL byte; otherwise keep identifiers opaque.
    if "\x00" in shipment_id:
        raise PricingError(422, "VALIDATION_ERROR", "Shipment identifier cannot contain a NUL byte.")


def quote_response(quote: PricingQuote) -> QuoteResponse:
    return QuoteResponse(
        quote_id=quote.quote_id,
        shipment_id=quote.shipment_id,
        quote_version=quote.quote_version,
        inputs=quote_inputs(quote),
        gross_amount=quote.gross_amount,
        commission_amount=quote.commission_amount,
        driver_net_amount=quote.driver_net_amount,
        breakdown=QuoteBreakdown(
            base_amount=quote.gross_amount,
            distance_amount=quote.distance_amount,
            stop_fee=quote.stop_fee,
            rate_per_km=quote.rate_per_km,
            commission_rate_bps=quote.commission_rate_bps,
        ),
        created_at=quote.created_at,
    )


@router.post("/shipments/{shipment_id}/quote", response_model=QuoteResponse)
def post_quote(shipment_id: str, body: QuoteRequest, session: DatabaseSession) -> QuoteResponse:
    validate_shipment_id(shipment_id)
    return quote_response(create_quote(session, shipment_id, body))


@router.get("/shipments/{shipment_id}/quotes/latest", response_model=QuoteResponse)
def get_latest_quote(shipment_id: str, session: DatabaseSession) -> QuoteResponse:
    validate_shipment_id(shipment_id)
    quote = latest_quote(session, shipment_id)
    if quote is None:
        raise PricingError(404, "QUOTE_NOT_FOUND", "No quote exists for this shipment.")
    return quote_response(quote)
