"""Domain errors. Services raise these; main.py turns them into HTTP responses,
so services never need to import FastAPI."""


class AppError(Exception):
    status_code = 400
    detail = "Bad request"

    def __init__(self, detail: str | None = None, headers: dict[str, str] | None = None):
        self.detail = detail or self.detail
        self.headers = headers
        super().__init__(self.detail)


class UsernameTakenError(AppError):
    status_code = 409
    detail = "Username already taken"


class InvalidCredentialsError(AppError):
    status_code = 401
    detail = "Invalid username or PIN"


class AccountDisabledError(AppError):
    status_code = 403
    detail = "Account is disabled"


class AccountLockedError(AppError):
    status_code = 429
    detail = "Too many failed attempts. Try again later."

    def __init__(self, retry_after: int):
        super().__init__(headers={"Retry-After": str(retry_after)})


class SamePinError(AppError):
    status_code = 400
    detail = "New PIN must differ from the current PIN"
    

 
class LLMUnavailableError(AppError):
    status_code = 502
    detail = "The assistant is unavailable right now. Try again shortly."


class ResourceNotFoundError(AppError):
    status_code = 404
    detail = "Resource not found"


class ResourceForbiddenError(AppError):
    status_code = 403
    detail = "You do not have access to this resource"


class ResourceConflictError(AppError):
    status_code = 409
    detail = "Resource conflicts with existing data"


class InvalidRequestError(AppError):
    status_code = 422
    detail = "Request is invalid"


class MusicProviderError(AppError):
    status_code = 502
    detail = "Music provider request failed"
