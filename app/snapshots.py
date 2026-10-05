from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.errors import PricingError
from app.db.models import IdempotencyKey, PriceSnapshot
from app.quotes import latest_quote


def get_snapshot(session: Session, shipment_id: str) -> PriceSnapshot | None:
    return session.scalar(select(PriceSnapshot).where(PriceSnapshot.shipment_id == shipment_id))


def confirm_snapshot(
    session: Session, shipment_id: str, idempotency_key: str,
) -> tuple[PriceSnapshot, bool]:
    with session.begin():
        # Always lock key before shipment. Two-int key locks use a separate
        # PostgreSQL lock namespace from Gate 3's bigint shipment locks.
        session.execute(
            text("SELECT pg_advisory_xact_lock(1, hashtext(:key))"),
            {"key": idempotency_key},
        )
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:shipment_id, 0))"),
            {"shipment_id": shipment_id},
        )
        existing_key = session.get(IdempotencyKey, idempotency_key)
        if existing_key is not None:
            if (
                existing_key.operation != "confirm_snapshot"
                or existing_key.shipment_id != shipment_id
            ):
                raise PricingError(
                    409, "IDEMPOTENCY_CONFLICT",
                    "Idempotency key belongs to a different operation or shipment.",
                )
            snapshot = session.get(PriceSnapshot, existing_key.snapshot_id)
            assert snapshot is not None  # Protected by the idempotency record's foreign key.
            return snapshot, False

        if get_snapshot(session, shipment_id) is not None:
            raise PricingError(
                409, "SNAPSHOT_ALREADY_EXISTS", "A snapshot already exists for this shipment."
            )
        quote = latest_quote(session, shipment_id)
        if quote is None:
            raise PricingError(404, "QUOTE_NOT_FOUND", "No quote exists for this shipment.")

        snapshot = PriceSnapshot(
            shipment_id=shipment_id,
            quote_id=quote.quote_id,
            quote_version=quote.quote_version,
            gross_amount=quote.gross_amount,
            commission_amount=quote.commission_amount,
            driver_net_amount=quote.driver_net_amount,
        )
        session.add(snapshot)
        session.flush()
        session.add(
            IdempotencyKey(
                key=idempotency_key,
                operation="confirm_snapshot",
                shipment_id=shipment_id,
                snapshot_id=snapshot.snapshot_id,
            )
        )
    # The transaction has committed before the caller can publish an event.
    return snapshot, True
