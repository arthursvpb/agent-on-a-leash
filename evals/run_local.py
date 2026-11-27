from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.graph import Graph, Ticket
from src.policy import Decision

from .cases import CASES, CaseInput
from .evaluators import Turn, score


def config_for(
    ticket_id: str, thread_id: str, eval_case: str, classifier_name: str
) -> RunnableConfig:
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": f"ticket {ticket_id}",
        "metadata": {
            "thread_id": thread_id,
            "eval_case": eval_case,
            "classifier": classifier_name,
        },
        "tags": ["damaged-order", classifier_name],
    }


def observe(graph: Graph, entry: Ticket | Command[str], config: RunnableConfig) -> Turn:
    nodes: list[str] = []
    for update in graph.stream(entry, config, stream_mode="updates"):
        nodes.extend(key for key in update if key != "__interrupt__")
    snapshot = graph.get_state(config)
    pending = snapshot.interrupts
    decision: Decision = snapshot.values["decision"]
    return {
        "kind": decision.kind,
        "reason": decision.reason,
        "rule": decision.rule,
        "amount_cents": decision.amount_cents,
        "approved_by": decision.approved_by,
        "reply": snapshot.values["reply"],
        "nodes": nodes + list(snapshot.next),
        "waiting_at": list(snapshot.next),
        "interrupt": pending[0].value if pending else None,
    }


def run_case(
    graph: Graph, case: CaseInput, classifier_name: str = "offline"
) -> list[Turn]:
    config = config_for(case["id"], str(uuid4()), case["id"], classifier_name)
    turns: list[Turn] = []
    for message in case["messages"]:
        turn = observe(
            graph,
            {
                "ticket_id": case["id"],
                "customer_email": case["email"],
                "messages": [message],
            },
            config,
        )
        turns.append(turn)
        if turn["interrupt"] is not None:
            if case["review"] is not None:
                command: Command[str] = Command(resume=case["review"])
                turns.append(observe(graph, command, config))
            break
    return turns


def run_eval(graph: Graph, classifier_name: str = "offline") -> int:
    totals: dict[str, int] = {}
    passed = 0
    for index, case in enumerate(CASES):
        scores = score(case, run_case(graph, case, classifier_name))
        if index == 0:
            print("case", *(row["key"] for row in scores), sep="  ")
        values = (str(row["score"]).center(len(row["key"])) for row in scores)
        print("  ".join([f"{case['id']:<4}", *values]).rstrip())
        passed += all(row["score"] == 1 for row in scores)
        for row in scores:
            key = row["key"]
            totals[key] = totals.get(key, 0) + row["score"]
            if not row["score"]:
                print(f"  {key}: {row['comment']}")
    print("  ".join(f"{key} {n}/{len(CASES)}" for key, n in totals.items()))
    print(f"{passed}/{len(CASES)} passed")
    return int(passed != len(CASES))
