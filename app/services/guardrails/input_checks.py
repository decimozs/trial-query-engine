import re

from app.core.config import settings
from app.services.guardrails.types import GuardrailDecision

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(the\s+)?(above|previous|prior)",
    r"system\s+prompt",
    r"developer\s+message",
    r"you\s+are\s+now",
    r"act\s+as\s+(dan|a\s+different)",
    r"jailbreak",
    r"reveal\s+(your\s+)?instructions",
    r"role\s*:\s*(system|assistant|developer)",
]

PII_PATTERNS = {
    "email": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "mrn": r"\b(?:mrn|medical\s+record\s+number)\s*[:#-]?\s*[A-Z0-9-]{5,}\b",
}

DOMAIN_TERMS = {
    "a1c",
    "adverse",
    "clinical",
    "condition",
    "criteria",
    "diabetes",
    "eligibility",
    "enroll",
    "exclusion",
    "inclusion",
    "intervention",
    "nct",
    "outcome",
    "patient",
    "phase",
    "placebo",
    "recruiting",
    "study",
    "trial",
    "treatment",
}

OUT_OF_SCOPE_PATTERNS = [
    r"\bwrite\s+me\s+(a\s+)?(poem|song|story)\b",
    r"\bwhat'?s\s+the\s+weather\b",
    r"\bmake\s+me\s+a\s+recipe\b",
    r"\bwrite\s+(python|javascript|sql)\s+code\b",
]


def check_input_length(question: str) -> GuardrailDecision:
    if len(question) > settings.guardrail_max_question_chars:
        return GuardrailDecision(
            stage="input",
            check_name="length",
            result="block",
            detail="question exceeds maximum allowed length",
            metadata={"max_chars": settings.guardrail_max_question_chars, "actual_chars": len(question)},
        )
    return GuardrailDecision(stage="input", check_name="length", result="pass")


def check_prompt_injection(question: str) -> GuardrailDecision:
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, question, flags=re.IGNORECASE):
            return GuardrailDecision(
                stage="input",
                check_name="prompt_injection",
                result="block",
                detail=f"matched pattern: {pattern}",
            )
    return GuardrailDecision(stage="input", check_name="prompt_injection", result="pass")


def detect_pii(text: str) -> list[str]:
    detected = []
    for name, pattern in PII_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            detected.append(name)
    return detected


def check_input_pii(question: str) -> GuardrailDecision:
    detected = detect_pii(question)
    if not detected:
        return GuardrailDecision(stage="input", check_name="pii", result="pass")
    result = "block" if any(item in {"ssn", "mrn"} for item in detected) else "flag"
    return GuardrailDecision(
        stage="input",
        check_name="pii",
        result=result,
        detail="potential PII detected",
        metadata={"entities": detected},
    )


def check_scope(question: str) -> GuardrailDecision:
    lowered = question.lower()
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, lowered):
            return GuardrailDecision(
                stage="input",
                check_name="scope",
                result="block",
                detail=f"out-of-scope request matched pattern: {pattern}",
            )

    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    if tokens & DOMAIN_TERMS:
        return GuardrailDecision(stage="input", check_name="scope", result="pass")
    return GuardrailDecision(
        stage="input",
        check_name="scope",
        result="flag",
        detail="question has low clinical-trial domain signal",
    )
