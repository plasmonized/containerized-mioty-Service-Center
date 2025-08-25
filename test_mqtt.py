
import asyncio
import logging
from aiomqtt import Client
from bssci_config import MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, BASE_TOPIC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mqtt_connection():
    """Test MQTT connection and publishing"""
    logger.info("Testing MQTT connection...")
    logger.info(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    logger.info(f"Username: {MQTT_USERNAME}")
    logger.info(f"Password: {'*' * len(MQTT_PASSWORD) if MQTT_PASSWORD else 'NOT SET'}")
    
    try:
        async with Client(
            hostname=MQTT_BROKER,
            port=MQTT_PORT,
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
            keepalive=60,
            timeout=10
        ) as client:
            logger.info("✅ MQTT connection successful!")
            
            # Test publishing a message
            test_topic = f"{BASE_TOPIC}test/connection"
            test_message = '{"status": "connection_test", "timestamp": "' + str(asyncio.get_event_loop().time()) + '"}'
            
            logger.info(f"Publishing test message to {test_topic}")
            await client.publish(test_topic, test_message, qos=1)
            logger.info("✅ Test message published successfully!")
            
            logger.info("✅ MQTT test completed successfully")
            return True
            
    except Exception as e:
        logger.error(f"❌ MQTT test failed: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_mqtt_connection())
    if result:
        print("MQTT connection test: PASSED")
    else:
        print("MQTT connection test: FAILED")
