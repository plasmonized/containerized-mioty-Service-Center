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
                logger.info(f"📋 Protocol: MQTT v3.1.1")
                logger.info(f"🎯 Config Topic: {self.config_topic}")
                logger.info(f"🏠 Base Topic: {self.base_topic}")

                # Create MQTT client with explicit v3.1.1 settings
                logger.info("🔧 Creating MQTT client with v3.1.1 configuration...")
                
                async with Client(
                    hostname=self.broker_host, 
                    port=MQTT_PORT, 
                    username=MQTT_USERNAME, 
                    password=MQTT_PASSWORD,
                    protocol=paho.mqtt.client.MQTTv311,
                    keepalive=60,
                    # Remove clean_session as it might be causing issues with aiomqtt
                ) as client:
                    logger.info("✅ MQTT CLIENT CONNECTION SUCCESSFUL!")
                    logger.info("✅ Authentication completed successfully")
                    logger.info("✅ MQTT v3.1.1 protocol negotiated")
                    logger.info("🚀 Starting MQTT message handlers...")

                    # Reset retry delay on successful connection
                    retry_delay = 5.0

                    # Test connection with a ping
                    logger.info("🏓 Testing MQTT connection with ping...")
                    test_topic = f"{self.base_topic}/connection_test"
                    test_payload = f'{{"status": "connected", "timestamp": "{asyncio.get_event_loop().time()}"}}'
                    await client.publish(test_topic, test_payload, qos=0)
                    logger.info("✅ MQTT ping successful - connection is stable")

                    # Run both handlers concurrently
                    logger.info("🎭 Starting concurrent MQTT handlers...")
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
                logger.error(f"📍 Error Module: {type(e).__module__}")
                
                # Enhanced error diagnostics
                if hasattr(e, 'args') and e.args:
                    logger.error(f"📋 Error Args: {e.args}")
                if hasattr(e, 'errno'):
                    logger.error(f"🔢 Error Code: {e.errno}")
                    
                # Connection details
                logger.error("🔧 CONNECTION DIAGNOSTICS:")
                logger.error(f"   📡 Broker: {self.broker_host}:{MQTT_PORT}")
                logger.error(f"   👤 Username: {MQTT_USERNAME}")
                logger.error(f"   🔐 Password Length: {len(MQTT_PASSWORD) if MQTT_PASSWORD else 0}")
                logger.error(f"   📋 Protocol: MQTT v3.1.1 (paho.mqtt.client.MQTTv311)")
                
                # Network diagnostics
                logger.error("🌐 NETWORK DIAGNOSTICS:")
                try:
                    import socket
                    logger.error(f"   🔍 Attempting DNS resolution for {self.broker_host}...")
                    ip = socket.gethostbyname(self.broker_host)
                    logger.error(f"   ✅ DNS Resolution: {self.broker_host} -> {ip}")
                    
                    logger.error(f"   🔍 Testing TCP connection to {ip}:{MQTT_PORT}...")
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((ip, MQTT_PORT))
                    sock.close()
                    
                    if result == 0:
                        logger.error(f"   ✅ TCP Connection: Port {MQTT_PORT} is reachable")
                    else:
                        logger.error(f"   ❌ TCP Connection: Port {MQTT_PORT} is NOT reachable (Error: {result})")
                except Exception as net_error:
                    logger.error(f"   ❌ Network diagnostic failed: {net_error}")
                
                logger.error("⏰ RETRY INFORMATION:")
                logger.error(f"   Current delay: {retry_delay}s")
                logger.error(f"   Next attempt in: {retry_delay} seconds")
                logger.error(f"   Max delay cap: {max_delay}s")
                logger.error("=" * 60)
                
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, max_delay)  # Exponential backoff with max 60s

    async def _handle_incoming(self, client: Client) -> None:
        logger.info("🔔 MQTT INCOMING HANDLER STARTING")
        logger.info("=" * 50)
        logger.info(f"📌 Subscription Topic: {self.config_topic}")
        logger.info("🔧 Attempting topic subscription...")
        
        try:
            await client.subscribe(self.config_topic)
            logger.info("✅ MQTT SUBSCRIPTION SUCCESSFUL")
            logger.info(f"✅ Subscribed to: {self.config_topic}")
            logger.info("👂 MQTT incoming message handler is now ACTIVE and listening...")
            logger.info("   Waiting for configuration updates from MQTT broker...")
            logger.info("=" * 50)
        except Exception as sub_error:
            logger.error(f"❌ MQTT subscription failed: {sub_error}")
            raise

        message_count = 0
        try:
            async for message in client.messages:
                message_count += 1
                logger.info("🎉 MQTT INCOMING MESSAGE RECEIVED!")
                logger.info("=" * 50)
                logger.info(f"📨 Message #{message_count}")
                logger.info(f"📍 Topic: {message.topic}")
                logger.info(f"📏 Payload Size: {len(message.payload) if message.payload else 0} bytes")
                logger.info(f"🕒 Received at: {asyncio.get_event_loop().time()}")

                try:
                    topic_parts = str(message.topic).split("/")
                    base_parts = self.base_topic.split("/")
                    eui_index = len(base_parts) + 1
                    
                    logger.info(f"🔍 Topic Analysis:")
                    logger.info(f"   Full topic: {message.topic}")
                    logger.info(f"   Topic parts: {topic_parts}")
                    logger.info(f"   Base topic parts: {base_parts}")
                    logger.info(f"   EUI index: {eui_index}")
                    
                    if eui_index < len(topic_parts):
                        eui = topic_parts[eui_index]
                        logger.info(f"   ✅ Extracted EUI: {eui}")
                    else:
                        logger.error(f"   ❌ Cannot extract EUI from topic structure")
                        continue

                    logger.info(f"📄 Processing payload...")
                    logger.debug(f"Raw payload: {message.payload}")

                    payload = message.payload
                    if isinstance(payload, (bytes, bytearray)):
                        logger.info("   Payload type: bytes/bytearray - decoding...")
                        config = json.loads(payload.decode())
                    elif isinstance(payload, str):
                        logger.info("   Payload type: string - parsing JSON...")
                        config = json.loads(payload)
                    else:
                        raise TypeError(f"Unsupported payload type: {type(payload)}")

                    config["eui"] = eui
                    logger.info("✅ CONFIGURATION PARSED SUCCESSFULLY")
                    logger.info(f"📝 Configuration for endpoint {eui}:")
                    logger.info(f"   - EUI: {config.get('eui', 'N/A')}")
                    logger.info(f"   - Network Key: {config.get('nwKey', 'N/A')[:8]}..." if config.get('nwKey') else "   - Network Key: N/A")
                    logger.info(f"   - Short Address: {config.get('shortAddr', 'N/A')}")
                    logger.info(f"   - Bidirectional: {config.get('bidi', 'N/A')}")

                    logger.info("📤 Queuing configuration for TLS Server processing...")
                    await self.mqtt_in_queue.put(config)
                    logger.info(f"✅ Configuration queued successfully for EUI {eui}")
                    logger.info("=" * 50)

                except Exception as e:
                    logger.error("❌ MQTT MESSAGE PROCESSING FAILED")
                    logger.error("=" * 50)
                    logger.error(f"🚨 Error: {e}")
                    logger.error(f"🔍 Error Type: {type(e).__name__}")
                    logger.error(f"📍 Topic: {message.topic}")
                    logger.error(f"📄 Raw payload: {message.payload}")
                    logger.error("=" * 50)
                    
        except Exception as handler_error:
            logger.error("❌ MQTT INCOMING HANDLER FAILED")
            logger.error(f"🚨 Handler Error: {handler_error}")
            logger.error(f"🔍 Error Type: {type(handler_error).__name__}")
            raise

    async def _handle_outgoing(self, client: Client) -> None:
        logger.info("📤 MQTT outgoing message handler started and ready to publish messages")
        message_count = 0

        try:
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
                    logger.info(f"   Full Topic: {topic}")
                    logger.info(f"   Payload Size: {len(msg['payload'])} bytes")

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

                    logger.info(f"   📡 Publishing to MQTT broker {self.broker_host}:{MQTT_PORT}...")

                    # Publish with timeout
                    await asyncio.wait_for(
                        client.publish(topic, msg["payload"], qos=1),
                        timeout=10
                    )

                    logger.info(f"✅ MQTT MESSAGE #{message_count} PUBLISHED SUCCESSFULLY")
                    logger.info(f"   Topic: {topic}")
                    logger.info(f"   ===================================")

                except asyncio.TimeoutError:
                    logger.error(f"❌ MQTT publish timeout for message #{message_count}")
                    logger.error(f"   Topic: {topic if 'topic' in locals() else 'unknown'}")
                    # Put message back in queue for retry
                    if 'msg' in locals():
                        await self.mqtt_out_queue.put(msg)
                    raise ConnectionError("Publish timeout - connection may be unstable")

                except Exception as e:
                    logger.error(f"❌ MQTT PUBLISH ERROR for message #{message_count}")
                    logger.error(f"   Error Type: {type(e).__name__}")
                    logger.error(f"   Error Message: {str(e)}")

                    # For connection errors, re-raise to trigger reconnection
                    if isinstance(e, (ConnectionError, OSError)) or "connection" in str(e).lower():
                        logger.error("   Connection error detected - triggering reconnection")
                        # Put message back in queue for retry
                        if 'msg' in locals():
                            await self.mqtt_out_queue.put(msg)
                        raise

                    # For other errors, log and continue
                    logger.error(f"   Skipping message due to non-connection error")

        except Exception as e:
            logger.error(f"❌ MQTT outgoing handler failed: {e}")
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