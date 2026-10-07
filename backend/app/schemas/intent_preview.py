from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


CardFactor = Literal["distance", "safety", "streetlight", "cctv", "stairs", "crossing", "bridge", "time"]
CardState = Literal["analyzing", "applied", "not_applied"]
CARD_ORDER = ("distance", "safety", "streetlight", "cctv", "stairs", "crossing", "bridge", "time")


class ConditionCard(BaseModel):
    factor: CardFactor
    state: CardState
    direction: Literal["maximize", "minimize", "avoid"] | None = None
    period: Literal["day", "night"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    judgment: Literal["apply", "skip", "pending", "avoid", "minimize", "day", "night"] | None = None


class IntentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain text")
        return value


class IntentPreviewResponse(BaseModel):
    query: str
    model: str
    conditions: list[ConditionCard]
    cached: bool = False
    input_tokens: int | None = None


class IntentPreviewStatus(BaseModel):
    enabled: bool
    configured: bool
    available: bool
