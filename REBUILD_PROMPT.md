# Cloud Status Monitor — Full Rebuild Prompt
# ============================================
# Use this prompt to recreate the entire Phase 1 implementation from scratch.
# Working directory: d:/outskill/download_detector/

---

## GOAL

Build a **Cloud Service Status Monitor** that polls the official status APIs of
Azure, GCP, OCI, and Cloudflare every 60 seconds, filters to USA regions only,
and displays results in two modes:
- Web UI (default): Azure-style status page with provider tabs, service × region
  matrix, incident banners, and a slide-in detail panel
- Terminal UI (optional): Rich live dashboard table

Preview mode available at /demo with realistic simulated incidents.

---

## STACK

- Python 3.11
- httpx — HTTP client
- feedparser — Azure RSS parsing
- pydantic v2 + pydantic-settings — data models + config
- apscheduler — background polling scheduler
- flask — web server
- rich — terminal dashboard
- pyyaml — config file parsing
- pytest — tests

---

## PROJECT STRUCTURE

```
download_detector/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── REBUILD_PROMPT.md         (this file)
├── PHASE2_PROMPT.md          (workload impact feature — future)
├── config/
│   └── services.yaml
├── src/
│   └── download_detector/
│       ├── __init__.py       (empty)
│       ├── models.py
│       ├── store.py
│       ├── config.py
│       ├── scheduler.py
│       ├── main.py
│       ├── collectors/
│       │   ├── __init__.py   (empty)
│       │   ├── base.py
│       │   ├── azure.py
│       │   ├── gcp.py
│       │   ├── oci.py
│       │   └── cloudflare.py
│       ├── filters/
│       │   ├── __init__.py   (empty)
│       │   └── region.py
│       └── ui/
│           ├── __init__.py   (empty)
│           ├── terminal.py
│           └── web.py
└── tests/
    ├── __init__.py           (empty)
    ├── conftest.py
    ├── test_collectors/
    │   └── __init__.py       (empty)
    ├── test_filters.py
    └── test_models.py
```

---

## FILE: pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "download-detector"
version = "0.1.0"
description = "Cloud service status monitor for Azure, OCI, GCP, and Cloudflare (USA regions)"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "rich>=13.7",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "feedparser>=6.0",
    "apscheduler>=3.10",
    "pyyaml>=6.0",
    "flask>=3.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-httpx>=0.30", "pytest-cov>=5.0"]

[project.scripts]
download-detector = "download_detector.main:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## FILE: config/services.yaml

```yaml
# Cloud Service Status Monitor Configuration
# Phase 1: All USA-region incidents shown (service_filter empty = show all)
# Phase 2: Populate service_filter with your org's services

polling_interval_seconds: 60

azure:
  enabled: true
  service_filter: []
  # service_filter:
  #   - "Azure Storage"
  #   - "Azure Virtual Machines"
  #   - "Azure Kubernetes Service"
  #   - "Azure Active Directory"
  #   - "Azure SQL Database"

gcp:
  enabled: true
  service_filter: []
  # service_filter:
  #   - "Cloud Run"
  #   - "Cloud SQL"
  #   - "Google Kubernetes Engine"
  #   - "Cloud Storage"
  #   - "Vertex AI"

oci:
  enabled: true
  service_filter: []
  # service_filter:
  #   - "Object Storage"
  #   - "Compute"
  #   - "Kubernetes Engine (OKE)"
  #   - "Autonomous Database"

cloudflare:
  enabled: true
  service_filter: []
  # service_filter:
  #   - "CDN/Cache"
  #   - "DNS"
  #   - "Workers"
  #   - "Access"
```

---

## FILE: src/download_detector/models.py

```python
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
    status: str
    affected_services: list[str]
    affected_regions: list[str]
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
```

---

## FILE: src/download_detector/store.py

