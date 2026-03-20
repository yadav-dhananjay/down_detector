import logging
import signal
import threading
import sys

from .config import AppConfig
from .store import StatusStore
from .scheduler import build_scheduler, initial_collect_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
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

    # Initial data fetch before showing UI
    logger.info("Performing initial data collection...")
    initial_collect_all(collectors, store)

    # Start background polling
    scheduler.start()
    logger.info("Polling scheduler started (interval: %ds)", config.polling_interval_seconds)

    try:
        if config.ui == "terminal":
            from .ui.terminal import run_terminal_dashboard
            run_terminal_dashboard(store, config.polling_interval_seconds, stop_event)
        else:
            # Web UI (default)
            from .ui.web import create_app
            import webbrowser, threading as _t
            app = create_app(store)
            url = f"http://localhost:{config.web_port}"
            logger.info("Web UI: %s", url)
            # Open browser after a short delay so Flask is ready
            _t.Timer(1.5, lambda: webbrowser.open(url)).start()
            app.run(host="0.0.0.0", port=config.web_port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown(wait=False)
        for collector in collectors:
            collector.close()
        logger.info("Bye.")


if __name__ == "__main__":
    main()
