import json
import os
from pathlib import Path

import pytest

import backend.portability.restore as restore_module
from backend.core.config import settings
from backend.portability import journal as journal_module
from backend.portability.journal import (
    RestoreJournalError,
    atomic_restore_write,
    clear_restore_journal,
    prepare_restore_journal,
    read_restore_journal,
)
from backend.storage import atomic


@pytest.fixture
def journal_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    return tmp_path


def _copies(root: Path, user_id: int = 7) -> tuple[Path, Path]:
    directory = root / ".restore" / f"user-{user_id}"
    return directory / "journal.json", directory / "journal.backup.json"


def _write_raw_copies(root: Path, payload: dict, *, user_id: int = 7) -> None:
    primary, backup = _copies(root, user_id)
    primary.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    primary.write_bytes(encoded)
    backup.write_bytes(encoded)


def _checksummed_payload(paths: list[str]) -> dict:
    payload = {
        "version": 1,
        "generation": 1,
        "user_id": 7,
        "archive_fingerprint": "a" * 64,
        "paths": paths,
    }
    return {**payload, "checksum": journal_module._payload_checksum(payload)}


def test_journal_checksum_and_redundant_copies_round_trip(journal_root: Path) -> None:
    prepare_restore_journal(7, "a" * 64, ["assets/aa/" + "a" * 64])

    primary, backup = _copies(journal_root)
    assert primary.read_bytes() == backup.read_bytes()
    payload = json.loads(primary.read_text(encoding="utf-8"))
    assert payload["generation"] == 1
    assert len(payload["checksum"]) == 64
    assert read_restore_journal(7) == payload


def test_corrupt_primary_falls_back_to_backup_and_retry_repairs_both(
    journal_root: Path,
) -> None:
    path = "assets/aa/" + "a" * 64
    prepare_restore_journal(7, "b" * 64, [path])
    primary, backup = _copies(journal_root)
    primary.write_text('{"version":1,"checksum":"broken"}', encoding="utf-8")

    assert read_restore_journal(7)["archive_fingerprint"] == "b" * 64
    prepare_restore_journal(7, "b" * 64, [path])

    assert primary.read_bytes() == backup.read_bytes()
    assert read_restore_journal(7)["generation"] == 2


def test_torn_copy_update_selects_monotonic_newer_generation_and_repairs(
    journal_root: Path,
) -> None:
    first = "assets/aa/" + "a" * 64
    second = "assets/bb/" + "b" * 64
    prepare_restore_journal(7, "c" * 64, [first])
    _primary, backup = _copies(journal_root)
    old_backup = backup.read_bytes()

    prepare_restore_journal(7, "c" * 64, [first, second])
    backup.write_bytes(old_backup)

    recovered = read_restore_journal(7)
    assert recovered["generation"] == 2
    assert recovered["paths"] == [first, second]
    prepare_restore_journal(7, "c" * 64, [first, second])
    primary, backup = _copies(journal_root)
    assert primary.read_bytes() == backup.read_bytes()


def test_valid_non_monotonic_copies_fail_closed(journal_root: Path) -> None:
    first = "assets/aa/" + "a" * 64
    second = "assets/bb/" + "b" * 64
    prepare_restore_journal(7, "d" * 64, [first])
    primary, backup = _copies(journal_root)
    payload = json.loads(backup.read_text(encoding="utf-8"))
    payload["generation"] = 2
    payload["paths"] = [second]
    backup.write_text(
        json.dumps(journal_module._with_checksum(payload), sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RestoreJournalError, match="not monotonic"):
        read_restore_journal(7)
    assert primary.exists() and backup.exists()


def test_restore_staging_survives_hard_crash_and_retry_cleans_only_owner_tree(
    journal_root: Path,
    monkeypatch,
) -> None:
    relative_path = "assets/aa/" + "a" * 64
    prepare_restore_journal(7, "e" * 64, [relative_path])
    original_replace = journal_module.durable_replace

    def hard_crash_before_publish(source, destination):
        if Path(destination) == journal_root / relative_path:
            raise KeyboardInterrupt("simulated hard stop")
        return original_replace(source, destination)

    monkeypatch.setattr(journal_module, "durable_replace", hard_crash_before_publish)
    with pytest.raises(KeyboardInterrupt, match="hard stop"):
        atomic_restore_write(7, relative_path, b"private restore bytes")

    staging = journal_root / ".restore" / "user-7" / "staging"
    assert [path.read_bytes() for path in staging.iterdir()] == [b"private restore bytes"]
    monkeypatch.setattr(journal_module, "durable_replace", original_replace)

    prepare_restore_journal(7, "e" * 64, [relative_path])
    assert not staging.exists()
    destination, created = atomic_restore_write(7, relative_path, b"private restore bytes")
    assert created is True
    assert destination.read_bytes() == b"private restore bytes"


def test_clear_journal_removes_private_staging_residue(journal_root: Path) -> None:
    path = "assets/aa/" + "a" * 64
    prepare_restore_journal(7, "f" * 64, [path])
    staging = journal_root / ".restore" / "user-7" / "staging"
    staging.mkdir()
    (staging / ".write-private").write_bytes(b"private")

    clear_restore_journal(7)

    assert not (journal_root / ".restore" / "user-7").exists()


def test_both_invalid_copies_fail_closed(journal_root: Path) -> None:
    prepare_restore_journal(7, "1" * 64, ["assets/11/" + "1" * 64])
    primary, backup = _copies(journal_root)
    primary.write_text("{}", encoding="utf-8")
    backup.write_text("[]", encoding="utf-8")

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)


