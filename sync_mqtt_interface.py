
import json
import logging
import threading
import time
from queue import Queue, Empty
import paho.mqtt.client as mqtt

import bssci_config
from bssci_config import MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, BASE_TOPIC

logger = logging.getLogger(__name__)


class SyncMQTTClient:
    def __init__(self, mqtt_out_queue: Queue, mqtt_in_queue: Queue):
        self.broker_host = MQTT_BROKER
        if BASE_TOPIC[-1] == "/":
            self.base_topic = BASE_TOPIC[:-1]
        else:
            self.base_topic = BASE_TOPIC
        self.config_topic = self.base_topic + "/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue
        self.client = None
        self.connected = False
        self.running = True

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("✅ MQTT CLIENT CONNECTION SUCCESSFUL!")
            logger.info("✅ Authentication completed successfully")
            self.connected = True
            
            # Subscribe to config topic
            logger.info(f"📌 Subscribing to: {self.config_topic}")
            client.subscribe(self.config_topic)
            logger.info("✅ MQTT SUBSCRIPTION SUCCESSFUL")
            
            # Test connection
            test_topic = f"{self.base_topic}/connection_test"
            test_payload = f'{{"status": "connected", "timestamp": "{time.time()}"}}'
            client.publish(test_topic, test_payload)
            logger.info("✅ MQTT ping successful - connection is stable")
            
        else:
            logger.error(f"❌ MQTT CONNECTION FAILED with code {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"🔌 MQTT client disconnected with code {rc}")
        self.connected = False

    def on_message(self, client, userdata, msg):
        try:
            logger.info(f"🎉 MQTT INCOMING MESSAGE RECEIVED!")
            logger.info(f"📍 Topic: {msg.topic}")
            
            # Extract EUI from topic
            topic_parts = msg.topic.split("/")
            base_parts = self.base_topic.split("/")
            eui = topic_parts[len(base_parts) + 1]
            
            config = json.loads(msg.payload.decode())
            config["eui"] = eui
            
            logger.info(f"✅ Configuration received for EUI {eui}")
            self.mqtt_in_queue.put(config)
            logger.info(f"✅ Configuration queued successfully")
            
        except Exception as e:
            logger.error(f"❌ Message processing failed: {e}")

    def start(self):
        """Start synchronous MQTT client"""
        logger.info("=" * 60)
        logger.info("🔄 MQTT CONNECTION ATTEMPT (SYNC)")
        logger.info("=" * 60)
        logger.info(f"📡 Broker: {self.broker_host}:{MQTT_PORT}")
        logger.info(f"👤 Username: {MQTT_USERNAME}")
        logger.info(f"🔐 Password: {'*' * len(MQTT_PASSWORD) if MQTT_PASSWORD else 'NOT SET'}")
        logger.info(f"🎯 Config Topic: {self.config_topic}")
        logger.info(f"🏠 Base Topic: {self.base_topic}")

        # Create MQTT client
        self.client = mqtt.Client()
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
        # Set callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

        retry_delay = 5.0
        max_delay = 60.0

        while self.running:
            try:
                logger.info("🔧 Creating MQTT client connection...")
                self.client.connect(self.broker_host, MQTT_PORT, 60)
                
                # Start the network loop in a separate thread
                self.client.loop_start()
                
                # Start outgoing message handler
                outgoing_thread = threading.Thread(target=self._handle_outgoing, daemon=True)
                outgoing_thread.start()
                
                logger.info("🚀 MQTT handlers started")
                
                # Keep the main thread alive
                while self.running:
                    time.sleep(1)
                    if not self.connected:
                        logger.warning("⚠️ Connection lost, attempting reconnection...")
                        break
                        
                # Reset retry delay on successful connection
                retry_delay = 5.0
                
            except Exception as e:
                logger.error("=" * 60)
                logger.error("❌ MQTT CONNECTION FAILED")
                logger.error("=" * 60)
                logger.error(f"🚨 Error: {e}")
                logger.error(f"🔍 Error Type: {type(e).__name__}")
                logger.error(f"⏰ Next attempt in: {retry_delay} seconds")
                logger.error("=" * 60)
                
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, max_delay)

    def _handle_outgoing(self):
        """Handle outgoing MQTT messages"""
        logger.info("🚀 MQTT OUTGOING HANDLER INITIALIZED")
        logger.info("📤 Ready to publish messages")
        message_count = 0

        while self.running:
            try:
                # Check queue with timeout
                try:
                    msg = self.mqtt_out_queue.get(timeout=1)
                except Empty:
                    continue
                
                if not self.connected:
                    # Put message back if not connected
                    self.mqtt_out_queue.put(msg)
                    time.sleep(1)
                    continue
                
                message_count += 1
                topic = f"{self.base_topic}/{msg['topic']}"

                logger.info(f"🎉 MESSAGE #{message_count} RECEIVED FOR PUBLISHING!")
                logger.info(f"   Topic: {topic}")
                logger.info(f"   Payload Size: {len(msg['payload'])} bytes")

                # Publish message
                print(f"{topic}:\n\t{msg['payload']}")  # Keep the original print
                result = self.client.publish(topic, msg["payload"], qos=0)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("✅ MQTT MESSAGE PUBLISHED SUCCESSFULLY!")
                else:
                    logger.error(f"❌ MQTT PUBLISH ERROR: {result.rc}")

            except Exception as e:
                logger.error(f"❌ MQTT OUTGOING HANDLER ERROR: {e}")
                time.sleep(1)

    def stop(self):
        """Stop the MQTT client"""
        self.running = False
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        logger.info("📨 MQTT client stopped")


if __name__ == "__main__":
    import sys
    from queue import Queue

    def send_mqtt(mqtt_out_queue: Queue) -> None:
        eui = "0123456789abcdef"
        data_dict = {
            "rxTime": int(time.time() * 1000000000),
            "snr": 23.673797607421875,
            "rssi": -72.2540283203125,
            "cnt": 3749,
            "data": [2, 193, 1, 125, 1, 225, 2, 236, 1, 48, 3, 121, 3, 65, 7, 218, 2, 120, 5, 93, 5],
        }
        while True:
            mqtt_out_queue.put(
                {"topic": f"ep/{eui}/ul", "payload": json.dumps(data_dict)}
            )
            time.sleep(5)

    def main() -> None:
        mqtt_out_queue = Queue()
        mqtt_in_queue = Queue()
        mqtt_client = SyncMQTTClient(mqtt_out_queue, mqtt_in_queue)
        
        # Start test sender in background
        sender_thread = threading.Thread(target=send_mqtt, args=(mqtt_out_queue,), daemon=True)
        sender_thread.start()
        
        mqtt_client.start()

    main()
