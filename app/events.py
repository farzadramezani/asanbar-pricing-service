from datetime import UTC, datetime
from functools import lru_cache
import json
from uuid import uuid4

from redis import Redis

from app.core.config import get_settings
from app.db.models import PriceSnapshot


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def publish_snapshot_created(
    redis: Redis, snapshot: PriceSnapshot, correlation_id: str | None,
) -> None:
    payload = {
        "event_id": str(uuid4()),
        "event_type": "price_snapshot.created",
        "occurred_at": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
        "data": {
            "shipment_id": snapshot.shipment_id,
            "price_snapshot_id": str(snapshot.snapshot_id),
            "quote_id": str(snapshot.quote_id),
            "gross_amount": snapshot.gross_amount,
            "commission_amount": snapshot.commission_amount,
            "driver_net_amount": snapshot.driver_net_amount,
            "currency": "IRR",
        },
    }
    redis.xadd("asanbar:events", {"payload": json.dumps(payload)})
