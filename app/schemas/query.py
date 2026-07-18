from pydantic import BaseModel, Field

from app.core.config import settings


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=settings.rag_top_k, ge=1, le=20)
    phase: str | None = None
    status: str | None = None
    condition: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: int
    chunk_uid: str
    chunk_source: str
    document_id: int
    nct_id: str
    title: str
    chunk_text: str
    distance: float
    semantic_score: float
    keyword_score: float
    blended_score: float


class QueryLatency(BaseModel):
    embed: int
    retrieval: int
    llm: int


class QueryResponse(BaseModel):
    answer: str
    retrieved_chunks: list[RetrievedChunk]
    latency_ms: QueryLatency
