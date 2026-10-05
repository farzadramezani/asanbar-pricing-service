import pytest

from app.calculation import calculate_price


def test_assignment_example_and_amount_balance():
    amounts = calculate_price(450, 2, 12000, 500000, 1000)
    assert amounts.distance_amount == 5400000
    assert amounts.gross_amount == 5900000
    assert amounts.commission_amount == 590000
    assert amounts.driver_net_amount == 5310000
    assert amounts.commission_amount + amounts.driver_net_amount == amounts.gross_amount


@pytest.mark.parametrize(('gross', 'expected'), [(4, 0), (5, 0), (6, 1), (15, 2), (25, 2), (26, 3)])
def test_integer_commission_rounding(gross, expected):
    amounts = calculate_price(1, 1, gross, 999, 1000)
    assert amounts.commission_amount == expected
    assert amounts.gross_amount == gross  # No fee for the first stop.
    assert amounts.driver_net_amount + amounts.commission_amount == gross


def test_large_integer_amounts_do_not_lose_precision():
    gross = 10**18 + 15
    amounts = calculate_price(1, 1, gross, 0, 1000)
    assert amounts.commission_amount == 10**17 + 2
    assert amounts.driver_net_amount + amounts.commission_amount == gross


@pytest.mark.parametrize('bps', [0, 1, 1000, 3333, 10000])
def test_balance_for_multiple_stops_and_commissions(bps):
    amounts = calculate_price(17, 4, 123, 456, bps)
    assert amounts.gross_amount == 17 * 123 + 3 * 456
    assert amounts.gross_amount == amounts.driver_net_amount + amounts.commission_amount
