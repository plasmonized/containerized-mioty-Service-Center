"""Web interface main module for mioty BSSCI Service Center."""

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta

import bssci_config
from main import main as bssci_main
from web_ui import create_app


class TimezoneFormatter(logging.Formatter):
    """Custom logging formatter with timezone support."""

    def __init__(self, fmt: str, datefmt: str = None) -> None:
        """Initialize the formatter with timezone settings."""
        super().__init__(fmt, datefmt)
        # Set timezone to UTC+2 (Central European Time)
        self.timezone = timezone(timedelta(hours=2))

    def formatTime(self, record: logging.LogRecord, datefmt: str = None) -> str:
        """Format timestamp with local timezone."""
        # Convert UTC timestamp to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.timezone)
        if datefmt:
            return local_time.strftime(datefmt)
        else:
            return local_time.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging() -> None:
    """Configure logging with timezone formatting."""
    logging.basicConfig(
        level=getattr(logging, bssci_config.LOG_LEVEL),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Apply timezone formatter to all handlers
    timezone_formatter = TimezoneFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    for handler in logging.root.handlers:
        handler.setFormatter(timezone_formatter)


# Global reference for TLS server instance
tls_server_instance = None


def get_tls_server():
    """Get the TLS server instance."""
    try:
        import main
        return getattr(main, "tls_server_instance", None)
    except Exception as e:
        logger.error(f"Error getting TLS server: {e}")
        return None


def run_web_ui() -> None:
    """Run the Flask web UI."""
    logger.info(f"Starting Web UI on {bssci_config.WEB_HOST}:{bssci_config.WEB_PORT}")
    app = create_app()
    app.config["DEBUG"] = bssci_config.WEB_DEBUG
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")

    app.run(
        host=bssci_config.WEB_HOST,
        port=bssci_config.WEB_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def run_bssci_service():
    """Run BSSCI service in background."""
    global tls_server_instance
    try:
        # Import and run the main BSSCI service
        import main
        asyncio.run(main.main())
    except Exception as e:
        logger.error(f"Error starting BSSCI service: {e}")

def main() -> None:
    """Main entry point combining web UI and BSSCI service."""
    global logger, tls_server_instance

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting BSSCI Service Center with Web UI")

    # Start BSSCI service in background thread
    bssci_thread = threading.Thread(target=run_bssci_service, daemon=True)
    bssci_thread.start()

    # Give the service a moment to start
    time.sleep(2)

    # Start web UI in a separate thread
    web_thread = threading.Thread(target=run_web_ui, daemon=True)
    web_thread.start()

    # Give web UI time to start
    time.sleep(2)
    logger.info(f"Web UI available at http://localhost:{bssci_config.WEB_PORT}")

    # Keep the main thread alive to allow background threads to run
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()