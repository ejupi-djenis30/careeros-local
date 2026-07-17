class ResumeNotFoundError(LookupError):
    pass


class ResumeConflictError(RuntimeError):
    pass


class ResumeValidationError(ValueError):
    pass
