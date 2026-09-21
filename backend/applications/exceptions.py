"""Stable domain exceptions shared by application services and transports."""


class ApplicationNotFoundError(LookupError):
    pass


class ApplicationConflictError(RuntimeError):
    pass


class ApplicationValidationError(ValueError):
    pass
