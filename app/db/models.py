from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.session import metadata


class Base(DeclarativeBase):
    metadata = metadata


class RateCard(Base):
    __tablename__ = "rate_cards"
    __table_args__ = (
        UniqueConstraint("cargo_type", "vehicle_type", name="uq_rate_cards_cargo_vehicle"),
        CheckConstraint("rate_per_km >= 0", name="ck_rate_cards_rate_nonnegative"),
        CheckConstraint("extra_stop_fee >= 0", name="ck_rate_cards_stop_fee_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cargo_type: Mapped[str] = mapped_column(String(50))
    vehicle_type: Mapped[str] = mapped_column(String(50))
    rate_per_km: Mapped[int] = mapped_column(BigInteger)
    extra_stop_fee: Mapped[int] = mapped_column(BigInteger)


class CommissionRule(Base):
    __tablename__ = "commission_rules"
    __table_args__ = (
        UniqueConstraint("name", name="uq_commission_rules_name"),
        CheckConstraint(
            "commission_rate_bps BETWEEN 0 AND 10000",
            name="ck_commission_rules_rate_bps",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    commission_rate_bps: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)


class PricingQuote(Base):
    __tablename__ = "pricing_quotes"
    __table_args__ = (
        UniqueConstraint("shipment_id", "quote_version", name="uq_pricing_quotes_shipment_version"),
        CheckConstraint("quote_version > 0", name="ck_pricing_quotes_version_positive"),
        CheckConstraint("distance_km > 0", name="ck_pricing_quotes_distance_positive"),
        CheckConstraint("stop_count >= 1", name="ck_pricing_quotes_stop_count_positive"),
        CheckConstraint(
            "gross_amount >= 0 AND commission_amount >= 0 AND driver_net_amount >= 0",
            name="ck_pricing_quotes_amounts_nonnegative",
        ),
        CheckConstraint(
            "driver_net_amount + commission_amount = gross_amount",
            name="ck_pricing_quotes_amount_balance",
        ),
    )

    quote_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    shipment_id: Mapped[str] = mapped_column(Text)
    quote_version: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[int] = mapped_column(BigInteger)
    stop_count: Mapped[int] = mapped_column(Integer)
    cargo_type: Mapped[str] = mapped_column(String(50))
    vehicle_type: Mapped[str] = mapped_column(String(50))
    gross_amount: Mapped[int] = mapped_column(BigInteger)
    commission_amount: Mapped[int] = mapped_column(BigInteger)
    driver_net_amount: Mapped[int] = mapped_column(BigInteger)
    distance_amount: Mapped[int] = mapped_column(BigInteger)
    stop_fee: Mapped[int] = mapped_column(BigInteger)
    rate_per_km: Mapped[int] = mapped_column(BigInteger)
    commission_rate_bps: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
