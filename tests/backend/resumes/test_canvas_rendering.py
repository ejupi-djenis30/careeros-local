from io import BytesIO
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from docx import Document
from PIL import Image
from pypdf import PdfReader


def test_saved_canvas_drives_pdf_docx_order_visibility_and_ats_quality(
    client, auth_headers, saved_detailed_profile, monkeypatch
):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", directory)
        generated = client.post(
            "/api/v1/resumes/generate",
            json={"title": "Canvas parity", "template_kind": "ats"},
            headers=auth_headers,
        )
        assert generated.status_code == 201, generated.text
        draft = generated.json()
        canvas = draft["canvas_document"]
        experience = next(section for section in canvas["sections"] if section["kind"] == "experience")
        education = next(section for section in canvas["sections"] if section["kind"] == "education")
        skill = next(section for section in canvas["sections"] if section["kind"] == "skill")
        experience["blocks"][0]["content"]["title"] = "Tailored Principal Engineer"
        experience["blocks"][0]["manual_fields"] = ["title"]
        experience["page_break_before"] = True
        skill["visible"] = False
        remaining = [
            section
            for section in canvas["sections"]
            if section["id"] not in {education["id"], experience["id"]}
        ]
        identity_summary = [
            section for section in remaining if section["kind"] in {"identity", "summary"}
        ]
        other = [section for section in remaining if section["kind"] not in {"identity", "summary"}]
        canvas["sections"] = [*identity_summary, education, experience, *other]
        payload = {
            "expected_revision": draft["revision"],
            "title": draft["title"],
            "template_kind": draft["template_kind"],
            "section_config": draft["section_config"],
            "selected_fact_ids": draft["selected_fact_ids"],
            "content_overrides": draft["content_overrides"],
            "photo_asset_id": None,
            "canvas_document": canvas,
        }
        saved = client.put(
            f"/api/v1/resumes/{draft['id']}", json=payload, headers=auth_headers
        )
        assert saved.status_code == 200, saved.text
        published = client.post(
            f"/api/v1/resumes/{draft['id']}/publish", headers=auth_headers
        )
        assert published.status_code == 201, published.text
        version = published.json()
        assert version["quality_report"]["layout"] == "single-column"
        assert version["quality_report"]["pdf_image_count"] == 0
        assert version["quality_report"]["page_count"] >= 2

        artifacts = {item["format"]: item for item in version["artifacts"]}
        pdf_bytes = client.get(
            f"/api/v1/resume-artifacts/{artifacts['pdf']['id']}", headers=auth_headers
        ).content
        pdf = PdfReader(BytesIO(pdf_bytes))
        pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        docx_bytes = client.get(
            f"/api/v1/resume-artifacts/{artifacts['docx']['id']}", headers=auth_headers
        ).content
        docx_text = "\n".join(paragraph.text for paragraph in Document(BytesIO(docx_bytes)).paragraphs)

        for text in (pdf_text, docx_text):
            assert "Tailored Principal Engineer" in text
            assert "Python" not in text
            assert text.index("EDUCATION") < text.index("EXPERIENCE")


def test_photo_canvas_uses_normalized_preview_and_two_column_pdf_docx(
    client, auth_headers, saved_detailed_profile, monkeypatch
):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr("backend.storage.atomic.settings.DATA_DIR", directory)
        source = BytesIO()
        Image.new("RGB", (900, 700), (38, 70, 83)).save(source, format="PNG")
        uploaded = client.post(
            "/api/v1/career-profile/photo",
            files={"file": ("profile.png", source.getvalue(), "image/png")},
            headers=auth_headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        photo = uploaded.json()
        preview = client.get(
            f"/api/v1/career-profile/photo/{photo['id']}", headers=auth_headers
        )
        assert preview.status_code == 200
        assert preview.headers["content-type"] == "image/jpeg"
        with Image.open(BytesIO(preview.content)) as normalized:
            assert normalized.size == (720, 720)
            assert not normalized.getexif()

        generated = client.post(
            "/api/v1/resumes/generate",
            json={
                "title": "Two-column photo canvas",
                "template_kind": "photo",
                "photo_asset_id": photo["id"],
            },
            headers=auth_headers,
        )
        assert generated.status_code == 201, generated.text
        draft = generated.json()
        canvas = draft["canvas_document"]
        canvas["style"]["columns"] = 2
        saved = client.put(
            f"/api/v1/resumes/{draft['id']}",
            json={
                "expected_revision": draft["revision"],
                "title": draft["title"],
                "template_kind": "photo",
                "section_config": draft["section_config"],
                "selected_fact_ids": draft["selected_fact_ids"],
                "content_overrides": draft["content_overrides"],
                "photo_asset_id": photo["id"],
                "canvas_document": canvas,
            },
            headers=auth_headers,
        )
        assert saved.status_code == 200, saved.text
        published = client.post(
            f"/api/v1/resumes/{draft['id']}/publish", headers=auth_headers
        )
        assert published.status_code == 201, published.text
        version = published.json()
        assert version["quality_report"]["layout"] == "two-column-photo"
        assert version["quality_report"]["pdf_image_count"] >= 1

        artifacts = {item["format"]: item for item in version["artifacts"]}
        pdf_bytes = client.get(
            f"/api/v1/resume-artifacts/{artifacts['pdf']['id']}", headers=auth_headers
        ).content
        page = PdfReader(BytesIO(pdf_bytes)).pages[0]
        heading_x: list[float] = []

        def capture_heading(text, current_matrix, text_matrix, _font, _size):
            if any(heading in text for heading in ("EXPERIENCE", "EDUCATION", "SKILLS")):
                x_position = (
                    float(text_matrix[4]) * float(current_matrix[0])
                    + float(text_matrix[5]) * float(current_matrix[2])
                    + float(current_matrix[4])
                )
                heading_x.append(x_position)

        page.extract_text(visitor_text=capture_heading)
        page_width = float(page.mediabox.width)
        assert min(heading_x) < page_width * 0.35
        assert max(heading_x) > page_width * 0.45

        docx_bytes = client.get(
            f"/api/v1/resume-artifacts/{artifacts['docx']['id']}", headers=auth_headers
        ).content
        with ZipFile(BytesIO(docx_bytes)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        assert "<w:cols" in document_xml
        assert 'w:num="2"' in document_xml
