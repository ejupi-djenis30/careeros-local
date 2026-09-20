"""Tests for the stdlib-only XLSX workbook reader."""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from backend.campaigns.xlsx_reader import (
    XlsxReadError,
    read_campaign_workbook,
)
from tests.backend.campaigns.fixture_builder import build_fictional_xlsx_bytes


def test_read_applications_with_shared_strings():
    data = build_fictional_xlsx_bytes(use_inline_strings=False)
    result = read_campaign_workbook(data)
    assert len(result.rows) == 4
    app1 = result.rows[0]
    assert app1.source_application_id == "APP-001"
    assert app1.status == "Applied"
    assert app1.company == "Acme Corp"
    assert app1.title == "Software Engineer"
    assert app1.location == "Zurich"
    assert app1.platform == "LinkedIn"
    assert app1.found_at == date(2026, 1, 10)
    assert app1.applied_at == date(2026, 1, 12)
    assert app1.follow_up_at == date(2026, 1, 26)
    assert app1.last_update_at == date(2026, 1, 15)
    assert app1.platform_url == "https://linkedin.com/jobs/view/1001"
    assert app1.job_posting_url == "https://careers.acme.com/jobs/1001"
    assert app1.url == "https://careers.acme.com/jobs/1001"
    assert len(app1.raw_record) == 28


def test_read_applications_with_inline_strings():
    data = build_fictional_xlsx_bytes(use_inline_strings=True)
    result = read_campaign_workbook(data)
    assert len(result.rows) == 4
    app2 = result.rows[1]
    assert app2.source_application_id == "APP-002"
    assert app2.status == "Closed"
    assert app2.company == "Globex Inc"


def test_read_booleans_and_numbers():
    custom_rows = [
        {
            "Application ID": "APP-BOOL",
            "Role Title": "Test Role",
            "Company Name": "Test Co",
            "Status": "Saved",
            "Referral": True,
            "Extra Field A": 42,
            "Extra Field B": 3.14,
        }
    ]
    data = build_fictional_xlsx_bytes(applications_rows=custom_rows)
    result = read_campaign_workbook(data)
    assert len(result.rows) == 1
    record = result.rows[0].raw_record
    assert record.get("Referral") is True
    assert record.get("Extra Field A") == 42
    assert abs(record.get("Extra Field B") - 3.14) < 1e-5


def test_numeric_typed_text_fields_are_normalized_without_losing_raw_values():
    typed_values = {
        "Application ID": 101,
        "Role Title": 102,
        "Company Name": 103,
        "Location": 104,
        "Status": 105,
        "Priority": 106,
        "Platform / Source": 107,
        "Job Category": 108,
        "Outcome": 109,
        "Next Action": 110,
        "Notes": 111,
    }
    data = build_fictional_xlsx_bytes(applications_rows=[typed_values])

    row = read_campaign_workbook(data).rows[0]

    assert row.source_application_id == "101"
    assert row.title == "102"
    assert row.company == "103"
    assert row.location == "104"
    assert row.status == "105"
    assert row.priority == "106"
    assert row.platform == "107"
    assert row.category == "108"
    assert row.outcome == "109"
    assert row.next_action == "110"
    assert row.notes == "111"
    for key, value in typed_values.items():
        assert row.raw_record[key] == value


def test_typed_text_fields_preserve_nonblank_source_whitespace():
    source_values = {
        "Application ID": "APP-SPACES",
        "Role Title": "  Synthetic role  ",
        "Company Name": "  Synthetic company  ",
        "Status": "  Applied  ",
        "Next Action": "  Review locally  ",
    }
    row = read_campaign_workbook(build_fictional_xlsx_bytes(applications_rows=[source_values])).rows[0]

    assert row.title == source_values["Role Title"]
    assert row.company == source_values["Company Name"]
    assert row.status == source_values["Status"]
    assert row.next_action == source_values["Next Action"]


def test_read_excel_dates():
    custom_rows = [
        {
            "Application ID": "APP-DATE",
            "Role Title": "Date Role",
            "Company Name": "Date Co",
            "Status": "Preparing",
            "Found Date": date(2026, 3, 15),
            "Applied Date": date(2026, 3, 20),
        }
    ]
    data = build_fictional_xlsx_bytes(applications_rows=custom_rows)
    result = read_campaign_workbook(data)
    app = result.rows[0]
    assert app.found_at == date(2026, 3, 15)
    assert app.applied_at == date(2026, 3, 20)


