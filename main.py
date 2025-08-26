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

    logger.info("Initializing BSSCI Service Center...")
    logger.info(f"Config: TLS Port {LISTEN_PORT}, MQTT Broker {MQTT_BROKER}:{MQTT_PORT}")

    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, mqtt_in_queue, mqtt_out_queue
    )
    tls_server_instance = tls_server  # Store global reference
    mqtt_client = MQTTClient(mqtt_out_queue, mqtt_in_queue)

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