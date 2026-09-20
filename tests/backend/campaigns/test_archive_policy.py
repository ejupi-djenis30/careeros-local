"""Tests for campaign archive policy, security boundaries, limits, and fingerprints."""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.campaigns.archive_policy import (
    MAX_MEMBERS,
    ArchivePolicyError,
    inspect_and_validate_campaign_archive,
)
from tests.backend.campaigns.fixture_builder import build_fictional_campaign_zip


def test_valid_archive_passes_and_computes_fingerprint():
    zip_bytes = build_fictional_campaign_zip()
    result = inspect_and_validate_campaign_archive(zip_bytes)
    assert result.fingerprint is not None
    assert len(result.fingerprint) == 64
    assert result.member_count > 0
    assert result.total_byte_size > 0
    assert "ApplicationTracker.xlsx" in result.members
    assert "Profile.md" in result.members


def test_fingerprint_deterministic_across_order_and_timestamps():
    members_a = {
        "Profile.md": "Fictional profile content A",
        "Goal.md": "Fictional goal content B",
    }
    # Create zip 1
    buf1 = io.BytesIO()
    with zipfile.ZipFile(buf1, "w") as zf:
        zinfo1 = zipfile.ZipInfo("Profile.md", date_time=(2026, 1, 1, 10, 0, 0))
        zf.writestr(zinfo1, members_a["Profile.md"])
        zinfo2 = zipfile.ZipInfo("Goal.md", date_time=(2026, 1, 1, 10, 0, 0))
        zf.writestr(zinfo2, members_a["Goal.md"])

    # Create zip 2 with reversed order and different timestamps
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zinfo2 = zipfile.ZipInfo("Goal.md", date_time=(2025, 5, 5, 12, 30, 0))
        zf.writestr(zinfo2, members_a["Goal.md"])
        zinfo1 = zipfile.ZipInfo("Profile.md", date_time=(2024, 8, 8, 8, 0, 0))
        zf.writestr(zinfo1, members_a["Profile.md"])

    res1 = inspect_and_validate_campaign_archive(buf1.getvalue())
    res2 = inspect_and_validate_campaign_archive(buf2.getvalue())
    assert res1.fingerprint == res2.fingerprint


def test_common_prefix_is_stripped():
    zip_bytes = build_fictional_campaign_zip(prefix="my-campaign-export/")
    result = inspect_and_validate_campaign_archive(zip_bytes)
    assert result.common_prefix == "my-campaign-export"
    assert "ApplicationTracker.xlsx" in result.members
    assert "Profile.md" in result.members


@pytest.mark.parametrize(
    ("member_path", "expected_path"),
    [
        ("assets/evidence.txt", "assets/evidence.txt"),
        ("application-packets/APP-ONLY/vacancy.md", "application-packets/APP-ONLY/vacancy.md"),
    ],
)
def test_single_allowlisted_root_directory_is_not_mistaken_for_wrapper(
    member_path: str,
    expected_path: str,
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member_path, b"fictional inert content")

    result = inspect_and_validate_campaign_archive(buf.getvalue())

    assert result.common_prefix == ""
    assert tuple(result.members) == (expected_path,)


def test_wrapper_is_stripped_when_it_contains_only_one_allowlisted_directory() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fictional-wrapper/assets/evidence.txt", b"fictional inert content")

    result = inspect_and_validate_campaign_archive(buf.getvalue())

    assert result.common_prefix == "fictional-wrapper"
    assert tuple(result.members) == ("assets/evidence.txt",)


