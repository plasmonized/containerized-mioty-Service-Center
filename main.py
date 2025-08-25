import asyncio
import logging
import os
import sys

from bssci_config import SENSOR_CONFIG_FILE, LISTEN_HOST, LISTEN_PORT, MQTT_BROKER, MQTT_PORT
from mqtt_interface import MQTTClient
from TLSServer import TLSServer

# Configure logging for both container and local environment
# Ensure logs directory exists
if os.path.exists('/app'):
    # Container environment
    os.makedirs('/app/logs', exist_ok=True)
    log_file = '/app/logs/bssci.log'
else:
    # Local development environment
    os.makedirs('logs', exist_ok=True)
    log_file = 'logs/bssci.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, mode='a')
    ]
)
logger = logging.getLogger(__name__)

async def main() -> None:
    logger.info("Starting BSSCI Service Center...")
    logger.info(f"TLS Server will listen on {LISTEN_HOST}:{LISTEN_PORT}")
    logger.info(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"Sensor config file: {SENSOR_CONFIG_FILE}")
    
    mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
    
    logger.info("Initializing TLS Server...")
    server = TLSServer(SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue)
    
    logger.info("Initializing MQTT Client...")
    mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)
    
    logger.info("Starting services...")
    await asyncio.gather(mqtt_server.start(), server.start_server())


if __name__ == "__main__":
    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is not None:
        asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