```python
from threading import Lock
from datetime import datetime, timedelta
from .models import StatusEvent, Provider


class StatusStore:
    """Thread-safe in-memory store keyed by (provider, incident_id)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._events: dict[tuple[Provider, str], StatusEvent] = {}
        self._poll_times: dict[Provider, datetime] = {}
        self._poll_errors: dict[Provider, str | None] = {}

    def upsert(self, provider: Provider, events: list[StatusEvent]) -> None:
        with self._lock:
            keys_to_remove = [k for k in self._events if k[0] == provider]
            for k in keys_to_remove:
                del self._events[k]
            for event in events:
                self._events[(provider, event.incident_id)] = event

    def set_poll_time(self, provider: Provider, t: datetime, error: str | None = None) -> None:
        with self._lock:
            self._poll_times[provider] = t
            self._poll_errors[provider] = error

    def get_active(self) -> list[StatusEvent]:
        with self._lock:
            return [e for e in self._events.values() if e.is_active]

    def get_all(self) -> list[StatusEvent]:
        with self._lock:
            return list(self._events.values())

    def get_by_provider(self, provider: Provider) -> list[StatusEvent]:
        with self._lock:
            return [e for k, e in self._events.items() if k[0] == provider]

    def last_poll_time(self, provider: Provider) -> datetime | None:
        return self._poll_times.get(provider)

    def last_poll_error(self, provider: Provider) -> str | None:
        return self._poll_errors.get(provider)

    def clear_resolved_older_than(self, hours: int = 24) -> None:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        with self._lock:
            to_remove = [
                k for k, e in self._events.items()
                if e.is_resolved and e.resolved_at and e.resolved_at.replace(tzinfo=None) < cutoff
            ]
            for k in to_remove:
                del self._events[k]

    def provider_summary(self) -> dict[Provider, dict]:
        summary = {}
        with self._lock:
            for provider in Provider:
                events = [e for k, e in self._events.items() if k[0] == provider]
                active = [e for e in events if e.is_active]
                poll_time = self._poll_times.get(provider)
                error = self._poll_errors.get(provider)
                summary[provider] = {
                    "active_count": len(active),
                    "last_poll": poll_time,
                    "error": error,
                    "events": active,
                }
        return summary
```

---

## FILE: src/download_detector/config.py

```python
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    enabled: bool = True
    service_filter: list[str] = []


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DD_", env_nested_delimiter="__")

    polling_interval_seconds: int = 60
    ui: str = "web"  # "web" or "terminal"
    web_port: int = 5000
    azure: ProviderConfig = ProviderConfig()
    gcp: ProviderConfig = ProviderConfig()
    oci: ProviderConfig = ProviderConfig()
    cloudflare: ProviderConfig = ProviderConfig()

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "AppConfig":
        if path is None:
            candidates = [
                Path("config/services.yaml"),
                Path(__file__).parent.parent.parent / "config" / "services.yaml",
            ]
            path = next((p for p in candidates if p.exists()), None)

        data: dict[str, Any] = {}
        if path and path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        return cls(**data)
```

---

## FILE: src/download_detector/filters/region.py

```python
"""USA region matching logic for each cloud provider."""

AZURE_USA_REGIONS: frozenset[str] = frozenset([
    "East US", "East US 2", "West US", "West US 2", "West US 3",
    "North Central US", "South Central US", "West Central US", "Central US",
])

OCI_USA_REGIONS: frozenset[str] = frozenset([
    "US East (Ashburn)", "US West (Phoenix)", "US Midwest (Chicago)",
    "US Gov East", "US Gov West", "US DoD East", "US DoD West",
])

def is_gcp_usa_region(location: str) -> bool:
    return location.lower().startswith("us-")

def filter_azure_usa_regions(regions: list[str]) -> list[str]:
    result = []
    for region in regions:
        for usa_region in AZURE_USA_REGIONS:
            if usa_region.lower() in region.lower():
                result.append(region)
                break
    return result

def filter_gcp_usa_regions(locations: list[str]) -> list[str]:
    return [loc for loc in locations if is_gcp_usa_region(loc)]

def filter_oci_usa_regions(regions: list[str]) -> list[str]:
    result = []
    for region in regions:
        for usa_region in OCI_USA_REGIONS:
            if usa_region.lower() in region.lower():
                result.append(region)
                break
    return result

def extract_azure_regions_from_text(text: str) -> list[str]:
    found = []
    text_lower = text.lower()
    for region in AZURE_USA_REGIONS:
        if region.lower() in text_lower:
            found.append(region)
    return found
```

---

## FILE: src/download_detector/collectors/base.py

