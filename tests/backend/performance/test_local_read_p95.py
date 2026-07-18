import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session

from backend.applications.models import Application, ApplicationEvent
from backend.applications.service import ApplicationService
from backend.career.models import CandidateProfile
from backend.career.service import CareerProfileService
from backend.models import BaseModel, User

RECORD_COUNT = 10_000
PAGE_SIZE = 200
SAMPLES = 30
P95_BUDGET_MS = 200.0

pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.getenv("RUN_PERFORMANCE_TESTS") != "1",
        reason="set RUN_PERFORMANCE_TESTS=1 to execute the 10k-record benchmark",
    ),
]


def _p95_ms(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _batches(rows: list[dict], size: int = 1000):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


@pytest.fixture
def benchmark_database_path():
    with TemporaryDirectory(prefix="careeros-performance-", ignore_cleanup_errors=True) as path:
        yield Path(path) / "careeros-performance.db"


def test_profile_and_application_page_reads_under_200ms_p95(
    benchmark_database_path, capsys
):
    database_path = benchmark_database_path
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    BaseModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        user = User(username="performance", hashed_password="not-used-in-benchmark")
        session.add(user)
        session.flush()
        session.add(
            CandidateProfile(
                id="00000000-0000-0000-0000-000000000001",
                user_id=user.id,
                revision=1,
                display_name="Performance Candidate",
                headline="Local-first benchmark",
                summary="Deterministic fixture",
                location={},
                work_authorization=[],
                preferences={},
            )
        )
        session.commit()

        application_rows = []
        event_rows = []
        for index in range(RECORD_COUNT):
            application_id = f"00000000-0000-0000-{index // 10_000:04d}-{index:012d}"
            application_rows.append(
                {
                    "id": application_id,
                    "user_id": user.id,
                    "job_id": None,
                    "resume_version_id": None,
                    "revision": 1,
                    "current_stage": "saved",
                    "job_snapshot": {
                        "schema_version": 1,
                        "title": f"Role {index}",
                        "company": f"Company {index % 100}",
                        "location": "Zurich",
                    },
                    "created_at": now,
                    "updated_at": now,
                }
            )
            event_rows.append(
                {
                    "id": f"10000000-0000-0000-{index // 10_000:04d}-{index:012d}",
                    "application_id": application_id,
                    "event_type": "stage",
                    "stage": "saved",
                    "occurred_at": now,
                    "note": None,
                    "payload": {"initial": True},
                    "created_at": now,
                }
            )

        for batch in _batches(application_rows):
            session.execute(insert(Application), batch)
        for batch in _batches(event_rows):
            session.execute(insert(ApplicationEvent), batch)
        session.commit()

        profile_service = CareerProfileService(session)
        application_service = ApplicationService(session)

        # Warm filesystem pages and SQLAlchemy/Pydantic code paths before sampling.
        assert profile_service.get(user.id) is not None
        assert len(application_service.list(user.id, limit=PAGE_SIZE)) == PAGE_SIZE

        profile_samples: list[float] = []
        application_samples: list[float] = []
        for _ in range(SAMPLES):
            session.expunge_all()
            started = time.perf_counter_ns()
            profile = profile_service.get(user.id)
            profile_samples.append((time.perf_counter_ns() - started) / 1_000_000)
            assert profile is not None

            session.expunge_all()
            started = time.perf_counter_ns()
            applications = application_service.list(user.id, limit=PAGE_SIZE)
            application_samples.append((time.perf_counter_ns() - started) / 1_000_000)
            assert len(applications) == PAGE_SIZE

        result = {
            "records": RECORD_COUNT,
            "page_size": PAGE_SIZE,
            "samples": SAMPLES,
            "profile_read_p95_ms": round(_p95_ms(profile_samples), 3),
            "application_page_p95_ms": round(_p95_ms(application_samples), 3),
            "budget_ms": P95_BUDGET_MS,
            "database_bytes": database_path.stat().st_size,
        }
        with capsys.disabled():
            print(f"CAREEROS_BENCHMARK={json.dumps(result, sort_keys=True)}")

        assert result["profile_read_p95_ms"] < P95_BUDGET_MS
        assert result["application_page_p95_ms"] < P95_BUDGET_MS

    engine.dispose()
