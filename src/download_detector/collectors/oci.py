import logging
from datetime import datetime

import httpx

from ..models import Provider, Severity, StatusEvent, STATUSPAGE_SEVERITY_MAP
from ..config import ProviderConfig
from ..filters.region import OCI_USA_REGIONS, filter_oci_usa_regions
from .base import BaseCollector, DEFAULT_HEADERS

logger = logging.getLogger(__name__)

OCI_SUMMARY_URL = "https://ocistatus.oracle.com/api/v2/summary.json"
OCI_UNRESOLVED_URL = "https://ocistatus.oracle.com/api/v2/incidents/unresolved.json"


class OCICollector(BaseCollector):
    provider = Provider.OCI

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        # OCI connectivity can be flaky; use retries at transport level
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
            transport=httpx.HTTPTransport(retries=3),
        )

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(OCI_SUMMARY_URL)
        resp.raise_for_status()
        data = resp.json()

        # Build component map for region detection
        all_components: list[dict] = data.get("components", [])
        component_map = {c["id"]: c for c in all_components}

        # Find USA region group component IDs
        usa_component_ids = self._find_usa_component_ids(all_components)

        incidents: list[dict] = data.get("incidents", [])
        events = []
        for inc in incidents:
            event = self._parse_incident(inc, component_map, usa_component_ids)
            events.append(event)

        # If no active incidents from summary, also check component statuses
        # for degraded USA components
        degraded_components = self._parse_degraded_components(all_components, usa_component_ids)
        events.extend(degraded_components)

        return events

    def _find_usa_component_ids(self, components: list[dict]) -> set[str]:
        """Find component IDs that correspond to USA OCI regions."""
        usa_ids: set[str] = set()
        for comp in components:
            name = comp.get("name", "")
            for usa_region in OCI_USA_REGIONS:
                if usa_region.lower() in name.lower():
                    usa_ids.add(comp["id"])
                    # Also add child components of this group
                    break
        return usa_ids

    def _parse_incident(self, inc: dict, component_map: dict, usa_ids: set[str]) -> StatusEvent:
        inc_components = inc.get("components", []) or []
        affected_services = [c.get("name", "") for c in inc_components if c.get("name")]
        affected_regions = [
            c.get("name", "") for c in inc_components
            if c.get("id") in usa_ids
        ]

        impact = inc.get("impact", "minor")
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
        description = updates[0].get("body", "") if updates else ""

        return StatusEvent(
            provider=Provider.OCI,
            incident_id=inc.get("id", ""),
            title=inc.get("name", "OCI Incident"),
            severity=severity,
            status=status,
            affected_services=affected_services,
            affected_regions=affected_regions,
            started_at=started_at,
            resolved_at=resolved_at,
            last_updated=last_updated,
            url=inc.get("shortlink") or "https://ocistatus.oracle.com",
            description=description,
            is_resolved=is_resolved,
        )

    def _parse_degraded_components(
        self, components: list[dict], usa_ids: set[str]
    ) -> list[StatusEvent]:
        """Create synthetic events for degraded USA components with no incident."""
        events = []
        for comp in components:
            if comp.get("id") not in usa_ids:
                continue
            status = comp.get("status", "operational")
            if status == "operational":
                continue
            severity = STATUSPAGE_SEVERITY_MAP.get(status, Severity.DEGRADED)
            events.append(StatusEvent(
                provider=Provider.OCI,
                incident_id=f"component-{comp['id']}",
                title=f"{comp.get('name', 'OCI Component')} — {status.replace('_', ' ').title()}",
                severity=severity,
                status=status,
                affected_services=[comp.get("name", "")],
                affected_regions=[comp.get("name", "")],
                started_at=self._parse_ts(comp.get("updated_at")),
                last_updated=self._parse_ts(comp.get("updated_at")),
                url="https://ocistatus.oracle.com",
                is_resolved=False,
            ))
        return events

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        filtered = []
        for event in events:
            # Synthetic component events already scoped to USA
            if event.incident_id.startswith("component-"):
                filtered.append(event)
                continue
            usa_regions = filter_oci_usa_regions(event.affected_regions)
            # Include if USA regions found, or if no region data (could be global)
            if usa_regions or not event.affected_regions:
                filtered.append(event.model_copy(update={"affected_regions": usa_regions or event.affected_regions}))
        return filtered

    @staticmethod
    def _parse_ts(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.utcnow()
