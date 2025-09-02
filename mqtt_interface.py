
"""MQTT interface for mioty BSSCI Service Center."""

import asyncio
import json
import logging
from typing import Dict, Any

from aiomqtt import Client, MqttError

import bssci_config

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT client for handling sensor configurations and data publishing."""

    def __init__(
        self,
        mqtt_out_queue: asyncio.Queue[Dict[str, str]],
        mqtt_in_queue: asyncio.Queue[Dict[str, str]],
    ) -> None:
        """Initialize MQTT client with configuration and queues."""
        self.broker_host = bssci_config.MQTT_BROKER

        # Normalize base topic
        if bssci_config.BASE_TOPIC.endswith("/"):
            self.base_topic = bssci_config.BASE_TOPIC[:-1]
        else:
            self.base_topic = bssci_config.BASE_TOPIC

        self.config_topic = self.base_topic + "/ep/+/config"
        self.command_topic = self.base_topic + "/ep/+/cmd"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

        # Add queue logging
        logger.info("🔍 MQTT Client Queue Assignment:")
        logger.info(f"   mqtt_out_queue ID: {id(self.mqtt_out_queue)}")
        logger.info(f"   mqtt_in_queue ID: {id(self.mqtt_in_queue)}")

    def log_queue_info(self) -> None:
        """Log queue information for debugging."""
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
        """Start MQTT client with connection retry logic."""
        retry_delay = 5.0
        max_delay = 60.0

        while True:
            try:
                logger.info("=" * 60)
                logger.info("🔄 MQTT CONNECTION ATTEMPT")
                logger.info("=" * 60)
                logger.info(f"📡 Broker: {self.broker_host}:{bssci_config.MQTT_PORT}")
                logger.info(f"👤 Username: {bssci_config.MQTT_USERNAME}")
                password_masked = (
                    "*" * len(bssci_config.MQTT_PASSWORD)
                    if bssci_config.MQTT_PASSWORD
                    else "NOT SET"
                )
                logger.info(f"🔐 Password: {password_masked}")
                logger.info(f"🎯 Config Topic: {self.config_topic}")
                logger.info(f"🏠 Base Topic: {self.base_topic}")

                logger.info("🔧 Creating MQTT client...")

                async with Client(
                    hostname=self.broker_host,
                    port=bssci_config.MQTT_PORT,
                    username=bssci_config.MQTT_USERNAME,
                    password=bssci_config.MQTT_PASSWORD,
                    keepalive=60,  # Send keepalive every 60 seconds
                    timeout=30,  # Connection timeout after 30 seconds
                ) as client:
                    logger.info("✅ MQTT CLIENT CONNECTION SUCCESSFUL!")
                    logger.info("✅ Authentication completed successfully")

                    # Reset retry delay on successful connection
                    retry_delay = 5.0

                    # Test connection
                    logger.info("🏓 Testing MQTT connection with ping...")
                    test_topic = f"{self.base_topic}/connection_test"
                    test_payload = json.dumps(
                        {
                            "status": "connected",
                            "timestamp": asyncio.get_event_loop().time(),
                        }
                    )
                    await client.publish(test_topic, test_payload)
                    logger.info("✅ MQTT ping successful - connection is stable")

                    # Run both handlers with health monitoring
                    logger.info(
                        "🎭 Starting concurrent MQTT handlers "
                        "with health monitoring..."
                    )
                    self.log_queue_info()

                    await asyncio.gather(
                        self._handle_incoming(client),
                        self._handle_outgoing(client),
                        self._connection_health_monitor(client),
                        return_exceptions=True,
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
        """Handle incoming MQTT messages."""
        logger.info("🔔 MQTT INCOMING HANDLER STARTING")
        logger.info("=" * 50)
        logger.info(f"📌 Config Subscription Topic: {self.config_topic}")
        logger.info(f"📌 Command Subscription Topic: {self.command_topic}")

        try:
            await client.subscribe(self.config_topic)
            await client.subscribe(self.command_topic)
            logger.info("✅ MQTT SUBSCRIPTIONS SUCCESSFUL")
            logger.info(
                "👂 MQTT incoming message handler is now ACTIVE and "
                "listening for config & commands..."
            )
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
                    await self._process_incoming_message(message)
                except Exception as e:
                    logger.error(f"❌ Message processing failed: {e}")

        except Exception as handler_error:
            logger.error(f"❌ MQTT INCOMING HANDLER FAILED: {handler_error}")
            raise

    async def _process_incoming_message(self, message) -> None:
        """Process a single incoming MQTT message."""
        topic_str = str(message.topic)
        payload_str = message.payload.decode("utf-8")
        payload_data = json.loads(payload_str)

        # Extract EUI from topic
        topic_parts = topic_str.split("/")
        base_parts = self.base_topic.split("/")

        if len(topic_parts) > len(base_parts) + 1:
            eui = topic_parts[len(base_parts) + 1]
            logger.info(f"🔑 Extracted EUI: {eui}")
            logger.info(f"📄 Payload: {payload_str}")

            # Check if this is a command or config message
            if topic_str.endswith("/cmd"):
                logger.info(f"📡 MQTT COMMAND received for EUI {eui}")
                # Send command to TLS server for processing
                command_msg = {"mqtt_topic": topic_str, "mqtt_payload": payload_data}
                await self.mqtt_in_queue.put(command_msg)
                logger.info("✅ MQTT command queued for processing")

            elif topic_str.endswith("/config"):
                logger.info(f"🔧 MQTT CONFIG received for EUI {eui}")
                config = payload_data
                config["eui"] = eui

                logger.info(f"✅ Configuration received for EUI {eui}")
                logger.info(f"   Queue size before put: {self.mqtt_in_queue.qsize()}")
                await self.mqtt_in_queue.put(config)
                logger.info("✅ Configuration queued successfully")
                logger.info(f"   Queue size after put: {self.mqtt_in_queue.qsize()}")
                logger.info(f"📋 Config: {json.dumps(config, indent=2)}")
            else:
                logger.warning(f"⚠️  Unknown topic type: {topic_str}")
        else:
            logger.warning(f"⚠️  Invalid topic format: {message.topic}")

    async def _connection_health_monitor(self, client: Client) -> None:
        """Monitor connection health and force reconnection if needed."""
        logger.info("💓 MQTT CONNECTION HEALTH MONITOR STARTED")

        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                # Send a test message to verify connection
                test_topic = f"{self.base_topic}/health_check"
                test_payload = json.dumps(
                    {"timestamp": asyncio.get_event_loop().time(), "status": "alive"}
                )

                logger.debug("💓 Performing MQTT health check...")
                await client.publish(test_topic, test_payload)
                logger.debug("✅ MQTT health check successful")

            except Exception as e:
                logger.error(f"💀 MQTT HEALTH CHECK FAILED: {e}")
                logger.error("🔄 Triggering connection reset...")
                raise  # This will cause reconnection

    async def _handle_outgoing(self, client: Client) -> None:
        """Handle outgoing MQTT messages."""
        logger.info("🚀 MQTT OUTGOING HANDLER INITIALIZED")
        logger.info("📤 Ready to publish messages")
        message_count = 0

        try:
            while True:
                msg = None  # Initialize msg to avoid unbound variable
                try:
                    logger.debug(
                        f"⏳ WAITING FOR MQTT MESSAGE in queue "
                        f"(size: {self.mqtt_out_queue.qsize()})"
                    )
                    msg = await self.mqtt_out_queue.get()
                    message_count += 1
                    topic = f"{self.base_topic}/{msg['topic']}"

                    logger.info(f"🎉 MESSAGE #{message_count} RECEIVED FOR PUBLISHING!")
                    logger.info(f"   Topic: {topic}")
                    logger.info(f"   Payload Size: {len(msg['payload'])} bytes")

                    # Publish message
                    logger.info(f"{topic}:\n\t{msg['payload']}")
                    await client.publish(topic, msg["payload"])

                    logger.info("✅ MQTT MESSAGE PUBLISHED SUCCESSFULLY!")

                except Exception as e:
                    logger.error(f"❌ MQTT PUBLISH ERROR: {e}")
                    # For connection errors, re-raise to trigger reconnection
                    if (
                        isinstance(e, (ConnectionError, OSError))
                        or "connection" in str(e).lower()
                        or "not currently connected" in str(e).lower()
                    ):
                        logger.error("   CONNECTION ERROR - TRIGGERING RECONNECTION")
                        if (
                            msg is not None
                        ):  # Only put back if msg was successfully retrieved
                            await self.mqtt_out_queue.put(msg)  # Put message back
                        raise
                    # For other errors, continue
                    logger.error("   NON-CONNECTION ERROR - Continuing...")

        except Exception as e:
            logger.error(f"❌ MQTT OUTGOING HANDLER FATAL ERROR: {e}")
            raise


async def main() -> None:
    """Test function for MQTT client."""
    import sys

    async def send_mqtt(mqtt_out_queue: asyncio.Queue[Dict[str, str]]) -> None:
        """Send test MQTT messages."""
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

    mqtt_out_queue: asyncio.Queue[Dict[str, str]] = asyncio.Queue()
    mqtt_in_queue: asyncio.Queue[Dict[str, str]] = asyncio.Queue()
    mqtt_server = MQTTClient(mqtt_out_queue, mqtt_in_queue)
    await asyncio.gather(mqtt_server.start(), send_mqtt(mqtt_out_queue))


if __name__ == "__main__":
    import sys

    if sys.platform.startswith("win"):
        policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy_cls is not None:
            asyncio.set_event_loop_policy(policy_cls())
    asyncio.run(main())
