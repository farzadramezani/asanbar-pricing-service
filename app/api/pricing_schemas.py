from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QuoteInputs(BaseModel):
    distance_km: int = Field(gt=0, le=2**63 - 1, strict=True)
    stop_count: int = Field(ge=1, le=2**31 - 1, strict=True)
    cargo_type: str
    vehicle_type: str


class QuoteRequest(BaseModel):
    inputs: QuoteInputs
    force_recalculate: bool = False


class QuoteBreakdown(BaseModel):
    base_amount: int
    distance_amount: int
    stop_fee: int
    rate_per_km: int
    commission_rate_bps: int


class QuoteResponse(BaseModel):
    quote_id: UUID
    shipment_id: str
    quote_version: int
    inputs: QuoteInputs
    gross_amount: int
    commission_amount: int
    driver_net_amount: int
    currency: Literal["IRR"] = "IRR"
    breakdown: QuoteBreakdown
    created_at: datetime