def test_duplicate_application_id_rejected():
    duplicate_rows = [
        {
            "Application ID": "DUP-001",
            "Role Title": "Role 1",
            "Company Name": "Co 1",
            "Status": "Saved",
        },
        {
            "Application ID": "DUP-001",
            "Role Title": "Role 2",
            "Company Name": "Co 2",
            "Status": "Saved",
        },
    ]
    data = build_fictional_xlsx_bytes(applications_rows=duplicate_rows)
    with pytest.raises(XlsxReadError, match="Duplicate source application ID"):
        read_campaign_workbook(data)


def test_missing_application_id_rejected():
    missing_id_rows = [
        {
            "Application ID": "",
            "Role Title": "No ID Role",
            "Company Name": "Co",
            "Status": "Saved",
        }
    ]
    data = build_fictional_xlsx_bytes(applications_rows=missing_id_rows)
    with pytest.raises(XlsxReadError, match="missing source application ID"):
        read_campaign_workbook(data)


def test_credentials_sheet_counts_rows_without_materializing_values():
    data = build_fictional_xlsx_bytes(credentials_count=7)
    result = read_campaign_workbook(data)
    assert result.credentials_count == 7
    # Verify no credentials content is exposed in the result object
    assert not hasattr(result, "credentials_rows")
    assert not hasattr(result, "credentials_data")
    assert not hasattr(result, "credentials_cells")


def test_missing_applications_sheet_rejected():
    data = build_fictional_xlsx_bytes(applications_sheet_name="WrongSheetName")
    with pytest.raises(XlsxReadError, match="Applications sheet not found"):
        read_campaign_workbook(data)


def test_read_applications_with_opc_absolute_relationship_targets():
    """Regression test: OPC package-absolute targets (e.g. /xl/worksheets/sheet1.xml) must parse correctly."""
    data = build_fictional_xlsx_bytes(use_opc_absolute_targets=True)
    result = read_campaign_workbook(data)
    assert len(result.rows) == 4
    assert result.rows[0].source_application_id == "APP-001"
    assert result.rows[0].company == "Acme Corp"


def test_opc_relationship_normalizer_boundaries():
    from backend.campaigns.xlsx_reader import normalize_opc_target

    # Valid package-absolute and relative paths
    assert normalize_opc_target("xl", "/xl/worksheets/sheet1.xml") == "xl/worksheets/sheet1.xml"
    assert normalize_opc_target("xl", "worksheets/sheet1.xml") == "xl/worksheets/sheet1.xml"

    # External targets rejected
    with pytest.raises(XlsxReadError, match="External relationship target"):
        normalize_opc_target("xl", "https://example.com/sheet.xml", target_mode="External")
    with pytest.raises(XlsxReadError, match="External relationship target"):
        normalize_opc_target("xl", "http://example.com/sheet.xml", target_mode="external")
    with pytest.raises(XlsxReadError, match="drive/UNC/URL prefix"):
        normalize_opc_target("xl", "https://example.com/sheet.xml")

    # Backslashes rejected
    with pytest.raises(XlsxReadError, match="backslash"):
        normalize_opc_target("xl", "worksheets\\sheet1.xml")

    # Drive or UNC rejected
    with pytest.raises(XlsxReadError, match="drive/UNC/URL prefix"):
        normalize_opc_target("xl", "C:/sheet.xml")
    with pytest.raises(XlsxReadError, match="drive/UNC/URL prefix"):
        normalize_opc_target("xl", "//server/share/sheet.xml")

    # Traversal rejected
    with pytest.raises(XlsxReadError, match="traversal"):
        normalize_opc_target("xl", "../../../etc/passwd")

    # Empty target rejected
    with pytest.raises(XlsxReadError, match="empty"):
        normalize_opc_target("xl", "")


def test_missing_sheet_member_raises_xlsx_read_error():
    custom_rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/missing.xml"/>'
    ]
    data = build_fictional_xlsx_bytes(custom_wb_rels=custom_rels, include_credentials_sheet=False)
    with pytest.raises(XlsxReadError, match="not found"):
        read_campaign_workbook(data)


