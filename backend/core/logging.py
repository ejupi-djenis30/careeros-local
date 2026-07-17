import logging
import re

REDACTED = "[redacted]"

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?is)(\b(?:api[_-]?key|authorization|password|refresh[_-]?token|access[_-]?token|"
    r"secret|email|phone|prompt|content|summary|description|payload|request[_-]?body)\b"
    r"\s*[:=]\s*)(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^,}\]\s]+)"
)
_CONTEXT_QUOTE = re.compile(
    r"(?i)(\b(?:query|location|occupation|role|company|title)\b[^'\"\n]{0,30})"
    r"(['\"])(.*?)\2"
)
_SQL_PARAMETERS = re.compile(r"(?is)(\[parameters:\s*).*?(\](?:\s*\(|$))")
_FAILURE_DETAILS = re.compile(
    r"(?is)(\b(?:failed|failure|error|exception)\b[^:=\n]{0,80}[:=]\s*)(.+)$"
)


def redact_text(value: object) -> str:
    text = str(value)
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _EMAIL.sub("[redacted-email]", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = _CONTEXT_QUOTE.sub(lambda match: f"{match.group(1)}'{REDACTED}'", text)
    text = _SQL_PARAMETERS.sub(lambda match: f"{match.group(1)}{REDACTED}{match.group(2)}", text)
    text = _FAILURE_DETAILS.sub(lambda match: f"{match.group(1)}[redacted-detail]", text)
    return text


class PrivacyRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


class PrivacyFormatter(logging.Formatter):
    def formatException(self, exc_info) -> str:  # noqa: N802 - stdlib API
        return redact_text(super().formatException(exc_info))


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    formatter = PrivacyFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    for handler in root.handlers:
        handler.setFormatter(formatter)
        if not any(isinstance(item, PrivacyRedactionFilter) for item in handler.filters):
            handler.addFilter(PrivacyRedactionFilter())

