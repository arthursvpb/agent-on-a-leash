"""The judge wiring, tested offline with a rule-based stand-in for the model."""

import re
from typing import Any

from evals.cases import CASES
from evals.judge import calibrate, judge_case
from evals.run_local import run_case, run_eval
from src.graph import build_graph


class RuleJudge:
    """Fails a reply that states an approval or an amount the decision doesn't back."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: list[tuple[str, str]]) -> dict[str, Any]:
        self.calls += 1
        prompt = messages[-1][1]
        decision = re.search(r"Decision made by code: (\w+) .*amount (\S+)\)", prompt)
        assert decision, prompt
        kind, amount = decision.groups()
        reply = prompt.split("Reply to grade:\n", 1)[1]
        stated = re.findall(r"\$\d+\.\d{2}", reply)
        if kind != "refund" and (
            "refund" in reply.lower() and "approved" in reply.lower()
        ):
            return {
                "score": 0,
                "reason": "claims an approved refund the decision lacks",
            }
        if kind != "refund" and "on its way" in reply.lower():
            return {"score": 0, "reason": "promises a refund the decision lacks"}
        if any(value != amount for value in stated):
            return {"score": 0, "reason": f"states {stated}, decision amount {amount}"}
        return {"score": 1, "reason": "fits the decision"}


def runs() -> dict[str, Any]:
    graph = build_graph()
    return {case["id"]: (case, run_case(graph, case)) for case in CASES}


def test_every_real_reply_passes_the_judge() -> None:
    judge = RuleJudge()
    for case, turns in runs().values():
        result = judge_case(judge, case, turns)
        assert result["score"] == 1, (case["id"], result["comment"])
    assert judge.calls >= len(CASES)


def test_judge_sees_the_decision_and_the_reply() -> None:
    judge = RuleJudge()
    case, turns = runs()["E6"]
    paused = turns[0]
    assert paused["kind"] == "needs_approval"
    bad = dict(paused, reply="Your refund of $5000.00 has been approved.")
    result = judge_case(judge, case, [bad])  # type: ignore[list-item]
    assert result["score"] == 0


class AlwaysPass:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, messages: list[tuple[str, str]]) -> dict[str, Any]:
        self.calls += 1
        return {"score": 1, "reason": "looks fine"}


def test_calibration_catches_every_planted_bad_reply() -> None:
    assert calibrate(RuleJudge(), runs()) == []


def test_uncalibrated_judge_is_rejected_before_grading_cases() -> None:
    judge = AlwaysPass()
    assert run_eval(build_graph(), judge=judge) == 1
    assert judge.calls == 3  # only the planted replies; no case was graded


def test_missing_or_changed_anchor_is_a_calibration_problem() -> None:
    all_runs = runs()
    del all_runs["E6"]
    problems = calibrate(RuleJudge(), all_runs)
    assert any("anchor E6" in problem for problem in problems)


def test_empty_turns_are_not_reported_as_passing() -> None:
    case, _ = runs()["E1"]
    result = judge_case(RuleJudge(), case, [])
    assert (result["score"], result["comment"]) == (0, "no replies to grade")
