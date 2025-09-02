"""Main entry point for the mioty BSSCI Service Center."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import bssci_config
from mqtt_interface import MQTTClient
from TLSServer import TLSServer
from queue_logger import setup_queue_logging, log_all_queue_stats


class TimezoneFormatter(logging.Formatter):
    """Custom logging formatter with timezone support."""

    def __init__(self, fmt: str, datefmt: Optional[str] = None) -> None:
        """Initialize the formatter with timezone settings."""
        super().__init__(fmt, datefmt)
        # Set timezone to UTC+2 (Central European Time)
        self.timezone = timezone(timedelta(hours=2))

    def formatTime(
        self, record: logging.LogRecord, datefmt: Optional[str] = None
    ) -> str:
        """Format timestamp with local timezone."""
        # Convert UTC timestamp to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.timezone)
        if datefmt:
            return local_time.strftime(datefmt)
        else:
            return local_time.strftime("%Y-%m-%d %H:%M:%S")


def setup_logging() -> logging.Logger:
    """Configure logging with timezone formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Apply timezone formatter to all handlers
    timezone_formatter = TimezoneFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    for handler in logging.root.handlers:
        handler.setFormatter(timezone_formatter)

    return logging.getLogger(__name__)


# Global TLS server instance for web UI access
tls_server_instance: Optional[TLSServer] = None


async def queue_stats_reporter(queue_loggers: dict) -> None:
    """Report queue statistics periodically."""
    while True:
        await asyncio.sleep(60)  # Log stats every minute
        log_all_queue_stats(queue_loggers)


async def main() -> None:
    """Main entry point for the BSSCI Service Center."""
    global tls_server, mqtt_interface

    logging.basicConfig(
        level=getattr(logging, bssci_config.LOG_LEVEL.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
        ]
        + ([logging.FileHandler(bssci_config.LOG_FILE)] if bssci_config.LOG_FILE else []),
    )

    logger.info("Starting mioty BSSCI Service Center")
    logger.info(f"Listening on {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")
    logger.info(f"MQTT Broker: {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")

    # Create communication queues
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    # Initialize MQTT interface
    mqtt_interface = MQTTInterface(mqtt_out_queue, mqtt_in_queue)

    # Initialize TLS server
    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue
    )

    # Store instances globally for web UI access
    import sys
    sys.modules['__main__'].tls_server = tls_server
    sys.modules['__main__'].mqtt_interface = mqtt_interface

    # Start services
    await asyncio.gather(
        mqtt_interface.run(),
        tls_server.start_server(),
        tls_server.status_task(),
        return_exceptions=True,
    )

# Global variables for web UI access
tls_server = None
mqtt_interface = None


if __name__ == "__main__":
    # Set Windows-specific event loop policy if available
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())