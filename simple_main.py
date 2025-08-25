import asyncio
import logging
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bssci.config import config as bssci_config
from bssci.interfaces.simple_mqtt_interface import SimpleMQTTClient
from bssci.interfaces.tls_interface import TLSServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    logger.info("🚀 Starting Simple BSSCI Service...")

    # First, check if port is already in use
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('0.0.0.0', bssci_config.LISTEN_PORT))
        logger.info(f"✅ Port {bssci_config.LISTEN_PORT} is available")
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.error(f"❌ Port {bssci_config.LISTEN_PORT} is already in use!")
            logger.error("   Another BSSCI service instance may be running.")
            logger.error("   Please stop the other instance first.")
            return
        else:
            raise

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

    # Start MQTT first (it's more likely to succeed)
    logger.info("🔄 Starting MQTT client first...")
    mqtt_task = asyncio.create_task(mqtt_client.start())

    # Give MQTT a moment to connect
    await asyncio.sleep(2)

    logger.info("🔄 Starting TLS server...")
    tls_task = asyncio.create_task(tls_server.start_server())

    # Wait for both services
    try:
        await asyncio.gather(tls_task, mqtt_task)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        tls_task.cancel()
        mqtt_task.cancel()
        try:
            await asyncio.gather(tls_task, mqtt_task, return_exceptions=True)
        except:
            pass
    except Exception as e:
        logger.error(f"💥 Service error: {e}")
        # If one fails, cancel the other
        tls_task.cancel()
        mqtt_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"💥 Main execution error: {e}")
        sys.exit(1)