from __future__ import annotations

import re
from html import escape
from urllib.parse import unquote, urlsplit

from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import parse_xml

SAFE_SCHEMES = {"http", "https", "mailto"}
URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'{}|\\^`]+|mailto:[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
)


def is_safe_url(url: str) -> bool:
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    decoded = unquote(url)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in decoded):
        return False
    if any(char in url for char in ("\\", '"', "<", ">")):
        return False
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in SAFE_SCHEMES:
            return False
        if parsed.scheme == "mailto":
            return bool(re.fullmatch(r"[^@/:?#]+@[^@/:?#]+\.[^@/:?#]+", parsed.path)) and not (
                parsed.netloc or parsed.query or parsed.fragment
            )
        return (
            bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def format_pdf_link(url: str, text: str | None = None, color: str = "#1D4ED8") -> str:
    cleaned = url
    if not is_safe_url(cleaned):
        return escape(text or cleaned)
    display = escape(text or cleaned)
    return f'<a href="{escape(cleaned)}" color="{color}"><u>{display}</u></a>'


def add_docx_hyperlink(
    paragraph,
    url: str,
    text: str | None = None,
    color: str = "1D4ED8",
    underline: bool = True,
    font_size_pt: float | None = None,
) -> None:
    cleaned = url
    display = (text or cleaned).strip()
    if not is_safe_url(cleaned):
        run = paragraph.add_run(display)
        if font_size_pt:
            from docx.shared import Pt

            run.font.size = Pt(font_size_pt)
        return

    part = paragraph.part
    r_id = part.relate_to(cleaned, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hex_color = color.lstrip("#")
    u_val = "single" if underline else "none"
    sz_xml = f'<w:sz w:val="{int(font_size_pt * 2)}"/>' if font_size_pt else ""

    xml = (
        f'<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'r:id="{r_id}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<w:r><w:rPr><w:color w:val="{hex_color}"/><w:u w:val="{u_val}"/>{sz_xml}</w:rPr>'
        f"<w:t>{escape(display)}</w:t></w:r></w:hyperlink>"
    )
    paragraph._p.append(parse_xml(xml))
