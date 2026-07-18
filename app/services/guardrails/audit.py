from datetime import datetime, timezone

from app.mongo.client import mongo_db
from app.services.guardrails.types import GuardrailDecision


async def log_guardrail_decisions(
    *,
    user_id: int,
    query_id: str,
    decisions: list[GuardrailDecision],
) -> None:
    if not decisions:
        return

    await mongo_db.guardrail_log.insert_many(
        [
            {
                "user_id": user_id,
                "query_id": query_id,
                "stage": decision.stage,
                "check_name": decision.check_name,
                "result": decision.result,
                "detail": decision.detail,
                "metadata": decision.metadata,
                "created_at": datetime.now(timezone.utc),
            }
            for decision in decisions
        ]
    )
