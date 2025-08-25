import asyncio
import logging

import bssci_config
from bssci_config import SENSOR_CONFIG_FILE, LISTEN_HOST, LISTEN_PORT, MQTT_BROKER, MQTT_PORT
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    global tls_server_instance
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue
    )
    tls_server_instance = tls_server  # Store global reference
    mqtt_client = MQTTClient(mqtt_out_queue, mqtt_in_queue)

    # Create tasks for both services
    tls_task = asyncio.create_task(tls_server.start_server())
    mqtt_task = asyncio.create_task(mqtt_client.start())

    logger.info("Starting BSSCI Service Center...")
    logger.info("✓ Both TLS Server and MQTT Interface are starting...")

    try:
        # Wait for both tasks to complete (they should run indefinitely)
        await asyncio.gather(tls_task, mqtt_task)
    except KeyboardInterrupt:
        logger.info("Shutting down BSSCI Service Center...")
        tls_task.cancel()
        mqtt_task.cancel()

        try:
            await asyncio.gather(tls_task, mqtt_task, return_exceptions=True)
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

        logger.info("✓ BSSCI Service Center shut down complete")

# Global TLS server instance for web UI access
tls_server_instance = None


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())