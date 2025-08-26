
import asyncio
import logging
from simple_mqtt_interface import SimpleMQTTClient
from TLSServer import TLSServer
import bssci_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    logger.info("🚀 Starting Simple BSSCI Service...")
    
    # Create message queues
    mqtt_out_queue = asyncio.Queue()
    mqtt_in_queue = asyncio.Queue()
    
    # Create services
    tls_server = TLSServer(
        bssci_config.SENSOR_CONFIG_FILE, 
        mqtt_in_queue, 
        mqtt_out_queue
    )
    mqtt_client = SimpleMQTTClient(mqtt_out_queue, mqtt_in_queue)
    
    # Start both services
    try:
        await asyncio.gather(
            tls_server.start_server(),
            mqtt_client.start()
        )
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"💥 Service error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
