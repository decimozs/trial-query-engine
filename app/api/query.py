import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies.auth import get_current_user
from app.models import User
from app.schemas.query import QueryRequest
from app.core.config import settings
from app.core.rate_limit import limiter
from app.services.query_workflow import QueryWorkflow


router = APIRouter(tags=["query"])
query_workflow = QueryWorkflow()


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/query")
@limiter.limit(settings.query_rate_limit)
async def query_trials(
    request: Request,
    query_request: QueryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    async def stream():
        async for event in query_workflow.run(
            user_id=current_user.id,
            request=query_request,
            session=session,
        ):
            yield sse_event(event.name, event.data)

    return StreamingResponse(stream(), media_type="text/event-stream")
