
import asyncio
import json
import logging
from aiomqtt import Client, MqttError
import paho.mqtt.client

import bssci_config
from bssci_config import MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, BASE_TOPIC

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
        """Start MQTT client with retry logic"""
        retry_delay = 5.0
        max_delay = 60.0

        while True:
            try:
                logger.info("=" * 60)
                logger.info("🔄 MQTT CONNECTION ATTEMPT")
                logger.info("=" * 60)
                logger.info(f"📡 Broker: {self.broker_host}:{MQTT_PORT}")
                logger.info(f"👤 Username: {MQTT_USERNAME}")
                logger.info(f"🔐 Password: {'*' * len(MQTT_PASSWORD) if MQTT_PASSWORD else 'NOT SET'}")
                logger.info(f"🎯 Config Topic: {self.config_topic}")
                logger.info(f"🏠 Base Topic: {self.base_topic}")

                # Simple client creation like the working version, but with auth
                logger.info("🔧 Creating MQTT client...")
                
                async with Client(
                    hostname=self.broker_host, 
                    port=MQTT_PORT, 
                    username=MQTT_USERNAME, 
                    password=MQTT_PASSWORD
                ) as client:
                    logger.info("✅ MQTT CLIENT CONNECTION SUCCESSFUL!")
                    logger.info("✅ Authentication completed successfully")
                    logger.info("🚀 Starting MQTT message handlers...")

                    # Reset retry delay on successful connection
                    retry_delay = 5.0

                    # Test connection
                    logger.info("🏓 Testing MQTT connection with ping...")
                    test_topic = f"{self.base_topic}/connection_test"
                    test_payload = f'{{"status": "connected", "timestamp": "{asyncio.get_event_loop().time()}"}}'
                    await client.publish(test_topic, test_payload)
                    logger.info("✅ MQTT ping successful - connection is stable")

                    # Run both handlers like the working version
                    logger.info("🎭 Starting concurrent MQTT handlers...")
                    logger.info("📊 MQTT STARTUP DIAGNOSTICS:")
                    logger.info(f"   Outgoing queue size: {self.mqtt_out_queue.qsize()}")
                    logger.info(f"   Incoming queue size: {self.mqtt_in_queue.qsize()}")
                    logger.info("✅ Starting handler tasks...")
                    
                    await asyncio.gather(
                        self._handle_incoming(client), 
                        self._handle_outgoing(client),
                        return_exceptions=True
                    )

            except Exception as e:
                logger.error("=" * 60)
                logger.error("❌ MQTT CONNECTION FAILED")
                logger.error("=" * 60)
                logger.error(f"🚨 Error: {e}")
                logger.error(f"🔍 Error Type: {type(e).__name__}")
                
                logger.error("⏰ RETRY INFORMATION:")
                logger.error(f"   Next attempt in: {retry_delay} seconds")
                logger.error("=" * 60)
                
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, max_delay)

    async def _handle_incoming(self, client: Client) -> None:
        logger.info("🔔 MQTT INCOMING HANDLER STARTING")
        logger.info("=" * 50)
        logger.info(f"📌 Subscription Topic: {self.config_topic}")
        
        try:
            await client.subscribe(self.config_topic)
            logger.info("✅ MQTT SUBSCRIPTION SUCCESSFUL")
            logger.info("👂 MQTT incoming message handler is now ACTIVE and listening...")
        except Exception as sub_error:
            logger.error(f"❌ MQTT subscription failed: {sub_error}")
            raise

        message_count = 0
        try:
            async for message in client.messages:
                message_count += 1
                logger.info(f"🎉 MQTT INCOMING MESSAGE #{message_count} RECEIVED!")
                logger.info(f"📍 Topic: {message.topic}")

                try:
                    # Extract EUI like the working version
                    eui = str(message.topic).split("/")[len(self.base_topic.split("/"))+1]
                    config = json.loads(message.payload.decode())
                    config["eui"] = eui
                    logger.info(f"✅ Configuration received for EUI {eui}")
                    await self.mqtt_in_queue.put(config)
                    logger.info(f"✅ Configuration queued successfully")

                except Exception as e:
                    logger.error(f"❌ Message processing failed: {e}")
                    
        except Exception as handler_error:
            logger.error(f"❌ MQTT INCOMING HANDLER FAILED: {handler_error}")
            raise

    async def _handle_outgoing(self, client: Client) -> None:
        logger.info("🚀 MQTT OUTGOING HANDLER INITIALIZED")
        logger.info("📤 Ready to publish messages")
        message_count = 0

        try:
            while True:
                try:
                    logger.info(f"⏳ WAITING FOR MQTT MESSAGE in queue (size: {self.mqtt_out_queue.qsize()})")
                    msg = await self.mqtt_out_queue.get()
                    message_count += 1
                    topic = f"{self.base_topic}/{msg['topic']}"

                    logger.info(f"🎉 MESSAGE #{message_count} RECEIVED FOR PUBLISHING!")
                    logger.info(f"   Topic: {topic}")
                    logger.info(f"   Payload Size: {len(msg['payload'])} bytes")

                    # Simple publish like the working version
                    print(f"{topic}:\n\t{msg['payload']}")  # Keep the original print
                    await client.publish(topic, msg["payload"])

                    logger.info("✅ MQTT MESSAGE PUBLISHED SUCCESSFULLY!")

                except Exception as e:
                    logger.error(f"❌ MQTT PUBLISH ERROR: {e}")
                    # For connection errors, re-raise to trigger reconnection
                    if isinstance(e, (ConnectionError, OSError)) or "connection" in str(e).lower():
                        logger.error("   CONNECTION ERROR - TRIGGERING RECONNECTION")
                        await self.mqtt_out_queue.put(msg)  # Put message back
                        raise
                    # For other errors, continue
                    logger.error("   NON-CONNECTION ERROR - Continuing...")

        except Exception as e:
            logger.error(f"❌ MQTT OUTGOING HANDLER FATAL ERROR: {e}")
            raise


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
