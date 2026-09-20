"""Tests for deterministic minimal Applications-only XLSX sanitizer."""

from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from typing import Any

from backend.campaigns.tracker_sanitizer import (
    FIXED_ZIP_TIMESTAMP,
    col_to_letter,
    sanitize_tracker_workbook,
)
from backend.campaigns.xlsx_reader import read_campaign_workbook
from tests.backend.campaigns.fixture_builder import (
    AUDITED_28_HEADERS,
    build_fictional_xlsx_bytes,
)

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def test_col_to_letter_mapping() -> None:
    assert col_to_letter(0) == "A"
    assert col_to_letter(25) == "Z"
    assert col_to_letter(26) == "AA"
    assert col_to_letter(27) == "AB"


def test_sanitizer_byte_determinism() -> None:
    headers = list(AUDITED_28_HEADERS)
    rows = [
        {
            "Application ID": "APP-DET-1",
            "Role Title": "Deterministic Engineer",
            "Company Name": "Acme Corp",
            "Date Found": date(2026, 3, 1),
            "Application Date": date(2026, 3, 2),
            "Priority": "High",
            "Status": "Applied",
            "Notes": "Some deterministic notes with special characters <>&'\"",
        },
        {
            "Application ID": "APP-DET-2",
            "Role Title": "Backend Specialist",
            "Company Name": "Globex Inc",
            "Date Found": date(2026, 3, 5),
            "Priority": "Medium",
            "Status": "Saved",
        },
    ]

    bytes1 = sanitize_tracker_workbook(headers, rows)
    bytes2 = sanitize_tracker_workbook(headers, rows)
    bytes3 = sanitize_tracker_workbook(headers, rows)

    assert bytes1 == bytes2 == bytes3
    assert hashlib.sha256(bytes1).hexdigest() == hashlib.sha256(bytes2).hexdigest()


def test_sanitizer_exact_round_trip_rows_and_headers() -> None:
    original_xlsx = build_fictional_xlsx_bytes(credentials_count=5)
    read_orig = read_campaign_workbook(original_xlsx)
    assert len(read_orig.rows) == 4
    assert read_orig.credentials_count == 5
    assert len(read_orig.headers) == 28

    sanitized = sanitize_tracker_workbook(read_orig.headers, read_orig.rows)
    read_sanitized = read_campaign_workbook(sanitized)

    # Headers match exact order
    assert read_sanitized.headers == read_orig.headers

    # Row count matches
    assert len(read_sanitized.rows) == len(read_orig.rows)

    # Credentials count is exactly 0 in sanitized version
    assert read_sanitized.credentials_count == 0

    # Verify every row and field matches exactly
    for orig_row, san_row in zip(read_orig.rows, read_sanitized.rows):
        assert san_row.source_application_id == orig_row.source_application_id
        assert san_row.title == orig_row.title
        assert san_row.company == orig_row.company
        assert san_row.location == orig_row.location
        assert san_row.status == orig_row.status
        assert san_row.priority == orig_row.priority
        assert san_row.platform == orig_row.platform
        assert san_row.category == orig_row.category
        assert san_row.outcome == orig_row.outcome
        assert san_row.found_at == orig_row.found_at
        assert san_row.applied_at == orig_row.applied_at
        assert san_row.follow_up_at == orig_row.follow_up_at
        assert san_row.last_update_at == orig_row.last_update_at
        assert san_row.next_action == orig_row.next_action
        assert san_row.notes == orig_row.notes
        assert san_row.platform_url == orig_row.platform_url
        assert san_row.job_posting_url == orig_row.job_posting_url
        assert san_row.url == orig_row.url
        assert san_row.raw_record == orig_row.raw_record


def test_sanitizer_credential_sentinel_absence() -> None:
    secret_pass = "SUPER_SECRET_PLAINTEXT_PASSWORD_9999"
    secret_user = "CRITICAL_USER_SENTINEL_8888"

    # Build workbook with credentials containing secret tokens
    custom_rows: list[dict[str, Any]] = [
        {
            "Application ID": "APP-SAFE-1",
            "Role Title": "Security Engineer",
            "Company Name": "SecureCo",
        }
    ]
    orig_xlsx = build_fictional_xlsx_bytes(
        applications_rows=custom_rows,
        credentials_count=3,
    )
    # Inject sentinel into the credentials sheet
    with zipfile.ZipFile(io.BytesIO(orig_xlsx), "r") as z_in:
        cred_xml = z_in.read("xl/worksheets/sheet2.xml").decode("utf-8")
        cred_xml_injected = cred_xml.replace("user0", secret_user).replace("pass0", secret_pass)
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w") as z_out:
                for item in z_in.infolist():
                    if item.filename == "xl/worksheets/sheet2.xml":
                        z_out.writestr(item.filename, cred_xml_injected.encode("utf-8"), compress_type=zipfile.ZIP_STORED)
                    else:
                        z_out.writestr(item, z_in.read(item.filename))

    injected_bytes = out_buf.getvalue()
    assert secret_user.encode("utf-8") in injected_bytes
    assert secret_pass.encode("utf-8") in injected_bytes

    # Parse and sanitize
    read_res = read_campaign_workbook(injected_bytes)
    assert read_res.credentials_count == 3
    sanitized = sanitize_tracker_workbook(read_res.headers, read_res.rows)

    # Prove sentinel absence across entire raw package bytes
    assert secret_user.encode("utf-8") not in sanitized
    assert secret_pass.encode("utf-8") not in sanitized

    # Inspect all members of sanitized ZIP
    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        names = zf.namelist()
        assert "xl/sharedStrings.xml" not in names
        assert not any("sheet2" in n.lower() for n in names)
        assert not any("credential" in n.lower() for n in names)

        for name in names:
            content = zf.read(name)
            assert secret_user.encode("utf-8") not in content
            assert secret_pass.encode("utf-8") not in content
            assert b"credential" not in content.lower()


def test_sanitizer_inline_strings_and_no_shared_strings() -> None:
    headers = ["Application ID", "Role Title", "Company Name", "Notes"]
    rows = [
        {
            "Application ID": "APP-INLINE-1",
            "Role Title": "Test Engineer",
            "Company Name": "Acme",
            "Notes": "Line with special chars: <foo> & <bar>",
        }
    ]
    sanitized = sanitize_tracker_workbook(headers, rows)

    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        assert "xl/sharedStrings.xml" not in zf.namelist()

        # Check sheet1.xml structure
        sheet1_xml = zf.read("xl/worksheets/sheet1.xml")
        root = ET.fromstring(sheet1_xml)
        for c in root.iter(f"{{{MAIN_NS}}}c"):
            t = c.attrib.get("t")
            # Must NOT use shared strings
            assert t != "s"
            if t == "inlineStr":
                is_elem = c.find(f"{{{MAIN_NS}}}is")
                assert is_elem is not None
                t_elem = is_elem.find(f"{{{MAIN_NS}}}t")
                assert t_elem is not None


def test_sanitizer_zip_metadata_and_member_order() -> None:
    headers = ["Application ID", "Role Title", "Company Name"]
    rows = [{"Application ID": "APP-1", "Role Title": "Dev", "Company Name": "Co"}]
    sanitized = sanitize_tracker_workbook(headers, rows)

    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        infolist = zf.infolist()
        names = [info.filename for info in infolist]
        # Verify deterministic sorted member order
        assert names == sorted(names)
        # Verify fixed timestamp
        for info in infolist:
            assert info.date_time == FIXED_ZIP_TIMESTAMP
            assert info.compress_type == zipfile.ZIP_DEFLATED


def test_sanitizer_round_trip_all_scalar_types_and_whitespace() -> None:
    headers = [
        "Application ID",
        "Role Title",
        "Company Name",
        "Is Active",
        "Headcount",
        "Salary Score",
        "Date Found",
        "Application Date",
        "Notes",
        "Empty Col",
    ]
    rows = [
        {
            "Application ID": "APP-SCALAR-1",
            "Role Title": "  Leading whitespace role",
            "Company Name": "Trailing whitespace corp  ",
            "Is Active": True,
            "Headcount": 42,
            "Salary Score": 125.75,
            "Date Found": date(2026, 3, 15),
            "Application Date": "2026-03-20",
            "Notes": "  Both leading and trailing whitespace  ",
            "Empty Col": None,
        },
        {
            "Application ID": "APP-SCALAR-2",
            "Role Title": "Normal Title",
            "Company Name": "Normal Company",
            "Is Active": False,
            "Headcount": -10,
            "Salary Score": -50.25,
            "Date Found": None,
            "Application Date": None,
            "Notes": "Simple note",
            "Empty Col": None,
        },
    ]

    sanitized = sanitize_tracker_workbook(headers, rows)

    # 1. Verify xml:space="preserve" is emitted for leading/trailing whitespace strings
    with zipfile.ZipFile(io.BytesIO(sanitized), "r") as zf:
        sheet1_text = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert 'xml:space="preserve">  Leading whitespace role</t>' in sheet1_text
        assert 'xml:space="preserve">Trailing whitespace corp  </t>' in sheet1_text
        assert 'xml:space="preserve">  Both leading and trailing whitespace  </t>' in sheet1_text
        # Normal strings should NOT have xml:space="preserve"
        assert '<t>Normal Title</t>' in sheet1_text
        assert '<t>Simple note</t>' in sheet1_text

    # 2. Round-trip through read_campaign_workbook
    read_res = read_campaign_workbook(sanitized)
    assert read_res.credentials_count == 0
    assert len(read_res.rows) == 2

    r1 = read_res.rows[0]
    assert r1.source_application_id == "APP-SCALAR-1"
    assert r1.title == "  Leading whitespace role"
    assert r1.company == "Trailing whitespace corp  "
    assert r1.notes == "  Both leading and trailing whitespace  "
    assert r1.found_at == date(2026, 3, 15)
    assert r1.applied_at == date(2026, 3, 20)
    assert r1.raw_record["Is Active"] is True
    assert r1.raw_record["Headcount"] == 42
    assert r1.raw_record["Salary Score"] == 125.75
    assert r1.raw_record["Empty Col"] is None
    assert r1.raw_record["Date Found"] == "2026-03-15"
    assert r1.raw_record["Application Date"] == "2026-03-20"

    r2 = read_res.rows[1]
    assert r2.source_application_id == "APP-SCALAR-2"
    assert r2.title == "Normal Title"
    assert r2.company == "Normal Company"
    assert r2.raw_record["Is Active"] is False
    assert r2.raw_record["Headcount"] == -10
    assert r2.raw_record["Salary Score"] == -50.25
    assert r2.found_at is None
    assert r2.applied_at is None
    assert r2.raw_record["Empty Col"] is None
    assert r2.raw_record["Date Found"] is None
