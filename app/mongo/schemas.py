from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawDocument(BaseModel):
    id: str = Field(alias="_id")
    source: Literal["clinicaltrials.gov"] = "clinicaltrials.gov"
    fetched_at: datetime = Field(default_factory=utc_now)
    raw: dict[str, Any]

    model_config = ConfigDict(populate_by_name=True)


class ChatLatency(BaseModel):
    embed: int
    retrieval: int
    llm: int


class ChatHistory(BaseModel):
    id: ObjectId | None = Field(default=None, alias="_id")
    user_id: int
    query_id: str | None = None
    question: str
    answer: str
    retrieved_chunk_ids: list[int]
    retrieved_chunk_uids: list[str] = Field(default_factory=list)
    guardrail_blocked: bool = False
    guardrail_flags: list[str] = Field(default_factory=list)
    latency_ms: ChatLatency
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)


class IngestionRun(BaseModel):
    id: ObjectId | None = Field(default=None, alias="_id")
    condition_queried: str
    studies_fetched: int
    studies_ingested: int = 0
    studies_skipped: int = 0
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: Literal["success", "failed"]
    error: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)


class GuardrailLog(BaseModel):
    id: ObjectId | None = Field(default=None, alias="_id")
    user_id: int
    query_id: str
    stage: Literal["input", "retrieval", "output"]
    check_name: str
    result: Literal["pass", "block", "flag"]
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)
