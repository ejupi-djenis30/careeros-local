"""Safe offline email draft generation and strict header/attachment validation."""

from __future__ import annotations

import email.utils
import re
from email.message import EmailMessage

from backend.applications.placeholders import contains_unresolved_placeholder
from backend.applications.schemas import EmailDraft, normalize_application_email


def validate_email_draft(
    draft: EmailDraft | None,
    available_packet_files: set[str],
    *,
    require_complete: bool = False,
) -> None:
    """Validate email draft for header injection, placeholders, and attachment integrity.

    Incomplete drafts are permitted during autosave, but publication enforces complete
    valid fields, strict attachment verification, and absence of placeholders.
    """
    if draft is None:
        return

    # 1. Header controls (no CRLF injection in subject or recipient)
    for header_name, value in [("subject", draft.subject), ("recipient", draft.recipient or "")]:
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError(f"Email {header_name} contains illegal header control characters")

    # 2. Placeholders validation
    for field_name, value in [("subject", draft.subject), ("body", draft.body)]:
        if value and contains_unresolved_placeholder(value):
            raise ValueError(
                f"Email {field_name} contains unresolved placeholders or instructions"
            )

    # 3. Mode validation
    if draft.mode not in {"short", "motivational"}:
        raise ValueError(f"Unsupported email draft mode: '{draft.mode}'")

    # 4. Attachment names validation
    for name in draft.attachment_names:
        clean_name = name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", clean_name) or ".." in clean_name:
            raise ValueError("Attachment name is not a canonical packet filename")
        if not clean_name:
            raise ValueError("Attachment name cannot be blank")
        if "/" in clean_name or "\\" in clean_name or ".." in clean_name:
            raise ValueError(
                f"Attachment name '{name}' contains forbidden path traversal characters"
            )
        if clean_name not in available_packet_files:
            raise ValueError(
                f"Email attachment '{clean_name}' does not match any selected packet file: "
                f"available files are {sorted(available_packet_files)}"
            )

    # 5. Publication completion requirements
    if draft.recipient:
        if normalize_application_email(draft.recipient) != draft.recipient:
            raise ValueError("Email recipient must be one canonical mailbox")
    if require_complete:
        if not draft.subject.strip():
            raise ValueError("Email draft requires a non-empty subject for publication")
        if not draft.body.strip():
            raise ValueError("Email draft requires a non-empty body for publication")


def generate_email_artifacts(
    draft: EmailDraft | None,
) -> dict[str, tuple[bytes, str]]:
    """Generate offline email draft (.eml) and checklist text artifact.

    Never opens network connections, SMTP sockets, or sends emails.
    """
    if draft is None or (not draft.subject.strip() and not draft.body.strip()):
        return {}

    validate_email_draft(draft, set(draft.attachment_names), require_complete=True)
    # 1. RFC 822 .eml file
    msg = EmailMessage()
    if draft.recipient and draft.recipient.strip():
        msg["To"] = draft.recipient.strip()
    msg["Subject"] = draft.subject.strip()
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg["MIME-Version"] = "1.0"
    msg["X-CareerOS-Email-Mode"] = draft.mode
    if draft.attachment_names:
        msg["X-CareerOS-Attachments"] = ", ".join(draft.attachment_names)
    msg.set_content(draft.body, charset="utf-8")
    eml_bytes = msg.as_bytes()

    # 2. Checklist text artifact
    checklist_lines = [
        "CAREEROS OFFLINE EMAIL DRAFT & CHECKLIST",
        "=" * 40,
        f"Mode:      {draft.mode}",
        f"Recipient: {draft.recipient or '(Not specified)'}",
        f"Subject:   {draft.subject}",
        f"Date:      {msg['Date']}",
        "",
        "MANUAL SENDING CHECKLIST:",
        "[ ] 1. Open your personal/work email client (CareerOS never sends emails)",
        f"[ ] 2. Set recipient: {draft.recipient or '[Enter recipient email]'}",
        f"[ ] 3. Set subject: {draft.subject}",
    ]
    if draft.attachment_names:
        checklist_lines.append("[ ] 4. Attach selected packet files:")
        for att in draft.attachment_names:
            checklist_lines.append(f"       - {att}")
        checklist_lines.append("[ ] 5. Review attached files match job requirements")
        checklist_lines.append("[ ] 6. Review message body below and send")
    else:
        checklist_lines.append("[ ] 4. Review message body below and send")

    checklist_lines.extend(
        [
            "",
            "MESSAGE BODY:",
            "-" * 40,
            draft.body,
            "-" * 40,
            "Note: This file is a local preparation artifact for your own records.",
            "",
        ]
    )
    checklist_bytes = "\n".join(checklist_lines).encode("utf-8")

    return {
        "email_draft.eml": (eml_bytes, "message/rfc822"),
        "email_checklist.txt": (checklist_bytes, "text/plain; charset=utf-8"),
    }
