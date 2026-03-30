"""Custom HTTP exceptions for FORGE Data API."""

from fastapi import status


class ForgeException(Exception):
    """Base class for all FORGE Data domain exceptions.

    Instances are caught by the exception handler in ``main.py`` and converted
    into :class:`fastapi.responses.JSONResponse` with the given ``status_code``.
    """

    def __init__(
        self,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: str = "An unexpected error occurred",
        code: str = "FORGE_ERROR",
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


# ── 400 Bad Request ────────────────────────────────────────────────────────────


class ValidationError(ForgeException):
    def __init__(self, detail: str = "Validation error") -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail, "VALIDATION_ERROR")


# ── 401 Unauthorized ──────────────────────────────────────────────────────────


class UnauthorizedException(ForgeException):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, "UNAUTHORIZED")


class InvalidCredentialsException(ForgeException):
    def __init__(self) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            "INVALID_CREDENTIALS",
        )


class TokenExpiredException(ForgeException):
    def __init__(self) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, "Token has expired", "TOKEN_EXPIRED")


# ── 403 Forbidden ─────────────────────────────────────────────────────────────


class ForbiddenException(ForgeException):
    def __init__(self, detail: str = "You do not have permission to perform this action") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail, "FORBIDDEN")


class InsufficientRoleException(ForgeException):
    def __init__(self, required_role: str) -> None:
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            f"This action requires the '{required_role}' role or higher",
            "INSUFFICIENT_ROLE",
        )


# ── 404 Not Found ─────────────────────────────────────────────────────────────


class NotFoundException(ForgeException):
    def __init__(self, resource: str = "Resource", resource_id: str | None = None) -> None:
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} '{resource_id}' not found"
        super().__init__(status.HTTP_404_NOT_FOUND, detail, "NOT_FOUND")


# ── 409 Conflict ──────────────────────────────────────────────────────────────


class ConflictException(ForgeException):
    def __init__(self, detail: str = "Resource already exists") -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, "CONFLICT")


class EmailAlreadyExistsException(ForgeException):
    def __init__(self) -> None:
        super().__init__(
            status.HTTP_409_CONFLICT,
            "An account with this email address already exists",
            "EMAIL_EXISTS",
        )


# ── 503 Service Unavailable ───────────────────────────────────────────────────


class ServiceUnavailableException(ForgeException):
    def __init__(self, service: str = "Upstream service") -> None:
        super().__init__(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"{service} is currently unavailable",
            "SERVICE_UNAVAILABLE",
        )


class JupyterUnavailableException(ServiceUnavailableException):
    def __init__(self) -> None:
        super().__init__("Jupyter Kernel Gateway")


# ── Helpers ────────────────────────────────────────────────────────────────────


def raise_if_not_found(obj: object | None, resource: str, resource_id: str | None = None) -> None:
    """Raise :class:`NotFoundException` when *obj* is None."""
    if obj is None:
        raise NotFoundException(resource, resource_id)
