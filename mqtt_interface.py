import asyncio
import json
import logging
from typing import Dict, Any
from aiomqtt import Client

from bssci_config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, BASE_TOPIC
)

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(
        self,
        mqtt_out_queue: asyncio.Queue[dict[str, str]],
        mqtt_in_queue: asyncio.Queue[dict[str, str]],
    ):
        self.broker_host = MQTT_BROKER
        if BASE_TOPIC.endswith("/"):
            self.base_topic = BASE_TOPIC[:-1]
        else:
            self.base_topic = BASE_TOPIC
        self.config_topic = self.base_topic + "/ep/+/config"
        self.command_topic = self.base_topic + "/ep/+/cmd"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

        # Add queue logging
        logger.info("🔍 MQTT Client Queue Assignment:")
        logger.info(f"   mqtt_out_queue ID: {id(self.mqtt_out_queue)}")
        logger.info(f"   mqtt_in_queue ID: {id(self.mqtt_in_queue)}")

    def log_queue_info(self) -> None:
        """Log queue information for debugging"""
        logger.info("🔍 MQTT Client Queue Information:")
        logger.info(
            f"   mqtt_out_queue ID: {id(self.mqtt_out_queue)}, "
            f"size: {self.mqtt_out_queue.qsize()}"
        )
        logger.info(
            f"   mqtt_in_queue ID: {id(self.mqtt_in_queue)}, "
            f"size: {self.mqtt_in_queue.qsize()}"
        )

    async def start(self) -> None:
        """Start MQTT client with simple connection pattern"""
        retry_delay = 5.0
        max_delay = 60.0

        while True:
            try:
                logger.info("=" * 60)
                logger.info("🔄 MQTT CONNECTION ATTEMPT")
                logger.info("=" * 60)
                logger.info(f"📡 Broker: {self.broker_host}:{MQTT_PORT}")
                logger.info(f"👤 Username: {MQTT_USERNAME}")
                logger.info(
                    f"🔐 Password: "
                    f"{'*' * len(MQTT_PASSWORD) if MQTT_PASSWORD else 'NOT SET'}"
                )
                logger.info(f"🎯 Config Topic: {self.config_topic}")
                logger.info(f"🏠 Base Topic: {self.base_topic}")

                # Use the working simple pattern with authentication
                logger.info("🔧 Creating MQTT client...")

                async with Client(
                    hostname=self.broker_host,
                    port=MQTT_PORT,
                    username=MQTT_USERNAME,
                    password=MQTT_PASSWORD,
                    keepalive=60,  # Send keepalive every 60 seconds
                    timeout=30     # Connection timeout after 30 seconds
                ) as client:
                    logger.info("✅ MQTT CLIENT CONNECTION SUCCESSFUL!")
                    logger.info("✅ Authentication completed successfully")

                    # Reset retry delay on successful connection
                    retry_delay = 5.0

                    # Test connection
                    logger.info("🏓 Testing MQTT connection with ping...")
                    test_topic = f"{self.base_topic}/connection_test"
                    test_payload = f'{{"status": "connected", "timestamp": "{asyncio.get_event_loop().time()}"}}'
                    await client.publish(test_topic, test_payload)
                    logger.info("✅ MQTT ping successful - connection is stable")

                    # Run both handlers with health monitoring
                    logger.info("🎭 Starting concurrent MQTT handlers with health monitoring...")
                    self.log_queue_info()

                    await asyncio.gather(
                        self._handle_incoming(client),
                        self._handle_outgoing(client),
                        self._connection_health_monitor(client),
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
            # Subscribe to topics with retained messages handling
            topics = [
                (f"{self.base_topic}ep/+/dl", 0),  # Downlink messages
                (f"{self.base_topic}ep/+/cmd", 0),  # Command messages
                (f"{self.base_topic}config/+", 0),  # Configuration messages
                ("EP/+/cmd/", 0),  # Remote EP command messages from application center
            ]
            await client.subscribe(topics)
            logger.info("✅ MQTT SUBSCRIPTION SUCCESSFUL")
            logger.info(f"👂 MQTT listening on config topic: {self.config_topic}")
            logger.info(f"👂 MQTT listening on command topic: {self.command_topic}")
            logger.info(f"👂 MQTT listening on EP command topic: EP/+/cmd/")
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
                    topic_parts = str(message.topic).split("/")
                    base_parts = self.base_topic.split("/")

                    if len(topic_parts) > len(base_parts) + 1:
                        eui = topic_parts[len(base_parts) + 1]
                        logger.info(f"🔑 Extracted EUI: {eui}")

                        payload_str = message.payload.decode('utf-8')
                        logger.info(f"📄 Payload: {payload_str}")

                        payload_dict = json.loads(payload_str)

                        # Check if this is a command message
                        if "/cmd/" in str(message.topic):
                            await self.handle_command_message(str(message.topic), payload_dict)
                            return

                        # Check if this is an EP command message (/EP/+/cmd/)
                        if str(message.topic).startswith("EP/") and "/cmd/" in str(message.topic):
                            await self.handle_ep_command_message(str(message.topic), payload_dict)
                            return

                        # This is a config message
                        config = payload_dict
                        config["eui"] = eui
                        config["message_type"] = "config"

                        logger.info(f"✅ Configuration received for EUI {eui}")
                        logger.info(f"   Queue size before put: {self.mqtt_in_queue.qsize()}")
                        await self.mqtt_in_queue.put(config)
                        logger.info(f"✅ Configuration queued successfully")
                        logger.info(f"   Queue size after put: {self.mqtt_in_queue.qsize()}")
                        logger.info(f"📋 Config: {json.dumps(config, indent=2)}")

                    else:
                        logger.warning(f"⚠️  Invalid topic format: {message.topic}")

                except Exception as e:
                    logger.error(f"❌ Message processing failed: {e}")

        except Exception as handler_error:
            logger.error(f"❌ MQTT INCOMING HANDLER FAILED: {handler_error}")
            raise

    async def _connection_health_monitor(self, client: Client) -> None:
        """Monitor connection health and force reconnection if needed"""
        logger.info("💓 MQTT CONNECTION HEALTH MONITOR STARTED")

        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                # Send a test message to verify connection
                test_topic = f"{self.base_topic}/health_check"
                test_payload = f'{{"timestamp": "{asyncio.get_event_loop().time()}", "status": "alive"}}'

                logger.debug("💓 Performing MQTT health check...")
                await client.publish(test_topic, test_payload)
                logger.debug("✅ MQTT health check successful")

            except Exception as e:
                logger.error(f"💀 MQTT HEALTH CHECK FAILED: {e}")
                logger.error("🔄 Triggering connection reset...")
                raise  # This will cause reconnection

    async def _handle_outgoing(self, client: Client) -> None:
        logger.info("🚀 MQTT OUTGOING HANDLER INITIALIZED")
        logger.info("📤 Ready to publish messages")
        message_count = 0

        try:
            while True:
                try:
                    logger.debug(f"⏳ WAITING FOR MQTT MESSAGE in queue (size: {self.mqtt_out_queue.qsize()})")
                    msg = await self.mqtt_out_queue.get()
                    message_count += 1
                    topic = f"{self.base_topic}/{msg['topic']}"

                    logger.info(f"🎉 MESSAGE #{message_count} RECEIVED FOR PUBLISHING!")
                    logger.info(f"   Topic: {topic}")
                    logger.info(f"   Payload Size: {len(msg['payload'])} bytes")

                    # Use the working simple publish pattern
                    print(f"{topic}:\n\t{msg['payload']}")  # Keep the original print
                    await client.publish(topic, msg["payload"])

                    logger.info("✅ MQTT MESSAGE PUBLISHED SUCCESSFULLY!")

                except Exception as e:
                    logger.error(f"❌ MQTT PUBLISH ERROR: {e}")
                    # For connection errors, re-raise to trigger reconnection
                    if isinstance(e, (ConnectionError, OSError)) or "connection" in str(e).lower() or "not currently connected" in str(e).lower():
                        logger.error("   CONNECTION ERROR - TRIGGERING RECONNECTION")
                        await self.mqtt_out_queue.put(msg)  # Put message back
                        raise
                    # For other errors, continue
                    logger.error("   NON-CONNECTION ERROR - Continuing...")

        except Exception as e:
            logger.error(f"❌ MQTT OUTGOING HANDLER FATAL ERROR: {e}")
            raise

    async def handle_command_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle command messages from MQTT"""
        logger.info(f"🎯 Processing command message from topic: {topic}")

        try:
            # Extract EUI from topic
            topic_parts = topic.split('/')
            if len(topic_parts) >= 4 and topic_parts[0] == "ep":
                eui = topic_parts[1]
                command = payload.get('command', '').lower()

                logger.info(f"Command for sensor {eui}: {command}")

                # Create command message for TLS server processing
                command_msg = {
                    'message_type': 'command',
                    'eui': eui,
                    'action': command,
                    'timestamp': payload.get('timestamp', asyncio.get_event_loop().time())
                }

                # Add to in_queue for TLS server processing
                await self.mqtt_in_queue.put(command_msg)
                logger.info(f"✅ Command queued for TLS server processing")

        except Exception as e:
            logger.error(f"❌ Error handling command message: {e}")
            logger.error(f"   Topic: {topic}")
            logger.error(f"   Payload: {payload}")

    async def handle_ep_command_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """Handle EP command messages from MQTT (/EP/+/cmd/)"""
        logger.info(f"🎯 Processing EP command message from topic: {topic}")

        try:
            # Extract EUI from topic pattern /EP/{eui}/cmd/
            topic_parts = topic.split('/')
            if len(topic_parts) >= 4 and topic_parts[0] == "EP" and topic_parts[2] == "cmd":
                eui = topic_parts[1]

                # Handle different command types
                if isinstance(payload, str):
                    command = payload.lower().strip()
                    payload_dict = {"command": command}
                else:
                    command = payload.get('command', payload.get('action', '')).lower().strip()
                    payload_dict = payload

                logger.info(f"EP Command for sensor {eui}: {command}")

                # Validate command
                valid_commands = ['detach', 'attach', 'status']
                if command not in valid_commands:
                    logger.warning(f"⚠️  Invalid EP command: {command}. Valid commands: {valid_commands}")
                    return

                # Create command message for TLS server processing
                command_msg = {
                    'message_type': 'command',
                    'eui': eui,
                    'action': command,
                    'source': 'ep_command',
                    'timestamp': payload_dict.get('timestamp', asyncio.get_event_loop().time())
                }

                # Add to in_queue for TLS server processing
                await self.mqtt_in_queue.put(command_msg)
                logger.info(f"✅ EP Command queued for TLS server processing")

                # Send acknowledgment back to application center
                ack_topic = f"EP/{eui}/response"
                ack_payload = {
                    "command": command,
                    "status": "received",
                    "timestamp": asyncio.get_event_loop().time()
                }

                await self.mqtt_out_queue.put({
                    "topic": ack_topic,
                    "payload": json.dumps(ack_payload)
                })

                logger.info(f"📤 EP Command acknowledgment sent to {ack_topic}")

        except Exception as e:
            logger.error(f"❌ Error handling EP command message: {e}")
            logger.error(f"   Topic: {topic}")
            logger.error(f"   Payload: {payload}")


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