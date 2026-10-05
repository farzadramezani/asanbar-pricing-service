from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String, UniqueConstraint
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
