import asyncio
import json
import logging
from aiomqtt import Client
import bssci_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler("mqtt_interface.log", maxBytes=1024 * 1024, backupCount=5),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class SimpleMQTTClient:
    """A simple MQTT client that handles connections and message passing."""

    def __init__(
        self,
        mqtt_out_queue: asyncio.Queue,
        mqtt_in_queue: asyncio.Queue,
        broker_host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        base_topic: str = None,
        config_topic: str = None,
    ):
        self.broker_host = broker_host or bssci_config.MQTT_BROKER
        self.port = port or bssci_config.MQTT_PORT
        self.username = username or bssci_config.MQTT_USERNAME
        self.password = password or bssci_config.MQTT_PASSWORD
        self.base_topic = (base_topic or bssci_config.BASE_TOPIC).rstrip('/')
        self.config_topic = config_topic or f"{self.base_topic}/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

    async def _handle_incoming_messages(self, client: Client):
        """Handle incoming messages from the MQTT broker."""
        while True:
            try:
                message: MQTTMessage = await client.get_message()
                logger.info(f"📥 Received message: {message.topic} - {message.payload.decode()}")

                # Put the message into the in_queue for processing by other parts of the app
                await self.in_queue.put({"topic": message.topic, "payload": message.payload.decode()})

            except Exception as e:
                logger.error(f"❌ Error receiving MQTT message: {e}")
                await asyncio.sleep(1)  # Wait a bit before retrying

    async def _handle_outgoing_messages(self, client: Client):
        """Handle outgoing messages from the out_queue."""
        while True:
            try:
                message_data = await self.out_queue.get()
                topic = message_data.get("topic")
                payload = message_data.get("payload")

                if topic and payload:
                    logger.info(f"📤 Sending message: {topic} - {payload}")
                    await client.publish(topic, payload)
                    logger.info("✅ Message sent successfully!")
                else:
                    logger.warning("⚠️ Invalid message data received for sending.")

                self.out_queue.task_done()  # Mark the task as done

            except Exception as e:
                logger.error(f"❌ Error sending MQTT message: {e}")
                await asyncio.sleep(1)  # Wait a bit before retrying

    async def start(self):
        """Start MQTT client with simple retry logic"""
        retry_count = 0
        max_retries = 3

        while True:
            try:
                retry_count += 1
                logger.info(f"🔄 MQTT Connection attempt #{retry_count}")
                logger.info(f"   Broker: {self.broker_host}:{self.port}")
                logger.info(f"   Username: {self.username}")
                logger.info(f"   Base topic: {self.base_topic}")

                async with Client(
                    hostname=self.broker_host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    keepalive=60,
                    timeout=10
                ) as client:
                    logger.info("✅ MQTT connected successfully!")
                    retry_count = 0  # Reset retry counter on success

                    # Test the connection with a ping
                    test_topic = f"{self.base_topic}/test/ping"
                    await client.publish(test_topic, '{"status": "connected"}')
                    logger.info("✅ MQTT connection test successful")

                    # Subscribe to configuration updates
                    await client.subscribe(self.config_topic)
                    logger.info(f"📡 Subscribed to {self.config_topic}")

                    # Run both handlers concurrently
                    await asyncio.gather(
                        self._handle_incoming_messages(client),
                        self._handle_outgoing_messages(client)
                    )

            except Exception as e:
                logger.error(f"❌ MQTT connection failed (attempt {retry_count}): {e}")

                if retry_count >= max_retries:
                    logger.error("❌ Max retries reached, continuing with longer delays...")
                    retry_count = 0
                    await asyncio.sleep(30)  # Longer delay after max retries
                else:
                    await asyncio.sleep(5)


if __name__ == "__main__":
    async def test():
        """Test MQTT connection independently"""
        print("🧪 Testing MQTT connection...")

        out_queue = asyncio.Queue()
        in_queue = asyncio.Queue()

        # Test data
        test_data = {
            "topic": "ep/test123/ul",
            "payload": json.dumps({"test": "data", "timestamp": 1234567890})
        }

        client = SimpleMQTTClient(out_queue, in_queue)

        # Send test message every 10 seconds
        async def send_test():
            await asyncio.sleep(3)  # Wait for connection
            while True:
                print("📤 Sending test message...")
                await out_queue.put(test_data)
                await asyncio.sleep(10)

        try:
            await asyncio.gather(client.start(), send_test())
        except KeyboardInterrupt:
            print("🛑 Test stopped")

    print("Starting MQTT test...")
    asyncio.run(test())