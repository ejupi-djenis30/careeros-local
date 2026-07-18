import logging

from backend.core.logging import PrivacyFormatter, PrivacyRedactionFilter, redact_text


def test_redactor_removes_contact_prompt_and_credentials():
    raw = (
        "email=ada@example.test phone='+41 79 123 45 67' "
        "prompt='My complete private career history' "
        "Authorization: Bearer secret-token"
    )
    redacted = redact_text(raw)
    assert "ada@example.test" not in redacted
    assert "private career history" not in redacted
    assert "secret-token" not in redacted
    assert "[redacted]" in redacted


def test_logging_filter_redacts_formatted_arguments():
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Search failed: %s",
        args=("response body contains candidate@example.test and a private summary",),
        exc_info=None,
    )
    assert PrivacyRedactionFilter().filter(record)
    rendered = PrivacyFormatter("%(message)s").format(record)
    assert "candidate@example.test" not in rendered
    assert "private summary" not in rendered
    assert "redacted-detail" in rendered
