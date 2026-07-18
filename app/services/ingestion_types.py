from dataclasses import dataclass


@dataclass(frozen=True)
class StudyMetadata:
    nct_id: str
    title: str
    condition: str | None
    phase: str | None
    status: str | None
    brief_summary: str


@dataclass(frozen=True)
class StudyTextSection:
    source: str
    text: str
