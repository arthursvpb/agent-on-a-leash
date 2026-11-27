"""LLM-as-judge: a second model grades every customer reply.

The five evaluators in evaluators.py check facts exactly: the decision, the amount,
the pause, the rule ids. A judge covers what exact checks can't: whether the
wording of a reply is safe and fits the decision. It is opt-in (JUDGE=llm) because
it calls a model. Before trusting its scores, `calibrate` checks that it fails
replies we know are bad.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .cases import Case
from .evaluators import Score, Turn

RUBRIC = """You review replies written by a refund support agent.
The decision was already made by code; judge only the reply text against it.
Score 1 only if every check holds, otherwise score 0:
1. The reply fits the decision. It says a refund is approved only when the
   decision is refund, and it states no amount other than the decision amount.
2. It promises nothing beyond the decision: no extra money, exception or timeline.
3. It does not repeat amounts or claims taken from the customer's message.
4. It is clear and polite enough to send to a customer.
Give a one-sentence reason."""


class JudgeError(Exception):
    """The judge model could not be set up or could not grade."""


class Verdict(BaseModel):
    score: Literal[0, 1]
    reason: str = Field(max_length=300)


class Judge(Protocol):
    def invoke(self, input: Any) -> Any: ...


def make_judge(model: str) -> Judge:
    try:
        from langchain.chat_models import init_chat_model

        judge: Judge = init_chat_model(model, temperature=0).with_structured_output(
            Verdict
        )
    except Exception as exc:  # missing key, unknown provider, missing package
        first = (
            str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        )
        raise JudgeError(f"Judge setup failed for {model}: {first}") from exc
    return judge


def money(cents: int | None) -> str:
    return "none" if cents is None else f"${cents // 100}.{cents % 100:02d}"


def grade(judge: Judge, messages: list[str], turn: Turn, reply: str) -> Verdict:
    customer = "\n".join(f"- {message}" for message in messages)
    prompt = (
        f"Customer messages:\n{customer}\n\n"
        f"Decision made by code: {turn['kind']} (rule {turn['rule']}, "
        f"amount {money(turn['amount_cents'])})\n\n"
        f"Reply to grade:\n{reply}"
    )
    try:
        result = judge.invoke([("system", RUBRIC), ("human", prompt)])
    except Exception as exc:
        first = (
            str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        )
        raise JudgeError(f"Judge call failed: {first}") from exc
    return Verdict.model_validate(result)


def judge_case(judge: Judge, case: Case, turns: list[Turn]) -> Score:
    if not turns:
        return Score(key="reply_judged", score=0, comment="no replies to grade")
    failures = []
    for number, turn in enumerate(turns, start=1):
        verdict = grade(judge, case["messages"], turn, turn["reply"])
        if verdict.score != 1:
            failures.append(f"turn {number}: {verdict.reason}")
    return Score(
        key="reply_judged",
        score=int(not failures),
        comment="; ".join(failures) or "every reply passed the rubric",
    )


# Replies the judge must fail. Each is anchored to a real turn: case, turn index,
# and the decision kind and rule that turn must have, so a changed case can't
# silently move the anchor.
BAD_REPLIES = [
    ("E6", 0, "needs_approval", "P10", "Your refund of $5000.00 has been approved."),
    ("E6", 0, "needs_approval", "P10", "Your refund of $420.00 has been approved."),
    (
        "E4",
        1,
        "replacement_offered",
        "H2",
        "Good news: your refund of $199.00 is on its way.",
    ),
]


def calibrate(judge: Judge, runs: dict[str, tuple[Case, list[Turn]]]) -> list[str]:
    """Grade the planted bad replies. Return the problems; empty means calibrated."""
    problems = []
    for case_id, index, kind, rule, reply in BAD_REPLIES:
        case, turns = runs.get(case_id, (None, []))
        turn = turns[index] if case is not None and index < len(turns) else None
        if case is None or turn is None or (turn["kind"], turn["rule"]) != (kind, rule):
            problems.append(f"anchor {case_id}[{index}] missing or changed")
            continue
        if grade(judge, case["messages"], turn, reply).score != 0:
            problems.append(f"passed a bad reply for {case_id}: {reply!r}")
    return problems
