from .policy import Decision


def render(decision: Decision, order_id: str | None) -> str:
    if decision.kind == "refund":
        assert decision.amount_cents is not None
        dollars, cents = divmod(decision.amount_cents, 100)
        return f"Your refund of ${dollars}.{cents:02d} has been approved."
    if decision.reason == "not_found":
        return f"I couldn't find {order_id}. Please check the order number and send it again."
    if decision.reason == "not_delivered":
        return "A support specialist can check your delivery status."
    return {
        "handoff": "A support specialist can help with your request.",
        "ask_order_id": "Could you send your order number?",
        "decline": "This order is outside the return window. You can request a human review.",
        "replacement": "Your replacement has been approved.",
        "needs_approval": "Your request is under review.",
        "replacement_offered": "We can offer a replacement or arrange a human review.",
    }[decision.kind]
