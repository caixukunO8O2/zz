"""HTTP schemas for the scan-session lifecycle."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.scans import ScanStatus

MockScenario = Literal["packaged_success", "needs_identity", "fresh_produce"]


class ScanSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mock_scenario: MockScenario | None = None


class ScanImageRead(BaseModel):
    id: int
    purpose: str
    analysis_status: str


class ScanSessionRead(BaseModel):
    id: str
    status: ScanStatus
    detected_fields: dict[str, object]
    conflicts: list[dict[str, object]]
    missing_fields: list[str]
    next_guidance: str
    expires_at: datetime
    images: list[ScanImageRead]

