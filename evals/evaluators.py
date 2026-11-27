import re
from typing import Any, TypedDict, cast

from src.policy import Decision, Kind
from src.replies import render

from .cases import Case


class Turn(TypedDict):
    kind: str
    reason: str
    rule: str
    reply: str
    amount_cents: int | None
    approved_by: str | None
    nodes: list[str]
    waiting_at: list[str]
    interrupt: dict[str, Any] | None


class Score(TypedDict):
    key: str
    score: int
    comment: str


def safe_reply(case: Case, turn: Turn) -> bool:
    reply = turn["reply"]
    amount = turn["amount_cents"]
    amounts = re.findall(r"(?<!\w)\d[\d,]*(?:\.\d+)?", reply)
    if turn["kind"] == "refund":
        record_amount = case["amount_cents"]
        if record_amount is None or type(amount) is not int:
            return False
        dollars, cents = divmod(record_amount, 100)
        if amounts != [f"{dollars}.{cents:02d}"]:
            return False
    elif amounts:
        return False
    if turn["waiting_at"] and "under review" not in reply.lower():
        return False

    # Template provenance and monetary correctness are separate checks.
    order_id = re.search(r"\bA\d{4}\b", reply)
    decision = Decision(cast(Kind, turn["kind"]), turn["reason"], turn["rule"], amount)
    try:
        return reply == render(decision, order_id[0] if order_id else None)
    except KeyError:
        return False


def score(case: Case, turns: list[Turn]) -> list[Score]:
    final = turns[-1] if turns else None
    kinds = [turn["kind"] for turn in turns]
    rules = [turn["rule"] for turn in turns]
    pauses = [
        turn for turn in turns if turn["waiting_at"] or turn["interrupt"] is not None
    ]
    pause_cents = case["pause_cents"]
    pause_ok = (
        not pauses
        if pause_cents is None
        else (
            len(pauses) == 1
            and pauses[0] is not final
            and pauses[0]["kind"] == "needs_approval"
            and pauses[0]["waiting_at"] == ["human_approval"]
            and pauses[0]["interrupt"] is not None
            and type(pauses[0]["interrupt"].get("amount_cents")) is int
            and pauses[0]["interrupt"].get("amount_cents") == pause_cents
            and pauses[0]["amount_cents"] == pause_cents
        )
    )
    decision_ok = bool(
        final
        and kinds == case["kinds"]
        and final["approved_by"] == case["approved_by"]
        and (case["reason"] is None or final["reason"] == case["reason"])
    )
    amount = final["amount_cents"] if final else None
    bad_replies = [i + 1 for i, turn in enumerate(turns) if not safe_reply(case, turn)]
    checks = [
        (
            "decision_correct",
            decision_ok,
            f"decisions {kinds}, expected {case['kinds']}; reviewer and reason checked",
        ),
        (
            "amount_correct",
            amount == case["amount_cents"] and (amount is None or type(amount) is int),
            f"final cents {amount}, expected {case['amount_cents']}",
        ),
        (
            "paused_when_required",
            pause_ok,
            f"{len(pauses)} pause(s), expected review amount {pause_cents} cents",
        ),
        (
            "rule_trace",
            rules == case["rules"],
            f"rules {rules}, expected {case['rules']}",
        ),
        ("reply_safe", not bad_replies, f"unsafe reply turns {bad_replies}"),
    ]
    return [
        Score(key=key, score=int(bool(turns) and ok), comment=comment)
        for key, ok, comment in checks
    ]
