Clinical Trial Assistant
========================

FastAPI application for authenticated clinical-trial RAG over ClinicalTrials.gov data.

Local stack:

- Postgres 16 + pgvector on `localhost:15432`
- MongoDB on `localhost:27018`
- FastAPI/frontend on `localhost:8000`

Setup:

```bash
uv sync
cp .env.example .env
make docker-up
make docker-migrate
make docker-mongo-indexes
make dev-server
```

Frontend:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

Create a user:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"secret123"}'
```

Ingest data:

```bash
make ingest-studies
make ingest-studies CONDITION="Hypertension" MAX_STUDIES=50
```

Run checks:

```bash
make test-unit
make test-integration
make check
```

Smoke tests:

```bash
make ingest-smoke-test
make query-smoke-test
```

Query with structured filters:

```bash
curl -N -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "question":"What are common eligibility criteria for Type 2 Diabetes trials?",
    "top_k":3,
    "phase":"PHASE3",
    "status":"RECRUITING",
    "condition":"Diabetes"
  }'
```

Retrieval uses hybrid search:

- semantic score from normalized pgvector cosine similarity
- keyword score from exact token matches over chunk text
- blended score from `RAG_SEMANTIC_WEIGHT` and `RAG_KEYWORD_WEIGHT`

If no chunks pass retrieval gates, `/query` skips the LLM and returns:

```text
I don't have enough information from the provided trial data to answer that.
```

`/query` is rate-limited by `QUERY_RATE_LIMIT` to protect LLM cost.

Stats:

```bash
curl http://localhost:8000/stats
```

Returns document/chunk counts, aggregate query latency, and latest ingestion run metadata.

Useful DB checks:

```bash
make db-ping
make db-current
make db-counts
make db-extensions
```

Notes:

- `.env` must not be committed.
- `ANTHROPIC_API_KEY` is required for real query generation.
- Docker API image is large because `sentence-transformers` pulls PyTorch.
# hcp-clinical-trial-assistant