```python
import logging
from abc import ABC, abstractmethod
from datetime import datetime
import httpx
from ..models import Provider, StatusEvent
from ..config import ProviderConfig

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "download-detector/0.1 (cloud-status-monitor)",
    "Accept": "application/json",
}

class BaseCollector(ABC):
    provider: Provider

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
        )

    def collect(self) -> list[StatusEvent]:
        try:
            events = self._fetch_and_parse()
            events = self._filter_usa_regions(events)
            if self.config.service_filter:
                events = self._filter_by_org_services(events)
            return events
        except httpx.TimeoutException:
            logger.warning("%s: request timed out", self.provider.value)
        except httpx.ConnectError as e:
            logger.warning("%s: connection error: %s", self.provider.value, e)
        except httpx.HTTPStatusError as e:
            logger.warning("%s: HTTP %s from %s", self.provider.value, e.response.status_code, e.request.url)
        except Exception as e:
            logger.exception("%s: unexpected error: %s", self.provider.value, e)
        return []

    @abstractmethod
    def _fetch_and_parse(self) -> list[StatusEvent]: ...

    @abstractmethod
    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]: ...

    def _filter_by_org_services(self, events: list[StatusEvent]) -> list[StatusEvent]:
        service_filter = [s.lower() for s in self.config.service_filter]
        return [
            e for e in events
            if any(svc in s.lower() for svc in service_filter for s in e.affected_services)
        ]

    def close(self) -> None:
        self._client.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.utcnow()
```

---

## FILE: src/download_detector/collectors/azure.py

```python
import logging, re
from datetime import datetime
from email.utils import parsedate_to_datetime
import feedparser
from ..models import Provider, Severity, StatusEvent
from ..config import ProviderConfig
from ..filters.region import extract_azure_regions_from_text
from .base import BaseCollector

logger = logging.getLogger(__name__)
AZURE_RSS_URL = "https://rssfeed.azure.status.microsoft/en-us/status/feed/"
_CRITICAL_KEYWORDS = ("outage", "down", "unavailable", "critical")
_DEGRADED_KEYWORDS = ("degraded", "degradation", "latency", "connectivity", "intermittent", "partial", "slow")
_MAINTENANCE_KEYWORDS = ("maintenance", "planned", "upgrade")

def _infer_severity(title: str, description: str) -> Severity:
    combined = (title + " " + description).lower()
    if any(kw in combined for kw in _CRITICAL_KEYWORDS): return Severity.CRITICAL
    if any(kw in combined for kw in _MAINTENANCE_KEYWORDS): return Severity.MAINTENANCE
    if any(kw in combined for kw in _DEGRADED_KEYWORDS): return Severity.DEGRADED
    return Severity.OUTAGE

def _extract_service_from_title(title: str) -> list[str]:
    if " - " in title: return [title.split(" - ")[0].strip()]
    return [title.strip()]

def _extract_incident_id(link: str) -> str:
    match = re.search(r"trackingid=([A-Z0-9\-]+)", link, re.IGNORECASE)
    if match: return match.group(1)
    return link.rstrip("/").split("/")[-1] or link

class AzureCollector(BaseCollector):
    provider = Provider.AZURE

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(AZURE_RSS_URL, headers={"Accept": "application/rss+xml, application/xml, text/xml"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        return [e for e in (self._parse_entry(entry) for entry in feed.entries) if e]

    def _parse_entry(self, entry) -> StatusEvent | None:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        summary = getattr(entry, "summary", "") or ""
        published = getattr(entry, "published", None)
        updated = getattr(entry, "updated", None)
        incident_id = _extract_incident_id(link) if link else title[:50]
        services = _extract_service_from_title(title)
        severity = _infer_severity(title, summary)
        regions = extract_azure_regions_from_text(summary)
        started_at = self._parse_rfc_date(published)
        last_updated = self._parse_rfc_date(updated) or started_at
        clean_desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", summary)).strip()
        return StatusEvent(
            provider=Provider.AZURE, incident_id=incident_id, title=title[:120],
            severity=severity, status="active", affected_services=services,
            affected_regions=regions, started_at=started_at, last_updated=last_updated,
            url=link or "https://status.azure.com", description=clean_desc[:500], is_resolved=False,
        )

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        result = []
        for event in events:
            if event.affected_regions:
                result.append(event)
            else:
                result.append(event.model_copy(update={"affected_regions": ["(region not specified)"]}))
        return result

    @staticmethod
    def _parse_rfc_date(value: str | None) -> datetime:
        if not value: return datetime.utcnow()
        try: return parsedate_to_datetime(value).replace(tzinfo=None)
        except Exception:
            try: return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception: return datetime.utcnow()
```

