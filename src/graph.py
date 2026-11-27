import operator
from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from langsmith import traceable
from pydantic import BaseModel, Field

from .classifier import Classifier, OfflineClassifier
from .orders import Order, OrderStore
from .policy import Decision, decide, review
from .replies import render
from .request import Request


class Ticket(TypedDict, total=False):
    ticket_id: str
    customer_email: str
    messages: Annotated[list[str], operator.add]


class State(Ticket, total=False):
    request: Request
    order: Order | None
    decision: Decision
    reply: str
    reviewer: str | None


class Review(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=1)


Graph = CompiledStateGraph[State, None, Ticket, State]
traced_decide = traceable(decide)


def build_graph(
    classifier: Classifier | None = None,
    store: OrderStore | None = None,
    clock: Callable[[], date] = lambda: date(2026, 3, 15),
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> Graph:
    interpreter = classifier or OfflineClassifier()
    orders = store or OrderStore()

    def classify(state: State) -> State:
        request = interpreter.classify(state["messages"][-1])
        previous = state.get("decision")
        if previous and previous.kind == "ask_order_id":
            request = state["request"].model_copy(update={"order_id": request.order_id})
        return {"request": request, "order": None, "reviewer": None}

    def after_classify(state: State) -> Literal["lookup_order", "apply_policy"]:
        request = state["request"]
        if request.intent == "damaged_item" and request.order_id:
            return "lookup_order"
        return "apply_policy"

    def lookup_order(state: State) -> State:
        order_id = state["request"].order_id
        assert order_id is not None
        return {"order": orders.get(order_id)}

    def apply_policy(state: State) -> State:
        decision = traced_decide(
            state["request"], state.get("order"), state["customer_email"], clock()
        )
        if decision.kind == "needs_approval":
            return {
                "decision": decision,
                "reply": render(decision, state["request"].order_id),
            }
        return {"decision": decision}

    def after_policy(state: State) -> Literal["human_approval", "finalize"]:
        if state["decision"].kind == "needs_approval":
            return "human_approval"
        return "finalize"

    def human_approval(state: State) -> State:
        order = state["order"]
        assert order is not None
        pending = state["decision"]
        payload = {
            "ticket_id": state["ticket_id"],
            "order_id": order.order_id,
            "item": order.item,
            "amount_cents": pending.amount_cents,
            "rule": pending.rule,
        }
        answer = interrupt(payload, response_schema=Review)
        decision = review(pending, answer.decision, answer.reviewer)
        return {
            "decision": decision,
            "reviewer": answer.reviewer,
        }

    def finalize(state: State) -> State:
        return {"reply": render(state["decision"], state["request"].order_id)}

    flow = StateGraph(State, input_schema=Ticket, output_schema=State)
    flow.add_node(classify)
    flow.add_node(lookup_order)
    flow.add_node(apply_policy)
    flow.add_node(human_approval)
    flow.add_node(finalize)
    flow.add_edge(START, "classify")
    flow.add_conditional_edges("classify", after_classify)
    flow.add_edge("lookup_order", "apply_policy")
    flow.add_conditional_edges("apply_policy", after_policy)
    flow.add_edge("human_approval", "finalize")
    flow.add_edge("finalize", END)
    saver = InMemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=[Order, Request, Decision])
    )
    return flow.compile(checkpointer=checkpointer or saver)
