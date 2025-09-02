import asyncio
import logging
import threading
import signal
from bssci_config import LISTEN_PORT, CERT_FILE, KEY_FILE, CA_FILE
from TLSServer import TLSServer
from mqtt_interface import MQTTClient
import bssci_config

logger = logging.getLogger(__name__)


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Shutdown signal received, stopping services...")

    # Stop TLS server
    if tls_server_instance:
        try:
            tls_server_instance.stop()
        except Exception as e:
            logger.error(f"Error stopping TLS server: {e}")

    # Stop MQTT interface
    if mqtt_interface_instance:
        try:
            # Use asyncio to run the async stop method
            if hasattr(mqtt_interface_instance, 'stop'):
                asyncio.run(mqtt_interface_instance.stop())
        except Exception as e:
            logger.error(f"Error stopping MQTT interface: {e}")

    exit(0)


tls_server_instance = None
mqtt_interface_instance = None


def setup_logging():
    """Configure logging for the application"""
    # Configure logging with timezone
    import time
    from datetime import datetime, timezone, timedelta

    class TimezoneFormatter(logging.Formatter):
        def __init__(self, fmt, datefmt=None):
            super().__init__(fmt, datefmt)
            # Set timezone to UTC+2 (Central European Time)
            self.timezone = timezone(timedelta(hours=2))

        def formatTime(self, record, datefmt=None):
            # Convert UTC timestamp to local timezone
            utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
            local_time = utc_time.astimezone(self.timezone)
            if datefmt:
                return local_time.strftime(datefmt)
            else:
                return local_time.strftime('%Y-%m-%d %H:%M:%S')

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Apply timezone formatter to all handlers
    timezone_formatter = TimezoneFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    )
    for handler in logging.root.handlers:
        handler.setFormatter(timezone_formatter)

    logger.info("Logging configured with timezone.")


def run_bssci_service():
    """Run the main BSSCI service"""
    global tls_server_instance, mqtt_interface_instance

    setup_logging()
    logger.info("Starting BSSCI Service Center")

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Create communication queues
        mqtt_out_queue = asyncio.Queue()
        mqtt_in_queue = asyncio.Queue()

        # Initialize TLS Server with queues
        logger.info("Initializing TLS Server...")
        tls_server_instance = TLSServer(
            bssci_config.SENSOR_CONFIG_FILE,
            mqtt_out_queue,
            mqtt_in_queue)

        # Initialize MQTT Interface with queues
        logger.info("Initializing MQTT Interface...")
        mqtt_interface_instance = MQTTClient(mqtt_out_queue, mqtt_in_queue)

        # Set MQTT interface in TLS server for bidirectional communication
        tls_server_instance.set_mqtt_interface(mqtt_interface_instance)

        # Create the main event loop
        async def run_services():
            # Start both services concurrently
            await asyncio.gather(
                tls_server_instance.start_server(),
                mqtt_interface_instance.start()
            )

        # Start both services
        logger.info("Starting TLS Server and MQTT Interface...")
        asyncio.run(run_services())

    except KeyboardInterrupt:
        logger.info("Shutdown signal received via keyboard interrupt")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Error in main service: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        signal_handler(signal.SIGTERM, None)


if __name__ == "__main__":
    run_bssci_service()