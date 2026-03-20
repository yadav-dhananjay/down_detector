from datetime import datetime
from download_detector.models import StatusEvent, Provider, Severity


def make_event(**kwargs):
    defaults = dict(
        provider=Provider.GCP,
        incident_id="test-001",
        title="Test Incident",
        severity=Severity.DEGRADED,
        status="investigating",
        affected_services=["Cloud Run"],
        affected_regions=["us-east1"],
        started_at=datetime(2024, 1, 1, 12, 0),
        last_updated=datetime(2024, 1, 1, 12, 30),
    )
    defaults.update(kwargs)
    return StatusEvent(**defaults)


def test_is_active_when_not_resolved():
    e = make_event(is_resolved=False)
    assert e.is_active is True


def test_is_active_false_when_resolved():
    e = make_event(is_resolved=True, resolved_at=datetime(2024, 1, 1, 13, 0))
    assert e.is_active is False


def test_duration_str_minutes():
    e = make_event(
        started_at=datetime(2024, 1, 1, 12, 0),
        resolved_at=datetime(2024, 1, 1, 12, 45),
        is_resolved=True,
    )
    assert e.duration_str == "45m"


def test_duration_str_hours():
    e = make_event(
        started_at=datetime(2024, 1, 1, 12, 0),
        resolved_at=datetime(2024, 1, 1, 14, 30),
        is_resolved=True,
    )
    assert e.duration_str == "2h 30m"


def test_model_serialization():
    e = make_event()
    d = e.model_dump()
    assert d["provider"] == "gcp"
    assert d["severity"] == "degraded"
