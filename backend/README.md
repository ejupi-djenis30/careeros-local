# Backend

The backend is a bundled FastAPI sidecar and local domain runtime. It is not a hosted multi-tenant service.

## Boundaries

- Routes validate transport and delegate.
- Domain packages own business rules and transactions.
- Repositories isolate SQLAlchemy queries where a domain requires them.
- `backend/inference` owns local runtime adapters; `backend/ai` owns contracts and orchestration.
- `backend/search` owns the decomposed search pipeline.
- `backend/portability` owns versioned export, restore, and compatibility.

All persistent models must be registered in `backend/model_registry.py` and migrated with Alembic. Stored paths must use `backend/storage/atomic.py`; absolute or escaping paths are invalid.

## Run and test

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
.venv\Scripts\python.exe -m ruff check backend tests/backend alembic/versions
.venv\Scripts\python.exe -m pytest tests/backend -q
```

The test suite blocks public network access by default. Add strict contract fixtures for AI changes and rollback tests for persistence changes. Never assert success by swallowing an exception.
