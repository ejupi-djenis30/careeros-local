import logging
import re
from collections.abc import Mapping
from numbers import Number
from typing import Any

REDACTED = "[redacted]"

_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{6,}\d)(?!\w)")
_SENSITIVE_LINE = re.compile(
    r"(?im)(\b(?:api[_-]?key|authorization|password|refresh[_-]?token|access[_-]?token|"
    r"secret|email|phone|prompt|model[_ -]?output|document(?:[_ -]?body)?|cv(?:[_ -]?content)?|"
    r"profile(?:[_ -]?(?:content|summary))?|content|summary|description|payload|"
    r"request[_ -]?body)\b\s*[:=]\s*).*$"
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
    text = _PHONE.sub("[redacted-phone]", text)
    text = _SENSITIVE_LINE.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = _CONTEXT_QUOTE.sub(lambda match: f"{match.group(1)}'{REDACTED}'", text)
    text = _SQL_PARAMETERS.sub(lambda match: f"{match.group(1)}{REDACTED}{match.group(2)}", text)
    text = _FAILURE_DETAILS.sub(lambda match: f"{match.group(1)}[redacted-detail]", text)
    return text


def _redact_argument(value: Any) -> Any:
    """Keep diagnostic metrics while excluding arbitrary application content.

    Logging arguments are untrusted by default: strings can contain profile data,
    provider payloads or exception messages even when the format string looks safe.
    """
    if value is None or isinstance(value, (bool, Number)):
        return value
    if isinstance(value, BaseException):
        return f"exception_type={type(value).__name__}"
    if isinstance(value, Mapping):
        return {key: REDACTED for key in value}
    if isinstance(value, tuple):
        return tuple(_redact_argument(item) for item in value)
    if isinstance(value, (list, set, frozenset)):
        return REDACTED
    return REDACTED


def _redact_arguments(args: Any) -> Any:
    if isinstance(args, Mapping):
        return {key: _redact_argument(value) for key, value in args.items()}
    if isinstance(args, tuple):
        return tuple(_redact_argument(value) for value in args)
    return _redact_argument(args)


class PrivacyRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.args = _redact_arguments(record.args)
        record.msg = redact_text(record.getMessage())
        record.args = ()
        return True


class PrivacyFormatter(logging.Formatter):
    def formatException(self, exc_info) -> str:  # noqa: N802 - stdlib API
        exception_type = getattr(exc_info[0], "__name__", "Exception")
        return f"exception_type={exception_type}"

    def formatStack(self, stack_info: str) -> str:  # noqa: N802 - stdlib API
        return "stack=[redacted]"


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
