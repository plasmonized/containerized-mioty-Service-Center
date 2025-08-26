
import json
import logging
import threading
import time
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
import queue

from bssci_config import MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, BASE_TOPIC

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/mqtt_detailed.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class SyncMQTTClient:
    def __init__(self, mqtt_out_queue: queue.Queue, mqtt_in_queue: queue.Queue):
        self.broker_host = MQTT_BROKER
        self.broker_port = MQTT_PORT
        self.username = MQTT_USERNAME
        self.password = MQTT_PASSWORD
        
        if BASE_TOPIC.endswith("/"):
            self.base_topic = BASE_TOPIC[:-1]
        else:
            self.base_topic = BASE_TOPIC
            
        self.config_topic = f"{self.base_topic}/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue
        
        # Connection state tracking
        self.connected = False
        self.connection_attempts = 0
        self.last_connection_attempt = 0
        self.reconnect_delay = 5
        self.max_reconnect_delay = 300
        
        # Message counters
        self.messages_sent = 0
        self.messages_received = 0
        self.connection_errors = 0
        
        # Create MQTT client
        self.client = mqtt.Client(client_id=f"bssci_service_{int(time.time())}")
        self.client.username_pw_set(self.username, self.password)
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        self.client.on_log = self._on_log
        
        # Threading control
        self.stop_event = threading.Event()
        self.publisher_thread = None
        self.connection_monitor_thread = None
        
        logger.info("=" * 80)
        logger.info("🚀 SYNC MQTT CLIENT INITIALIZED")
        logger.info("=" * 80)
        logger.info(f"📡 Broker: {self.broker_host}:{self.broker_port}")
        logger.info(f"👤 Username: {self.username}")
        logger.info(f"🔐 Password: {'*' * len(self.password) if self.password else 'NOT SET'}")
        logger.info(f"🏠 Base Topic: {self.base_topic}")
        logger.info(f"🎯 Config Topic: {self.config_topic}")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            self.connection_attempts = 0
            self.reconnect_delay = 5
            logger.info("=" * 80)
            logger.info("✅ MQTT CONNECTION SUCCESSFUL!")
            logger.info("=" * 80)
            logger.info(f"🔗 Connected to {self.broker_host}:{self.broker_port}")
            logger.info(f"🏷️  Client ID: {self.client._client_id.decode()}")
            logger.info(f"🔄 Clean Session: {flags.get('session present', False)}")
            
            # Subscribe to config topic
            result, mid = client.subscribe(self.config_topic, qos=1)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"📥 SUBSCRIBED TO: {self.config_topic} (Message ID: {mid})")
            else:
                logger.error(f"❌ SUBSCRIPTION FAILED: {result}")
                
            # Send connection test
            self._send_connection_test()
            
        else:
            self.connected = False
            self.connection_errors += 1
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorised"
            }
            error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
            logger.error("=" * 80)
            logger.error("❌ MQTT CONNECTION FAILED!")
            logger.error("=" * 80)
            logger.error(f"🚨 Error Code: {rc}")
            logger.error(f"🚨 Error Message: {error_msg}")
            logger.error(f"📊 Total Connection Errors: {self.connection_errors}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning("=" * 80)
        logger.warning("⚠️  MQTT DISCONNECTED!")
        logger.warning("=" * 80)
        logger.warning(f"🔌 Disconnect Code: {rc}")
        logger.warning(f"📊 Messages Sent: {self.messages_sent}")
        logger.warning(f"📊 Messages Received: {self.messages_received}")
        
        if rc != 0:
            logger.error("🚨 Unexpected disconnection! Will attempt to reconnect...")

    def _on_message(self, client, userdata, msg):
        self.messages_received += 1
        logger.info("=" * 60)
        logger.info(f"📨 MQTT MESSAGE RECEIVED #{self.messages_received}")
        logger.info("=" * 60)
        logger.info(f"📍 Topic: {msg.topic}")
        logger.info(f"📏 Payload Size: {len(msg.payload)} bytes")
        logger.info(f"🔢 QoS: {msg.qos}")
        logger.info(f"🔄 Retain: {msg.retain}")
        
        try:
            # Parse message like the async version
            topic_parts = msg.topic.split("/")
            base_parts = self.base_topic.split("/")
            
            if len(topic_parts) > len(base_parts) + 1:
                eui = topic_parts[len(base_parts) + 1]
                logger.info(f"🔑 Extracted EUI: {eui}")
                
                payload_str = msg.payload.decode('utf-8')
                logger.info(f"📄 Payload: {payload_str}")
                
                config = json.loads(payload_str)
                config["eui"] = eui
                
                self.mqtt_in_queue.put(config)
                logger.info("✅ Configuration queued successfully")
                logger.info(f"📋 Config: {json.dumps(config, indent=2)}")
            else:
                logger.warning(f"⚠️  Invalid topic format: {msg.topic}")
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            logger.error(f"📄 Raw payload: {msg.payload}")
        except Exception as e:
            logger.error(f"❌ Message processing failed: {e}")
            logger.error(f"🔍 Error type: {type(e).__name__}")

    def _on_publish(self, client, userdata, mid):
        logger.info(f"✅ MESSAGE PUBLISHED (Message ID: {mid})")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        logger.info(f"✅ SUBSCRIPTION CONFIRMED (Message ID: {mid}, QoS: {granted_qos})")

    def _on_log(self, client, userdata, level, buf):
        # Map paho-mqtt log levels to Python logging levels
        level_map = {
            mqtt.MQTT_LOG_DEBUG: logging.DEBUG,
            mqtt.MQTT_LOG_INFO: logging.INFO,
            mqtt.MQTT_LOG_NOTICE: logging.INFO,
            mqtt.MQTT_LOG_WARNING: logging.WARNING,
            mqtt.MQTT_LOG_ERR: logging.ERROR
        }
        python_level = level_map.get(level, logging.INFO)
        logger.log(python_level, f"🔧 MQTT Client: {buf}")

    def _send_connection_test(self):
        """Send a test message to verify connection"""
        try:
            test_topic = f"{self.base_topic}/connection_test"
            test_payload = {
                "status": "connected",
                "timestamp": time.time(),
                "client_id": self.client._client_id.decode()
            }
            
            result, mid = self.client.publish(
                test_topic, 
                json.dumps(test_payload), 
                qos=1
            )
            
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"🏓 CONNECTION TEST SENT (Message ID: {mid})")
            else:
                logger.error(f"❌ CONNECTION TEST FAILED: {result}")
                
        except Exception as e:
            logger.error(f"❌ Connection test error: {e}")

    def _publisher_worker(self):
        """Handle outgoing messages in a separate thread"""
        logger.info("🚀 MQTT PUBLISHER THREAD STARTED")
        
        while not self.stop_event.is_set():
            try:
                # Wait for message with timeout
                try:
                    msg = self.mqtt_out_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                if not self.connected:
                    logger.warning("⚠️  Not connected - requeueing message")
                    self.mqtt_out_queue.put(msg)
                    time.sleep(1)
                    continue
                
                self.messages_sent += 1
                topic = f"{self.base_topic}/{msg['topic']}"
                payload = msg['payload']
                
                logger.info("=" * 60)
                logger.info(f"📤 PUBLISHING MESSAGE #{self.messages_sent}")
                logger.info("=" * 60)
                logger.info(f"📍 Topic: {topic}")
                logger.info(f"📏 Payload Size: {len(payload)} bytes")
                logger.info(f"📄 Payload Preview: {payload[:200]}{'...' if len(payload) > 200 else ''}")
                
                # Print to console like the original
                print(f"{topic}:\n\t{payload}")
                
                result, mid = self.client.publish(topic, payload, qos=1)
                
                if result == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"✅ PUBLISH QUEUED (Message ID: {mid})")
                else:
                    logger.error(f"❌ PUBLISH FAILED: {result}")
                    # Put message back in queue
                    self.mqtt_out_queue.put(msg)
                    
            except Exception as e:
                logger.error(f"❌ Publisher thread error: {e}")
                logger.error(f"🔍 Error type: {type(e).__name__}")
                time.sleep(1)
                
        logger.info("🛑 MQTT PUBLISHER THREAD STOPPED")

    def _connection_monitor(self):
        """Monitor connection and handle reconnection"""
        logger.info("👁️  CONNECTION MONITOR THREAD STARTED")
        
        while not self.stop_event.is_set():
            try:
                if not self.connected:
                    current_time = time.time()
                    
                    if current_time - self.last_connection_attempt >= self.reconnect_delay:
                        self.connection_attempts += 1
                        self.last_connection_attempt = current_time
                        
                        logger.info("=" * 80)
                        logger.info(f"🔄 RECONNECTION ATTEMPT #{self.connection_attempts}")
                        logger.info("=" * 80)
                        logger.info(f"⏰ Delay: {self.reconnect_delay} seconds")
                        
                        try:
                            self.client.reconnect()
                        except Exception as e:
                            logger.error(f"❌ Reconnection failed: {e}")
                            # Increase delay exponentially with max limit
                            self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)
                            logger.error(f"⏰ Next attempt in: {self.reconnect_delay} seconds")
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"❌ Connection monitor error: {e}")
                time.sleep(5)
                
        logger.info("🛑 CONNECTION MONITOR THREAD STOPPED")

    def start(self):
        """Start the MQTT client and all worker threads"""
        logger.info("=" * 80)
        logger.info("🚀 STARTING SYNC MQTT CLIENT")
        logger.info("=" * 80)
        
        try:
            # Connect to broker
            logger.info(f"🔗 Connecting to {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            
            # Start network loop in background
            self.client.loop_start()
            
            # Start worker threads
            self.publisher_thread = threading.Thread(target=self._publisher_worker, daemon=True)
            self.connection_monitor_thread = threading.Thread(target=self._connection_monitor, daemon=True)
            
            self.publisher_thread.start()
            self.connection_monitor_thread.start()
            
            logger.info("✅ ALL MQTT THREADS STARTED SUCCESSFULLY")
            
        except Exception as e:
            logger.error(f"❌ Failed to start MQTT client: {e}")
            raise

    def stop(self):
        """Stop the MQTT client and all threads"""
        logger.info("🛑 STOPPING SYNC MQTT CLIENT...")
        
        self.stop_event.set()
        
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            
        if self.publisher_thread:
            self.publisher_thread.join(timeout=5)
            
        if self.connection_monitor_thread:
            self.connection_monitor_thread.join(timeout=5)
            
        logger.info("✅ SYNC MQTT CLIENT STOPPED")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "connected": self.connected,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "connection_attempts": self.connection_attempts,
            "connection_errors": self.connection_errors,
            "broker": f"{self.broker_host}:{self.broker_port}",
            "base_topic": self.base_topic
        }


if __name__ == "__main__":
    # Test the MQTT client
    import queue
    
    mqtt_out_queue = queue.Queue()
    mqtt_in_queue = queue.Queue()
    
    client = SyncMQTTClient(mqtt_out_queue, mqtt_in_queue)
    
    try:
        client.start()
        
        # Send test message
        time.sleep(2)
        test_message = {
            "topic": "test/message",
            "payload": json.dumps({"test": "data", "timestamp": time.time()})
        }
        mqtt_out_queue.put(test_message)
        
        # Keep running
        while True:
            time.sleep(1)
            stats = client.get_stats()
            if stats["messages_sent"] > 0 or stats["messages_received"] > 0:
                logger.info(f"📊 STATS: {json.dumps(stats, indent=2)}")
                
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
        client.stop()