def test_credentials_empty_or_whitespace_cells_not_counted():
    import io
    import zipfile

    # Build raw xlsx with whitespace/empty credential rows
    base_xlsx = build_fictional_xlsx_bytes(include_credentials_sheet=False)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()

    # Custom sheet2 with empty, whitespace, and 1 real row
    sheet2_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <sheetData>\n'
        '    <row r="1"><c r="A1" t="inlineStr"><is><t>Header</t></is></c></row>\n'
        '    <row r="2"><c r="A2" t="inlineStr"><is><t>   </t></is></c></row>\n'
        '    <row r="3"><c r="A3" t="inlineStr"><is><t></t></is></c></row>\n'
        '    <row r="4"><c r="A4"><v>   </v></c></row>\n'
        '    <row r="5"><c r="A5" t="inlineStr"><is><t>RealPlatform</t></is></c></row>\n'
        '  </sheetData>\n'
        '</worksheet>'
    )

    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b"</sheets>", b'<sheet name="Platform Credentials" sheetId="2" r:id="rId99"/></sheets>')
            elif item.filename == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
                )
            z_out.writestr(item, content)
        z_out.writestr("xl/worksheets/sheet2.xml", sheet2_xml)

    result = read_campaign_workbook(out_buf.getvalue())
    assert result.credentials_count == 1


def test_declared_credentials_missing_member_fails_closed():
    base_xlsx = build_fictional_xlsx_bytes(include_credentials_sheet=False)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b"</sheets>", b'<sheet name="Platform Credentials" sheetId="2" r:id="rId99"/></sheets>')
            elif item.filename == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/missing_creds.xml"/></Relationships>',
                )
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="not found"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_shared_strings_malformed_xml_fails():
    import io
    import zipfile

    base_xlsx = build_fictional_xlsx_bytes()
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/sharedStrings.xml":
                content = b"<broken xml unclosed"
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="invalid XML"):
        read_campaign_workbook(out_buf.getvalue())


def test_header_discovery_requires_exact_id_alias_and_rejects_candidate():
    custom_headers = ["Candidate", "Role Title", "Company Name", "Status"]
    data = build_fictional_xlsx_bytes(custom_headers=custom_headers)
    with pytest.raises(XlsxReadError, match="header row not found"):
        read_campaign_workbook(data)


def test_duplicate_normalized_headers_rejected():
    custom_headers = ["Application ID", "Status", "status", "Company Name"]
    data = build_fictional_xlsx_bytes(custom_headers=custom_headers)
    with pytest.raises(XlsxReadError, match="Duplicate header columns"):
        read_campaign_workbook(data)


def test_raw_record_contains_json_safe_dates():
    custom_rows = [
        {
            "Application ID": "APP-JSON-SAFE",
            "Role Title": "Engineer",
            "Company Name": "Acme",
            "Status": "Applied",
            "Found Date": date(2026, 1, 15),
        }
    ]
    data = build_fictional_xlsx_bytes(applications_rows=custom_rows)
    result = read_campaign_workbook(data)
    app = result.rows[0]
    # Date object exists in projection attribute
    assert app.found_at == date(2026, 1, 15)
    # Raw record contains ISO formatted string for JSON safety
    assert app.raw_record["Found Date"] == "2026-01-15"
    assert isinstance(app.raw_record["Found Date"], str)


