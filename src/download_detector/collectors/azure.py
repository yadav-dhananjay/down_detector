import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from ..models import Provider, Severity, StatusEvent
from ..config import ProviderConfig
from ..filters.region import extract_azure_regions_from_text, AZURE_USA_REGIONS
from .base import BaseCollector

logger = logging.getLogger(__name__)

AZURE_RSS_URL = "https://rssfeed.azure.status.microsoft/en-us/status/feed/"

# Keywords in RSS title that hint at severity
_CRITICAL_KEYWORDS = ("outage", "down", "unavailable", "critical")
_DEGRADED_KEYWORDS = ("degraded", "degradation", "latency", "connectivity", "intermittent", "partial", "slow")
_MAINTENANCE_KEYWORDS = ("maintenance", "planned", "upgrade")


def _infer_severity(title: str, description: str) -> Severity:
    combined = (title + " " + description).lower()
    if any(kw in combined for kw in _CRITICAL_KEYWORDS):
        return Severity.CRITICAL
    if any(kw in combined for kw in _MAINTENANCE_KEYWORDS):
        return Severity.MAINTENANCE
    if any(kw in combined for kw in _DEGRADED_KEYWORDS):
        return Severity.DEGRADED
    return Severity.OUTAGE  # default for any active incident


def _extract_service_from_title(title: str) -> list[str]:
    """Azure RSS titles are typically: 'Service Name - Incident Type'."""
    if " - " in title:
        return [title.split(" - ")[0].strip()]
    return [title.strip()]


def _extract_incident_id(link: str) -> str:
    """Extract tracking ID from Azure incident URL like ?trackingid=8GCS-858."""
    match = re.search(r"trackingid=([A-Z0-9\-]+)", link, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: use last URL segment
    return link.rstrip("/").split("/")[-1] or link


class AzureCollector(BaseCollector):
    provider = Provider.AZURE

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(AZURE_RSS_URL, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        events = []
        for entry in feed.entries:
            event = self._parse_entry(entry)
            if event:
                events.append(event)

        return events

    def _parse_entry(self, entry) -> StatusEvent | None:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        summary = getattr(entry, "summary", "") or ""
        published = getattr(entry, "published", None)
        updated = getattr(entry, "updated", None)

        incident_id = _extract_incident_id(link) if link else title[:50]
        services = _extract_service_from_title(title)
        severity = _infer_severity(title, summary)

        # Extract regions from description HTML/text
        regions = extract_azure_regions_from_text(summary)
        if not regions:
            # If no specific region mentioned, treat as potentially all USA regions
            regions = []

        started_at = self._parse_rfc_date(published)
        last_updated = self._parse_rfc_date(updated) or started_at

        # Strip HTML tags from description
        clean_desc = re.sub(r"<[^>]+>", " ", summary).strip()
        clean_desc = re.sub(r"\s+", " ", clean_desc)

        return StatusEvent(
            provider=Provider.AZURE,
            incident_id=incident_id,
            title=title[:120],
            severity=severity,
            status="active",
            affected_services=services,
            affected_regions=regions,
            started_at=started_at,
            last_updated=last_updated,
            url=link or "https://status.azure.com",
            description=clean_desc[:500],
            is_resolved=False,  # RSS only shows active incidents
        )

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        """For Azure RSS: include events with explicit USA regions, or events
        with no region info (could be global/all regions).
        """
        result = []
        for event in events:
            if event.affected_regions:
                # Has region data — keep only if any USA region present
                # (already extracted as USA regions by extract_azure_regions_from_text)
                result.append(event)
            else:
                # No region extracted — include with a note that region is unknown
                result.append(event.model_copy(update={"affected_regions": ["(region not specified)"]}))
        return result

    @staticmethod
    def _parse_rfc_date(value: str | None) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return parsedate_to_datetime(value).replace(tzinfo=None)
        except Exception:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                return datetime.utcnow()
