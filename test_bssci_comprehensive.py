
import asyncio
import ssl
import msgpack
import json
import time
from datetime import datetime
from aiomqtt import Client
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class BSScITestClient:
    def __init__(self, host="0.0.0.0", port=16017, use_ssl=True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.reader = None
        self.writer = None

    async def connect(self):
        """Establish a persistent connection"""
        try:
            if self.use_ssl:
                # Create SSL context for client
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE  # Skip server verification for testing
                
                # Load client certificate for mutual authentication
                try:
                    ssl_context.load_cert_chain('certs/client_cert.pem', 'certs/client_key.pem')
                    print("[SSL] Client certificate loaded")
                except Exception as cert_error:
                    print(f"[SSL] Warning: Could not load client certificate: {cert_error}")
                
                # Connect with SSL
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port, ssl=ssl_context
                )
                print("✅ Connected to BSSCI server (SSL/TLS secured)")
            else:
                # Connect without SSL for insecure mode
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
                print("✅ Connected to BSSCI server (insecurely)")

        except Exception as e:
            print(f"❌ Connection error: {e}")
            raise

    async def disconnect(self):
        """Close the connection"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("🔌 Disconnected from BSSCI server")

    async def send_message(self, message_dict, expect_response=True):
        """Send a message using the existing connection"""
        try:
            if not self.writer or self.writer.is_closing():
                raise Exception("Connection lost")

            # Encode the message
            msg_pack = encode_message(message_dict)

            # Send with BSSCI protocol format
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
            self.writer.write(full_message)
            await self.writer.drain()

            print(f"📤 Sent: {message_dict}")

            if expect_response:
                # Read response with timeout
                try:
                    response_data = await asyncio.wait_for(self.reader.read(4096), timeout=10.0)
                    if response_data:
                        # Parse response
                        if len(response_data) > 12:
                            identifier = response_data[:8]
                            length = int.from_bytes(response_data[8:12], byteorder='little')
                            msg_data = response_data[12:12+length]
                            response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                            print(f"📨 Received: {response}")
                            return response
                    else:
                        print("❌ Connection closed by server")
                        self.writer = None
                        self.reader = None
                except asyncio.TimeoutError:
                    print("⏰ Response timeout")
                    return None

        except Exception as e:
            print(f"❌ Error sending message: {e}")
            # Mark connection as lost
            self.writer = None
            self.reader = None
            raise

class MQTTTestMonitor:
    def __init__(self, broker_host="akahlig.selfhost.co", broker_port=1887, username="bssci", password="test=1234"):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.received_messages = []
        self.test_topic_base = "test"

    async def start_monitoring(self):
        """Start monitoring MQTT messages"""
        print(f"🔍 Starting MQTT monitoring on {self.broker_host}:{self.broker_port}")
        print(f"📡 Monitoring topics: {self.test_topic_base}/#")
        
        try:
            async with Client(self.broker_host, port=self.broker_port, username=self.username, password=self.password) as client:
                await client.subscribe(f"{self.test_topic_base}/#")
                print("✅ MQTT monitoring started")
                
                async for message in client.messages:
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    topic = str(message.topic)
                    
                    try:
                        payload = json.loads(message.payload.decode())
                        formatted_payload = json.dumps(payload, indent=2)
                    except:
                        formatted_payload = str(message.payload)
                    
                    print(f"🔔 [{timestamp}] MQTT Message:")
                    print(f"   📍 Topic: {topic}")
                    print(f"   📦 Payload: {formatted_payload}")
                    
                    self.received_messages.append({
                        'timestamp': timestamp,
                        'topic': topic,
                        'payload': payload if isinstance(formatted_payload, str) and formatted_payload.startswith('{') else formatted_payload
                    })
                    
        except Exception as e:
            print(f"❌ MQTT monitoring error: {e}")

    async def send_test_configuration(self):
        """Send test sensor configuration via MQTT"""
        print(f"📝 Sending test sensor configuration via MQTT")
        
        test_sensor_config = {
            "eui": "ABCDEF1234567890",
            "nwKey": "0123456789ABCDEF0123456789ABCDEF",
            "shortAddr": "CAFE",
            "bidi": True
        }
        
        try:
            async with Client(self.broker_host, port=self.broker_port, username=self.username, password=self.password) as client:
                config_topic = f"{self.test_topic_base}/ep/{test_sensor_config['eui']}/config"
                await client.publish(config_topic, json.dumps(test_sensor_config))
                print(f"✅ Published sensor config to: {config_topic}")
                print(f"📋 Config: {json.dumps(test_sensor_config, indent=2)}")
                
        except Exception as e:
            print(f"❌ Error sending MQTT configuration: {e}")

async def run_comprehensive_bssci_test():
    """Run comprehensive BSSCI protocol test"""
    print("🚀 COMPREHENSIVE BSSCI PROTOCOL TEST")
    print("=" * 80)
    print(f"🕐 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize MQTT monitor
    mqtt_monitor = MQTTTestMonitor()
    
    # Start MQTT monitoring in background
    mqtt_task = asyncio.create_task(mqtt_monitor.start_monitoring())
    await asyncio.sleep(2)  # Give MQTT time to connect
    
    # Send test configuration first
    await mqtt_monitor.send_test_configuration()
    await asyncio.sleep(3)  # Wait for configuration to be processed
    
    # Initialize BSSCI client - connect to local server
    client = BSScITestClient(host="localhost", port=16017, use_ssl=False)
    
    test_results = []
    
    try:
        # Connect to BSSCI server
        print("\n🔗 PHASE 1: CONNECTION ESTABLISHMENT")
        print("-" * 50)
        await client.connect()
        
        # Test 1: Connection handshake
        print("\n📋 Test 1: Connection Handshake")
        connection_msg = {
            "command": "con",
            "opId": 2001,
            "bsEui": 0x70B3D59CD0000022,  # Test base station EUI
            "snBsUuid": [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80, 
                        0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0x11]
        }
        response = await client.send_message(connection_msg)
        test_results.append(("Connection Request", response is not None))
        
        # Test 2: Complete connection
        print("\n📋 Test 2: Connection Complete")
        connection_complete_msg = {
            "command": "conCmp",
            "opId": 2001
        }
        await client.send_message(connection_complete_msg, expect_response=False)
        test_results.append(("Connection Complete", True))
        await asyncio.sleep(2)  # Wait for attachment process
        
        print("\n🔄 PHASE 2: PROTOCOL OPERATIONS")
        print("-" * 50)
        
        # Test 3: Ping/Pong
        print("\n📋 Test 3: Ping/Pong Communication")
        ping_msg = {
            "command": "ping",
            "opId": 2002
        }
        response = await client.send_message(ping_msg)
        test_results.append(("Ping Communication", response is not None and response.get("command") == "pingRsp"))
        
        # Test 4: Status Response
        print("\n📋 Test 4: Status Response")
        status_msg = {
            "command": "statusRsp",
            "opId": 2003,
            "code": 0,
            "memLoad": 0.25,
            "cpuLoad": 0.15,
            "dutyCycle": 0.12,
            "time": int(time.time() * 1_000_000_000),  # Nanoseconds
            "uptime": 3600  # 1 hour
        }
        response = await client.send_message(status_msg)
        test_results.append(("Status Response", response is not None and response.get("command") == "statusCmp"))
        
        print("\n📡 PHASE 3: SENSOR DATA SIMULATION")
        print("-" * 50)
        
        # Test 5: Multiple sensor uplink messages
        test_sensors = [
            {
                "eui": 0x74731D0000000089,  # From endpoints.json
                "data": [0x01, 0x02, 0x03, 0x04, 0x05]
            },
            {
                "eui": 0x74731D00000000F8,  # From endpoints.json  
                "data": [0x10, 0x20, 0x30, 0x40, 0x50, 0x60]
            },
            {
                "eui": 0xABCDEF1234567890,  # Test sensor we configured via MQTT
                "data": [0xCA, 0xFE, 0xBA, 0xBE]
            }
        ]
        
        uplink_success_count = 0
        for i, sensor in enumerate(test_sensors, 1):
            print(f"\n📋 Test 5.{i}: Sensor Uplink Data - EUI {sensor['eui']:016X}")
            
            ul_data_msg = {
                "command": "ulData",
                "opId": 2004 + i,
                "epEui": sensor["eui"],
                "rxTime": int(time.time() * 1_000_000_000),  # Current time in nanoseconds
                "snr": 15.5 + i,
                "rssi": -75.2 - i,
                "packetCnt": 100 + i,
                "userData": sensor["data"]
            }
            
            response = await client.send_message(ul_data_msg)
            success = response is not None and response.get("command") == "ulDataRsp"
            if success:
                uplink_success_count += 1
            test_results.append((f"Uplink Data Sensor {i}", success))
            
            await asyncio.sleep(1)  # Space out the messages
        
        print(f"\n📊 PHASE 4: LOAD TEST")
        print("-" * 50)
        
        # Test 6: Rapid message sequence
        print(f"📋 Test 6: Rapid Message Sequence (10 messages)")
        rapid_success_count = 0
        for i in range(10):
            ul_data_msg = {
                "command": "ulData", 
                "opId": 3000 + i,
                "epEui": 0x74731D0000000089,
                "rxTime": int(time.time() * 1_000_000_000),
                "snr": 12.0 + (i * 0.5),
                "rssi": -80.0 - i,
                "packetCnt": 200 + i,
                "userData": [i, i+1, i+2, i+3]
            }
            
            response = await client.send_message(ul_data_msg)
            if response and response.get("command") == "ulDataRsp":
                rapid_success_count += 1
            
            await asyncio.sleep(0.1)  # Rapid fire
        
        test_results.append(("Rapid Message Test", rapid_success_count >= 8))  # Allow some tolerance
        
        print(f"\n⏳ Waiting 10 seconds for MQTT message propagation...")
        await asyncio.sleep(10)
        
    except Exception as e:
        print(f"❌ Test execution error: {e}")
        test_results.append(("Test Execution", False))
        
    finally:
        await client.disconnect()
        mqtt_task.cancel()
        
        # Print comprehensive test results
        print(f"\n📋 COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        print(f"🕐 Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        passed_tests = 0
        total_tests = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
            if result:
                passed_tests += 1
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {passed_tests}")
        print(f"   Failed: {total_tests - passed_tests}")
        print(f"   Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print(f"\n📡 MQTT MESSAGES RECEIVED:")
        if mqtt_monitor.received_messages:
            for msg in mqtt_monitor.received_messages[-10:]:  # Show last 10 messages
                print(f"   [{msg['timestamp']}] {msg['topic']}")
        else:
            print("   ⚠️  No MQTT messages received")
        
        print(f"\n🎯 TEST COMPLETE")

if __name__ == "__main__":
    # Set up event loop policy for Windows compatibility
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass  # Not on Windows
    
    asyncio.run(run_comprehensive_bssci_test())
