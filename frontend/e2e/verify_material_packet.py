"""Verify the real browser downloads with independent document parsers."""

import hashlib
import json
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from pypdf import PdfReader


def verify(folder: Path) -> None:
    with ZipFile(folder / "packet.zip") as packet:
        manifest = json.loads(packet.read("manifest.json"))
        assert manifest["schema_version"] == "3.0"
        assert manifest["generation_provenance"]["source"] == "external-agent"
        entries = manifest["entries"]
        assert len({entry["path"] for entry in entries}) == len(entries)
        for entry in entries:
            data = packet.read(entry["path"])
            assert len(data) == entry["byte_size"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            downloaded = folder / entry["path"]
            if downloaded.is_file():
                assert downloaded.read_bytes() == data
        assert len(json.loads(packet.read("material-evidence.json"))) == 3
    pdf = PdfReader(folder / "cover_letter.pdf")
    assert len(pdf.pages) == 1
    assert all(abs(float(page.mediabox.width) - 595.28) < 1 for page in pdf.pages)
    text = "\n".join(page.extract_text() for page in pdf.pages)
    assert "Python" in text and "Application" in text and "Synthetic Systems" in text
    doc = Document(folder / "cover_letter.docx")
    assert "Python" in "\n".join(para.text for para in doc.paragraphs)
    assert abs(doc.sections[0].page_width.mm - 210) < 1
    email = BytesParser(policy=policy.default).parsebytes((folder / "email_draft.eml").read_bytes())
    assert email["Subject"] == "Application — reviewed locally"
    assert email["X-CareerOS-Email-Mode"] == "motivational"
    assert "Python" in email.get_content()
    assert "CareerOS never sends emails" in (folder / "email_checklist.txt").read_text()
    print("Verified manifest, exact member bytes, A4 letter text, and offline email")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
