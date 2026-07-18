from pydantic import BaseModel, Field

from app.core.config import settings


class IngestRequest(BaseModel):
    condition: str = Field(min_length=1)
    max_studies: int = Field(default=settings.ingest_default_max_studies, ge=1, le=1000)


class IngestResponse(BaseModel):
    studies_ingested: int
    status: str
