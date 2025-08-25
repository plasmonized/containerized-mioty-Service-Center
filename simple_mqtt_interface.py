
import asyncio
import json
import logging
from aiomqtt import Client
import bssci_config

logger = logging.getLogger(__name__)

class SimpleMQTTClient:
    def __init__(self, mqtt_out_queue, mqtt_in_queue):
        self.broker_host = bssci_config.MQTT_BROKER
        self.port = bssci_config.MQTT_PORT
        self.username = bssci_config.MQTT_USERNAME
        self.password = bssci_config.MQTT_PASSWORD
        self.base_topic = bssci_config.BASE_TOPIC.rstrip('/')
        self.config_topic = f"{self.base_topic}/ep/+/config"
        self.mqtt_out_queue = mqtt_out_queue
        self.mqtt_in_queue = mqtt_in_queue

    async def start(self):
        """Start MQTT client with simple retry logic"""
        while True:
            try:
                logger.info(f"🔄 Connecting to MQTT broker {self.broker_host}:{self.port}")
                
                async with Client(
                    hostname=self.broker_host,
                    port=self.port,
                    username=self.username,
                    password=self.password
                ) as client:
                    logger.info("✅ MQTT connected successfully!")
                    
                    # Subscribe to configuration updates
                    await client.subscribe(self.config_topic)
                    logger.info(f"📡 Subscribed to {self.config_topic}")
                    
                    # Run both handlers concurrently
                    await asyncio.gather(
                        self._handle_incoming_messages(client),
                        self._handle_outgoing_messages(client)
                    )
                    
            except Exception as e:
                logger.error(f"❌ MQTT connection failed: {e}")
                logger.info("🔄 Retrying in 5 seconds...")
                await asyncio.sleep(5)

    async def _handle_incoming_messages(self, client):
        """Handle incoming MQTT configuration messages"""
        async for message in client.messages:
            try:
                # Extract EUI from topic: bssci/ep/{EUI}/config
                topic_parts = str(message.topic).split('/')
                eui = topic_parts[-2]  # Get EUI from topic structure
                
                # Parse configuration
                config = json.loads(message.payload.decode())
                config["eui"] = eui
                
                logger.info(f"📨 Config received for EUI {eui}")
                await self.mqtt_in_queue.put(config)
                
            except Exception as e:
                logger.error(f"❌ Error processing incoming message: {e}")

    async def _handle_outgoing_messages(self, client):
        """Handle outgoing MQTT data messages"""
        while True:
            try:
                # Wait for message from queue
                msg = await self.mqtt_out_queue.get()
                
                # Publish to MQTT
                topic = f"{self.base_topic}/{msg['topic']}"
                await client.publish(topic, msg['payload'])
                
                logger.debug(f"📤 Published to {topic}")
                print(f"{topic}:\n\t{msg['payload']}")  # Keep console output
                
            except Exception as e:
                logger.error(f"❌ Error publishing message: {e}")
                # Put message back in queue for retry
                await self.mqtt_out_queue.put(msg)
                await asyncio.sleep(1)

if __name__ == "__main__":
    async def test():
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
            while True:
                await out_queue.put(test_data)
                await asyncio.sleep(10)
        
        await asyncio.gather(client.start(), send_test())
    
    asyncio.run(test())