---

## FILE: src/download_detector/collectors/gcp.py

```python
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

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(GCP_INCIDENTS_URL)
        resp.raise_for_status()
        incidents: list[dict] = resp.json()
        return [self._parse_incident(inc) for inc in incidents if self._is_relevant(inc)]

    def _is_relevant(self, incident: dict) -> bool:
        if not incident.get("end"): return True
        try:
            end = datetime.fromisoformat(incident["end"].replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - end).total_seconds() / 3600 < 24
        except Exception: return True

    def _parse_incident(self, inc: dict) -> StatusEvent:
        severity = GCP_SEVERITY_MAP.get((inc.get("severity") or "low").lower(), Severity.DEGRADED)
        all_locations = list(inc.get("affected_locations") or [])
        all_locations += [loc for loc in (inc.get("previously_affected_locations") or []) if loc not in all_locations]
        products = [p.get("title", p.get("id", "")) for p in (inc.get("affected_products") or [])]
        started_at = self._parse_ts(inc.get("begin"))
        resolved_at = self._parse_ts(inc.get("end"))
        updates = inc.get("updates") or []
        update_times = [self._parse_ts(u.get("modified")) for u in updates if u.get("modified")]
        last_updated = max(update_times) if update_times else started_at
        description = updates[0].get("text", inc.get("external_desc", "")) if updates else inc.get("external_desc", "")
        return StatusEvent(
            provider=Provider.GCP, incident_id=str(inc.get("id", "")),
            title=inc.get("external_desc", "GCP Incident")[:120],
            severity=severity, status="ongoing" if not inc.get("end") else "resolved",
            affected_services=products, affected_regions=all_locations,
            started_at=started_at, resolved_at=resolved_at, last_updated=last_updated,
            url=f"https://status.cloud.google.com/incidents/{inc.get('id', '')}",
            description=description, is_resolved=bool(inc.get("end")),
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
        if not value: return datetime.utcnow()
        try: return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception: return datetime.utcnow()
```

---

## FILE: src/download_detector/collectors/oci.py

```python
import logging
from datetime import datetime
import httpx
from ..models import Provider, Severity, StatusEvent, STATUSPAGE_SEVERITY_MAP
from ..config import ProviderConfig
from ..filters.region import OCI_USA_REGIONS, filter_oci_usa_regions
from .base import BaseCollector, DEFAULT_HEADERS

logger = logging.getLogger(__name__)
OCI_SUMMARY_URL = "https://ocistatus.oracle.com/api/v2/summary.json"

class OCICollector(BaseCollector):
    provider = Provider.OCI

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS, timeout=httpx.Timeout(20.0),
            follow_redirects=True, transport=httpx.HTTPTransport(retries=3),
        )

    def _fetch_and_parse(self) -> list[StatusEvent]:
        resp = self._client.get(OCI_SUMMARY_URL)
        resp.raise_for_status()
        data = resp.json()
        all_components = data.get("components", [])
        usa_ids = self._find_usa_component_ids(all_components)
        events = [self._parse_incident(inc, usa_ids) for inc in (data.get("incidents", []))]
        events.extend(self._parse_degraded_components(all_components, usa_ids))
        return events

    def _find_usa_component_ids(self, components: list[dict]) -> set[str]:
        usa_ids: set[str] = set()
        for comp in components:
            for usa_region in OCI_USA_REGIONS:
                if usa_region.lower() in comp.get("name", "").lower():
                    usa_ids.add(comp["id"])
                    break
        return usa_ids

    def _parse_incident(self, inc: dict, usa_ids: set[str]) -> StatusEvent:
        inc_components = inc.get("components", []) or []
        affected_services = [c.get("name", "") for c in inc_components if c.get("name")]
        affected_regions = [c.get("name", "") for c in inc_components if c.get("id") in usa_ids]
        severity = {"none": Severity.OPERATIONAL, "minor": Severity.DEGRADED, "major": Severity.OUTAGE,
                    "critical": Severity.CRITICAL, "maintenance": Severity.MAINTENANCE}.get(inc.get("impact", "minor"), Severity.DEGRADED)
        status = inc.get("status", "")
        updates = inc.get("incident_updates") or []
        started_at = self._parse_ts(inc.get("created_at"))
        return StatusEvent(
            provider=Provider.OCI, incident_id=inc.get("id", ""), title=inc.get("name", "OCI Incident"),
            severity=severity, status=status, affected_services=affected_services, affected_regions=affected_regions,
            started_at=started_at,
            resolved_at=self._parse_ts(inc.get("resolved_at")) if inc.get("resolved_at") else None,
            last_updated=self._parse_ts(updates[0].get("updated_at")) if updates else started_at,
            url=inc.get("shortlink") or "https://ocistatus.oracle.com",
            description=updates[0].get("body", "") if updates else "",
            is_resolved=status == "resolved",
        )

    def _parse_degraded_components(self, components: list[dict], usa_ids: set[str]) -> list[StatusEvent]:
        events = []
        for comp in components:
            if comp.get("id") not in usa_ids: continue
            status = comp.get("status", "operational")
            if status == "operational": continue
            severity = STATUSPAGE_SEVERITY_MAP.get(status, Severity.DEGRADED)
            events.append(StatusEvent(
                provider=Provider.OCI, incident_id=f"component-{comp['id']}",
                title=f"{comp.get('name', 'OCI Component')} — {status.replace('_', ' ').title()}",
                severity=severity, status=status,
                affected_services=[comp.get("name", "")], affected_regions=[comp.get("name", "")],
                started_at=self._parse_ts(comp.get("updated_at")),
                last_updated=self._parse_ts(comp.get("updated_at")),
                url="https://ocistatus.oracle.com", is_resolved=False,
            ))
        return events

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        filtered = []
        for event in events:
            if event.incident_id.startswith("component-"):
                filtered.append(event); continue
            usa_regions = filter_oci_usa_regions(event.affected_regions)
            if usa_regions or not event.affected_regions:
                filtered.append(event.model_copy(update={"affected_regions": usa_regions or event.affected_regions}))
        return filtered

    @staticmethod
    def _parse_ts(value: str | None) -> datetime:
        if not value: return datetime.utcnow()
        try: return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception: return datetime.utcnow()
```

