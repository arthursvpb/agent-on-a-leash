from collections import Counter
from collections.abc import Callable, Iterator
from typing import Any, cast
from uuid import uuid5

from langsmith import Client
from langsmith.schemas import Example

from src.graph import Graph

from .cases import CASES, Case, CaseInput
from .evaluators import Score, Turn, score
from .judge import Judge, judge_case
from .run_local import run_case

DATASET = "agent-on-a-leash-cases"


def dataset_cases(client: Client) -> Iterator[Example]:
    dataset = (
        client.read_dataset(dataset_name=DATASET)
        if client.has_dataset(dataset_name=DATASET)
        else client.create_dataset(DATASET)
    )
    existing = {
        (row.inputs or {}).get("id"): row.id
        for row in client.list_examples(dataset_id=dataset.id)
    }
    ids = []
    missing = []
    for case in CASES:
        case_id = case["id"]
        if case_id in existing:
            ids.append(existing[case_id])
            continue
        example_id = uuid5(dataset.id, case_id)
        ids.append(example_id)
        inputs = {
            key: value
            for key, value in case.items()
            if key in CaseInput.__annotations__
        }
        reference = {key: value for key, value in case.items() if key not in inputs}
        missing.append(
            {"id": example_id, "inputs": inputs, "reference_outputs": reference}
        )
    if missing:
        client.create_examples(dataset_id=dataset.id, examples=missing)
    return client.list_examples(dataset_id=dataset.id, example_ids=ids)


def evaluate_case(
    inputs: dict[str, Any], outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, list[Score]]:
    case = cast(Case, {**inputs, **reference_outputs})
    return {"results": score(case, outputs.get("turns", []))}


def judged_case(judge: Judge) -> Callable[..., dict[str, list[Score]]]:
    def reply_judged(
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        reference_outputs: dict[str, Any],
    ) -> dict[str, list[Score]]:
        case = cast(Case, {**inputs, **reference_outputs})
        return {"results": [judge_case(judge, case, outputs.get("turns", []))]}

    return reply_judged


def run_hosted(graph: Graph, classifier_name: str, judge: Judge | None = None) -> int:
    client = Client()
    expected = 5 if judge is None else 6

    def target(inputs: dict[str, Any]) -> dict[str, list[Turn]]:
        return {"turns": run_case(graph, cast(CaseInput, inputs), classifier_name)}

    rows = client.evaluate(
        target,
        data=dataset_cases(client),
        evaluators=[evaluate_case]
        if judge is None
        else [evaluate_case, judged_case(judge)],
        experiment_prefix="damaged-order",
        metadata={"classifier": classifier_name},
    )
    totals: Counter[str] = Counter()
    passed = 0
    for row in rows:
        results = row["evaluation_results"]["results"]
        for result in results:
            totals[result.key] += result.score == 1
        passed += len(results) == expected and all(
            result.score == 1 for result in results
        )
    print("  ".join(f"{key} {total}/{len(CASES)}" for key, total in totals.items()))
    print(f"{passed}/{len(CASES)} passed")
    return int(passed != len(CASES))
