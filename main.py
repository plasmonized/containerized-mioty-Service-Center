
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
    """Main application entry point."""
    global tls_server_instance

    logger = setup_logging()

    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    logger.info("Initializing BSSCI Service Center...")
    logger.info(
        f"Config: TLS Port {bssci_config.LISTEN_PORT}, "
        f"MQTT Broker {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}"
    )

    # Setup queue logging to monitor queue usage
    queue_loggers = setup_queue_logging(
        {"mqtt_out_queue": mqtt_out_queue, "mqtt_in_queue": mqtt_in_queue}
    )

    logger.info("🔍 Queue Instance Analysis:")
    logger.info(f"   mqtt_out_queue ID: {id(mqtt_out_queue)}")
    logger.info(f"   mqtt_in_queue ID: {id(mqtt_in_queue)}")

    # Initialize services with consistent queue instances
    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue
    )
    tls_server_instance = tls_server  # Store global reference
    mqtt_client = MQTTClient(mqtt_out_queue, mqtt_in_queue)

    logger.info("🔍 Queue Assignment Verification:")
    logger.info(f"   TLS Server mqtt_out_queue ID: {id(tls_server.mqtt_out_queue)}")
    logger.info(f"   TLS Server mqtt_in_queue ID: {id(tls_server.mqtt_in_queue)}")
    logger.info(f"   MQTT Client mqtt_out_queue ID: {id(mqtt_client.mqtt_out_queue)}")
    logger.info(f"   MQTT Client mqtt_in_queue ID: {id(mqtt_client.mqtt_in_queue)}")

    # Start the stats reporter task
    asyncio.create_task(queue_stats_reporter(queue_loggers))

    logger.info("Starting BSSCI Service Center...")
    logger.info("✓ Both TLS Server and MQTT Interface are starting...")

    try:
        # Start both services concurrently
        await asyncio.gather(
            tls_server.start_server(), mqtt_client.start(), return_exceptions=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down BSSCI Service Center...")
    except Exception as e:
        logger.error(f"Service error: {e}")
        raise

    logger.info("✓ BSSCI Service Center shut down complete")


if __name__ == "__main__":
    # Set Windows-specific event loop policy if available
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
