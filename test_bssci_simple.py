
import asyncio
import ssl
import msgpack
import json
import time
from datetime import datetime
from protocol import encode_message

IDENTIFIER = bytes("MIOTYB01", 'utf-8')

class SimpleTestClient:
    def __init__(self, host="localhost", port=16017):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None

    async def connect(self):
        """Connect without SSL for local testing"""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            print(f"✅ Connected to BSSCI server at {self.host}:{self.port}")
        except Exception as e:
            print(f"❌ Connection error: {e}")
            raise

    async def disconnect(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            print("🔌 Disconnected from BSSCI server")

    async def send_message(self, message_dict, expect_response=True):
        try:
            msg_pack = encode_message(message_dict)
            full_message = IDENTIFIER + len(msg_pack).to_bytes(4, byteorder='little') + msg_pack
            
            self.writer.write(full_message)
            await self.writer.drain()
            print(f"📤 Sent: {message_dict['command']} (opId: {message_dict.get('opId', 'N/A')})")

            if expect_response:
                try:
                    response_data = await asyncio.wait_for(self.reader.read(4096), timeout=5.0)
                    if response_data and len(response_data) > 12:
                        length = int.from_bytes(response_data[8:12], byteorder='little')
                        msg_data = response_data[12:12+length]
                        response = msgpack.unpackb(msg_data, raw=False, strict_map_key=False)
                        print(f"📨 Received: {response['command']} (opId: {response.get('opId', 'N/A')})")
                        return response
                except asyncio.TimeoutError:
                    print("⏰ Response timeout")
                    return None
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

async def run_simple_test():
    """Run a simple BSSCI test against the current server"""
    print("🧪 SIMPLE BSSCI PROTOCOL TEST")
    print("=" * 60)
    
    client = SimpleTestClient()
    
    try:
        # Connect
        await client.connect()
        
        # 1. Connection handshake
        print("\n📋 Test 1: Connection Handshake")
        response = await client.send_message({
            "command": "con",
            "opId": 1001,
            "bsEui": 0x70B3D59CD0000022,
            "snBsUuid": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
        })
        
        if response and response.get("command") == "conRsp":
            print("✅ Connection handshake successful")
            
            # 2. Complete connection
            print("\n📋 Test 2: Connection Complete")
            await client.send_message({"command": "conCmp", "opId": 1001}, expect_response=False)
            await asyncio.sleep(2)  # Wait for attachment process
            print("✅ Connection complete sent")
            
            # 3. Ping test
            print("\n📋 Test 3: Ping Test")
            response = await client.send_message({"command": "ping", "opId": 1002})
            if response and response.get("command") == "pingRsp":
                print("✅ Ping test successful")
            else:
                print("❌ Ping test failed")
            
            # 4. Status report
            print("\n📋 Test 4: Status Report")
            response = await client.send_message({
                "command": "statusRsp",
                "opId": 1003,
                "code": 0,
                "memLoad": 0.25,
                "cpuLoad": 0.15,
                "dutyCycle": 0.10,
                "time": int(time.time() * 1_000_000_000),
                "uptime": 3600
            })
            if response and response.get("command") == "statusCmp":
                print("✅ Status report successful")
            else:
                print("❌ Status report failed")
            
            # 5. Sensor data simulation
            print("\n📋 Test 5: Sensor Data Simulation")
            
            # Use a sensor from endpoints.json
            sensor_eui = 0x74731d0000000089
            response = await client.send_message({
                "command": "ulData",
                "opId": 1004,
                "epEui": sensor_eui,
                "rxTime": int(time.time() * 1_000_000_000),
                "snr": 15.5,
                "rssi": -75.2,
                "packetCnt": 123,
                "userData": [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
            })
            if response and response.get("command") == "ulDataRsp":
                print("✅ Sensor data simulation successful")
                print(f"   📡 Data sent for sensor: {sensor_eui:016X}")
            else:
                print("❌ Sensor data simulation failed")
            
            # 6. Multiple sensor data
            print("\n📋 Test 6: Multiple Sensor Data")
            test_sensors = [0x74731d00000000f8, 0x74731d00000000f9, 0xfca84a030000130a]
            
            for i, eui in enumerate(test_sensors):
                response = await client.send_message({
                    "command": "ulData",
                    "opId": 1005 + i,
                    "epEui": eui,
                    "rxTime": int(time.time() * 1_000_000_000),
                    "snr": 12.0 + i,
                    "rssi": -80.0 - i,
                    "packetCnt": 200 + i,
                    "userData": [0x10 + i, 0x20 + i, 0x30 + i, 0x40 + i]
                })
                
                if response and response.get("command") == "ulDataRsp":
                    print(f"   ✅ Sensor {eui:016X}: Data sent successfully")
                else:
                    print(f"   ❌ Sensor {eui:016X}: Data send failed")
                
                await asyncio.sleep(0.5)
        
        else:
            print("❌ Connection handshake failed")
        
        print("\n🎯 Test completed!")
        print("💡 Check the server logs and MQTT broker for published messages")
        print("📡 Messages should appear on MQTT topics under 'bssci/'")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    
    asyncio.run(run_simple_test())
