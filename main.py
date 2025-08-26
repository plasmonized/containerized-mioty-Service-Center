import asyncio
import logging

import bssci_config
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Starting BSSCI Service Center...")
    logger.info(f"TLS Server will listen on {bssci_config.LISTEN_HOST}:{bssci_config.LISTEN_PORT}")
    logger.info(f"MQTT Broker: {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")
    logger.info(f"Sensor config file: {bssci_config.SENSOR_CONFIG_FILE}")

    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

    logger.info("Initializing TLS Server...")
    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue
    )

    logger.info("Initializing MQTT Client...")
    mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)

    logger.info("Starting services...")
    await asyncio.gather(mqtt_server.start(), tls_server.start_server())


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())