def test_sentinel_secret_privacy_regression():
    """Privacy regression: credentials text must never be retained in memory or results."""
    import io
    import zipfile

    # Build an XLSX with sentinel credentials in shared strings and inline strings
    base_xlsx = build_fictional_xlsx_bytes(include_credentials_sheet=False)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()

    with zipfile.ZipFile(in_buf, "r") as z_in:
        sst_xml_bytes = z_in.read("xl/sharedStrings.xml")
        base_count = sst_xml_bytes.count(b"<si>")

    idx0 = base_count
    idx1 = base_count + 1
    idx2 = base_count + 2
    idx3 = base_count + 3
    idx4 = base_count + 4
    idx5 = base_count + 5
    idx6 = base_count + 6
    idx7 = base_count + 7
    idx8 = base_count + 8

    # sheet2 has:
    # row 1: header
    # row 2: shared strings idx0 ("Platform"), idx1 ("user1"), idx2 ("SENTINEL-SECRET-PWD-ALPHA")
    # row 3: shared strings idx3 ("Platform2"), idx4 ("user2"), idx5 ("   ") (whitespace)
    # row 4: inline string with "SENTINEL-SECRET-PWD-BETA"
    # row 5: only empty shared strings idx6 (""), idx7 ("   ") (should NOT count)
    # row 6: shared string idx8 ("SENTINEL-SECRET-PWD-GAMMA")
    sheet2_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <sheetData>\n'
        '    <row r="1"><c r="A1" t="inlineStr"><is><t>Platform</t></is></c><c r="B1" t="inlineStr"><is><t>Username</t></is></c><c r="C1" t="inlineStr"><is><t>Password</t></is></c></row>\n'
        f'    <row r="2"><c r="A2" t="s"><v>{idx0}</v></c><c r="B2" t="s"><v>{idx1}</v></c><c r="C2" t="s"><v>{idx2}</v></c></row>\n'
        f'    <row r="3"><c r="A3" t="s"><v>{idx3}</v></c><c r="B3" t="s"><v>{idx4}</v></c><c r="C3" t="s"><v>{idx5}</v></c></row>\n'
        '    <row r="4"><c r="A4" t="inlineStr"><is><t>InlinePlat</t></is></c><c r="B4" t="inlineStr"><is><t>user4</t></is></c><c r="C4" t="inlineStr"><is><t>SENTINEL-SECRET-PWD-BETA</t></is></c></row>\n'
        f'    <row r="5"><c r="A5" t="s"><v>{idx6}</v></c><c r="B5" t="s"><v>{idx7}</v></c></row>\n'
        f'    <row r="6"><c r="A6" t="s"><v>{idx8}</v></c></row>\n'
        '  </sheetData>\n'
        '</worksheet>'
    )

    in_buf.seek(0)
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b"</sheets>", b'<sheet name="Platform Credentials" sheetId="2" r:id="rId99"/></sheets>')
            elif item.filename == "xl/_rels/workbook.xml.rels":
                content = content.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId99" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>',
                )
            elif item.filename == "xl/sharedStrings.xml":
                sst_extra = (
                    '<si><t>PlatformExtra</t></si>'
                    '<si><t>user1</t></si>'
                    '<si><t>SENTINEL-SECRET-PWD-ALPHA</t></si>'
                    '<si><t>PlatformExtra2</t></si>'
                    '<si><t>user2</t></si>'
                    '<si><t>   </t></si>'
                    '<si><t></t></si>'
                    '<si><t>   </t></si>'
                    '<si><t>SENTINEL-SECRET-PWD-GAMMA</t></si>'
                )
                content = content.replace(b"</sst>", (sst_extra + "</sst>").encode("utf-8"))
            z_out.writestr(item, content)
        z_out.writestr("xl/worksheets/sheet2.xml", sheet2_xml)

    result = read_campaign_workbook(out_buf.getvalue())
    # Count: row 2 (data), row 3 (data), row 4 (data), row 5 (all whitespace/empty -> skipped), row 6 (data) -> 4 data rows
    assert result.credentials_count == 4

    # Sentinel secret check: NEVER materialized in any result attribute, string, repr, or row
    assert "SENTINEL-SECRET" not in repr(result)
    assert "SENTINEL-SECRET" not in str(result)
    for row in result.rows:
        assert "SENTINEL-SECRET" not in repr(row)
        for val in row.raw_record.values():
            assert "SENTINEL-SECRET" not in str(val)


def test_declared_shared_strings_missing_member_fails_closed():
    base_xlsx = build_fictional_xlsx_bytes()
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            if item.filename != "xl/sharedStrings.xml":
                z_out.writestr(item, z_in.read(item.filename))

    with pytest.raises(XlsxReadError, match="Declared sharedStrings member not found"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_styles_missing_member_fails_closed():
    base_xlsx = build_fictional_xlsx_bytes()
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            if item.filename != "xl/styles.xml":
                z_out.writestr(item, z_in.read(item.filename))

    with pytest.raises(XlsxReadError, match="Declared styles member not found"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_styles_malformed_xml_fails():
    base_xlsx = build_fictional_xlsx_bytes()
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/styles.xml":
                content = b"<broken styles xml"
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="invalid XML"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_credentials_missing_relationship_id_fails():
    base_xlsx = build_fictional_xlsx_bytes(include_credentials_sheet=False)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b"</sheets>", b'<sheet name="Platform Credentials" sheetId="2"/></sheets>')
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="missing relationship ID"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_credentials_missing_relationship_in_rels_fails():
    base_xlsx = build_fictional_xlsx_bytes(include_credentials_sheet=False)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = content.replace(b"</sheets>", b'<sheet name="Platform Credentials" sheetId="2" r:id="rIdNotExist"/></sheets>')
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="references missing relationship"):
        read_campaign_workbook(out_buf.getvalue())


