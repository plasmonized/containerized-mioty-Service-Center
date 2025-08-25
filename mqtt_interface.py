import asyncio
import json
import logging

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
        logger.info(f"Base topic: {self.base_topic}")
        logger.info(f"Config subscription topic: {self.config_topic}")
        
        try:
            logger.info("Establishing connection to MQTT broker...")
            async with Client(self.broker_host, port=MQTT_PORT, username=MQTT_USERNAME, password=MQTT_PASSWORD) as client:
                logger.info("✓ MQTT client connected successfully")
                logger.info("Starting MQTT message handlers...")
                await asyncio.gather(
                    self._handle_incoming(client), self._handle_outgoing(client)
                )
        except Exception as e:
            logger.error(f"✗ MQTT connection failed: {e}")
            logger.error(f"Connection details - Broker: {self.broker_host}:{MQTT_PORT}, Username: {MQTT_USERNAME}")
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
            
            logger.info(f"📤 Publishing MQTT message #{message_count} ({msg_type})")
            logger.info(f"   Topic: {topic}")
            logger.debug(f"   Payload: {msg['payload']}")
            
            try:
                await client.publish(topic, msg["payload"])
                logger.info(f"✓ Message #{message_count} published successfully")
            except Exception as e:
                logger.error(f"✗ Failed to publish message #{message_count}: {e}")
                logger.error(f"   Topic: {topic}")
                logger.error(f"   Payload: {msg['payload']}")


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
