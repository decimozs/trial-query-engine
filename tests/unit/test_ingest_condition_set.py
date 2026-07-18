import asyncio

from scripts import ingest_condition_set


def test_parse_conditions_defaults_and_pipe_separated_values() -> None:
    assert ingest_condition_set.parse_conditions(None) == ingest_condition_set.DEFAULT_CONDITIONS
    assert ingest_condition_set.parse_conditions("Asthma| Breast Cancer |") == [
        "Asthma",
        "Breast Cancer",
    ]


def test_ingest_condition_set_calls_each_condition(monkeypatch) -> None:
    calls = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_ingest_studies(condition, max_studies, session):
        calls.append((condition, max_studies, session))
        return 2

    async def fake_close_mongo():
        return None

    class FakeEngine:
        async def dispose(self):
            return None

    monkeypatch.setenv("CONDITIONS", "Asthma|Breast Cancer")
    monkeypatch.setenv("MAX_STUDIES_PER_CONDITION", "7")
    monkeypatch.setattr(ingest_condition_set, "async_session", lambda: FakeSession())
    monkeypatch.setattr(ingest_condition_set, "ingest_studies", fake_ingest_studies)
    monkeypatch.setattr(ingest_condition_set, "close_mongo", fake_close_mongo)
    monkeypatch.setattr(ingest_condition_set, "engine", FakeEngine())

    asyncio.run(ingest_condition_set.main())

    assert [(condition, max_studies) for condition, max_studies, _ in calls] == [
        ("Asthma", 7),
        ("Breast Cancer", 7),
    ]
