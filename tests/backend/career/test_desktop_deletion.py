from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from backend.ai.models import AIExecution
from backend.career.models import CareerAsset
from backend.core.config import settings

PROFILE = {
    "expected_revision": 0,
    "display_name": "Katherine Johnson",
    "headline": "Research mathematician",
    "summary": "Calculates reliable trajectories.",
    "email": "katherine@example.test",
    "location": {"city": "Hampton", "country": "US"},
    "preferences": {},
    "facts": [],
    "goals": [],
}


@pytest.fixture
def deletion_root(monkeypatch):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        monkeypatch.setattr(settings, "DATA_DIR", str(root))
        monkeypatch.setenv("CAREEROS_DESKTOP_DATA_DIR", str(root))
        yield root


def test_device_erasure_removes_owned_data_but_preserves_unrelated_files(
    client, auth_headers, db_session, test_user, deletion_root
):
    profile = client.put(
        "/api/v1/career-profile", json=PROFILE, headers=auth_headers
    )
    assert profile.status_code == 200, profile.text
    source = client.post(
        "/api/v1/career-profile/sources",
        files={"file": ("proof.txt", b"verified", "text/plain")},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text

    execution = AIExecution(
        user_id=test_user.id,
        task="profile_analysis",
        contract_version="1.0.0",
        model_id="local-test",
        input_fingerprint="a" * 64,
        output_fingerprint=None,
        evidence_count=1,
        accepted=False,
        repair_count=1,
        validation_codes=["missing_citation"],
        duration_ms=10,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.expire_all()
    asset_path = db_session.query(CareerAsset).one().storage_path

    owned_files = (
        deletion_root / "models" / "runtime" / "v1" / "llama-server.exe",
        deletion_root / "models" / "weights" / "model.gguf",
        deletion_root / "staging" / "local-model" / "partial.download",
    )
    for path in owned_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"owned")
    unrelated = (
        deletion_root / "unrelated.keep",
        deletion_root / "backups" / "manual-backup.zip",
        deletion_root / "staging" / "another-tool" / "keep.bin",
    )
    for path in unrelated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"keep")

    denied = client.delete("/api/v1/portability/erase", headers=auth_headers)
    assert denied.status_code == 409
    erased = client.delete(
        "/api/v1/portability/erase",
        headers={**auth_headers, "X-Confirm-Erase": "ERASE-LOCAL-CAREER-DATA"},
    )
    assert erased.status_code == 200, erased.text
    assert erased.json()["profiles"] == 1
    assert erased.json()["ai_executions"] == 1
    assert erased.json()["model_files"] == 3
    assert not (deletion_root / asset_path).exists()
    assert all(not path.exists() for path in owned_files)
    assert all(path.read_bytes() == b"keep" for path in unrelated)
