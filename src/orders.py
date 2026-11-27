from datetime import date
from importlib.resources import files

from langchain_core.tools import tool
from pydantic import BaseModel, Field, TypeAdapter


class Order(BaseModel, frozen=True):
    order_id: str
    email: str
    item: str
    price_cents: int = Field(strict=True, ge=0)
    delivered_on: date | None
    in_stock: bool


class OrderStore:
    def __init__(self) -> None:
        data = files(__package__).joinpath("orders.json").read_bytes()
        records = TypeAdapter(list[Order]).validate_json(data)
        self._orders = {record.order_id: record for record in records}

    def get(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)


@tool
def lookup_order(order_id: str) -> Order | None:
    """Look up a fictional order by its order number."""
    return OrderStore().get(order_id)
