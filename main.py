import asyncio
import logging

import bssci_config
from bssci_config import SENSOR_CONFIG_FILE, LISTEN_HOST, LISTEN_PORT, MQTT_BROKER, MQTT_PORT
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

# Configure logging with timezone
import time
from datetime import datetime, timezone, timedelta

class TimezoneFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None):
        super().__init__(fmt, datefmt)
        self.timezone_offset = timedelta(hours=2)  # +2 hours from UTC
    
    def formatTime(self, record, datefmt=None):
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time + self.timezone_offset
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
for handler in logging.root.handlers:
    handler.setFormatter(TimezoneFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        '%Y-%m-%d %H:%M:%S'
    ))
logger = logging.getLogger(__name__)

async def main():
    global tls_server_instance
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    logger.info("Initializing BSSCI Service Center...")
    logger.info(f"Config: TLS Port {LISTEN_PORT}, MQTT Broker {MQTT_BROKER}:{MQTT_PORT}")

    # Setup queue logging to monitor queue usage
    from queue_logger import setup_queue_logging, log_all_queue_stats
    queue_loggers = setup_queue_logging({
        'mqtt_out_queue': mqtt_out_queue,
        'mqtt_in_queue': mqtt_in_queue
    })

    logger.info("🔍 Queue Instance Analysis:")
    logger.info(f"   mqtt_out_queue ID: {id(mqtt_out_queue)}")
    logger.info(f"   mqtt_in_queue ID: {id(mqtt_in_queue)}")

    # Fixed parameter order - both should use the same queue instances consistently
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

    # Periodic queue statistics
    async def queue_stats_reporter():
        while True:
            await asyncio.sleep(60)  # Log stats every minute
            log_all_queue_stats(queue_loggers)

    # Start the stats reporter task
    asyncio.create_task(queue_stats_reporter())

    logger.info("Starting BSSCI Service Center...")
    logger.info("✓ Both TLS Server and MQTT Interface are starting...")

    try:
        # Start both services concurrently
        await asyncio.gather(
            tls_server.start_server(),
            mqtt_client.start(),
            return_exceptions=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down BSSCI Service Center...")
    except Exception as e:
        logger.error(f"Service error: {e}")
    
    logger.info("✓ BSSCI Service Center shut down complete")

# Global TLS server instance for web UI access
tls_server_instance = None


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())