def test_traversal_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("assets/../../etc/passwd", b"fictional")
    with pytest.raises(ArchivePolicyError, match="traversal"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_absolute_path_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("/Profile.md", b"fictional")
    with pytest.raises(ArchivePolicyError, match="absolute"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_backslash_rejected():
    # Construct raw zip bytes where filename has literal backslash with equal length
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", b"fictional")
    raw = bytearray(buf.getvalue())
    # Replace test.txt (8 chars) with a\\cd.txt (8 chars) to preserve offsets
    raw = raw.replace(b"test.txt", b"a\\cd.txt")
    with pytest.raises(ArchivePolicyError, match="backslash"):
        inspect_and_validate_campaign_archive(bytes(raw))


def test_drive_or_unc_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("C:/Profile.md", b"fictional")
    with pytest.raises(ArchivePolicyError, match="drive or UNC"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_symlink_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zinfo = zipfile.ZipInfo("Profile.md")
        zinfo.external_attr = 0o120777 << 16  # S_IFLNK
        zf.writestr(zinfo, b"target")
    with pytest.raises(ArchivePolicyError, match="symlink"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_encrypted_entry_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Profile.md", b"secret")
    raw = bytearray(buf.getvalue())
    # Set encryption flag in central directory entry (signature PK\x01\x02) at offset 8
    cd_offset = raw.find(b"PK\x01\x02")
    assert cd_offset != -1
    raw[cd_offset + 8] |= 0x01
    with pytest.raises(ArchivePolicyError, match="encrypted"):
        inspect_and_validate_campaign_archive(bytes(raw))


def test_case_insensitive_duplicate_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Profile.md", b"one")
        zf.writestr("profile.md", b"two")
    with pytest.raises(ArchivePolicyError, match="duplicate"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_max_members_limit_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(MAX_MEMBERS + 1):
            zf.writestr(f"assets/f_{i}.txt", b"x")
    with pytest.raises(ArchivePolicyError, match="members limit"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_max_file_size_rejected(monkeypatch):
    monkeypatch.setattr("backend.campaigns.archive_policy.MAX_FILE_BYTES", 10)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Profile.md", b"this string exceeds ten bytes")
    with pytest.raises(ArchivePolicyError, match="file size limit"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_unsupported_root_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("outputs/something.csv", b"fictional")
    with pytest.raises(ArchivePolicyError, match="unsupported root"):
        inspect_and_validate_campaign_archive(buf.getvalue())

    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("careeros-local/secret.txt", b"fictional")
    with pytest.raises(ArchivePolicyError, match="unsupported root"):
        inspect_and_validate_campaign_archive(buf2.getvalue())


def test_harmless_file_content_containing_central_directory_signature_accepted():
    # File content contains b"PK\x01\x02\x00\x00..." which mimics a central directory signature
    fake_cd_sig = b"Some harmless prefix PK\x01\x02\x00\x00\\bad\\path.txt and suffix"
    zip_bytes = build_fictional_campaign_zip(
        members={"application-packets/APP-001/notes.txt": fake_cd_sig}
    )
    result = inspect_and_validate_campaign_archive(zip_bytes)
    assert result.fingerprint is not None
    assert "application-packets/APP-001/notes.txt" in result.members


def test_control_characters_rejected():
    # 1. Non-null control character (SOH \x01)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Profile\x01.md", b"fictional")
    with pytest.raises(ArchivePolicyError, match="control characters"):
        inspect_and_validate_campaign_archive(buf.getvalue())

    # 2. Control character in subfolder
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("assets/test\r.txt", b"fictional")
    with pytest.raises(ArchivePolicyError, match="control characters"):
        inspect_and_validate_campaign_archive(buf2.getvalue())

    # 3. Literal null byte in raw entry name
    buf3 = io.BytesIO()
    with zipfile.ZipFile(buf3, "w") as zf:
        zf.writestr("Profile.md", b"content")
        zf.writestr("assets/ctrl_test.txt", b"content")
    raw = bytearray(buf3.getvalue()).replace(b"assets/ctrl_test.txt", b"assets/ctrl_\x00est.txt")
    with pytest.raises(ArchivePolicyError, match="control characters"):
        inspect_and_validate_campaign_archive(bytes(raw))


def test_unicode_nfc_casefold_duplicate_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Include Profile.md so common_prefix is not assets/
        zf.writestr("Profile.md", b"# Profile")
        # NFD form: e + combining acute accent (\u0065\u0301)
        # NFC form: e with acute (\u00e9) in uppercase
        zf.writestr("assets/resum\u0065\u0301.pdf", b"one")
        zf.writestr("assets/RESUM\u00c9.pdf", b"two")
    with pytest.raises(ArchivePolicyError, match="duplicate"):
        inspect_and_validate_campaign_archive(buf.getvalue())


def test_composed_and_decomposed_archives_yield_identical_fingerprint():
    # Archive 1 with decomposed Unicode NFD filename
    zip_bytes_nfd = build_fictional_campaign_zip(
        members={"application-packets/APP-001/resum\u0065\u0301.pdf": b"%PDF-1.4 fictional cv"}
    )
    # Archive 2 with composed Unicode NFC filename
    zip_bytes_nfc = build_fictional_campaign_zip(
        members={"application-packets/APP-001/resum\u00e9.pdf": b"%PDF-1.4 fictional cv"}
    )

    res_nfd = inspect_and_validate_campaign_archive(zip_bytes_nfd)
    res_nfc = inspect_and_validate_campaign_archive(zip_bytes_nfc)

    assert res_nfd.fingerprint == res_nfc.fingerprint
    assert "application-packets/APP-001/resum\u00e9.pdf" in res_nfd.members
    assert "application-packets/APP-001/resum\u00e9.pdf" in res_nfc.members
