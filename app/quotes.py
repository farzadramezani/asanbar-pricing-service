from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.errors import PricingError
from app.api.pricing_schemas import QuoteInputs, QuoteRequest
from app.calculation import calculate_price
from app.db.models import CommissionRule, PricingQuote, RateCard


def latest_quote(session: Session, shipment_id: str) -> PricingQuote | None:
    return session.scalar(
        select(PricingQuote)
        .where(PricingQuote.shipment_id == shipment_id)
        .order_by(PricingQuote.quote_version.desc())
        .limit(1)
    )


def quote_inputs(quote: PricingQuote) -> QuoteInputs:
    return QuoteInputs(
        distance_km=quote.distance_km,
        stop_count=quote.stop_count,
        cargo_type=quote.cargo_type,
        vehicle_type=quote.vehicle_type,
    )


def create_quote(session: Session, shipment_id: str, request: QuoteRequest) -> PricingQuote:
    with session.begin():
        # Serialize even the first quote for a shipment without adding a shipment table.
        # A hash collision only makes unrelated shipments wait for each other.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:shipment_id, 0))"),
            {"shipment_id": shipment_id},
        )
        previous = latest_quote(session, shipment_id)
        if previous and not request.force_recalculate and quote_inputs(previous) == request.inputs:
            return previous

        inputs = request.inputs
        rate_card = session.scalar(
            select(RateCard).where(
                RateCard.cargo_type == inputs.cargo_type,
                RateCard.vehicle_type == inputs.vehicle_type,
            )
        )
        if rate_card is None:
            raise PricingError(
                422, "UNKNOWN_RATE_CARD", "No rate card matches the cargo and vehicle types."
            )
        commission = session.scalar(
            select(CommissionRule).where(
                CommissionRule.name == "default", CommissionRule.active.is_(True),
            )
        )
        if commission is None:
            raise PricingError(
                503, "COMMISSION_RULE_UNAVAILABLE",
                "The active default commission rule is unavailable.",
            )

        amounts = calculate_price(
            inputs.distance_km, inputs.stop_count,
            rate_card.rate_per_km, rate_card.extra_stop_fee, commission.commission_rate_bps,
        )
        if amounts.gross_amount > 2**63 - 1:
            raise PricingError(
                422, "AMOUNT_OUT_OF_RANGE", "Calculated amount exceeds the database integer range."
            )
        quote = PricingQuote(
            shipment_id=shipment_id,
            quote_version=previous.quote_version + 1 if previous else 1,
            **inputs.model_dump(),
            gross_amount=amounts.gross_amount,
            commission_amount=amounts.commission_amount,
            driver_net_amount=amounts.driver_net_amount,
            distance_amount=amounts.distance_amount,
            stop_fee=rate_card.extra_stop_fee,
            rate_per_km=rate_card.rate_per_km,
            commission_rate_bps=commission.commission_rate_bps,
        )
        session.add(quote)
        session.flush()
    return quote
