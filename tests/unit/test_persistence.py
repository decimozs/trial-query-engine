from app.schemas.query import QueryLatency, RetrievedChunk
from app.services.guardrails.types import GuardrailDecision
from app.services.persistence import make_chat_history_document, make_guardrail_documents


def retrieved_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=1,
        chunk_uid="uid-1",
        chunk_source="brief_summary",
        document_id=2,
        nct_id="NCT00000001",
        title="Trial",
        chunk_text="Trial text",
        distance=0.2,
        semantic_score=0.8,
        keyword_score=0.5,
        blended_score=0.71,
    )


def test_make_chat_history_document_records_guardrail_state() -> None:
    document = make_chat_history_document(
        user_id=1,
        query_id="query-1",
        question="Question?",
        answer="Answer.",
        retrieved_chunks=[retrieved_chunk()],
        latency_ms=QueryLatency(embed=1, retrieval=2, llm=3),
        guardrail_decisions=[
            GuardrailDecision(stage="input", check_name="scope", result="flag"),
            GuardrailDecision(stage="output", check_name="grounding", result="block"),
        ],
    )

    assert document["retrieved_chunk_ids"] == [1]
    assert document["retrieved_chunk_uids"] == ["uid-1"]
    assert document["guardrail_blocked"] is True
    assert document["guardrail_flags"] == ["scope"]
    assert document["latency_ms"] == {"embed": 1, "retrieval": 2, "llm": 3}


def test_make_guardrail_documents_records_decisions() -> None:
    documents = make_guardrail_documents(
        user_id=1,
        query_id="query-1",
        decisions=[
            GuardrailDecision(
                stage="input",
                check_name="prompt_injection",
                result="block",
                detail="matched",
                metadata={"pattern": "ignore"},
            )
        ],
    )

    assert len(documents) == 1
    assert documents[0]["query_id"] == "query-1"
    assert documents[0]["check_name"] == "prompt_injection"
    assert documents[0]["result"] == "block"
    assert documents[0]["metadata"] == {"pattern": "ignore"}
