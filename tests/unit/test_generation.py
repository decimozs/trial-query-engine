from app.schemas.query import RetrievedChunk
from app.services.generation import build_prompt


def test_build_prompt_contains_grounding_instruction_question_and_sources() -> None:
    chunk = RetrievedChunk(
        chunk_id=1,
        chunk_uid="uid-1",
        chunk_source="eligibility_criteria",
        document_id=2,
        nct_id="NCT00000001",
        title="Diabetes Trial",
        chunk_text="Eligible participants had Type 2 Diabetes.",
        distance=0.1,
        semantic_score=0.9,
        keyword_score=0.4,
        blended_score=0.75,
    )

    prompt = build_prompt("Who is eligible?", [chunk])

    assert "Answer only from the provided clinical trial context" in prompt
    assert "If the context is insufficient" in prompt
    assert "Who is eligible?" in prompt
    assert "Diabetes Trial" in prompt
    assert "NCT00000001" in prompt
    assert "eligibility_criteria" in prompt
    assert "Eligible participants had Type 2 Diabetes." in prompt