def test_declared_credentials_malformed_xml_fails():
    base_xlsx = build_fictional_xlsx_bytes(credentials_count=1)
    in_buf = io.BytesIO(base_xlsx)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as z_in, zipfile.ZipFile(out_buf, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/worksheets/sheet2.xml":
                content = b"<broken worksheet xml"
            z_out.writestr(item, content)

    with pytest.raises(XlsxReadError, match="invalid XML"):
        read_campaign_workbook(out_buf.getvalue())


def test_inner_xlsx_zip_security_bounds(monkeypatch):
    import io
    import stat
    import zipfile

    # 1. Traversal segment
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/../secret.txt", b"x")
    with pytest.raises(XlsxReadError, match="traversal"):
        read_campaign_workbook(buf.getvalue())

    # 2. Encrypted entry
    base_xlsx = build_fictional_xlsx_bytes()
    raw = bytearray(base_xlsx)
    cd_offset = raw.find(b"PK\x01\x02")
    raw[cd_offset + 8] |= 0x01
    with pytest.raises(XlsxReadError, match="encrypted"):
        read_campaign_workbook(bytes(raw))

    # 3. Members count limit
    monkeypatch.setattr("backend.campaigns.xlsx_security.XLSX_MAX_MEMBERS", 3)
    with pytest.raises(XlsxReadError, match="exceeds members limit"):
        read_campaign_workbook(base_xlsx)

    # 4. Total expanded bytes limit
    monkeypatch.undo()
    monkeypatch.setattr("backend.campaigns.xlsx_security.XLSX_MAX_EXPANDED_BYTES", 50)
    with pytest.raises(XlsxReadError, match="exceeds expanded limit"):
        read_campaign_workbook(base_xlsx)

    # 5. Member size limit
    monkeypatch.undo()
    monkeypatch.setattr("backend.campaigns.xlsx_security.XLSX_MAX_MEMBER_BYTES", 50)
    with pytest.raises(XlsxReadError, match="exceeds size limit"):
        read_campaign_workbook(base_xlsx)

    # 6. Symlink entry
    monkeypatch.undo()
    buf_sym = io.BytesIO()
    with zipfile.ZipFile(buf_sym, "w") as zf:
        zinfo = zipfile.ZipInfo("xl/workbook.xml")
        zinfo.external_attr = (stat.S_IFLNK << 16)
        zf.writestr(zinfo, b"target")
    with pytest.raises(XlsxReadError, match="symlink"):
        read_campaign_workbook(buf_sym.getvalue())

    # 7. Absolute path
    buf_abs = io.BytesIO()
    with zipfile.ZipFile(buf_abs, "w") as zf:
        zf.writestr("/xl/workbook.xml", b"x")
    with pytest.raises(XlsxReadError, match="absolute path"):
        read_campaign_workbook(buf_abs.getvalue())

    # 8. Backslash in entry name
    buf_bs = io.BytesIO()
    with zipfile.ZipFile(buf_bs, "w") as zf:
        zf.writestr("test.xml", b"x")
    raw_bs = bytearray(buf_bs.getvalue()).replace(b"test.xml", b"a\\cd.xml")
    with pytest.raises(XlsxReadError, match="backslash"):
        read_campaign_workbook(bytes(raw_bs))

    # 9. Drive or UNC path
    buf_drive = io.BytesIO()
    with zipfile.ZipFile(buf_drive, "w") as zf:
        zf.writestr("C:/xl/workbook.xml", b"x")
    with pytest.raises(XlsxReadError, match="drive or UNC"):
        read_campaign_workbook(buf_drive.getvalue())

    # 10. Duplicate entry
    buf_dup = io.BytesIO()
    with zipfile.ZipFile(buf_dup, "w") as zf:
        zf.writestr("xl/workbook.xml", b"one")
        zf.writestr("XL/WORKBOOK.XML", b"two")
    with pytest.raises(XlsxReadError, match="duplicate entry"):
        read_campaign_workbook(buf_dup.getvalue())

    # 11. Unicode NFC casefold duplicate entry
    buf_uni = io.BytesIO()
    with zipfile.ZipFile(buf_uni, "w") as zf:
        zf.writestr("xl/resum\u0065\u0301.xml", b"one")
        zf.writestr("xl/RESUM\u00c9.xml", b"two")
    with pytest.raises(XlsxReadError, match="duplicate entry"):
        read_campaign_workbook(buf_uni.getvalue())

    # 12. Control characters in entry name
    buf_ctrl = io.BytesIO(base_xlsx)
    out_ctrl = io.BytesIO()
    with zipfile.ZipFile(buf_ctrl, "r") as z_in, zipfile.ZipFile(out_ctrl, "w") as z_out:
        for item in z_in.infolist():
            z_out.writestr(item, z_in.read(item.filename))
        z_out.writestr("xl/work\x01sheet.xml", b"x")
    with pytest.raises(XlsxReadError, match="control characters"):
        read_campaign_workbook(out_ctrl.getvalue())

    # 13. Control characters in relationship target
    buf_rel_ctrl = io.BytesIO(base_xlsx)
    out_rel_ctrl = io.BytesIO()
    with zipfile.ZipFile(buf_rel_ctrl, "r") as z_in, zipfile.ZipFile(out_rel_ctrl, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/_rels/workbook.xml.rels":
                content = content.replace(b'Target="worksheets/sheet1.xml"', 'Target="worksheets/sheet\u200b1.xml"'.encode("utf-8"))
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="control characters"):
        read_campaign_workbook(out_rel_ctrl.getvalue())


def test_streaming_parser_bypasses_tree_for_shared_strings_and_credentials(monkeypatch):
    """Regression test proving neither sharedStrings.xml nor credentials worksheet goes through safe_read_xml tree parser."""
    import backend.campaigns.xlsx_reader as reader_mod

    calls: list[str] = []
    orig_safe_read = reader_mod.safe_read_xml

    def spy_safe_read(zf, path):
        calls.append(path)
        return orig_safe_read(zf, path)

    monkeypatch.setattr(reader_mod, "safe_read_xml", spy_safe_read)

    data = build_fictional_xlsx_bytes(credentials_count=3)
    result = read_campaign_workbook(data)
    assert result.credentials_count == 3

    # Proves safe_read_xml was called for package metadata and Applications sheet
    assert "xl/workbook.xml" in calls
    assert "xl/_rels/workbook.xml.rels" in calls
    assert any("sheet1" in c for c in calls)

    # Proves NEITHER sharedStrings.xml nor credentials sheet went through safe_read_xml (tree parser)
    assert not any("sharedstrings" in c.lower() for c in calls)
    assert not any("sheet2" in c.lower() for c in calls)


def test_reject_dtd_and_entity_in_xml():
    base_xlsx = build_fictional_xlsx_bytes(credentials_count=1)

    # 1. DTD in workbook.xml
    buf_dtd = io.BytesIO(base_xlsx)
    out_dtd = io.BytesIO()
    with zipfile.ZipFile(buf_dtd, "r") as z_in, zipfile.ZipFile(out_dtd, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/workbook.xml":
                content = b'<!DOCTYPE workbook SYSTEM "http://example.com/evil.dtd">\n' + content
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="DTD or ENTITY"):
        read_campaign_workbook(out_dtd.getvalue())

    # 2. ENTITY in sharedStrings.xml
    buf_ent = io.BytesIO(base_xlsx)
    out_ent = io.BytesIO()
    with zipfile.ZipFile(buf_ent, "r") as z_in, zipfile.ZipFile(out_ent, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/sharedStrings.xml":
                content = b'<!DOCTYPE sst [<!ENTITY xxe "evil">]>\n' + content
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="DTD or ENTITY"):
        read_campaign_workbook(out_ent.getvalue())

    # 3. DTD in credentials worksheet
    buf_cred = io.BytesIO(base_xlsx)
    out_cred = io.BytesIO()
    with zipfile.ZipFile(buf_cred, "r") as z_in, zipfile.ZipFile(out_cred, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/worksheets/sheet2.xml":
                content = b'<!DOCTYPE worksheet SYSTEM "evil.dtd">\n' + content
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="DTD or ENTITY"):
        read_campaign_workbook(out_cred.getvalue())


def test_shared_strings_part_absent_fails_closed():
    # Workbook has cells with t="s", but sharedStrings part is absent from rels and package
    custom_wb_rels = [
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    ]
    data = build_fictional_xlsx_bytes(
        use_inline_strings=False,
        include_credentials_sheet=False,
        custom_wb_rels=custom_wb_rels,
    )
    # Remove sharedStrings.xml from package
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as z_in, zipfile.ZipFile(out, "w") as z_out:
        for item in z_in.infolist():
            if item.filename != "xl/sharedStrings.xml":
                z_out.writestr(item, z_in.read(item.filename))

    with pytest.raises(XlsxReadError, match="sharedStrings part is absent"):
        read_campaign_workbook(out.getvalue())


def test_negative_and_out_of_range_shared_references_fail_closed():
    base_xlsx = build_fictional_xlsx_bytes(use_inline_strings=False, include_credentials_sheet=False)

    # 1. Out of range shared-string index
    buf1 = io.BytesIO(base_xlsx)
    out1 = io.BytesIO()
    with zipfile.ZipFile(buf1, "r") as z_in, zipfile.ZipFile(out1, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                # Replace a shared-string index with 99999
                content = content.replace(b'<v>0</v>', b'<v>99999</v>', 1)
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="out of range"):
        read_campaign_workbook(out1.getvalue())

    # 2. Negative shared-string index
    buf2 = io.BytesIO(base_xlsx)
    out2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "r") as z_in, zipfile.ZipFile(out2, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<v>0</v>', b'<v>-1</v>', 1)
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="Negative shared-string index"):
        read_campaign_workbook(out2.getvalue())

    # 3. Malformed shared-string index
    buf3 = io.BytesIO(base_xlsx)
    out3 = io.BytesIO()
    with zipfile.ZipFile(buf3, "r") as z_in, zipfile.ZipFile(out3, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b'<v>0</v>', b'<v>not_a_number</v>', 1)
            z_out.writestr(item, content)
    with pytest.raises(XlsxReadError, match="Malformed shared-string index"):
        read_campaign_workbook(out3.getvalue())


