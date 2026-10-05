from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    snapshot_id: UUID
    shipment_id: str
    quote_id: UUID
    quote_version: int
    gross_amount: int
    commission_amount: int
    driver_net_amount: int
    currency: Literal["IRR"] = "IRR"
    confirmed_at: datetime
