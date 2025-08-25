import asyncio
import logging
import socket
import bssci_config
from simple_mqtt_interface import SimpleMQTTClient
from TLSServer import TLSServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    logger.info("🚀 Starting Simple BSSCI Service...")

    # Check if port is already in use
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((bssci_config.LISTEN_HOST, bssci_config.LISTEN_PORT))
        logger.info(f"✅ Port {bssci_config.LISTEN_PORT} is available")
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.error(f"❌ Port {bssci_config.LISTEN_PORT} is already in use!")
            logger.error("   Killing existing processes and retrying...")
            import subprocess
            try:
                # Kill any python processes using the port
                subprocess.run(["pkill", "-f", "python"], check=False)
                await asyncio.sleep(2)
                
                # Try again
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((bssci_config.LISTEN_HOST, bssci_config.LISTEN_PORT))
                logger.info(f"✅ Port {bssci_config.LISTEN_PORT} is now available")
            except:
                logger.error(f"❌ Could not free port {bssci_config.LISTEN_PORT}")
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
    mqtt_client = SimpleMQTTClient(
        mqtt_out_queue, 
        mqtt_in_queue,
        bssci_config.MQTT_BROKER,
        bssci_config.MQTT_PORT,
        bssci_config.MQTT_USERNAME,
        bssci_config.MQTT_PASSWORD,
        bssci_config.BASE_TOPIC,
        f"{bssci_config.BASE_TOPIC.rstrip('/')}/ep/+/config"
    )

    logger.info("🔄 Starting both MQTT and TLS services...")
    
    # Start both services concurrently
    try:
        await asyncio.gather(
            mqtt_client.start(),
            tls_server.start_server()
        )
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"💥 Service error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"💥 Main execution error: {e}")
        sys.exit(1)