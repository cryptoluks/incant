"""
Custom exceptions for Incant.
"""


class IncantError(Exception):
    """Base exception for all Incant errors."""

    pass


class ConfigurationError(IncantError):
    """Raised when there's an issue with configuration loading or parsing."""

    pass


class InstanceError(IncantError):
    """Raised when there's an issue with instance operations."""

    pass


class ProjectError(IncantError):
    """Raised when there's an issue with project operations."""

    pass


class ProvisioningError(IncantError):
    """Raised when there's an issue with provisioning operations."""

    pass


class IncusCommandError(IncantError):
    """Raised when an Incus command fails."""

    def __init__(self, message: str, command: str = None, stderr: str = None):
        super().__init__(message)
        self.command = command
        self.stderr = stderr
