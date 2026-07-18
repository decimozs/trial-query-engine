from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from typing import Any

import asyncio
import httpx
import anyio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Document, DocumentChunk
from app.mongo.client import mongo_db


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


def get_nested(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def first_or_join(value: Any) -> str | None:
    if isinstance(value, list):
        items = [str(item) for item in value if item]
        return ", ".join(items) if items else None
    return str(value) if value else None


async def fetch_studies(condition: str, max_studies: int) -> list[dict[str, Any]]:
    studies: list[dict[str, Any]] = []
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while len(studies) < max_studies:
            remaining = max_studies - len(studies)
            params: dict[str, Any] = {
                "query.cond": condition,
                "pageSize": min(settings.ingest_page_size, remaining),
                "format": "json",
            }
            if page_token:
                params["pageToken"] = page_token

            response = await client.get(
                f"{settings.clinicaltrials_base_url}/studies", params=params
            )
            response.raise_for_status()
            payload = response.json()

            studies.extend(payload.get("studies", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
            if settings.clinicaltrials_page_delay_seconds > 0:
                await asyncio.sleep(settings.clinicaltrials_page_delay_seconds)

    return studies[:max_studies]


def extract_metadata(study: dict[str, Any]) -> StudyMetadata | None:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    nct_id = identification.get("nctId")
    title = identification.get("briefTitle") or identification.get("officialTitle")
    brief_summary = get_nested(protocol, ("descriptionModule", "briefSummary")) or title

    if not nct_id or not title or not brief_summary:
        return None

    return StudyMetadata(
        nct_id=str(nct_id),
        title=str(title),
        condition=first_or_join(get_nested(protocol, ("conditionsModule", "conditions"))),
        phase=first_or_join(get_nested(protocol, ("designModule", "phases"))),
        status=get_nested(protocol, ("statusModule", "overallStatus")),
        brief_summary=str(brief_summary),
    )


def extract_intervention_text(protocol: dict[str, Any]) -> str | None:
    interventions = get_nested(protocol, ("armsInterventionsModule", "interventions"))
    if not isinstance(interventions, list):
        return None

    lines = []
    for intervention in interventions:
        if not isinstance(intervention, dict):
            continue
        name = intervention.get("name")
        description = intervention.get("description")
        if name or description:
            lines.append(f"{name or 'Intervention'}: {description or ''}".strip())
    return "\n".join(lines) if lines else None


def extract_outcome_text(protocol: dict[str, Any]) -> str | None:
    outcomes_module = protocol.get("outcomesModule", {})
    lines = []
    for key in ("primaryOutcomes", "secondaryOutcomes"):
        outcomes = outcomes_module.get(key)
        if not isinstance(outcomes, list):
            continue
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            measure = outcome.get("measure")
            time_frame = outcome.get("timeFrame")
            if measure or time_frame:
                lines.append(f"{measure or 'Outcome'} ({time_frame or 'time frame not specified'})")
    return "\n".join(lines) if lines else None


def extract_text_sections(study: dict[str, Any], metadata: StudyMetadata) -> list[StudyTextSection]:
    protocol = study.get("protocolSection", {})
    section_values = [
        ("brief_summary", metadata.brief_summary),
        ("detailed_description", get_nested(protocol, ("descriptionModule", "detailedDescription"))),
        ("eligibility_criteria", get_nested(protocol, ("eligibilityModule", "eligibilityCriteria"))),
        ("interventions", extract_intervention_text(protocol)),
        ("outcomes", extract_outcome_text(protocol)),
    ]

    sections: list[StudyTextSection] = []
    seen = set()
    for source, text in section_values:
        if not text:
            continue
        normalized = " ".join(str(text).split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        sections.append(StudyTextSection(source=source, text=normalized))

    return sections


async def store_raw_document(study: dict[str, Any]) -> bool:
    metadata = extract_metadata(study)
    if metadata is None:
        return False

    await mongo_db.raw_documents.replace_one(
        {"_id": metadata.nct_id},
        {
            "_id": metadata.nct_id,
            "source": "clinicaltrials.gov",
            "fetched_at": datetime.now(timezone.utc),
            "raw": study,
        },
        upsert=True,
    )
    return True


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size_words,
    overlap: int = settings.chunk_overlap_words,
) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size:
        return [" ".join(words)]

    chunks: list[str] = []
    step = max(chunk_size - overlap, 1)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + chunk_size]
        if chunk_words:
            chunks.append(" ".join(chunk_words))
        if start + chunk_size >= len(words):
            break

    return chunks


def chunk_sections(sections: list[StudyTextSection]) -> list[StudyTextSection]:
    chunks: list[StudyTextSection] = []
    for section in sections:
        for chunk in chunk_text(section.text):
            chunks.append(StudyTextSection(source=section.source, text=chunk))
    return chunks


def make_chunk_uid(nct_id: str, source: str, chunk_index: int, chunk_text: str) -> str:
    value = f"{nct_id}\0{source}\0{chunk_index}\0{chunk_text}".encode("utf-8")
    return sha256(value).hexdigest()


@lru_cache(maxsize=1)
def get_embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model_name)


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    if not chunks:
        return []
    embeddings = get_embedding_model().encode(chunks, normalize_embeddings=True)
    return [embedding.tolist() for embedding in embeddings]


async def embed_chunks_async(chunks: list[str]) -> list[list[float]]:
    return await anyio.to_thread.run_sync(embed_chunks, chunks)


async def store_document_and_chunks(
    metadata: StudyMetadata,
    chunks: list[StudyTextSection],
    embeddings: list[list[float]],
    session: AsyncSession,
) -> bool:
    if not chunks or len(chunks) != len(embeddings):
        return False

    result = await session.execute(select(Document).where(Document.nct_id == metadata.nct_id))
    document = result.scalar_one_or_none()
    if document is None:
        document = Document(nct_id=metadata.nct_id, title=metadata.title)
        session.add(document)
        await session.flush()

    document.title = metadata.title
    document.condition = metadata.condition
    document.phase = metadata.phase
    document.status = metadata.status
    document.brief_summary = metadata.brief_summary

    chunk_uids = [make_chunk_uid(metadata.nct_id, chunk.source, index, chunk.text) for index, chunk in enumerate(chunks)]
    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.chunk_uid.not_in(chunk_uids),
        )
    )
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        chunk_uid = chunk_uids[index]
        result = await session.execute(select(DocumentChunk).where(DocumentChunk.chunk_uid == chunk_uid))
        document_chunk = result.scalar_one_or_none()
        if document_chunk is None:
            document_chunk = DocumentChunk(
                document_id=document.id,
                chunk_uid=chunk_uid,
                chunk_source=chunk.source,
                chunk_index=index,
                chunk_text=chunk.text,
                embedding=embedding,
            )
        else:
            document_chunk.document_id = document.id
            document_chunk.chunk_source = chunk.source
            document_chunk.chunk_index = index
            document_chunk.chunk_text = chunk.text
            document_chunk.embedding = embedding
        session.add(
            document_chunk
        )

    await session.commit()
    return True


