from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies.auth import require_admin
from app.models import User
from app.schemas.ingestion import IngestRequest, IngestResponse
from app.services.ingestion import ingest_studies


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_async_session),
) -> IngestResponse:
    studies_ingested = await ingest_studies(request.condition, request.max_studies, session)
    return IngestResponse(studies_ingested=studies_ingested, status="ok")
