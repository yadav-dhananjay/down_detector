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
            # Remove old events for this provider, then insert fresh ones
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
        """Returns per-provider health summary."""
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
