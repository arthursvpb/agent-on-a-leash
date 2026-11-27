"""Policy boundaries: the rules that decide money, tested without any model."""

from datetime import date

import pytest

from src.orders import Order
from src.policy import decide, review
from src.request import Request

TODAY = date(2026, 3, 15)


def order(
    price_cents: int = 2400, days_ago: int | None = 3, in_stock: bool = True
) -> Order:
    delivered = (
        None if days_ago is None else date.fromordinal(TODAY.toordinal() - days_ago)
    )
    return Order(
        order_id="A9000",
        email="test@example.com",
        item="Test item",
        price_cents=price_cents,
        delivered_on=delivered,
        in_stock=in_stock,
    )


def request(wants: str = "refund") -> Request:
    return Request(
        intent="damaged_item", order_id="A9000", wants=wants, summary="damaged"
    )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("price", "kind", "rule"),
    [(15000, "refund", "P9"), (15001, "needs_approval", "P10")],
)
def test_approval_threshold(price: int, kind: str, rule: str) -> None:
    decision = decide(request(), order(price_cents=price), "test@example.com", TODAY)
    assert (decision.kind, decision.rule, decision.amount_cents) == (kind, rule, price)


@pytest.mark.parametrize(("days", "kind"), [(30, "refund"), (31, "decline")])
def test_return_window(days: int, kind: str) -> None:
    assert (
        decide(request(), order(days_ago=days), "test@example.com", TODAY).kind == kind
    )


def test_sender_must_match_order_case_insensitively() -> None:
    assert decide(request(), order(), "TEST@Example.com", TODAY).kind == "refund"
    assert decide(request(), order(), "other@example.com", TODAY).rule == "P4"


def test_out_of_stock_replacement_falls_back_to_refund() -> None:
    decision = decide(
        request("replacement"), order(in_stock=False), "test@example.com", TODAY
    )
    assert decision.kind == "refund"


def test_only_a_pending_refund_can_be_reviewed() -> None:
    pending = decide(request(), order(price_cents=42000), "test@example.com", TODAY)
    assert review(pending, "approve", "reviewer-7").approved_by == "reviewer-7"
    assert review(pending, "reject", "reviewer-7").kind == "replacement_offered"
    with pytest.raises(ValueError):
        review(decide(request(), order(), "test@example.com", TODAY), "approve", "r")
