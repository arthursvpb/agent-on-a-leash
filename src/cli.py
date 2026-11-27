import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.types import Command

from evals.cases import CASES
from evals.run_local import config_for, observe, run_case, run_eval

from .classifier import ClassifierError, LLMClassifier
from .graph import Graph, build_graph


def demo(graph: Graph, classifier_name: str) -> None:
    for case in CASES:
        if case["id"] not in {"E1", "E2", "E3", "E4", "E6"}:
            continue
        print(case["id"])
        messages = iter(case["messages"])
        waiting = False
        for turn in run_case(graph, case, classifier_name):
            if waiting and (review := case["review"]):
                print("  Reviewer", review["reviewer"], review["decision"])
            else:
                print("  Customer", next(messages))
            nodes = turn["nodes"]
            print("  Nodes   ", " -> ".join(nodes))
            print("  Decision", turn["kind"], f"({turn['rule']})")
            print("  Reply   ", turn["reply"])
            waiting = turn["interrupt"] is not None
            if turn["interrupt"] is not None:
                print("  Internal review", json.dumps(turn["interrupt"]))
        print()


def read_review() -> dict[str, str]:
    answer = input("Reviewer decision (approve/reject)> ").strip().lower()
    while answer not in {"approve", "reject"}:
        answer = input("Enter approve or reject> ").strip().lower()
    reviewer = input("Reviewer ID> ").strip()
    while not reviewer:
        reviewer = input("Enter a reviewer ID> ").strip()
    return {"decision": answer, "reviewer": reviewer}


def chat(graph: Graph, classifier_name: str) -> None:
    ticket_id = f"chat-{uuid4().hex[:8]}"
    config = config_for(ticket_id, ticket_id, "chat", classifier_name)
    email = input("Fictional customer email> ").strip()
    while message := input("Customer message (blank to finish)> ").strip():
        turn = observe(
            graph,
            {"ticket_id": ticket_id, "customer_email": email, "messages": [message]},
            config,
        )
        print(turn["reply"])
        if turn["interrupt"] is not None:
            print("Internal review", json.dumps(turn["interrupt"]))
            answer = read_review()
            resumed = observe(graph, Command(resume=answer), config)
            print(resumed["reply"])


def run(command: str) -> int:
    if command == "graph":
        print(build_graph().get_graph().draw_mermaid())
        return 0
    if command == "eval-langsmith" and not os.getenv("LANGSMITH_API_KEY"):
        print("skipped: no LANGSMITH_API_KEY")
        return 0
    name = os.getenv("CLASSIFIER", "offline")
    if name not in {"llm", "offline"}:
        raise ValueError("CLASSIFIER must be offline or llm")
    model = os.getenv("MODEL", "openai:gpt-4.1-mini")
    classifier = LLMClassifier(model) if name == "llm" else None
    today = date.fromisoformat(os.getenv("LEASH_TODAY", "2026-03-15"))
    graph = build_graph(classifier=classifier, clock=lambda: today)
    if command == "eval-langsmith":
        from evals.run_langsmith import run_hosted

        return run_hosted(graph, name)
    if command == "eval":
        return run_eval(graph, name)
    if command == "demo":
        demo(graph, name)
    else:
        chat(graph, name)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("demo", "chat", "eval", "eval-langsmith", "graph")
    )
    command = parser.parse_args().command
    load_dotenv(Path(".env"))
    os.environ.setdefault("LANGSMITH_PROJECT", "agent-on-a-leash")
    try:
        return run(command)
    except (ClassifierError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    except EOFError:
        print()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
