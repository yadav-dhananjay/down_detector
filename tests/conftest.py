import pytest
from down_detector.config import ProviderConfig
from down_detector.store import StatusStore


@pytest.fixture
def empty_config():
    return ProviderConfig(enabled=True, service_filter=[])


@pytest.fixture
def org_config():
    return ProviderConfig(enabled=True, service_filter=["Cloud Run", "Cloud Storage"])


@pytest.fixture
def store():
    return StatusStore()
