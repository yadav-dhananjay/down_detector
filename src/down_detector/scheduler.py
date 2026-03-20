import logging
import random
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
    """Create and return a configured scheduler and collector instances."""
    collectors: list[BaseCollector] = []

    if config.azure.enabled:
        collectors.append(AzureCollector(config.azure))
    if config.gcp.enabled:
        collectors.append(GCPCollector(config.gcp))
    if config.oci.enabled:
        collectors.append(OCICollector(config.oci))
    if config.cloudflare.enabled:
        collectors.append(CloudflareCollector(config.cloudflare))

    scheduler = BackgroundScheduler(daemon=True)
    interval = config.polling_interval_seconds

    for collector in collectors:
        jitter = random.randint(0, min(10, interval // 6))
        # OCI gets a longer interval due to connectivity issues
        provider_interval = interval + 30 if collector.provider == Provider.OCI else interval
        scheduler.add_job(
            func=_run_collector,
            trigger=IntervalTrigger(seconds=provider_interval, jitter=jitter),
            args=[collector, store],
            id=f"collect_{collector.provider.value}",
            name=f"Collect {collector.provider.value.upper()} status",
            replace_existing=True,
            max_instances=1,
        )

    return scheduler, collectors


def initial_collect_all(collectors: list[BaseCollector], store: StatusStore) -> None:
    """Run all collectors once synchronously before starting the scheduler."""
    for collector in collectors:
        logger.info("Initial collection: %s", collector.provider.value)
        _run_collector(collector, store)