---

## FILE: src/download_detector/collectors/cloudflare.py

```python
import logging
from datetime import datetime
from ..models import Provider, Severity, StatusEvent
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
        all_components = data.get("components", [])
        component_map = {c["id"]: c for c in all_components}
        na_group_id = next(
            (c["id"] for c in all_components if c.get("group") and "north america" in c.get("name", "").lower()), None
        )
        self._usa_component_ids = {
            c["id"] for c in all_components
            if c.get("group_id") == na_group_id and "united states" in c.get("name", "").lower()
        }
        return [e for e in (self._parse_incident(inc, component_map) for inc in data.get("incidents", [])) if e]

    def _parse_incident(self, inc: dict, component_map: dict) -> StatusEvent | None:
        inc_components = inc.get("components", [])
        affected_services = [c.get("name", "") for c in inc_components if c.get("name")]
        impact = inc.get("impact", "none")
        severity = {"none": Severity.OPERATIONAL, "minor": Severity.DEGRADED, "major": Severity.OUTAGE,
                    "critical": Severity.CRITICAL, "maintenance": Severity.MAINTENANCE}.get(impact, Severity.DEGRADED)
        status = inc.get("status", "")
        updates = inc.get("incident_updates") or []
        started_at = self._parse_ts(inc.get("created_at"))
        return StatusEvent(
            provider=Provider.CLOUDFLARE, incident_id=inc.get("id", ""),
            title=inc.get("name", "Cloudflare Incident"), severity=severity, status=status,
            affected_services=affected_services,
            affected_regions=[c.get("name", "") for c in inc_components if c.get("id") in self._usa_component_ids],
            started_at=started_at,
            resolved_at=self._parse_ts(inc.get("resolved_at")) if inc.get("resolved_at") else None,
            last_updated=self._parse_ts(updates[0].get("updated_at")) if updates else started_at,
            url=inc.get("shortlink") or f"https://www.cloudflarestatus.com/incidents/{inc.get('id','')}",
            description=updates[0].get("body", "") if updates else "",
            is_resolved=status == "resolved",
        )

    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        return events  # USA filtering done in _parse_incident via _usa_component_ids

    @staticmethod
    def _parse_ts(value: str | None) -> datetime:
        if not value: return datetime.utcnow()
        try: return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception: return datetime.utcnow()
```

---

## FILE: src/download_detector/scheduler.py

