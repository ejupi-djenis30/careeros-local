"""Streaming SAX parsers for shared strings and credentials without DOM trees."""

from __future__ import annotations

import io
import xml.sax
from dataclasses import dataclass

from backend.campaigns.xlsx_security import XlsxReadError, check_no_dtd_or_entity


@dataclass(slots=True)
class CredentialRowProbe:
    shared_indices: list[int]
    has_non_empty_inline: bool
    has_non_empty_scalar: bool

    def is_non_empty(self, cred_strings_non_empty: dict[int, bool]) -> bool:
        if self.has_non_empty_inline or self.has_non_empty_scalar:
            return True
        return any(cred_strings_non_empty.get(idx, False) for idx in self.shared_indices)


class _CredentialsSheetHandler(xml.sax.ContentHandler):
    __slots__ = (
        "current_row",
        "row_probes",
        "in_cell",
        "cell_type",
        "in_is",
        "in_t",
        "in_v",
        "shared_index_parts",
    )

    def __init__(self) -> None:
        super().__init__()
        self.row_probes: list[CredentialRowProbe] = []
        self.current_row: CredentialRowProbe | None = None
        self.in_cell = False
        self.cell_type: str | None = None
        self.in_is = False
        self.in_t = False
        self.in_v = False
        self.shared_index_parts: list[str] = []

    def startElement(self, name: str, attrs: xml.sax.xmlreader.AttributesImpl) -> None:
        tag = name.split(":")[-1]
        if tag == "row":
            self.current_row = CredentialRowProbe(
                shared_indices=[],
                has_non_empty_inline=False,
                has_non_empty_scalar=False,
            )
        elif tag == "c":
            self.in_cell = True
            self.cell_type = attrs.get("t")
            self.shared_index_parts = []
        elif tag == "is":
            self.in_is = True
        elif tag == "t":
            self.in_t = True
        elif tag == "v":
            self.in_v = True

    def characters(self, content: str) -> None:
        if not self.current_row:
            return
        if self.in_is and self.in_t:
            if content.strip():
                self.current_row.has_non_empty_inline = True
        elif self.in_v:
            if self.cell_type == "s":
                self.shared_index_parts.append(content)
            else:
                if content.strip():
                    self.current_row.has_non_empty_scalar = True

    def endElement(self, name: str) -> None:
        tag = name.split(":")[-1]
        if tag == "row":
            if self.current_row is not None:
                self.row_probes.append(self.current_row)
                self.current_row = None
        elif tag == "c":
            if self.current_row is not None:
                if self.cell_type == "s":
                    val_str = "".join(self.shared_index_parts).strip()
                    if val_str:
                        try:
                            idx = int(val_str)
                        except ValueError as exc:
                            raise XlsxReadError(f"Malformed shared-string index: {val_str}") from exc
                        if idx < 0:
                            raise XlsxReadError(f"Negative shared-string index: {idx}")
                        self.current_row.shared_indices.append(idx)
            self.in_cell = False
            self.cell_type = None
            self.shared_index_parts = []
        elif tag == "is":
            self.in_is = False
        elif tag == "t":
            self.in_t = False
        elif tag == "v":
            self.in_v = False


def scan_credentials_worksheet_stream(xml_bytes: bytes, path: str = "Platform Credentials") -> list[CredentialRowProbe]:
    check_no_dtd_or_entity(xml_bytes, path)
    handler = _CredentialsSheetHandler()
    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_external_ges, False)
    parser.setFeature(xml.sax.handler.feature_external_pes, False)
    parser.setContentHandler(handler)
    try:
        parser.parse(io.BytesIO(xml_bytes))
    except (xml.sax.SAXException, ValueError) as exc:
        if isinstance(exc, XlsxReadError):
            raise
        raise XlsxReadError(f"Credentials sheet contains invalid XML: {exc}") from exc
    return handler.row_probes


class _SharedStringsHandler(xml.sax.ContentHandler):
    __slots__ = (
        "app_indices",
        "cred_indices",
        "app_strings",
        "cred_non_empty",
        "current_idx",
        "in_si",
        "in_t",
        "is_app",
        "is_cred",
        "text_buffer",
        "has_cred_text",
    )

    def __init__(self, app_indices: set[int], cred_indices: set[int]) -> None:
        super().__init__()
        self.app_indices = app_indices
        self.cred_indices = cred_indices
        self.app_strings: dict[int, str] = {}
        self.cred_non_empty: dict[int, bool] = {}
        self.current_idx = -1
        self.in_si = False
        self.in_t = False
        self.is_app = False
        self.is_cred = False
        self.text_buffer: list[str] = []
        self.has_cred_text = False

    def startElement(self, name: str, attrs: xml.sax.xmlreader.AttributesImpl) -> None:
        tag = name.split(":")[-1]
        if tag == "si":
            self.current_idx += 1
            self.in_si = True
            self.is_app = self.current_idx in self.app_indices
            self.is_cred = self.current_idx in self.cred_indices
            self.text_buffer = []
            self.has_cred_text = False
        elif tag == "t" and self.in_si:
            self.in_t = True

    def characters(self, content: str) -> None:
        if not (self.in_si and self.in_t):
            return
        if self.is_app:
            self.text_buffer.append(content)
        if self.is_cred:
            if content.strip():
                self.has_cred_text = True

    def endElement(self, name: str) -> None:
        tag = name.split(":")[-1]
        if tag == "si":
            if self.is_app:
                self.app_strings[self.current_idx] = "".join(self.text_buffer)
            if self.is_cred:
                self.cred_non_empty[self.current_idx] = self.has_cred_text
            self.in_si = False
            self.is_app = False
            self.is_cred = False
            self.text_buffer = []
            self.has_cred_text = False
        elif tag == "t":
            self.in_t = False


def parse_shared_strings_stream(
    xml_bytes: bytes,
    app_indices: set[int],
    cred_indices: set[int],
    path: str = "sharedStrings.xml",
) -> tuple[dict[int, str], dict[int, bool], int]:
    check_no_dtd_or_entity(xml_bytes, path)
    handler = _SharedStringsHandler(app_indices, cred_indices)
    parser = xml.sax.make_parser()
    parser.setFeature(xml.sax.handler.feature_external_ges, False)
    parser.setFeature(xml.sax.handler.feature_external_pes, False)
    parser.setContentHandler(handler)
    try:
        parser.parse(io.BytesIO(xml_bytes))
    except (xml.sax.SAXException, ValueError) as exc:
        raise XlsxReadError(f"Shared strings part contains invalid XML: {exc}") from exc
    total_count = handler.current_idx + 1
    return handler.app_strings, handler.cred_non_empty, total_count
