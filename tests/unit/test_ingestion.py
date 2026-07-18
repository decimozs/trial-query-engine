import httpx
import pytest

from app.services import ingestion
from app.services.ingestion import StudyMetadata, chunk_text, embed_chunks, extract_metadata


def sample_study(nct_id: str = "NCT00000001", summary: str | None = "Summary text"):
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": "Brief title",
                "officialTitle": "Official title",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "conditionsModule": {"conditions": ["Diabetes Type 2"]},
            "designModule": {"phases": ["PHASE3"]},
        }
    }
    if summary is not None:
        study["protocolSection"]["descriptionModule"] = {"briefSummary": summary}
    return study


def test_extract_metadata_reads_clinicaltrials_shape() -> None:
    metadata = extract_metadata(sample_study())

    assert metadata == StudyMetadata(
        nct_id="NCT00000001",
        title="Brief title",
        condition="Diabetes Type 2",
        phase="PHASE3",
        status="RECRUITING",
        brief_summary="Summary text",
    )


def test_extract_metadata_falls_back_to_title_and_skips_missing_nct_id() -> None:
    metadata = extract_metadata(sample_study(summary=None))
    assert metadata is not None
    assert metadata.brief_summary == "Brief title"

    missing_nct = sample_study()
    del missing_nct["protocolSection"]["identificationModule"]["nctId"]
    assert extract_metadata(missing_nct) is None


def test_chunk_text_splits_with_overlap() -> None:
    text = " ".join(str(index) for index in range(12))

    chunks = chunk_text(text, chunk_size=5, overlap=2)

    assert chunks == ["0 1 2 3 4", "3 4 5 6 7", "6 7 8 9 10", "9 10 11"]


def test_embed_chunks_returns_python_lists(monkeypatch) -> None:
    class FakeEmbedding:
        def __init__(self, values):
            self.values = values

        def tolist(self):
            return self.values

    class FakeModel:
        def encode(self, chunks, normalize_embeddings=False):
            assert normalize_embeddings is True
            return [FakeEmbedding([1.0] * 384) for _ in chunks]

    monkeypatch.setattr(ingestion, "get_embedding_model", lambda: FakeModel())

    embeddings = embed_chunks(["a", "b"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384


@pytest.mark.anyio
async def test_fetch_studies_follows_next_page_token(monkeypatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "pageToken=next" in str(request.url):
            return httpx.Response(200, json={"studies": [sample_study("NCT00000002")]})
        return httpx.Response(
            200,
            json={"studies": [sample_study("NCT00000001")], "nextPageToken": "next"},
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(ingestion.httpx, "AsyncClient", async_client)

    studies = await ingestion.fetch_studies("diabetes", 2)

    assert [study["protocolSection"]["identificationModule"]["nctId"] for study in studies] == [
        "NCT00000001",
        "NCT00000002",
    ]
    assert len(requests) == 2


@pytest.mark.anyio
async def test_ingest_studies_failure_records_fetched_count(monkeypatch) -> None:
    failure_payload = {}

    async def fake_fetch_studies(condition: str, max_studies: int):
        return [sample_study("NCT00000001"), sample_study("NCT00000002")]

    async def fake_start_ingestion_run(condition: str, studies_fetched: int):
        assert studies_fetched == 2
        return "run-1"

    async def fake_store_raw_document(study):
        return True

    async def fail_embed_chunks_async(chunks):
        raise RuntimeError("embedding failed")

    async def fake_fail_ingestion_run(run_id, **kwargs):
        failure_payload["run_id"] = run_id
        failure_payload.update(kwargs)

    monkeypatch.setattr(ingestion, "fetch_studies", fake_fetch_studies)
    monkeypatch.setattr(ingestion, "start_ingestion_run", fake_start_ingestion_run)
    monkeypatch.setattr(ingestion, "store_raw_document", fake_store_raw_document)
    monkeypatch.setattr(ingestion, "embed_chunks_async", fail_embed_chunks_async)
    monkeypatch.setattr(ingestion, "fail_ingestion_run", fake_fail_ingestion_run)

    with pytest.raises(RuntimeError, match="embedding failed"):
        await ingestion.ingest_studies("diabetes", 2, session=None)

    assert failure_payload["run_id"] == "run-1"
    assert failure_payload["studies_fetched"] == 2
    assert failure_payload["studies_ingested"] == 0
