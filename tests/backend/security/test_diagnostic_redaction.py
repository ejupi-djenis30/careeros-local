import io
import logging

from backend.core.logging import PrivacyFormatter, PrivacyRedactionFilter, redact_text


def _capture_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(PrivacyRedactionFilter())
    handler.setFormatter(PrivacyFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, stream


def test_cross_domain_diagnostics_exclude_private_content():
    sentinels = {
        "email": "private.person@example.test",
        "phone": "+41 79 123 45 67",
        "profile": "PROFILE-SUMMARY-ULTRA-PRIVATE",
        "document": "DOCUMENT-BODY-ULTRA-PRIVATE",
        "prompt": "PROMPT-ULTRA-PRIVATE",
        "output": "MODEL-OUTPUT-ULTRA-PRIVATE",
        "payload": "PROVIDER-PAYLOAD-ULTRA-PRIVATE",
        "secret": "SECRET-TOKEN-ULTRA-PRIVATE",
        "exception": "EXCEPTION-DOCUMENT-ULTRA-PRIVATE",
    }
    logger, stream = _capture_logger("tests.diagnostic.cross_domain")

    logger.info(f"contact {sentinels['email']} {sentinels['phone']}")
    logger.info(f"profile summary: {sentinels['profile']}")
    logger.info("document body: %s", sentinels["document"])
    logger.debug("prompt=%s", sentinels["prompt"])
    logger.debug("model output=%s", sentinels["output"])
    logger.debug("provider payload: %s", {"resume": sentinels["payload"]})
    logger.warning("secret=%s", sentinels["secret"])
    try:
        raise RuntimeError(sentinels["exception"])
    except RuntimeError:
        logger.exception("resume_export failed")

    diagnostic = stream.getvalue()
    assert all(value not in diagnostic for value in sentinels.values())
    assert "[redacted]" in diagnostic
    assert "[redacted-email]" in diagnostic
    assert "[redacted-phone]" in diagnostic
    assert "resume_export failed" in diagnostic
    assert "exception_type=RuntimeError" in diagnostic


def test_structured_arguments_preserve_metrics_but_not_strings():
    logger, stream = _capture_logger("tests.diagnostic.structured")

    logger.info(
        "resume_export operation=%s rows=%d success=%s metadata=%s",
        "publish_pdf",
        12,
        True,
        {"profile": "PRIVATE-METADATA-SENTINEL"},
    )

    diagnostic = stream.getvalue()
    assert "PRIVATE-METADATA-SENTINEL" not in diagnostic
    assert "rows=12" in diagnostic
    assert "success=True" in diagnostic
    assert "operation=[redacted]" in diagnostic


def test_redact_text_covers_multitoken_content_and_contact_details():
    value = redact_text(
        "profile summary: private multi token profile\n"
        "document body=private multi token document\n"
        "contact private.person@example.test or +41 (79) 123-45-67"
    )

    assert "private multi token" not in value
    assert "private.person@example.test" not in value
    assert "+41 (79) 123-45-67" not in value
