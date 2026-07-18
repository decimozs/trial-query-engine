from dataclasses import dataclass, field
from typing import Literal

GuardrailStage = Literal["input", "retrieval", "output"]
GuardrailResult = Literal["pass", "block", "flag"]


@dataclass(frozen=True)
class GuardrailDecision:
    stage: GuardrailStage
    check_name: str
    result: GuardrailResult
    detail: str | None = None
    metadata: dict = field(default_factory=dict)
