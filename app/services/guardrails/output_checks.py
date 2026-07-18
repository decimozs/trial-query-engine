import re

from app.core.config import settings
from app.schemas.query import RetrievedChunk
from app.services.guardrails.input_checks import detect_pii
from app.services.guardrails.types import GuardrailDecision

SAFE_FALLBACK_PREFIXES = (
    "I don't have enough information from the provided trial data",
    "I can't provide that answer because it could not be grounded",
    "Generation is not configured.",
    "Generation failed before completion.",
)

STOPWORDS = {
    "about",
    "after",
    "also",
    "answer",
    "because",
    "between",
    "could",
    "from",
    "have",
    "into",
    "that",
    "their",
    "there",
    "these",
    "this",
    "trial",
    "trials",
    "using",
    "with",
    "would",
}


def meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in STOPWORDS
    }


def grounding_overlap(answer: str, chunks: list[RetrievedChunk]) -> float:
    answer_tokens = meaningful_tokens(answer)
    if not answer_tokens:
        return 1.0
    context_tokens = meaningful_tokens(" ".join(chunk.chunk_text for chunk in chunks))
    if not context_tokens:
        return 0.0
    return len(answer_tokens & context_tokens) / len(answer_tokens)


def check_grounding(answer: str, chunks: list[RetrievedChunk]) -> GuardrailDecision:
    if answer.startswith(SAFE_FALLBACK_PREFIXES):
        return GuardrailDecision(stage="output", check_name="grounding", result="pass")

    overlap = grounding_overlap(answer, chunks)
    if overlap < settings.guardrail_min_grounding_overlap:
        return GuardrailDecision(
            stage="output",
            check_name="grounding",
            result="block",
            detail="answer has low overlap with retrieved context",
            metadata={"overlap": overlap, "min_overlap": settings.guardrail_min_grounding_overlap},
        )
    return GuardrailDecision(
        stage="output",
        check_name="grounding",
        result="pass",
        metadata={"overlap": overlap},
    )


def check_output_pii(answer: str, chunks: list[RetrievedChunk]) -> GuardrailDecision:
    detected = detect_pii(answer)
    if not detected:
        return GuardrailDecision(stage="output", check_name="pii", result="pass")

    context = " ".join(chunk.chunk_text for chunk in chunks)
    context_entities = set(detect_pii(context))
    result = "flag" if set(detected).issubset(context_entities) else "block"
    return GuardrailDecision(
        stage="output",
        check_name="pii",
        result=result,
        detail="potential PII detected in generated answer",
        metadata={"entities": detected},
    )
