from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Provider(str, Enum):
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"
    CLOUDFLARE = "cloudflare"


class Severity(str, Enum):
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    OUTAGE = "outage"
    CRITICAL = "critical"


# Maps raw provider status strings to unified Severity
STATUSPAGE_SEVERITY_MAP: dict[str, Severity] = {
    "operational": Severity.OPERATIONAL,
    "under_maintenance": Severity.MAINTENANCE,
    "degraded_performance": Severity.DEGRADED,
    "partial_outage": Severity.OUTAGE,
    "major_outage": Severity.CRITICAL,
}

GCP_SEVERITY_MAP: dict[str, Severity] = {
    "low": Severity.DEGRADED,
    "medium": Severity.OUTAGE,
    "high": Severity.CRITICAL,
}


class StatusEvent(BaseModel):
    provider: Provider
    incident_id: str
    title: str
    severity: Severity
    status: str  # raw provider status string
    affected_services: list[str]
    affected_regions: list[str]  # USA regions only
    started_at: datetime
    resolved_at: Optional[datetime] = None
    last_updated: datetime
    url: Optional[str] = None
    description: str = ""
    is_resolved: bool = Field(default=False)

    @property
    def is_active(self) -> bool:
        return not self.is_resolved

    @property
    def duration_str(self) -> str:
        end = self.resolved_at or datetime.utcnow()
        delta = end - self.started_at.replace(tzinfo=None) if self.started_at.tzinfo else end - self.started_at
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 60:
            return f"{total_minutes}m"
        hours = total_minutes // 60
        mins = total_minutes % 60
        return f"{hours}h {mins}m"
