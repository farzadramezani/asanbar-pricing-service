from dataclasses import dataclass


@dataclass(frozen=True)
class PricingAmounts:
    distance_amount: int
    gross_amount: int
    commission_amount: int
    driver_net_amount: int


def calculate_price(
    distance_km: int,
    stop_count: int,
    rate_per_km: int,
    stop_fee: int,
    commission_rate_bps: int,
) -> PricingAmounts:
    distance_amount = distance_km * rate_per_km
    gross_amount = distance_amount + stop_fee * max(0, stop_count - 1)
    commission_amount, remainder = divmod(gross_amount * commission_rate_bps, 10000)
    # Match round(): nearest integer, with exact halves rounded to even.
    if remainder > 5000 or (remainder == 5000 and commission_amount % 2):
        commission_amount += 1
    return PricingAmounts(
        distance_amount=distance_amount,
        gross_amount=gross_amount,
        commission_amount=commission_amount,
        driver_net_amount=gross_amount - commission_amount,
    )
