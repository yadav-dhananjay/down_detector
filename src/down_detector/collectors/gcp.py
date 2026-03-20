import logging
from datetime import datetime, timezone

from ..models import Provider, Severity, StatusEvent, GCP_SEVERITY_MAP
from ..config import ProviderConfig
from ..filters.region import filter_gcp_usa_regions
from .base import BaseCollector

logger = logging.getLogger(__name__)

GCP_INCIDENTS_URL = "https://status.cloud.google.com/incidents.json"


class GCPCollector(BaseCollector):
    provider = Provider.GCP

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(GCP_INCIDENTS_URL)
        resp.raise_for_status()
        incidents: list[dict] = resp.json()
        return [self._parse_incident(inc) for inc in incidents if self._is_relevant(inc)]

    def _is_relevant(self, incident: dict) -> bool:
        """Include ongoing incidents and those resolved within the last 24h."""
        if not incident.get("end"):
            return True
        # Also include recently resolved ones for visibility
        try:
            end_str = incident["end"]
            # GCP uses ISO 8601 format
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - end).total_seconds() / 3600
            return age_hours < 24
        except Exception:
            return True

    def _parse_incident(self, inc: dict) -> StatusEvent:
        severity_str = (inc.get("severity") or "low").lower()
        severity = GCP_SEVERITY_MAP.get(severity_str, Severity.DEGRADED)

        # Collect affected regions from both current and previously affected
        all_locations: list[str] = list(inc.get("affected_locations") or [])
        all_locations += [
            loc for loc in (inc.get("previously_affected_locations") or [])
            if loc not in all_locations
        ]

        # Collect affected product names
        products = [p.get("title", p.get("id", "")) for p in (inc.get("affected_products") or [])]

        # Parse timestamps
        started_at = self._parse_ts(inc.get("begin"))
        resolved_at = self._parse_ts(inc.get("end"))
        last_updated = started_at

        updates = inc.get("updates") or []
        if updates:
            update_times = [self._parse_ts(u.get("modified")) for u in updates if u.get("modified")]
            if update_times:
                last_updated = max(update_times)

        description = inc.get("external_desc", "")
        if updates:
            latest = updates[0]
            description = latest.get("text", description)

        return StatusEvent(
            provider=Provider.GCP,
            incident_id=str(inc.get("id", "")),
            title=inc.get("external_desc", "GCP Incident")[:120],
            severity=severity,
            status="ongoing" if not inc.get("end") else "resolved",
            affected_services=products,
            affected_regions=all_locations,
            started_at=started_at,
            resolved_at=resolved_at,
            last_updated=last_updated,
            url=f"https://status.cloud.google.com/incidents/{inc.get('id', '')}",
            description=description,
            is_resolved=bool(inc.get("end")),
        )

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        filtered = []
        for event in events:
            usa_regions = filter_gcp_usa_regions(event.affected_regions)
            if usa_regions:
                filtered.append(event.model_copy(update={"affected_regions": usa_regions}))
        return filtered

    @staticmethod
    def _parse_ts(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()