def test_credentials_handler_never_buffers_or_retains_scalar_sentinel():
    """Verify scalar credential values are never buffered or joined in memory."""
    import xml.sax

    from backend.campaigns.xlsx_stream import (
        _CredentialsSheetHandler,
        scan_credentials_worksheet_stream,
    )

    sentinel = "SENTINEL-SCALAR-SECRET-VALUE-NEVER-BUFFERED-987654321"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <sheetData>\n'
        '    <row r="1">\n'
        '      <c r="A1"><v>HeaderPlatform</v></c>\n'
        '      <c r="B1"><v>HeaderUser</v></c>\n'
        '      <c r="C1"><v>HeaderPass</v></c>\n'
        '    </row>\n'
        '    <row r="2">\n'
        '      <c r="A2"><v>LinkedIn</v></c>\n'
        f'      <c r="B2"><v>{sentinel}</v></c>\n'
        '    </row>\n'
        '    <row r="3">\n'
        '      <c r="A3" t="s"><v>42</v></c>\n'
        '    </row>\n'
        '  </sheetData>\n'
        '</worksheet>'
    ).encode("utf-8")

    # 1. Drive through scan_credentials_worksheet_stream
    probes = scan_credentials_worksheet_stream(xml_content)
    assert len(probes) == 3

    # Row 1 has scalar headers
    assert probes[0].has_non_empty_scalar is True
    # Row 2 has scalar values including the sentinel
    assert probes[1].has_non_empty_scalar is True
    # Row 3 has shared-string index 42
    assert probes[2].shared_indices == [42]

    # Prove sentinel text is not anywhere in the returned probes structure
    assert sentinel not in repr(probes)
    assert sentinel not in str(probes)

    # 2. Directly drive the SAX handler and verify internal state during and after parsing
    handler = _CredentialsSheetHandler()
    parser = xml.sax.make_parser()
    parser.setContentHandler(handler)
    parser.parse(io.BytesIO(xml_content))

    # Verify shared_index_parts only buffered shared indices and never the scalar sentinel
    assert handler.shared_index_parts == []
    # Verify no attribute on handler holds the sentinel
    for slot in handler.__slots__:
        val = getattr(handler, slot)
        assert sentinel not in str(val)

    # 3. Verify malformed and negative shared index validation in credentials sheet stream
    malformed_xml = b'<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>invalid</v></c></row></sheetData></worksheet>'
    with pytest.raises(XlsxReadError, match="Malformed shared-string index"):
        scan_credentials_worksheet_stream(malformed_xml)

    negative_xml = b'<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>-9</v></c></row></sheetData></worksheet>'
    with pytest.raises(XlsxReadError, match="Negative shared-string index"):
        scan_credentials_worksheet_stream(negative_xml)