```python
import logging, random
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .collectors.azure import AzureCollector
from .collectors.gcp import GCPCollector
from .collectors.oci import OCICollector
from .collectors.cloudflare import CloudflareCollector
from .collectors.base import BaseCollector
from .config import AppConfig
from .store import StatusStore
from .models import Provider

logger = logging.getLogger(__name__)

def _run_collector(collector: BaseCollector, store: StatusStore) -> None:
    provider = collector.provider
    try:
        events = collector.collect()
        store.upsert(provider, events)
        store.set_poll_time(provider, datetime.utcnow(), error=None)
        logger.debug("%s: collected %d events", provider.value, len(events))
    except Exception as e:
        store.set_poll_time(provider, datetime.utcnow(), error=str(e))
        logger.error("%s: collector job failed: %s", provider.value, e)

def build_scheduler(config: AppConfig, store: StatusStore) -> tuple[BackgroundScheduler, list[BaseCollector]]:
    collectors: list[BaseCollector] = []
    if config.azure.enabled:     collectors.append(AzureCollector(config.azure))
    if config.gcp.enabled:       collectors.append(GCPCollector(config.gcp))
    if config.oci.enabled:       collectors.append(OCICollector(config.oci))
    if config.cloudflare.enabled: collectors.append(CloudflareCollector(config.cloudflare))
    scheduler = BackgroundScheduler(daemon=True)
    interval = config.polling_interval_seconds
    for collector in collectors:
        jitter = random.randint(0, min(10, interval // 6))
        provider_interval = interval + 30 if collector.provider == Provider.OCI else interval
        scheduler.add_job(
            func=_run_collector, args=[collector, store],
            trigger=IntervalTrigger(seconds=provider_interval, jitter=jitter),
            id=f"collect_{collector.provider.value}", replace_existing=True, max_instances=1,
        )
    return scheduler, collectors

def initial_collect_all(collectors: list[BaseCollector], store: StatusStore) -> None:
    for collector in collectors:
        logger.info("Initial collection: %s", collector.provider.value)
        _run_collector(collector, store)
```

---

## FILE: src/download_detector/main.py

```python
import logging, signal, threading
from .config import AppConfig
from .store import StatusStore
from .scheduler import build_scheduler, initial_collect_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

def main() -> None:
    config = AppConfig.from_yaml()
    store = StatusStore()
    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    logger.info("Starting Cloud Status Monitor (UI: %s)", config.ui)

    scheduler, collectors = build_scheduler(config, store)
    logger.info("Performing initial data collection...")
    initial_collect_all(collectors, store)
    scheduler.start()
    logger.info("Polling scheduler started (interval: %ds)", config.polling_interval_seconds)

    try:
        if config.ui == "terminal":
            from .ui.terminal import run_terminal_dashboard
            run_terminal_dashboard(store, config.polling_interval_seconds, stop_event)
        else:
            from .ui.web import create_app
            import webbrowser, threading as _t
            app = create_app(store)
            url = f"http://localhost:{config.web_port}"
            logger.info("Web UI: %s", url)
            _t.Timer(1.5, lambda: webbrowser.open(url)).start()
            app.run(host="0.0.0.0", port=config.web_port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown(wait=False)
        for collector in collectors: collector.close()
        logger.info("Bye.")

if __name__ == "__main__":
    main()
```

---

## FILE: src/download_detector/ui/terminal.py

Full Rich terminal dashboard — reads from store every second, renders:
- Header panel: provider name, last poll time, incident count per provider
- Incidents table: Provider | Severity | Title | Services | Regions | Started | Duration
- Footer: key hints

Uses `rich.live.Live` with `Layout` split into header (size=5) / body / footer (size=1).
Severity color map: CRITICAL=bold red, OUTAGE=red, DEGRADED=yellow, MAINTENANCE=cyan, OPERATIONAL=green.
Sort incidents: severity order (critical first), then started_at.

(See full source in src/download_detector/ui/terminal.py — 193 lines)

---

## FILE: src/download_detector/ui/web.py

Flask app + complete single-file HTML/CSS/JS web UI.
Design: Microsoft Fluent Design System (white background, Segoe UI font, MS blue accents).

