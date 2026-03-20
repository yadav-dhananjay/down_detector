import logging
from abc import ABC, abstractmethod
from datetime import datetime

import httpx

from ..models import Provider, StatusEvent
from ..config import ProviderConfig

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "download-detector/0.1 (cloud-status-monitor; https://github.com/your-org/download-detector)",
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
        """Fetch, parse, filter, and return StatusEvents. Returns [] on error."""
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
    def _fetch_and_parse(self) -> list[StatusEvent]:
        """Fetch from provider API and return all parsed events (unfiltered)."""
        ...

    @abstractmethod
    def _filter_usa_regions(self, events: list[StatusEvent]) -> list[StatusEvent]:
        """Filter events to only those affecting USA regions."""
        ...

    def _filter_by_org_services(self, events: list[StatusEvent]) -> list[StatusEvent]:
        """Filter events to only those affecting configured org services."""
        service_filter = [s.lower() for s in self.config.service_filter]
        return [
            e for e in events
            if any(
                svc in s.lower()
                for svc in service_filter
                for s in e.affected_services
            )
        ]

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.utcnow()