def test_audited_28_headers_projections_and_verbatim_raw_record():
    from tests.backend.campaigns.fixture_builder import AUDITED_28_HEADERS

    assert len(AUDITED_28_HEADERS) == 28

    fictional_row = {
        "Application ID": "APP-28-AUDITED",
        "Role Title": "Principal Systems Engineer",
        "Company Name": "Apex Technologies",
        "Location": "Basel",
        "Job Category": "Systems",
        "Platform / Source": "LinkedIn Jobs",
        "Status": "Applied",
        "Priority": "High",
        "Platform URL": "https://linkedin.com/jobs/view/9999",
        "Job Posting URL": "https://careers.apex.example.com/jobs/9999",
        "Outcome": "Interview scheduled",
        "Date Found": date(2026, 2, 1),
        "Application Date": date(2026, 2, 3),
        "Follow-up Date": date(2026, 2, 17),
        "Last Update": date(2026, 2, 10),
        "Next Action": "Prepare presentation",
        "Notes": "Synthetic fictional notes for audited row",
        "Contact Person": "Jane Doe",
        "Contact Email": "jane.doe@apex.example.com",
        "Salary Range": "150k-170k CHF",
        "Workplace Type": "Hybrid",
        "Contract Type": "Permanent",
        "Requirements Summary": "Rust, Python, Linux kernel",
        "CV Template Used": "Systems-Template-v2",
        "Cover Letter Sent": "Yes",
        "Referral": "John Smith",
        "Archive Reason": "N/A",
        "Comments": "First-round screening passed",
    }

    data = build_fictional_xlsx_bytes(
        applications_rows=[fictional_row],
        custom_headers=AUDITED_28_HEADERS,
    )
    result = read_campaign_workbook(data)
    assert len(result.rows) == 1
    row = result.rows[0]

    # Verify all typed projections
    assert row.source_application_id == "APP-28-AUDITED"
    assert row.title == "Principal Systems Engineer"
    assert row.company == "Apex Technologies"
    assert row.location == "Basel"
    assert row.status == "Applied"
    assert row.priority == "High"
    assert row.platform == "LinkedIn Jobs"
    assert row.category == "Systems"
    assert row.outcome == "Interview scheduled"
    assert row.found_at == date(2026, 2, 1)
    assert row.applied_at == date(2026, 2, 3)
    assert row.follow_up_at == date(2026, 2, 17)
    assert row.last_update_at == date(2026, 2, 10)
    assert row.platform_url == "https://linkedin.com/jobs/view/9999"
    assert row.job_posting_url == "https://careers.apex.example.com/jobs/9999"
    # Deterministic preferred URL: job_posting_url first, then platform_url
    assert row.url == "https://careers.apex.example.com/jobs/9999"
    assert row.next_action == "Prepare presentation"
    assert row.notes == "Synthetic fictional notes for audited row"

    # Verify all 28 raw record keys are preserved verbatim
    assert len(row.raw_record) == 28
    for h in AUDITED_28_HEADERS:
        assert h in row.raw_record, f"Missing raw header: {h}"
        expected_val = fictional_row[h]
        if isinstance(expected_val, date):
            assert row.raw_record[h] == expected_val.isoformat()
        else:
            assert row.raw_record[h] == expected_val

    # Verify URL priority fallback: when Job Posting URL is absent, platform_url is preferred
    fictional_row_no_job_url = dict(fictional_row)
    fictional_row_no_job_url["Application ID"] = "APP-NO-JOB-URL"
    fictional_row_no_job_url["Job Posting URL"] = ""
    data2 = build_fictional_xlsx_bytes(
        applications_rows=[fictional_row_no_job_url],
        custom_headers=AUDITED_28_HEADERS,
    )
    result2 = read_campaign_workbook(data2)
    row2 = result2.rows[0]
    assert row2.job_posting_url is None
    assert row2.platform_url == "https://linkedin.com/jobs/view/9999"
    assert row2.url == "https://linkedin.com/jobs/view/9999"