### Flask routes:
- GET /                       — live UI
- GET /demo                   — demo UI with simulated incidents
- GET /api/summary            — {azure:{overall_status, active_count, last_poll, error}, ...}
- GET /api/matrix/<provider>  — {services[], regions[], matrix{svc:{reg:{status,incidents[]}}}, incidents[], ...}
- GET /api/demo/summary       — same shape, uses hardcoded demo data
- GET /api/demo/matrix/<p>    — same shape, uses hardcoded demo data
- GET /api/health             — {status:"ok", time:...}

### Demo data (_demo_matrix function):
Hardcoded realistic incidents for each provider showing all severity levels:
- Azure: Storage degraded (East US/East US 2), SQL outage (West US 2), Monitor maintenance (Central US)
- GCP: Cloud Run degraded (us-central1/us-east1), Cloud SQL critical (us-west1)
- OCI: Object Storage degraded (US East Ashburn)
- Cloudflare: Workers outage (Ashburn/NYC/Atlanta)

### UI features:
- Sticky top bar — color changes per provider brand (Azure=blue, GCP=Google blue, OCI=Oracle red, CF=orange)
- Provider tabs — brand-colored active state, logo emoji, green/yellow/red status dot, incident count badge
- Demo banner — yellow strip shown only on /demo with link back to live
- Incident banners — color-coded strips (red/orange/yellow/blue), click to open detail panel
- All clear banner — green, shown when no active incidents
- Service × Region matrix — table with colored SVG icons per cell (✓ degraded ⚠ outage ● critical ✕ maintenance 🕐)
- Cell tooltip — hover shows incident title
- Detail panel — slides in from right, shows severity pill, start time, duration, status, services tags, regions tags, description, "View on Provider" button
- Auto-refresh every 30s (live mode only)
- Manual refresh button with spin animation

### Provider brand colors:
- Azure: topbar #0078d4, tab active #0078d4
- GCP: topbar #1a73e8, tab active #4285f4
- OCI: topbar #c74634, tab active #c74634
- Cloudflare: topbar #f6821f, tab active #f6821f

### Key implementation note:
Demo mode is toggled by string replacement in the /demo route:
  `const DEMO_MODE = false;` → `const DEMO_MODE = true;`
Do NOT use JS comment-based replacement (causes syntax errors).

(See full source in src/download_detector/ui/web.py — 1083 lines)

---

## FILE: tests/conftest.py

```python
import pytest
from download_detector.config import ProviderConfig
from download_detector.store import StatusStore

@pytest.fixture
def empty_config():
    return ProviderConfig(enabled=True, service_filter=[])

@pytest.fixture
def org_config():
    return ProviderConfig(enabled=True, service_filter=["Cloud Run", "Cloud Storage"])

@pytest.fixture
def store():
    return StatusStore()
```

---

## FILE: tests/test_filters.py

```python
from download_detector.filters.region import (
    filter_azure_usa_regions, filter_gcp_usa_regions,
    filter_oci_usa_regions, extract_azure_regions_from_text,
)

def test_gcp_usa_filter_includes_us_regions():
    locs = ["us-east1", "us-central1", "europe-west1", "asia-east1"]
    assert filter_gcp_usa_regions(locs) == ["us-east1", "us-central1"]

def test_gcp_usa_filter_empty():
    assert filter_gcp_usa_regions([]) == []

def test_azure_usa_filter():
    regions = ["East US", "West Europe", "South Central US", "Japan East"]
    result = filter_azure_usa_regions(regions)
    assert "East US" in result
    assert "South Central US" in result
    assert "West Europe" not in result

def test_oci_usa_filter():
    regions = ["US East (Ashburn)", "EU Frankfurt 1", "US West (Phoenix)"]
    result = filter_oci_usa_regions(regions)
    assert "US East (Ashburn)" in result
    assert "US West (Phoenix)" in result
    assert "EU Frankfurt 1" not in result

def test_extract_azure_regions_from_text():
    text = "Customers in East US and West US 2 may experience issues."
    regions = extract_azure_regions_from_text(text)
    assert "East US" in regions
    assert "West US 2" in regions
    assert "West Europe" not in regions
```

---

## FILE: tests/test_models.py