async def ingest_studies(
    condition: str,
    max_studies: int,
    session: AsyncSession,
) -> int:
    started_at = datetime.now(timezone.utc)
    run_id = None
    ingested = 0
    skipped = 0

    try:
        studies = await fetch_studies(condition, max_studies)
        run = await mongo_db.ingestion_runs.insert_one(
            {
                "condition_queried": condition,
                "studies_fetched": len(studies),
                "studies_ingested": 0,
                "studies_skipped": 0,
                "started_at": started_at,
                "status": "success",
                "error": None,
            }
        )
        run_id = run.inserted_id

        for study in studies:
            metadata = extract_metadata(study)
            if metadata is None:
                skipped += 1
                continue

            await store_raw_document(study)
            chunks = chunk_sections(extract_text_sections(study, metadata))
            embeddings = await embed_chunks_async([chunk.text for chunk in chunks])
            stored = await store_document_and_chunks(metadata, chunks, embeddings, session)
            if stored:
                ingested += 1
            else:
                skipped += 1

        await mongo_db.ingestion_runs.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "studies_ingested": ingested,
                    "studies_skipped": skipped,
                    "completed_at": datetime.now(timezone.utc),
                    "status": "success",
                }
            },
        )
    except Exception as exc:
        if run_id is None:
            await mongo_db.ingestion_runs.insert_one(
                {
                    "condition_queried": condition,
                    "studies_fetched": 0,
                    "studies_ingested": ingested,
                    "studies_skipped": skipped,
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc),
                    "status": "failed",
                    "error": str(exc),
                }
            )
        else:
            await mongo_db.ingestion_runs.update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "studies_ingested": ingested,
                        "studies_skipped": skipped,
                        "completed_at": datetime.now(timezone.utc),
                        "status": "failed",
                        "error": str(exc),
                    }
                },
            )
        raise

    return ingested
