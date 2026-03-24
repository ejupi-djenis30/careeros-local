class CoreException(Exception):
    """Base exception for the application"""
    pass

class ConfigurationError(CoreException):
    """Raised when configuration is invalid"""
    pass

class ResourceNotFound(CoreException):
    """Raised when a requested resource is not found"""
    pass
