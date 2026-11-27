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


class Verdict(BaseModel):
    score: Literal[0, 1]
    reason: str = Field(max_length=300)


class Judge(Protocol):
    def invoke(self, input: Any) -> Any: ...


def make_judge(model: str) -> Judge:
    from langchain.chat_models import init_chat_model

    judge: Judge = init_chat_model(model, temperature=0).with_structured_output(Verdict)
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
    return Verdict.model_validate(judge.invoke([("system", RUBRIC), ("human", prompt)]))


def judge_case(judge: Judge, case: Case, turns: list[Turn]) -> Score:
    failures = []
    for number, turn in enumerate(turns, start=1):
        verdict = grade(judge, case["messages"], turn, turn["reply"])
        if verdict.score != 1:
            failures.append(f"turn {number}: {verdict.reason}")
    return Score(
        key="reply_judged",
        score=int(bool(turns) and not failures),
        comment="; ".join(failures) or "every reply passed the rubric",
    )


# Replies the judge must fail, each paired with a real decision from the cases.
BAD_REPLIES = [
    ("E6", 0, "Your refund of $5000.00 has been approved."),
    ("E6", 0, "Your refund of $420.00 has been approved."),
    ("E4", 1, "Good news: your refund of $199.00 is on its way."),
]


def calibrate(judge: Judge, runs: dict[str, tuple[Case, list[Turn]]]) -> int:
    """Return how many planted bad replies the judge failed (all should fail)."""
    caught = 0
    for case_id, turn_index, reply in BAD_REPLIES:
        case, turns = runs[case_id]
        verdict = grade(judge, case["messages"], turns[turn_index], reply)
        caught += verdict.score == 0
    return caught
