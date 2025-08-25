
import asyncio
import ssl
import msgpack
import json
import time
import os
from datetime import datetime
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class BSScILocalTestClient:
    def __init__(self, host="localhost", port=16017):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.use_ssl = True

    async def connect(self):
        """Connect with SSL first, fallback to non-SSL for local testing"""
        
        # First try SSL connection
        try:
            print("🔐 Attempting SSL connection...")
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Try to load client certificate if available
            cert_files = ['certs/client_cert.pem', 'certs/client_key.pem']
            if all(os.path.exists(f) for f in cert_files):
                ssl_context.load_cert_chain('certs/client_cert.pem', 'certs/client_key.pem')
                print("✅ Client certificate loaded")
            else:
                print("⚠️  Client certificate not found, proceeding without")
            
            self.reader, self.writer = await asyncio.open_connection(
                self.host, self.port, ssl=ssl_context
            )
            print("✅ Connected to BSSCI server (SSL/TLS)")
            self.use_ssl = True
            return
            
        except Exception as ssl_error:
            print(f"❌ SSL connection failed: {ssl_error}")
            print("🔄 Trying non-SSL connection for local testing...")
        
        # Fallback to non-SSL connection
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            print("✅ Connected to BSSCI server (non-SSL)")
            self.use_ssl = False
        except Exception as e:
            print(f"❌ All connection attempts failed: {e}")
            raise

    async def disconnect(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("🔌 Disconnected from BSSCI server")

    async def send_message(self, message_dict, expect_response=True, timeout=10.0):
        try:
            if not self.writer or self.writer.is_closing():
                raise Exception("Connection lost")

            msg_pack = encode_message(message_dict)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
            
            self.writer.write(full_message)
            await self.writer.drain()
            print(f"📤 Sent: {message_dict['command']} (opId: {message_dict.get('opId', 'N/A')})")

            if expect_response:
                try:
                    response_data = await asyncio.wait_for(self.reader.read(4096), timeout=timeout)
                    if response_data and len(response_data) > 12:
                        # Check for BSSCI identifier
                        if response_data[:8] == IDENTIFIER:
                            length = int.from_bytes(response_data[8:12], byteorder='little')
                            if len(response_data) >= 12 + length:
                                msg_data = response_data[12:12+length]
                                response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                                print(f"📨 Received: {response['command']} (opId: {response.get('opId', 'N/A')})")
                                return response
                    
                    print("📨 Received invalid or empty response")
                    return None
                except asyncio.TimeoutError:
                    print(f"⏰ Response timeout after {timeout}s")
                    return None
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

async def run_comprehensive_local_test():
    """Run comprehensive BSSCI test against local server"""
    print("🧪 COMPREHENSIVE LOCAL BSSCI TEST")
    print("=" * 80)
    print(f"🕐 Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check if server is likely running
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("localhost", 16017), timeout=2.0
        )
        writer.close()
        await writer.wait_closed()
        print("✅ BSSCI server appears to be running on localhost:16017")
    except:
        print("❌ BSSCI server not reachable on localhost:16017")
        print("💡 Make sure the server is running: python main.py")
        return

    client = BSScILocalTestClient()
    test_results = []
    
    try:
        # Connect
        await client.connect()
        
        print(f"\n🔗 PHASE 1: CONNECTION ESTABLISHMENT")
        print("-" * 50)
        
        # Test 1: Connection handshake
        print("\n📋 Test 1: Connection Handshake")
        response = await client.send_message({
            "command": "con",
            "opId": 3001,
            "bsEui": 0x70B3D59CD0000022,
            "snBsUuid": [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
                        0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0, 0x11]
        })
        
        if response and response.get("command") == "conRsp":
            print("✅ Connection handshake successful")
            test_results.append(("Connection Handshake", True))
            
            # Test 2: Complete connection
            print("\n📋 Test 2: Connection Complete")
            await client.send_message({"command": "conCmp", "opId": 3001}, expect_response=False)
            await asyncio.sleep(3)  # Wait for attachment process
            print("✅ Connection complete sent")
            test_results.append(("Connection Complete", True))
            
            print(f"\n🧪 PHASE 2: PROTOCOL TESTING")
            print("-" * 50)
            
            # Test 3: Ping test
            print("\n📋 Test 3: Ping Test")
            response = await client.send_message({"command": "ping", "opId": 3002})
            if response and response.get("command") == "pingRsp":
                print("✅ Ping test successful")
                test_results.append(("Ping Test", True))
            else:
                print("❌ Ping test failed")
                test_results.append(("Ping Test", False))
            
            # Test 4: Status report
            print("\n📋 Test 4: Base Station Status Report")
            response = await client.send_message({
                "command": "statusRsp",
                "opId": 3003,
                "code": 0,
                "memLoad": 0.25,
                "cpuLoad": 0.15,
                "dutyCycle": 0.10,
                "time": int(time.time() * 1_000_000_000),
                "uptime": 3600
            })
            if response and response.get("command") == "statusCmp":
                print("✅ Status report successful")
                test_results.append(("Status Report", True))
            else:
                print("❌ Status report failed")
                test_results.append(("Status Report", False))
            
            print(f"\n📡 PHASE 3: SENSOR DATA SIMULATION")
            print("-" * 50)
            
            # Test 5: Single sensor data
            print("\n📋 Test 5: Single Sensor Data")
            sensor_eui = 0x74731d0000000089  # From endpoints.json
            response = await client.send_message({
                "command": "ulData",
                "opId": 3004,
                "epEui": sensor_eui,
                "rxTime": int(time.time() * 1_000_000_000),
                "snr": 15.5,
                "rssi": -75.2,
                "packetCnt": 123,
                "userData": [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
            })
            if response and response.get("command") == "ulDataRsp":
                print(f"✅ Sensor data sent successfully for EUI: {sensor_eui:016X}")
                test_results.append(("Single Sensor Data", True))
            else:
                print("❌ Sensor data failed")
                test_results.append(("Single Sensor Data", False))
            
            # Test 6: Multiple sensors
            print("\n📋 Test 6: Multiple Sensor Data Burst")
            test_sensors = [
                0x74731d00000000f8,
                0x74731d00000000f9, 
                0xfca84a030000130a,
                0xABCDEF1234567890  # Test sensor from MQTT config
            ]
            
            successful_sensors = 0
            for i, eui in enumerate(test_sensors):
                response = await client.send_message({
                    "command": "ulData",
                    "opId": 3005 + i,
                    "epEui": eui,
                    "rxTime": int(time.time() * 1_000_000_000),
                    "snr": 12.0 + i,
                    "rssi": -80.0 - i,
                    "packetCnt": 200 + i,
                    "userData": [0x10 + i, 0x20 + i, 0x30 + i, 0x40 + i]
                })
                
                if response and response.get("command") == "ulDataRsp":
                    print(f"   ✅ Sensor {eui:016X}: Success")
                    successful_sensors += 1
                else:
                    print(f"   ❌ Sensor {eui:016X}: Failed")
                
                await asyncio.sleep(0.5)
            
            test_results.append(("Multiple Sensor Data", successful_sensors == len(test_sensors)))
            
            # Test 7: Edge cases
            print("\n📋 Test 7: Edge Cases")
            
            # Large payload
            large_payload = list(range(100))  # 100 byte payload
            response = await client.send_message({
                "command": "ulData", 
                "opId": 3010,
                "epEui": 0x74731d0000000089,
                "rxTime": int(time.time() * 1_000_000_000),
                "snr": 10.0,
                "rssi": -85.0,
                "packetCnt": 999,
                "userData": large_payload
            })
            
            if response and response.get("command") == "ulDataRsp":
                print("   ✅ Large payload (100 bytes): Success")
                test_results.append(("Large Payload", True))
            else:
                print("   ❌ Large payload failed")
                test_results.append(("Large Payload", False))
            
        else:
            print("❌ Connection handshake failed")
            test_results.append(("Connection Handshake", False))
            return
        
    except Exception as e:
        print(f"❌ Test execution error: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("Test Execution", False))
    
    finally:
        await client.disconnect()
        
        # Results summary
        print(f"\n📊 COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        print(f"🕐 Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        passed_tests = sum(1 for _, result in test_results if result)
        total_tests = len(test_results)
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\n📈 SUMMARY:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {passed_tests}")
        print(f"   Failed: {total_tests - passed_tests}")
        print(f"   Success Rate: {success_rate:.1f}%")
        
        if success_rate == 100:
            print("\n🎉 ALL TESTS PASSED! BSSCI interface is working correctly.")
        elif success_rate >= 70:
            print("\n⚠️  Most tests passed, minor issues detected.")
        else:
            print("\n❌ Significant issues detected. Check server logs for details.")
        
        print(f"\n💡 Next steps:")
        print(f"   1. Check MQTT broker (akahlig.selfhost.co:1887) for published messages")
        print(f"   2. Monitor server logs for detailed processing information")
        print(f"   3. Verify endpoints.json has the test sensors configured")
        print(f"   4. Check web UI at http://localhost:5000 for sensor status")

if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    
    asyncio.run(run_comprehensive_local_test())
