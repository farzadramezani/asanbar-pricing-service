from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from redis import Redis
from redis.exceptions import RedisError

from app.api.errors import PricingError
from app.api.pricing import DatabaseSession, validate_shipment_id
from app.api.snapshot_schemas import SnapshotResponse
from app.events import get_redis, publish_snapshot_created
from app.snapshots import confirm_snapshot, get_snapshot

router = APIRouter(prefix="/api/v1/pricing")


@router.post(
    "/shipments/{shipment_id}/confirm-snapshot",
    response_model=SnapshotResponse,
    status_code=201,
)
def post_confirm_snapshot(
    shipment_id: str,
    response: Response,
    session: DatabaseSession,
    redis: Annotated[Redis, Depends(get_redis)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    correlation_id: Annotated[str | None, Header(alias="X-Correlation-Id")] = None,
) -> SnapshotResponse:
    validate_shipment_id(shipment_id)
    if "\x00" in idempotency_key:
        raise PricingError(422, "VALIDATION_ERROR", "Idempotency key cannot contain a NUL byte.")
    snapshot, created = confirm_snapshot(session, shipment_id, idempotency_key)
    if created:
        try:
            publish_snapshot_created(redis, snapshot, correlation_id)
        except RedisError as exc:
            raise PricingError(
                503, "EVENT_PUBLISH_FAILED",
                "Snapshot was committed, but its event could not be published.",
            ) from exc
    else:
        response.status_code = 200
    return SnapshotResponse.model_validate(snapshot)


@router.get("/shipments/{shipment_id}/snapshot", response_model=SnapshotResponse)
def get_shipment_snapshot(shipment_id: str, session: DatabaseSession) -> SnapshotResponse:
    validate_shipment_id(shipment_id)
    snapshot = get_snapshot(session, shipment_id)
    if snapshot is None:
        raise PricingError(404, "SNAPSHOT_NOT_FOUND", "No snapshot exists for this shipment.")
    return SnapshotResponse.model_validate(snapshot)
