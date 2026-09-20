import io
from email import policy
from email.parser import BytesParser

import pytest
from docx import Document
from pypdf import PdfReader

from backend.applications.dossier_materials import _letter_sender
from backend.applications.email import generate_email_artifacts, validate_email_draft
from backend.applications.letters import (
    PageBudgetExceededError,
    _format_links_for_reportlab,
    generate_letter_artifacts,
)
from backend.applications.schemas import EmailDraft, GenerationProvenance, LetterOptions


@pytest.mark.parametrize(
    "patch",
    [
        {"source": "external_agent"},
        {"source": "unknown"},
        {"request_id": "bad"},
        {"grant_id": "bad"},
        {"input_digest": "a" * 63},
        {"payload_digest": "A" * 64},
        {"generated_at": "2026-09-13T12:00:00"},
        {"generated_at": "invalid"},
    ],
)
def test_generation_provenance_rejects_invalid_metadata(patch):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GenerationProvenance.model_validate(patch)


def test_generation_provenance_roundtrips_typed_metadata():
    value = dict(
        source="external-agent",
        request_id="11111111-1111-4111-8111-111111111111",
        grant_id="22222222-2222-4222-8222-222222222222",
        input_digest="a" * 64,
        payload_digest="b" * 64,
        generated_at="2026-09-13T12:00:00Z",
    )
    assert GenerationProvenance.model_validate(value).model_dump(mode="json") == value


@pytest.mark.parametrize("canvas", [False, True])
def test_letter_sender_preserves_selected_identity_and_excludes_hidden_contacts(canvas):
    snapshot = dict(
        profile=dict(
            display_name="Synthetic Owner",
            email="hidden@example.test",
            phone="hidden-phone",
            location={"city": "Selected City"},
            website="https://hidden.example.test",
        ),
        resume=dict(section_config=dict(order=[], include_location=True)),
        facts=[],
    )
    if canvas:
        snapshot["resume"]["canvas_document"] = dict(
            sections=[
                dict(
                    kind="identity",
                    title="Identity",
                    blocks=[
                        dict(
                            visible=True,
                            content=dict(
                                title="Approved Alias",
                                description="selected@example.test\nSelected City",
                            ),
                        )
                    ],
                )
            ]
        )
    name, contacts = _letter_sender(snapshot)
    assert name == ("Approved Alias" if canvas else "Synthetic Owner")
    assert contacts == (["selected@example.test", "Selected City"] if canvas else ["Selected City"])
    assert "hidden" not in " ".join(contacts)


def letter_values(**overrides):
    values = dict(
        cover_letter="I document platform operations in Zürich and Łódź.\n\n"
        "Details: https://example.test/work?a=1&b=2",
        options=LetterOptions(),
        applicant_name="Mira Vale",
        applicant_contact=["mira@example.test", "Zürich, CH"],
        recipient_lines=["Example AG", "Recruiting team"],
        subject="Platform application",
        date_str="2026-09-13",
    )
    return values | overrides


def test_letter_exports_one_a4_page_all_visible_text_and_actual_links():
    values = letter_values()
    artifacts = generate_letter_artifacts(**values)
    pdf = PdfReader(io.BytesIO(artifacts["cover_letter.pdf"][0]), strict=True)
    assert len(pdf.pages) == 1
    page = pdf.pages[0]
    assert float(page.mediabox.width) == pytest.approx(595.276, abs=1)
    assert float(page.mediabox.height) == pytest.approx(841.89, abs=1)
    text = page.extract_text()
    for required in [
        "Mira Vale",
        "mira@example.test",
        "Zürich",
        "Łódź",
        "Example AG",
        "Recruiting team",
        "2026-09-13",
        "Platform application",
        "Sincerely,",
    ]:
        assert required in text
    urls = [str(item.get_object()["/A"]["/URI"]) for item in page["/Annots"]]
    assert "https://example.test/work?a=1&b=2" in urls
    doc = Document(io.BytesIO(artifacts["cover_letter.docx"][0]))
    extracted = " ".join(doc.element.xpath(".//w:t/text()"))
    for required in ["Mira Vale", "mira@example.test", "Zürich", "Łódź", "Recruiting team"]:
        assert required in extracted
    assert "https://example.test/work?a=1&b=2" in [r.target_ref for r in doc.part.rels.values()]
    assert all(
        s.page_width.mm == pytest.approx(210, abs=0.1)
        and s.page_height.mm == pytest.approx(297, abs=0.1)
        for s in doc.sections
    )


def test_letter_escapes_every_fragment_even_when_a_link_is_present():
    markup = '<img src="file:///private/photo.jpg"/> <b>literal</b> https://example.test'
    formatted = _format_links_for_reportlab(markup)
    assert "<img" not in formatted and "<b>literal" not in formatted
    assert "&lt;img" in formatted and "&lt;b&gt;literal" in formatted
    artifacts = generate_letter_artifacts(**letter_values(cover_letter=markup))
    assert (
        "<b>literal</b>"
        in PdfReader(io.BytesIO(artifacts["cover_letter.pdf"][0])).pages[0].extract_text()
    )


def test_letter_page_budget_also_applies_to_docx_only_selection():
    with pytest.raises(PageBudgetExceededError):
        generate_letter_artifacts(
            **letter_values(
                cover_letter=("A complete paragraph about local operations. " * 40 + "\n\n") * 20,
                options=LetterOptions(formats=["docx"]),
            )
        )


@pytest.mark.parametrize(
    "options",
    [
        {"preset_id": "unknown"},
        {"template_version": 999},
        {"formats": []},
        {"formats": ["pdf", "pdf"]},
        {"preset_id": "software-en", "locale": "de"},
    ],
)
def test_letter_rejects_unsupported_template_contract(options):
    with pytest.raises(ValueError):
        LetterOptions(**options)


@pytest.mark.parametrize(
    "overrides",
    [
        {"recipient": "not an email"},
        {"subject": "Subject\x01hidden"},
        {"recipient": "a@example.test\r\nBcc:b@example.test"},
        {"attachment_names": [" resume.pdf "]},
        {"attachment_names": ["../resume.pdf"]},
        {"attachment_names": ["missing.pdf"]},
        {"subject": "[COMPANY]"},
    ],
)
def test_email_rejects_invalid_mailbox_headers_names_and_placeholders(overrides):
    with pytest.raises(ValueError):
        draft = EmailDraft(
            **(
                dict(
                    recipient="review@example.test",
                    subject="Application",
                    body="Please review the attached CV.",
                    attachment_names=["resume.pdf"],
                )
                | overrides
            )
        )
        validate_email_draft(draft, {"resume.pdf"}, require_complete=True)


def test_email_preserves_validated_names_in_offline_artifacts():
    draft = EmailDraft(
        recipient="review@example.test",
        subject="Application",
        body="Please review the CV.",
        attachment_names=["resume.pdf"],
    )
    validate_email_draft(draft, {"resume.pdf"}, require_complete=True)
    artifacts = generate_email_artifacts(draft)
    message = BytesParser(policy=policy.default).parsebytes(artifacts["email_draft.eml"][0])
    assert str(message["To"]) == draft.recipient
    assert str(message["X-CareerOS-Attachments"]) == "resume.pdf"
    assert message.get_body().get_content().strip() == draft.body
    assert "- resume.pdf" in artifacts["email_checklist.txt"][0].decode()