```python
from datetime import datetime
from download_detector.models import StatusEvent, Provider, Severity

def make_event(**kwargs):
    defaults = dict(
        provider=Provider.GCP, incident_id="test-001", title="Test Incident",
        severity=Severity.DEGRADED, status="investigating",
        affected_services=["Cloud Run"], affected_regions=["us-east1"],
        started_at=datetime(2024, 1, 1, 12, 0), last_updated=datetime(2024, 1, 1, 12, 30),
    )
    defaults.update(kwargs)
    return StatusEvent(**defaults)

def test_is_active_when_not_resolved():
    assert make_event(is_resolved=False).is_active is True

def test_is_active_false_when_resolved():
    assert make_event(is_resolved=True, resolved_at=datetime(2024, 1, 1, 13, 0)).is_active is False

def test_duration_str_minutes():
    e = make_event(started_at=datetime(2024, 1, 1, 12, 0), resolved_at=datetime(2024, 1, 1, 12, 45), is_resolved=True)
    assert e.duration_str == "45m"

def test_duration_str_hours():
    e = make_event(started_at=datetime(2024, 1, 1, 12, 0), resolved_at=datetime(2024, 1, 1, 14, 30), is_resolved=True)
    assert e.duration_str == "2h 30m"

def test_model_serialization():
    d = make_event().model_dump()
    assert d["provider"] == "gcp"
    assert d["severity"] == "degraded"
```

---

## FILE: Dockerfile

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
WORKDIR /app
RUN adduser --disabled-password --gecos "" appuser
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
COPY config/ /app/config/
USER appuser
ENV DD_UI=terminal
ENV DD_POLLING_INTERVAL_SECONDS=60
CMD ["download-detector"]
```

---

## FILE: docker-compose.yml

```yaml
services:
  monitor:
    build: .
    environment:
      DD_UI: terminal
      DD_POLLING_INTERVAL_SECONDS: "60"
    volumes:
      - ./config:/app/config:ro
    restart: unless-stopped
    tty: true
    stdin_open: true
  # monitor-web:
  #   build: .
  #   environment:
  #     DD_UI: web
  #     DD_POLLING_INTERVAL_SECONDS: "60"
  #   volumes:
  #     - ./config:/app/config:ro
  #   ports:
  #     - "5000:5000"
  #   restart: unless-stopped
```

---

## FILE: .dockerignore

```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
tests/
.git/
*.egg-info/
dist/
build/
.venv/
venv/
*.md
```

---

## HOW TO RUN LOCALLY

```bash
cd d:/outskill/download_detector
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"

# Run (web UI default, opens browser at http://localhost:5000)
.venv/Scripts/download-detector

# Demo mode (simulated incidents)
# visit http://localhost:5000/demo

# Terminal UI
DD_UI=terminal .venv/Scripts/download-detector

# Run tests
.venv/Scripts/pytest tests/ -v
```

## HOW TO RUN IN DOCKER

```bash
docker compose up
# or for web UI:
# set DD_UI=web and expose port 5000 in docker-compose.yml
```

## ENVIRONMENT VARIABLES

| Variable                    | Default  | Description                    |
|-----------------------------|----------|--------------------------------|
| DD_UI                       | web      | "web" or "terminal"            |
| DD_WEB_PORT                 | 5000     | Flask port                     |
| DD_POLLING_INTERVAL_SECONDS | 60       | Polling cadence in seconds      |
| DD_AZURE__ENABLED           | true     | Enable Azure collector         |
| DD_GCP__ENABLED             | true     | Enable GCP collector           |
| DD_OCI__ENABLED             | true     | Enable OCI collector           |
| DD_CLOUDFLARE__ENABLED      | true     | Enable Cloudflare collector    |

---

## KNOWN GOTCHAS

1. OCI status endpoint (ocistatus.oracle.com) can be slow — collector uses 20s
   timeout + 3 retries. It gets a 30s longer poll interval than other providers.

2. Azure has no public JSON API — uses RSS feed only. Severity is inferred from
   keyword matching in title/description, not from a structured field.

3. GCP includes incidents resolved in the last 24h — filtered by `_is_relevant()`.

4. Cloudflare USA filtering works by finding the "North America" group component
   and then filtering child components containing "United States".

5. Demo mode MUST use string replacement `const DEMO_MODE = false;` ->
   `const DEMO_MODE = true;` — do NOT use JS comment markers as it breaks the
   const declaration and crashes the entire script.

6. Python 3.11 is used locally (not 3.12). pyproject.toml says `>=3.11`.
   Dockerfile uses python:3.12-slim (fine for container builds).

7. No Google Fonts imports — Segoe UI is served from the system font stack:
   `font-family: 'Segoe UI', system-ui, -apple-system, sans-serif`
