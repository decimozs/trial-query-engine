from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.query import QueryLatency, QueryRequest, RetrievedChunk
from app.services.generation import GenerationConfigError, build_prompt, generate_answer
from app.services.guardrails.pipeline import (
    GuardrailDecision,
    GuardrailPipeline,
    blocking_decision,
    flagged_checks,
)
from app.services.persistence import log_chat_history, log_guardrail_decisions
from app.services.retrieval import embed_query_async, search_similar_chunks

NOT_ENOUGH_INFORMATION = "I don't have enough information from the provided trial data to answer that."
UNGROUNDED_REFUSAL = "I can't provide that answer because it could not be grounded in the retrieved trial data."


@dataclass(frozen=True)
class QueryEvent:
    name: str
    data: dict


def milliseconds_since(start: datetime) -> int:
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)


def request_filters(request: QueryRequest) -> dict[str, str]:
    filters = {
        "phase": request.phase,
        "status": request.status,
        "condition": request.condition,
    }
    return {key: value for key, value in filters.items() if value}


class QueryWorkflow:
    def __init__(self, guardrails: GuardrailPipeline | None = None) -> None:
        self.guardrails = guardrails or GuardrailPipeline()

    async def run(
        self,
        *,
        user_id: int,
        request: QueryRequest,
        session: AsyncSession,
    ) -> AsyncIterator[QueryEvent]:
        query_id = uuid4().hex
        decisions = self.guardrails.check_input(request.question)
        input_block = blocking_decision(decisions)
        if input_block is not None:
            async for event in self._blocked(
                user_id=user_id,
                query_id=query_id,
                question=request.question,
                answer=NOT_ENOUGH_INFORMATION,
                decision=input_block,
                decisions=decisions,
            ):
                yield event
            return

        embed_started = datetime.now(timezone.utc)
        query_embedding = await embed_query_async(request.question)
        embed_ms = milliseconds_since(embed_started)

        retrieval_started = datetime.now(timezone.utc)
        retrieved_chunks = await search_similar_chunks(
            session=session,
            query_embedding=query_embedding,
            question=request.question,
            top_k=request.top_k,
            filters=request_filters(request),
        )
        retrieval_ms = milliseconds_since(retrieval_started)

        await log_guardrail_decisions(user_id=user_id, query_id=query_id, decisions=decisions)
        yield QueryEvent("retrieval", {"chunks": [chunk.model_dump() for chunk in retrieved_chunks]})

        llm_started = datetime.now(timezone.utc)
        answer_parts: list[str] = []
        retrieval_decisions = self.guardrails.check_retrieval(retrieved_chunks)
        await log_guardrail_decisions(
            user_id=user_id,
            query_id=query_id,
            decisions=retrieval_decisions,
        )
        decisions.extend(retrieval_decisions)
        retrieval_block = blocking_decision(retrieval_decisions)

        if retrieval_block is not None:
            answer_parts.append(NOT_ENOUGH_INFORMATION)
            yield self._guardrail_event(retrieval_block)
            yield QueryEvent("token", {"text": NOT_ENOUGH_INFORMATION})
        else:
            prompt = build_prompt(request.question, retrieved_chunks)
            try:
                async for text in generate_answer(prompt):
                    answer_parts.append(text)
            except GenerationConfigError:
                answer_parts.append("Generation is not configured.")
                yield QueryEvent("error", {"message": "Generation is not configured."})
            except Exception:
                answer_parts.append("Generation failed before completion.")
                yield QueryEvent("error", {"message": "Generation failed before completion."})

        latency = QueryLatency(
            embed=embed_ms,
            retrieval=retrieval_ms,
            llm=milliseconds_since(llm_started),
        )
        answer = "".join(answer_parts)
        if retrieval_block is None:
            answer, output_block = await self._guard_output(
                user_id=user_id,
                query_id=query_id,
                answer=answer,
                chunks=retrieved_chunks,
                decisions=decisions,
            )
            if output_block is not None:
                yield self._guardrail_event(output_block)
            yield QueryEvent("token", {"text": answer})

        await log_chat_history(
            user_id=user_id,
            query_id=query_id,
            question=request.question,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            latency_ms=latency,
            guardrail_decisions=decisions,
        )
        yield QueryEvent(
            "done",
            {
                "answer": answer,
                "blocked": blocking_decision(decisions) is not None,
                "guardrail_flags": flagged_checks(decisions),
                "latency_ms": latency.model_dump(),
            },
        )

    async def _guard_output(
        self,
        *,
        user_id: int,
        query_id: str,
        answer: str,
        chunks: list[RetrievedChunk],
        decisions: list[GuardrailDecision],
    ) -> tuple[str, GuardrailDecision | None]:
        output_decisions = self.guardrails.check_output(answer, chunks)
        await log_guardrail_decisions(
            user_id=user_id,
            query_id=query_id,
            decisions=output_decisions,
        )
        decisions.extend(output_decisions)
        output_block = blocking_decision(output_decisions)
        if output_block is not None:
            return UNGROUNDED_REFUSAL, output_block
        return answer, None

    async def _blocked(
        self,
        *,
        user_id: int,
        query_id: str,
        question: str,
        answer: str,
        decision: GuardrailDecision,
        decisions: list[GuardrailDecision],
    ) -> AsyncIterator[QueryEvent]:
        await log_guardrail_decisions(user_id=user_id, query_id=query_id, decisions=decisions)
        yield self._guardrail_event(decision)
        yield QueryEvent("token", {"text": answer})
        latency = QueryLatency(embed=0, retrieval=0, llm=0)
        await log_chat_history(
            user_id=user_id,
            query_id=query_id,
            question=question,
            answer=answer,
            retrieved_chunks=[],
            latency_ms=latency,
            guardrail_decisions=decisions,
        )
        yield QueryEvent(
            "done",
            {
                "answer": answer,
                "blocked": True,
                "reason": decision.detail or decision.check_name,
                "latency_ms": latency.model_dump(),
            },
        )

    def _guardrail_event(self, decision: GuardrailDecision) -> QueryEvent:
        return QueryEvent(
            "guardrail",
            {
                "blocked": True,
                "stage": decision.stage,
                "check_name": decision.check_name,
                "reason": decision.detail or decision.check_name,
            },
        )
