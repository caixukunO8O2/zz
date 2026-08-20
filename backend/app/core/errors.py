"""Stable application error contract for API clients."""

from dataclasses import dataclass


@dataclass(slots=True)
class APIError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False

    def envelope(self) -> dict[str, dict[str, object]]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }
