import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["damaged_item", "order_status", "other"]
    order_id: str | None
    wants: Literal["refund", "replacement", "unspecified"]
    summary: str = Field(max_length=120)

    @field_validator("order_id")
    @classmethod
    def normalize_id(cls, value: str | None) -> str | None:
        normalized = (value or "").strip().upper()
        return normalized if re.fullmatch(r"A\d{4}", normalized) else None

    @field_validator("summary")
    @classmethod
    def single_line(cls, value: str) -> str:
        return " ".join(value.split())