def test_restore_journal_rejects_oversized_copies_before_json_decode(
    journal_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "PORTABLE_ARCHIVE_MAX_MEMBERS", 1)
    primary, backup = _copies(journal_root)
    primary.parent.mkdir(parents=True)
    oversized = b"x" * (journal_module._journal_maximum_bytes() + 1)
    primary.write_bytes(oversized)
    backup.write_bytes(oversized)

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)


def test_restore_journal_rejects_more_than_the_archive_member_limit(
    journal_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "PORTABLE_ARCHIVE_MAX_MEMBERS", 2)
    paths = [f"assets/{index:02x}/{'a' * 64}" for index in range(3)]
    _write_raw_copies(journal_root, _checksummed_payload(paths))

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)


def test_restore_journal_rejects_paths_longer_than_1024_characters(
    journal_root: Path,
) -> None:
    long_path = "assets/" + "a" * (journal_module._JOURNAL_PATH_MAX_CHARACTERS)
    _write_raw_copies(journal_root, _checksummed_payload([long_path]))

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)


def test_restore_journal_rejects_symlink_copies_without_following_targets(
    journal_root: Path,
) -> None:
    prepare_restore_journal(7, "2" * 64, ["assets/22/" + "2" * 64])
    primary, backup = _copies(journal_root)
    external_primary = journal_root / "external-primary.json"
    external_backup = journal_root / "external-backup.json"
    external_primary.write_bytes(primary.read_bytes())
    external_backup.write_bytes(backup.read_bytes())
    primary.unlink()
    backup.unlink()
    try:
        primary.symlink_to(external_primary)
        backup.symlink_to(external_backup)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable: {exc}")

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)

    assert external_primary.is_file() and external_backup.is_file()


def test_restore_journal_rejects_hard_linked_copies(journal_root: Path) -> None:
    prepare_restore_journal(7, "3" * 64, ["assets/33/" + "3" * 64])
    primary, backup = _copies(journal_root)
    primary.unlink()
    try:
        os.link(backup, primary)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable: {exc}")

    with pytest.raises(RestoreJournalError, match="unavailable or invalid"):
        read_restore_journal(7)

    assert primary.stat().st_nlink >= 2


def test_restore_journal_copy_rejects_lstat_open_swap(
    journal_root: Path,
    monkeypatch,
) -> None:
    prepare_restore_journal(7, "4" * 64, ["assets/44/" + "4" * 64])
    primary, _backup = _copies(journal_root)
    replacement = journal_root / "replacement-journal.json"
    replacement.write_bytes(primary.read_bytes())
    real_open = atomic.os.open
    swapped = False

    def swap_then_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == primary and not swapped:
            swapped = True
            replacement.replace(primary)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(atomic.os, "open", swap_then_open)
    state, _failure = journal_module._read_journal_copy(7, primary)

    assert swapped is True
    assert state == "invalid"


def test_atomic_restore_write_rejects_existing_hard_link_alias(journal_root: Path) -> None:
    relative_path = "assets/55/" + "5" * 64
    destination = journal_root / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"matching private bytes")
    alias = journal_root / "external-hard-link"
    try:
        os.link(destination, alias)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable: {exc}")

    with pytest.raises(ValueError, match="does not match"):
        atomic_restore_write(7, relative_path, b"matching private bytes")

    assert alias.read_bytes() == b"matching private bytes"


def test_restore_destination_probe_rejects_existing_hard_link_alias(
    journal_root: Path,
) -> None:
    relative_path = "assets/66/" + "6" * 64
    destination = journal_root / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"matching private bytes")
    alias = journal_root / "probe-hard-link"
    try:
        os.link(destination, alias)
    except OSError as exc:
        pytest.skip(f"Hard links are unavailable: {exc}")

    assert (
        restore_module._file_destinations_available([(relative_path, b"matching private bytes")])
        is False
    )


def test_atomic_restore_write_preserves_empty_file_semantics(journal_root: Path) -> None:
    relative_path = "assets/77/" + "7" * 64
    prepare_restore_journal(7, "7" * 64, [relative_path])

    destination, created = atomic_restore_write(7, relative_path, b"")
    assert created is True
    assert destination.read_bytes() == b""

    same_destination, created = atomic_restore_write(7, relative_path, b"")
    assert same_destination == destination
    assert created is False

    destination.write_bytes(b"conflicting bytes")
    with pytest.raises(ValueError, match="does not match"):
        atomic_restore_write(7, relative_path, b"")


def test_restore_destination_probe_preserves_empty_file_semantics(
    journal_root: Path,
) -> None:
    relative_path = "assets/88/" + "8" * 64
    destination = journal_root / relative_path

    assert restore_module._file_destinations_available([(relative_path, b"")]) is True
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"")
    assert restore_module._file_destinations_available([(relative_path, b"")]) is True
    destination.write_bytes(b"conflicting bytes")
    assert restore_module._file_destinations_available([(relative_path, b"")]) is False
    assert restore_module._file_destinations_available([("../outside", b"")]) is False
