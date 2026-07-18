import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.dependencies.auth import get_current_user
from app.models import User
from app.mongo.client import mongo_db
from app.schemas.query import QueryLatency, QueryRequest, RetrievedChunk
from app.services.generation import GenerationConfigError, build_prompt, generate_answer
from app.services.guardrails.audit import log_guardrail_decisions
from app.services.guardrails.pipeline import (
    GuardrailDecision,
    GuardrailPipeline,
    blocking_decision,
    flagged_checks,
)
from app.services.retrieval import embed_query_async, search_similar_chunks
from app.core.config import settings
from app.core.rate_limit import limiter


router = APIRouter(tags=["query"])
guardrail_pipeline = GuardrailPipeline()
NOT_ENOUGH_INFORMATION = "I don't have enough information from the provided trial data to answer that."
UNGROUNDED_REFUSAL = "I can't provide that answer because it could not be grounded in the retrieved trial data."


def milliseconds_since(start: datetime) -> int:
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def log_chat_history(
    user_id: int,
    query_id: str,
    question: str,
    answer: str,
    retrieved_chunks: list[RetrievedChunk],
    latency_ms: QueryLatency,
    guardrail_decisions: list[GuardrailDecision],
) -> None:
    await mongo_db.chat_history.insert_one(
        {
            "user_id": user_id,
            "query_id": query_id,
            "question": question,
            "answer": answer,
            "retrieved_chunk_ids": [chunk.chunk_id for chunk in retrieved_chunks],
            "retrieved_chunk_uids": [chunk.chunk_uid for chunk in retrieved_chunks],
            "guardrail_blocked": blocking_decision(guardrail_decisions) is not None,
            "guardrail_flags": flagged_checks(guardrail_decisions),
            "latency_ms": latency_ms.model_dump(),
            "created_at": datetime.now(timezone.utc),
        }
    )


async def blocked_stream(
    *,
    user_id: int,
    query_id: str,
    question: str,
    answer: str,
    decision: GuardrailDecision,
    decisions: list[GuardrailDecision],
    embed_ms: int = 0,
    retrieval_ms: int = 0,
) -> AsyncIterator[str]:
    await log_guardrail_decisions(user_id=user_id, query_id=query_id, decisions=decisions)
    yield sse_event(
        "guardrail",
        {
            "blocked": True,
            "stage": decision.stage,
            "check_name": decision.check_name,
            "reason": decision.detail or decision.check_name,
        },
    )
    yield sse_event("token", {"text": answer})
    latency = QueryLatency(embed=embed_ms, retrieval=retrieval_ms, llm=0)
    await log_chat_history(
        user_id=user_id,
        query_id=query_id,
        question=question,
        answer=answer,
        retrieved_chunks=[],
        latency_ms=latency,
        guardrail_decisions=decisions,
    )
    yield sse_event(
        "done",
        {
            "answer": answer,
            "blocked": True,
            "reason": decision.detail or decision.check_name,
            "latency_ms": latency.model_dump(),
        },
    )


@router.post("/query")
@limiter.limit(settings.query_rate_limit)
async def query_trials(
    request: Request,
    query_request: QueryRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    query_id = uuid4().hex
    filters = {
        "phase": query_request.phase,
        "status": query_request.status,
        "condition": query_request.condition,
    }
    filters = {key: value for key, value in filters.items() if value}
    guardrail_decisions = guardrail_pipeline.check_input(query_request.question)
    input_block = blocking_decision(guardrail_decisions)
    if input_block is not None:
        return StreamingResponse(
            blocked_stream(
                user_id=current_user.id,
                query_id=query_id,
                question=query_request.question,
                answer=NOT_ENOUGH_INFORMATION,
                decision=input_block,
                decisions=guardrail_decisions,
            ),
            media_type="text/event-stream",
        )

    try:
        embed_started = datetime.now(timezone.utc)
        query_embedding = await embed_query_async(query_request.question)
        embed_ms = milliseconds_since(embed_started)

        retrieval_started = datetime.now(timezone.utc)
        retrieved_chunks = await search_similar_chunks(
            session=session,
            query_embedding=query_embedding,
            question=query_request.question,
            top_k=query_request.top_k,
            filters=filters,
        )
        retrieval_ms = milliseconds_since(retrieval_started)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve relevant trial context",
        ) from exc

    async def stream() -> AsyncIterator[str]:
        await log_guardrail_decisions(
            user_id=current_user.id,
            query_id=query_id,
            decisions=guardrail_decisions,
        )
        yield sse_event(
            "retrieval",
            {"chunks": [chunk.model_dump() for chunk in retrieved_chunks]},
        )

        llm_started = datetime.now(timezone.utc)
        answer_parts: list[str] = []
        retrieval_decisions = guardrail_pipeline.check_retrieval(retrieved_chunks)
        await log_guardrail_decisions(
            user_id=current_user.id,
            query_id=query_id,
            decisions=retrieval_decisions,
        )
        guardrail_decisions.extend(retrieval_decisions)
        retrieval_block = blocking_decision(retrieval_decisions)

        if retrieval_block is not None:
            answer_parts.append(NOT_ENOUGH_INFORMATION)
            yield sse_event(
                "guardrail",
                {
                    "blocked": True,
                    "stage": retrieval_block.stage,
                    "check_name": retrieval_block.check_name,
                    "reason": retrieval_block.detail,
                },
            )
            yield sse_event("token", {"text": NOT_ENOUGH_INFORMATION})
        else:
            prompt = build_prompt(query_request.question, retrieved_chunks)
            try:
                async for text in generate_answer(prompt):
                    answer_parts.append(text)
            except GenerationConfigError:
                answer_parts.append("Generation is not configured.")
                yield sse_event("error", {"message": "Generation is not configured."})
            except Exception:
                answer_parts.append("Generation failed before completion.")
                yield sse_event("error", {"message": "Generation failed before completion."})

        latency = QueryLatency(
            embed=embed_ms,
            retrieval=retrieval_ms,
            llm=milliseconds_since(llm_started),
        )
        answer = "".join(answer_parts)
        if retrieval_block is None:
            output_decisions = guardrail_pipeline.check_output(answer, retrieved_chunks)
            await log_guardrail_decisions(
                user_id=current_user.id,
                query_id=query_id,
                decisions=output_decisions,
            )
            guardrail_decisions.extend(output_decisions)
            output_block = blocking_decision(output_decisions)
            if output_block is not None:
                answer = UNGROUNDED_REFUSAL
                yield sse_event(
                    "guardrail",
                    {
                        "blocked": True,
                        "stage": output_block.stage,
                        "check_name": output_block.check_name,
                        "reason": output_block.detail or output_block.check_name,
                    },
                )
            yield sse_event("token", {"text": answer})
        await log_chat_history(
            user_id=current_user.id,
            query_id=query_id,
            question=query_request.question,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            latency_ms=latency,
            guardrail_decisions=guardrail_decisions,
        )
        yield sse_event(
            "done",
            {
                "answer": answer,
                "blocked": blocking_decision(guardrail_decisions) is not None,
                "guardrail_flags": flagged_checks(guardrail_decisions),
                "latency_ms": latency.model_dump(),
            },
        )

    return StreamingResponse(stream(), media_type="text/event-stream")
