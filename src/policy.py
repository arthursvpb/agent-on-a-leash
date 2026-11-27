from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .orders import Order
    from .request import Request


Kind = Literal[
    "ask_order_id",
    "handoff",
    "decline",
    "replacement",
    "refund",
    "needs_approval",
    "replacement_offered",
]


@dataclass(frozen=True)
class Decision:
    kind: Kind
    reason: str
    rule: str
    amount_cents: int | None = None
    approved_by: str | None = None


def decide(
    request: Request, order: Order | None, customer_email: str, today: date
) -> Decision:
    if request.intent != "damaged_item":
        return Decision("handoff", "out_of_scope", "P1")
    if request.order_id is None:
        return Decision("ask_order_id", "missing_id", "P2")
    if order is None:
        return Decision("ask_order_id", "not_found", "P3")
    if order.email.casefold() != customer_email.casefold():
        return Decision("handoff", "identity_mismatch", "P4")
    if order.delivered_on is None:
        return Decision("handoff", "not_delivered", "P5")
    if (today - order.delivered_on).days > 30:
        return Decision("decline", "outside_window", "P6")
    if request.wants == "replacement" and order.in_stock:
        return Decision("replacement", "in_stock", "P7")
    amount = order.price_cents
    if amount <= 15000:
        return Decision("refund", "auto_approved", "P9", amount)
    return Decision("needs_approval", "over_limit", "P10", amount)


def review(
    pending: Decision, answer: Literal["approve", "reject"], reviewer: str
) -> Decision:
    if pending.rule != "P10" or pending.amount_cents is None:
        raise ValueError("Only a pending high-value refund can be reviewed")
    if not reviewer.strip():
        raise ValueError("A reviewer id is required")
    if answer == "approve":
        return Decision("refund", "approved", "H1", pending.amount_cents, reviewer)
    if answer == "reject":
        return Decision("replacement_offered", "rejected", "H2")
    raise ValueError("Answer must be approve or reject")
