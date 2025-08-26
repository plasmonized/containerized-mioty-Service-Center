
import logging
import queue
import threading
import time
import signal
import sys

from sync_mqtt_interface import SyncMQTTClient
from sync_tls_server import SyncTLSServer
import bssci_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bssci_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SyncBSSCIService:
    def __init__(self):
        # Create thread-safe queues for communication between TLS server and MQTT
        self.mqtt_out_queue = queue.Queue(maxsize=100)
        self.mqtt_in_queue = queue.Queue(maxsize=100)
        
        # Initialize components
        self.tls_server = SyncTLSServer(
            bssci_config.SENSOR_CONFIG_FILE, 
            self.mqtt_in_queue, 
            self.mqtt_out_queue
        )
        self.mqtt_client = SyncMQTTClient(self.mqtt_out_queue, self.mqtt_in_queue)
        
        # Threading control
        self.stop_event = threading.Event()
        self.threads = []
        
    def start(self):
        """Start all BSSCI service components"""
        logger.info("=" * 80)
        logger.info("🚀 STARTING SYNCHRONOUS BSSCI SERVICE CENTER")
        logger.info("=" * 80)
        logger.info(f"📡 TLS Port: {bssci_config.LISTEN_PORT}")
        logger.info(f"🏠 MQTT Broker: {bssci_config.MQTT_BROKER}:{bssci_config.MQTT_PORT}")
        logger.info(f"📁 Sensor Config: {bssci_config.SENSOR_CONFIG_FILE}")
        
        try:
            # Start MQTT client
            logger.info("🌐 Starting MQTT Client...")
            self.mqtt_client.start()
            
            # Start TLS server in separate thread
            logger.info("🔐 Starting TLS Server...")
            tls_thread = threading.Thread(target=self.tls_server.start, daemon=True)
            tls_thread.start()
            self.threads.append(tls_thread)
            
            # Start configuration processor
            config_thread = threading.Thread(target=self._process_configurations, daemon=True)
            config_thread.start()
            self.threads.append(config_thread)
            
            logger.info("✅ ALL SERVICES STARTED SUCCESSFULLY!")
            logger.info("🎯 BSSCI Service Center is ready for base station connections")
            
            # Keep main thread alive
            while not self.stop_event.is_set():
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Failed to start BSSCI service: {e}")
            self.stop()
            raise
            
    def _process_configurations(self):
        """Process incoming MQTT configuration messages"""
        logger.info("🔧 Configuration processor thread started")
        
        while not self.stop_event.is_set():
            try:
                # Check for incoming configuration updates
                try:
                    config = self.mqtt_in_queue.get(timeout=1.0)
                    logger.info(f"📨 Received configuration update: {config}")
                    
                    # Forward configuration to TLS server
                    if hasattr(self.tls_server, 'update_sensor_config'):
                        self.tls_server.update_sensor_config(config)
                        logger.info("✅ Configuration forwarded to TLS server")
                    
                except queue.Empty:
                    continue
                    
            except Exception as e:
                logger.error(f"❌ Configuration processor error: {e}")
                time.sleep(1)
                
        logger.info("🛑 Configuration processor thread stopped")
        
    def stop(self):
        """Stop all BSSCI service components"""
        logger.info("🛑 STOPPING SYNCHRONOUS BSSCI SERVICE CENTER...")
        
        self.stop_event.set()
        
        # Stop MQTT client
        if self.mqtt_client:
            self.mqtt_client.stop()
            
        # Stop TLS server
        if self.tls_server:
            self.tls_server.stop()
            
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5)
            
        logger.info("✅ SYNCHRONOUS BSSCI SERVICE CENTER STOPPED")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"🛑 Received signal {signum}, shutting down...")
    if 'service' in globals():
        service.stop()
    sys.exit(0)

def main():
    global service
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("🎯 INITIALIZING SYNCHRONOUS BSSCI SERVICE CENTER")
    
    # Create and start the service
    service = SyncBSSCIService()
    
    try:
        service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Service error: {e}")
    finally:
        service.stop()

if __name__ == "__main__":
    main()
