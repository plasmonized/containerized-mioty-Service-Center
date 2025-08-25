import asyncio
import json
import logging
from datetime import datetime

from aiomqtt import Client

from bssci_config import BASE_TOPIC, MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(
        self,
        mqtt_out_queue: asyncio.Queue[dict[str, str]],
        mqtt_in_queue: asyncio.Queue[dict[str, str]],
    ):
        self.broker_host = MQTT_BROKER
        if BASE_TOPIC[-1] == "/":
            self.base_topic = BASE_TOPIC[:-1]
        else:
            self.base_topic = BASE_TOPIC
        self.config_topic = self.base_topic + "/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

    async def start(self) -> None:
        logger.info(f"Initializing MQTT client connection...")
        logger.info(f"Broker: {self.broker_host}:{MQTT_PORT}")
        logger.info(f"Username: {MQTT_USERNAME}")
        logger.info(f"Password: {'*' * len(MQTT_PASSWORD) if MQTT_PASSWORD else 'NOT SET'}")
        logger.info(f"Base topic: {self.base_topic}")
        logger.info(f"Config subscription topic: {self.config_topic}")
        
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connection attempt {attempt + 1}/{max_retries} to MQTT broker...")
                logger.info(f"Connecting to {self.broker_host}:{MQTT_PORT}")
                
                async with Client(
                    hostname=self.broker_host, 
                    port=MQTT_PORT, 
                    username=MQTT_USERNAME, 
                    password=MQTT_PASSWORD,
                    keepalive=60,
                    timeout=10
                ) as client:
                    logger.info("✓ MQTT client connected successfully")
                    logger.info("✓ Authentication successful")
                    logger.info("Starting MQTT message handlers...")
                    await asyncio.gather(
                        self._handle_incoming(client), self._handle_outgoing(client)
                    )
                    # If we reach here, connection was stable
                    break
                    
            except Exception as e:
                logger.error(f"✗ MQTT connection attempt {attempt + 1} failed: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Connection details - Broker: {self.broker_host}:{MQTT_PORT}")
                logger.error(f"Username: {MQTT_USERNAME}")
                
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"❌ All MQTT connection attempts failed after {max_retries} tries")
                    logger.error("Please check:")
                    logger.error("  1. MQTT broker is running and accessible")
                    logger.error("  2. Network connectivity to broker")
                    logger.error("  3. Username/password credentials")
                    logger.error("  4. Broker port and hostname")
                    raise

    async def _handle_incoming(self, client: Client) -> None:
        logger.info(f"Subscribing to MQTT config topic: {self.config_topic}")
        await client.subscribe(self.config_topic)
        logger.info(f"✓ Successfully subscribed to MQTT topic: {self.config_topic}")
        logger.info("MQTT incoming message handler is now listening for configuration updates...")
        
        async for message in client.messages:
            topic_parts = str(message.topic).split("/")
            eui = topic_parts[len(self.base_topic.split("/")) + 1]
            
            logger.info(f"📥 MQTT message received on topic: {message.topic}")
            logger.debug(f"Raw payload: {message.payload}")
            
            try:
                payload = message.payload
                if isinstance(payload, (bytes, bytearray)):
                    config = json.loads(payload.decode())
                elif isinstance(payload, str):
                    config = json.loads(payload)
                else:
                    raise TypeError(f"Unsupported payload type: {type(payload)}")
                
                config["eui"] = eui
                logger.info(f"📝 Parsed configuration for endpoint {eui}:")
                logger.info(f"   - EUI: {config.get('eui', 'N/A')}")
                logger.info(f"   - Network Key: {config.get('nwKey', 'N/A')[:8]}...")
                logger.info(f"   - Short Address: {config.get('shortAddr', 'N/A')}")
                logger.info(f"   - Bidirectional: {config.get('bidi', 'N/A')}")
                
                await self.mqtt_in_queue.put(config)
                logger.info(f"✓ Configuration queued for processing")
            except Exception as e:
                logger.error(f"✗ Failed to process MQTT message from topic {message.topic}: {e}")
                logger.error(f"Raw payload: {message.payload}")

    async def _handle_outgoing(self, client: Client) -> None:
        logger.info("📤 MQTT outgoing message handler started and ready to publish messages")
        message_count = 0
        
        while True:
            try:
                msg = await self.mqtt_out_queue.get()
                message_count += 1
                topic = f"{self.base_topic}/{msg['topic']}"
                
                # Determine message type for better logging
                msg_type = "Unknown"
                if "/bs/" in msg['topic']:
                    msg_type = "Base Station Status"
                elif "/ep/" in msg['topic'] and "/ul" in msg['topic']:
                    msg_type = "Sensor Uplink Data"
                elif "/ep/" in msg['topic'] and "/config" in msg['topic']:
                    msg_type = "Sensor Configuration"
                
                logger.info(f"📤 MQTT OUTGOING MESSAGE #{message_count}")
                logger.info(f"   ===================================")
                logger.info(f"   Message Type: {msg_type}")
                logger.info(f"   Base Topic: {self.base_topic}")
                logger.info(f"   Raw Topic: {msg['topic']}")
                logger.info(f"   Full Topic: {topic}")
                logger.info(f"   Payload Size: {len(msg['payload'])} bytes")
                logger.info(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                
                # Log payload preview for status messages
                if msg_type == "Base Station Status":
                    try:
                        payload_data = json.loads(msg['payload'])
                        logger.info(f"   Status Preview: Code={payload_data.get('code', 'N/A')}, CPU={payload_data.get('cpuLoad', 0)*100:.1f}%, Mem={payload_data.get('memLoad', 0)*100:.1f}%")
                    except:
                        logger.info(f"   Payload Preview: {msg['payload'][:100]}...")
                elif msg_type == "Sensor Uplink Data":
                    try:
                        payload_data = json.loads(msg['payload'])
                        logger.info(f"   Sensor Preview: EUI from topic, BS={payload_data.get('bs_eui', 'N/A')}, Count={payload_data.get('cnt', 'N/A')}")
                    except:
                        logger.info(f"   Payload Preview: {msg['payload'][:100]}...")
                else:
                    logger.debug(f"   Payload: {msg['payload']}")
                
                logger.info(f"   📡 Attempting MQTT publish to broker {self.broker_host}:{MQTT_PORT}...")
                
                # Check if client is still connected
                if not hasattr(client, '_client') or not client._client.is_connected:
                    raise ConnectionError("MQTT client is not connected")
                
                result = await client.publish(topic, msg["payload"], qos=1)
                logger.info(f"   📡 Publish result: {result}")
                
                logger.info(f"✅ MQTT MESSAGE #{message_count} PUBLISHED SUCCESSFULLY")
                logger.info(f"   Topic: {topic}")
                logger.info(f"   Broker: {self.broker_host}:{MQTT_PORT}")
                logger.info(f"   QoS: 1")
                logger.info(f"   ===================================")
                
            except Exception as e:
                logger.error(f"❌ MQTT PUBLISH ERROR for message #{message_count}")
                logger.error(f"   Error Type: {type(e).__name__}")
                logger.error(f"   Error Message: {str(e)}")
                logger.error(f"   Broker: {self.broker_host}:{MQTT_PORT}")
                if 'topic' in locals():
                    logger.error(f"   Failed Topic: {topic}")
                if 'msg' in locals():
                    logger.error(f"   Failed Payload: {msg.get('payload', 'N/A')}")
                logger.error(f"   ===================================")
                
                # Check if this is a connection error
                if isinstance(e, (ConnectionError, OSError)):
                    logger.error("   Connection lost - this will trigger reconnection")
                    raise  # Re-raise to trigger reconnection
                
                # For other errors, continue processing other messages


if __name__ == "__main__":
    import sys

    async def send_mqtt(mqtt_out_queue: asyncio.Queue[dict[str, str]]) -> None:
        eui = "0123456789abcdef"
        data_dict = {
            "rxTime": 1751819907443066821,
            "snr": 23.673797607421875,
            "rssi": -72.2540283203125,
            "cnt": 3749,
            "data": [
                2,
                193,
                1,
                125,
                1,
                225,
                2,
                236,
                1,
                48,
                3,
                121,
                3,
                65,
                7,
                218,
                2,
                120,
                5,
                93,
                5,
            ],
        }
        while True:
            await mqtt_out_queue.put(
                {"topic": f"ep/{eui}/ul", "payload": json.dumps(data_dict)}
            )
            await asyncio.sleep(5)

    async def main() -> None:
        mqtt_out_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        mqtt_in_queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()
        mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)
        await asyncio.gather(mqtt_server.start(), send_mqtt(mqtt_out_queue))

    if sys.platform.startswith("win"):
        policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_cls is not None:
            asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
    while 1:
        pass
