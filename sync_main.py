
import logging
import threading
import time
from queue import Queue

import bssci_config
from sync_mqtt_interface import SyncMQTTClient
from sync_tls_server import SyncTLSServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Synchronous BSSCI Service Center...")
    logger.info(f"Config: TLS Port {bssci_config.LISTEN_PORT}, MQTT Broker {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")

    # Create synchronous queues
    mqtt_out_queue = Queue()
    mqtt_in_queue = Queue()

    # Create server instances
    tls_server = SyncTLSServer(bssci_config.SENSOR_CONFIG_FILE, mqtt_out_queue, mqtt_in_queue)
    mqtt_client = SyncMQTTClient(mqtt_out_queue, mqtt_in_queue)

    # Start TLS server in separate thread
    tls_thread = threading.Thread(target=tls_server.start_server, daemon=True)
    tls_thread.start()
    logger.info("✓ TLS Server started")

    # Start MQTT client in separate thread  
    mqtt_thread = threading.Thread(target=mqtt_client.start, daemon=True)
    mqtt_thread.start()
    logger.info("✓ MQTT Client started")

    logger.info("✓ Synchronous BSSCI Service Center running")

    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        tls_server.running = False
        mqtt_client.stop()

if __name__ == "__main__":
    main()
