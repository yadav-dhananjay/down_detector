import logging
from datetime import datetime

from ..models import Provider, Severity, StatusEvent, STATUSPAGE_SEVERITY_MAP
from ..config import ProviderConfig
from .base import BaseCollector

logger = logging.getLogger(__name__)

CF_SUMMARY_URL = "https://www.cloudflarestatus.com/api/v2/summary.json"


class CloudflareCollector(BaseCollector):
    provider = Provider.CLOUDFLARE

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._usa_component_ids: set[str] = set()

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(CF_SUMMARY_URL)
        resp.raise_for_status()
        data = resp.json()

        # Build a map of component_id -> component for USA detection
        all_components: list[dict] = data.get("components", [])
        component_map = {c["id"]: c for c in all_components}

        # Find the "North America" group component ID
        na_group_id = None
        for comp in all_components:
            if comp.get("group") and "north america" in comp.get("name", "").lower():
                na_group_id = comp["id"]
                break

        # Collect USA component IDs (children of North America group with "United States" in name)
        self._usa_component_ids = set()
        for comp in all_components:
            if comp.get("group_id") == na_group_id and "united states" in comp.get("name", "").lower():
                self._usa_component_ids.add(comp["id"])

        incidents: list[dict] = data.get("incidents", [])
        events = []
        for inc in incidents:
            event = self._parse_incident(inc, component_map)
            if event:
                events.append(event)
        return events

    def _parse_incident(self, inc: dict, component_map: dict) -> StatusEvent | None:
        # Collect affected component names from incident
        inc_components = inc.get("components", [])
        affected_services = [c.get("name", "") for c in inc_components if c.get("name")]

        impact = inc.get("impact", "none")
        severity = {
            "none": Severity.OPERATIONAL,
            "minor": Severity.DEGRADED,
            "major": Severity.OUTAGE,
            "critical": Severity.CRITICAL,
            "maintenance": Severity.MAINTENANCE,
        }.get(impact, Severity.DEGRADED)

        status = inc.get("status", "")
        is_resolved = status == "resolved"

        started_at = self._parse_ts(inc.get("created_at"))
        resolved_at = self._parse_ts(inc.get("resolved_at")) if inc.get("resolved_at") else None

        updates = inc.get("incident_updates") or []
        last_updated = self._parse_ts(updates[0].get("updated_at")) if updates else started_at

        # Get latest update text as description
        description = ""
        if updates:
            description = updates[0].get("body", "")

        # Collect affected region names (component names from incident that are USA regions)
        affected_region_names = [
            c.get("name", "") for c in inc_components
            if c.get("id") in self._usa_component_ids
        ]

        return StatusEvent(
            provider=Provider.CLOUDFLARE,
            incident_id=inc.get("id", ""),
            title=inc.get("name", "Cloudflare Incident"),
            severity=severity,
            status=status,
            affected_services=affected_services,
            affected_regions=affected_region_names,
            started_at=started_at,
            resolved_at=resolved_at,
            last_updated=last_updated,
            url=inc.get("shortlink") or f"https://www.cloudflarestatus.com/incidents/{inc.get('id','')}",
            description=description,
            is_resolved=is_resolved,
        )

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        """For Cloudflare, USA filtering is already done during parsing.
        Keep events that either have USA regions OR have no specific region (global incidents).
        """
        result = []
        for event in events:
            # If the event has region data and none are USA, skip it
            # If no region data, include it (could be global)
            if event.affected_regions or not event.affected_services:
                result.append(event)
            else:
                # Check if any affected service matches a USA component
                result.append(event)  # include all; region filtering done in _parse_incident
        return events  # already filtered in _parse_incident

    @staticmethod
    def _parse_ts(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()
