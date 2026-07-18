from app.schemas.query import RetrievedChunk
from app.services.guardrails.input_checks import (
    check_input_length,
    check_input_pii,
    check_prompt_injection,
    check_scope,
)
from app.services.guardrails.output_checks import check_grounding, check_output_pii
from app.services.guardrails.types import GuardrailDecision


class GuardrailPipeline:
    def check_input(self, question: str) -> list[GuardrailDecision]:
        return [
            check_input_length(question),
            check_prompt_injection(question),
            check_input_pii(question),
            check_scope(question),
        ]

    def check_retrieval(self, retrieved_chunks: list[RetrievedChunk]) -> list[GuardrailDecision]:
        if retrieved_chunks:
            top_score = max(chunk.blended_score for chunk in retrieved_chunks)
            return [
                GuardrailDecision(
                    stage="retrieval",
                    check_name="retrieval_confidence",
                    result="pass",
                    detail="retrieved context passed confidence gate",
                    metadata={"top_blended_score": top_score, "chunk_count": len(retrieved_chunks)},
                )
            ]

        return [
            GuardrailDecision(
                stage="retrieval",
                check_name="retrieval_confidence",
                result="block",
                detail="no retrieved chunks passed relevance gates",
                metadata={"chunk_count": 0},
            )
        ]

    def check_output(
        self, answer: str, retrieved_chunks: list[RetrievedChunk]
    ) -> list[GuardrailDecision]:
        return [
            check_grounding(answer, retrieved_chunks),
            check_output_pii(answer, retrieved_chunks),
        ]


def blocking_decision(decisions: list[GuardrailDecision]) -> GuardrailDecision | None:
    return next((decision for decision in decisions if decision.result == "block"), None)


def flagged_checks(decisions: list[GuardrailDecision]) -> list[str]:
    return [decision.check_name for decision in decisions if decision.result == "flag"]
